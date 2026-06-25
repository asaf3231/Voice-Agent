# Alta Outbound Voice Agent ("Aria")

An AI-driven, English-speaking outbound calling agent that pitches Alta's value proposition and books
meetings for the sales team. Built on Vapi (managed voice platform) with a modular speech pipeline:
Deepgram STT + GPT-4o + OpenAI TTS (Shimmer).

---

## Run from a clean checkout

```bash
# 1. Create a venv (Python 3.11+)
python3.13 -m venv .venv && source .venv/bin/activate   # macOS/Linux
# Windows: .venv\Scripts\Activate.ps1

# 2. Install all pinned deps
pip install -r requirements.txt

# 3. Configure secrets
cp .env.example .env
# Edit .env — fill real VAPI_API_KEY, CALCOM_API_KEY, etc.
# See .env.example for every variable. NEVER commit .env.

# 4. Run the offline deterministic test suite (no network, no call, no cost)
make test

# 5. Start the FastAPI webhook server (no call placed; cost = $0)
make serve
```

### Live demo call (gated — Stages 5 + 8 required)

```bash
# Only after Stage 5 (consent/budget) and Stage 8 (live provisioning) are complete:
make call TO=+15551234567   # consented, allowlisted number only
```

`make call` will **refuse and print an error** until those stages are wired.

---

## Architecture

```
synthetic lead list (data/leads.synthetic.json)
  → app/consent.py      — allowlist gate (single chokepoint, CON1)
  → app/budget.py       — hard cap guard (CALL4/SEC3)
  → app/vapi_client.py  — VoiceProvider adapter (Vapi: Deepgram STT + GPT-4o + OpenAI TTS)
      → DISCLOSURE_LINE spoken verbatim first (static first-message, CON2)
      → pitch / discovery / objection handling  (app/persona.py)
      → check_availability / book_meeting        (app/tools.py)
      → native Vapi end-call / FAILSAFE_HANGUP_LINE (CONV6)
  → app/orchestrate.py  — campaign runner
  → app/server.py       — FastAPI webhook handler (tool calls + call status)
  → app/eval/           — offline deterministic evaluation harness
```

## Governance (non-negotiable)

| Rule | Constant | Enforced by |
|---|---|---|
| Hard spend ceiling | `HARD_BUDGET_USD = $50` | `app/budget.py` (SEC2–SEC4) |
| Per-call ceiling | `MAX_COST_PER_CALL_USD = $1` | `budget_permits()` (SEC3) |
| Consent allowlist | only allowlisted numbers | `consent_allows()` (CON1) |
| Disclosure first | `DISCLOSURE_LINE`, byte-exact | Vapi static first-message (CON2) |
| Turn cap | `MAX_AGENT_TURNS = 40` | persona state machine (CONV5) |
| Wall-clock cap | `MAX_CALL_DURATION_S = 300` | Vapi + failsafe (CONV6) |

---

## Project files

| File | Purpose |
|---|---|
| `app/config.py` | All §9 constants + lazy env loader + AGENT_TOOLS |
| `app/budget.py` | Spend ledger + `budget_permits()` guard |
| `app/consent.py` | Allowlist gate + `consent_allows()` + `mask_phone()` |
| `app/persona.py` | System prompt + dialog policy (Stage 2) |
| `app/tools.py` | 5 agent callable functions (Stage 3) |
| `app/vapi_client.py` | VoiceProvider adapter — Vapi impl (Stage 4) |
| `app/server.py` | FastAPI webhook server (Stage 4) |
| `app/orchestrate.py` | Campaign runner (Stage 5) |
| `app/eval/` | Offline evaluation harness (Stage 6) |
| `data/` | Synthetic inputs (leads, ICP, value-prop) — never hardcoded |
| `tests/` | Offline deterministic suite — `make test` |
| `scripts/` | `place_demo_call.py`, `capture_receipts.py` |

---

## Budget tracking

Every live call writes a receipt to `receipts/` (redacted copies tracked; raw gitignored).
Run `scripts/capture_receipts.py` after a live session to reconcile spend against the $50 cap.
