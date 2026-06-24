# Live-Call Runbook — Alta Outbound Voice Agent ("Aria")

> The step-by-step procedure for the **Stage 8 live test**: place a real outbound call to a
> consented number, have Aria pitch + book a meeting, and capture receipts — all under the $50
> hard budget. **Run by the human operator** (real money, real calls). The PM/agent does **not**
> place live calls autonomously.

---

## 0. Preconditions (all must be green)

| # | Precondition | How to confirm |
|---|---|---|
| 1 | `.env` filled with the 5 required settings | `make preflight` → "PREFLIGHT PASSED" |
| 2 | `consent_allowlist.json` has the 3 consented numbers | `make preflight` (allowlist line shows `OK`) |
| 3 | Offline suite green | `make test` → all pass |
| 4 | Vapi: Twilio number `+972 53-563-6788` imported; `x-vapi-secret` set in Server → Authorization to the **same** value as `VAPI_WEBHOOK_SECRET` | Vapi dashboard |
| 5 | Cal.com: API key + event type configured; the event type is bookable | Cal.com dashboard |
| 6 | Public HTTPS tunnel reachable (ngrok/Cloudflare) → forwards to the local server | `curl https://<tunnel>/health` → `{"status":"ok"}` |

Required `.env` keys (names only — never commit values): `VAPI_API_KEY`, `VAPI_PHONE_NUMBER_ID`,
`VAPI_WEBHOOK_SECRET`, `CALCOM_API_KEY`, `CALCOM_EVENT_TYPE_ID`.

---

## 1. Pre-flight (no cost)

```bash
make preflight          # confirms settings present + allowlist loads (prints NO secret values)
make test               # 419 offline tests green
```
Do **not** proceed unless preflight says **PASSED**.

---

## 2. Start the webhook server + public tunnel (no cost)

```bash
make serve                       # FastAPI on :8000  (tool/status webhooks + /health)
# in a second shell — expose it publicly:
ngrok http 8000                  # → https://<random>.ngrok.app
```
- Put the public URL as the **Server URL** on the Vapi assistant/phone number (path `/webhook/tool`).
- Auth: Vapi sends `x-vapi-secret: <VAPI_WEBHOOK_SECRET>`; the server verifies it (constant-time,
  fail-closed). **Smoke test** (proves the public path + auth before spending a cent):
  ```bash
  curl -sS -X POST https://<tunnel>/webhook/tool \
       -H "x-vapi-secret: $VAPI_WEBHOOK_SECRET" \
       -H "content-type: application/json" \
       -d '{"name":"end_call","arguments":{"reason":"smoke"}}'
  # expect: {"ok": true, "data": {"ended": true, "reason": "smoke"}}
  # and with a WRONG/absent secret → HTTP 401 (never processed)
  ```

---

## 3. Place the live call (COSTS MONEY — sequential, one at a time)

```bash
make call TO=+9725XXXXXXXX        # a number ON the consent allowlist
```
What happens (the governed pipeline):
1. **Consent gate** — refuses instantly if the number isn't allowlisted (no call placed).
2. **Budget guard** — refuses if projected cost would breach the per-call ($1) or cumulative ($50) cap.
3. Vapi dials from `+972 53-563-6788`; Aria speaks the **byte-exact disclosure first** (static
   first-message), pitches from `data/value_prop.md`, handles objections, proposes a 30-min slot.
4. Tool calls (`check_availability` → `book_meeting`) route to the webhook → a real Cal.com event.
5. On success the script **records the actual cost** into the persistent ledger and prints the new
   cumulative.

> ⚠️ **Run calls strictly sequentially.** The budget ledger is single-writer; do not run a second
> `make call` (or the campaign runner) concurrently against the live budget. `MAX_LIVE_CALLS = 6`.

---

## 4. Capture receipts + reconcile (proof for the video)

```bash
python scripts/capture_receipts.py <call_id>     # writes receipts/<call_id>.json (redacted)
```
Then verify, from the sources (never from memory):
- **Disclosure** — confirm `DISCLOSURE_LINE` is the **verbatim first utterance** in the real Vapi
  transcript (`LIVE2`), not assumed.
- **Booking** — the meeting exists on the Cal.com calendar (`LIVE1`).
- **Cost** — each receipt's `cost_usd` ≤ `$1.00`; `make preflight` (or the ledger snapshot) shows
  cumulative ≤ `$50` (`LIVE3`/`SEC5`).
- **Keep one recorded successful call** as the Stage-9 video fallback.

---

## 5. Failure modes & recovery (reserve ~½ day — Red-Team Finding 7)

| Symptom | Likely cause | Action |
|---|---|---|
| Every webhook → 401 | `x-vapi-secret` ≠ `VAPI_WEBHOOK_SECRET`, or tunnel not pointed at `/webhook/tool` | align the secret; re-run the §2 smoke test |
| Call connects but never books | tool webhook unreachable (tunnel down) or Cal.com event misconfigured | check `make serve` logs; verify Cal.com `CALCOM_EVENT_TYPE_ID` |
| "calendar_unavailable" | Cal.com key/event id missing | fix `.env`; `make preflight` |
| Booked at the wrong time | lead-tz vs calendar-tz | `check_availability` returns both tz renderings; confirm the slot |
| Voicemail picked up | answering machine | `detect_voicemail` leaves ≤30s then ends; disposition `voicemail` |
| Budget refusal | cap reached | expected governance — stop; reconcile receipts |
| International dialing blocked | number can't reach the destination country | confirm Twilio/Vapi number permits the destination |

**If live fails on demo day:** fall back to the **pre-recorded successful call** for the Stage-9
video (Red-Team-approved). Do not retry live with zero slack against the video deadline.

---

## 6. Hard rules (do not violate)
- Never dial a number not on the consent allowlist; never disable the consent/budget gates.
- Never commit `.env`, the real `consent_allowlist.json`, real recordings/transcripts, or raw
  receipts (all gitignored).
- The disclosure is delivered verbatim by the platform (static first-message) — never edit it to a
  paraphrase.
- Every number reported in the video is read from its source (receipt / calendar / computed eval).
