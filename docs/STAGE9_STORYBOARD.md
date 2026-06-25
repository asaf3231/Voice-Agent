# Stage 9 — Video Demo Storyboard ("Aria" Outbound Voice Agent)

> Target length **~6–8 min**. Arc: **architecture → governance → live booking → eval numbers →
> receipts ≤ $50**. Every number shown is read from its source (receipt / Cal.com / computed eval),
> never from a slide typed earlier (`VID3`). Covers `VID1`–`VID3`.
>
> **Verify before recording (`VID3`):** the figures baked into this storyboard were PM-verified on
> 2026-06-25 and are deterministic, but re-run `make test`, `make eval`, and `make receipts` on the day
> so what's on screen matches the live source. The commands are deterministic/read-only — they will
> reproduce.

---

## Segment 1 — What it is (~45s)
- One line: *"Aria is an autonomous outbound voice agent that calls a prospect, pitches Alta, and
  books a meeting — under hard governance: consent, a byte-exact AI disclosure, turn/time
  caps, and a hard $50 budget."*
- Show the repo tree (the §2 layout): `app/` (config, persona, tools, vapi_client, server, budget,
  consent, calendar_client, orchestrate, eval/), `data/` synthetic inputs, `tests/`, `scripts/`.
- Say the stack: **Vapi** (telephony, Retell-swappable behind `VoiceProvider`) driving a **standard
  voice pipeline — OpenAI `gpt-4o` (chat LLM) + OpenAI TTS `shimmer` (voice) + Deepgram `nova-2`
  (transcriber)** + **FastAPI** webhooks + **Cal.com** booking. *(We moved off OpenAI realtime
  speech-to-speech: over telephony it fragmented mid-sentence; the standard STT→LLM→TTS pipeline is
  what Vapi is built for on phone calls — clean, non-fragmenting audio. Decision OQ-VOICE-1 revised,
  2026-06-24.)*

## Segment 2 — Architecture (~90s)
- Diagram the happy path: `lead → consent gate → budget guard → place_call (Vapi standard pipeline) →
  DISCLOSURE first → pitch → discovery → objection handling → check_availability → book_meeting →
  log_disposition → capture receipt`.
- Emphasize the **two seams** (adapters): `VoiceProvider` and `CalendarProvider` — the vendor is a
  config swap, not a rewrite.
- Emphasize **import-safety**: clients are lazy singletons; `import app.*` does nothing (no .env, no
  network, no call). Show `ENV4` passing (e.g. `python -c "import app.server"` from an empty dir).

## Segment 3 — Governance (the heart) (~120s)
Show each chokepoint as code + a passing test:
- **Consent** — `consent_allows` is the single gate; non-allowlisted → refused, never dialed;
  `do_not_call` suppressed. (`CON1`/`CON5`)
- **Disclosure first, byte-exact** — pinned to Vapi's **static first-message** (not a prompt the
  model could paraphrase). Current literal:
  *"Hi, this is Aria, an AI assistant calling on behalf of Alta. Do you have a quick minute?"*
  (`CON2`/`VOICE1`). **Honest compliance note:** recording stays **on** but the spoken *recording
  notice* was dropped — lawful only under **one-party consent** (the demo line is Asaf's own consented
  Israeli number). A recording notice must be restored before any two-party-consent / real-prospect
  use. (`CON3`)
- **Budget is hard** — `budget_permits` runs before every dial; per-call ≤ $1 and **cumulative ≤ $50
  persisted across runs** (show the persistent ledger). No path dials around it. (`SEC3`/`CALL4`)
- **Caps** — turn cap + wall-clock → `FAILSAFE_HANGUP_LINE` byte-exact. (`CONV5`/`CONV6`)
- **Anti-leakage** — `make test` includes the leakage audit: no secret/card-PAN/PII/hardcoded data in
  any tracked file; an independent **security review** gate ran on this PII/secret-handling system.
- One sentence on the **reviewer discipline**: contract-touching stages got a *genuinely independent*
  review — which caught two real bugs (a webhook that couldn't book; a budget cap that didn't persist)
  that the inline pass missed. (Shows the process working, honestly.)
- Optional: run `make test` live → **543 passed, 1 skipped, 1 xfailed** (verified 2026-06-25). The
  **skip** is the live-only barge-in stress check (`STR-T1`); the **xfail** is the Bug-1 slot-re-offer
  guard, deliberately red until that loop lands — call both out rather than hide them.

## Segment 4 — Live demo call (~120s) — `VID1`
- Run `make preflight` on camera → **PASSED** (names only, no secrets shown).
- `make serve` + tunnel; the signed-webhook smoke test returns `{"ok":true}` (and a wrong secret → 401).
- `make call TO=<consented number>` → **answer the phone on camera.** Aria opens with the verbatim
  disclosure, pitches, handles an objection, proposes a slot, and books.
- Cut to **Cal.com** showing the newly created event (the real booking).
- **Fallback (Red-Team-approved):** if a fresh live take is flaky on the day, play the **pre-recorded
  successful call** — call `019ef8f2-e3ba-7001-9099-aa56093a56d0` (cost **$0.1482**, real Cal.com event
  `ecFPyLMFsbohwue3si1GML`, disclosure byte-exact first, `interrupted: 0`); recording at
  `storage.vapi.ai/019ef8f2-…-mono.wav`. This is the safe spine — record a fresh take only as an upgrade.

## Segment 5 — Offline eval numbers (~75s) — `VID2`
- Run **`make eval`** on camera (deterministic, seeded, network-free — no `.env`, no call). It prints
  the **computed** A/B bake-off + the persona-matrix summary. Verified figures (2026-06-25):

  | variant | book_rate | disclosure | objection_handled | compliance | avg_turns | n_personas |
  |---|---|---|---|---|---|---|
  | **A — Consultative** | **0.4** | 0.8 | 1.0 | 1.0 | 3.4 | 5 |
  | B — Direct | 0.2 | 0.8 | 1.0 | 1.0 | 2.6 | 5 |

- Read the result: **Variant A (Consultative) booked 2× Variant B** (0.4 vs 0.2) → A is the locked
  persona. Stress the scores are **computed from the rubric over seeded transcripts, never hardcoded**
  (`EVAL2`/`LEAK4`); same seed ⇒ same numbers every run.

## Segment 6 — Receipts ≤ $50 (~45s) — `VID2`/`VID3`
- **Capture first (needs the real `.env`):** `make receipts CALL_IDS="<call_id> …"` writes a redacted
  `receipts/<call_id>.json` per call (call id + `cost_usd`, all but last 2 phone digits masked). Run
  this for the demo call(s) before recording — `receipts/` currently holds only the ledger, not per-call
  receipts.
- Show the redacted `receipts/*.json` and the ledger snapshot: **cumulative spend ≪ $50** (the hard
  cap). Reconcile: receipt figure == provider-reported cost (`SEC5`/`LIVE3`).
- Close: *"Real call, real booking, full governance, ~$X of the $50 spent — verifiable from the
  receipts and the calendar, not asserted."* (Fill `$X` from the captured receipts on the day.)

---

## Demo command cheat-sheet
| Command | Shows | Needs `.env`? |
|---|---|---|
| `make test` | offline suite green (543/1skip/1xfail) | no |
| `python -c "import app.server"` (empty dir) | import-safety (`ENV4`) | no |
| `make eval` | computed eval summary + A/B bake-off (`VID2`) | no |
| `make preflight` | live-readiness, names-only (no secrets) | yes |
| `make serve` + tunnel | webhook up; signed smoke `{"ok":true}` / 401 | yes |
| `make call TO=<#>` | the live booking call (`VID1`) | yes |
| `make receipts CALL_IDS="…"` | redacted per-call cost receipts (`VID2`) | yes |

## Pre-record checklist
- [ ] `make test` → green; note the skip/xfail are intentional (call them out, don't hide).
- [ ] `make eval` → table matches the figures in Segment 5 (deterministic — it will).
- [ ] `make preflight` → PASSED (rehearse so no secret is ever on screen — names only).
- [ ] One successful live call recorded + **`make receipts` run for it** (the fallback + the $50 proof).
- [ ] Cal.com event visible.
- [ ] Eval summary + receipts figures match their sources (verify before recording — `VID3`).
- [ ] Hide/scrub: `.env`, real numbers (mask all but last 2), the card number — none on screen.
- [ ] Length within ~6–8 min.
