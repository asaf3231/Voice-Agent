# Stage 9 — Video Demo Storyboard ("Aria" Outbound Voice Agent)

> Target length **~6–8 min**. Arc: **architecture → governance → live booking → eval numbers →
> receipts ≤ $50**. Every number shown is read from its source (receipt / Cal.com / computed eval),
> never from a slide typed earlier (`VID3`). Covers `VID1`–`VID3`.

---

## Segment 1 — What it is (~45s)
- One line: *"Aria is an autonomous outbound voice agent that calls a prospect, pitches Alta, and
  books a meeting — under hard governance: consent, a byte-exact AI disclosure, turn/time
  caps, and a hard $50 budget."*
- Show the repo tree (the §2 layout): `app/` (config, persona, tools, vapi_client, server, budget,
  consent, calendar_client, orchestrate, eval/), `data/` synthetic inputs, `tests/`, `scripts/`.
- Say the stack: **Vapi** (telephony, Retell-swappable behind `VoiceProvider`) + **OpenAI Realtime**
  brain + **FastAPI** webhooks + **Cal.com** booking.

## Segment 2 — Architecture (~90s)
- Diagram the happy path: `lead → consent gate → budget guard → place_call (Vapi+Realtime) →
  DISCLOSURE first → pitch → discovery → objection handling → check_availability → book_meeting →
  log_disposition → capture receipt`.
- Emphasize the **two seams** (adapters): `VoiceProvider` and `CalendarProvider` — the vendor is a
  config swap, not a rewrite.
- Emphasize **import-safety**: clients are lazy singletons; `import app.*` does nothing (no .env, no
  network, no call). Show `ENV4` passing.

## Segment 3 — Governance (the heart) (~120s)
Show each chokepoint as code + a passing test:
- **Consent** — `consent_allows` is the single gate; non-allowlisted → refused, never dialed;
  `do_not_call` suppressed. (`CON1`/`CON5`)
- **Disclosure first, byte-exact** — pinned to Vapi's **static first-message** (not a prompt the
  model could paraphrase). (`CON2`/`VOICE1`)
- **Budget is hard** — `budget_permits` runs before every dial; per-call ≤ $1 and **cumulative ≤ $50
  persisted across runs** (show the persistent ledger). No path dials around it. (`SEC3`/`CALL4`)
- **Caps** — turn cap + wall-clock → `FAILSAFE_HANGUP_LINE` byte-exact. (`CONV5`/`CONV6`)
- **Anti-leakage** — `make test` includes the leakage audit: no secret/card-PAN/PII/hardcoded data in
  any tracked file; an independent **security review** gate ran on this PII/secret-handling system.
- One sentence on the **reviewer discipline**: contract-touching stages got a *genuinely independent*
  review — which caught two real bugs (a webhook that couldn't book; a budget cap that didn't persist)
  that the inline pass missed. (Shows the process working, honestly.)

## Segment 4 — Live demo call (~120s) — `VID1`
- Run `make preflight` on camera → **PASSED** (names only, no secrets shown).
- `make serve` + tunnel; the signed-webhook smoke test returns `{"ok":true}` (and a wrong secret → 401).
- `make call TO=<consented number>` → **answer the phone on camera.** Aria opens with the verbatim
  disclosure, pitches, handles an objection, proposes a slot, and books.
- Cut to **Cal.com** showing the newly created event (the real booking).
- *(Fallback: if live is flaky, play the pre-recorded successful call — Red-Team-approved.)*

## Segment 5 — Offline eval numbers (~75s) — `VID2`
- Run the eval harness; show the **computed** persona-matrix summary (book-rate, disclosure-compliance,
  objection-handled, compliance, avg turns) — deterministic, seeded, network-free.
- Show the **A/B result**: enriched bake-off → **Variant A (Consultative) booked 2× Variant B** → why
  A is the locked persona. Stress the scores are **computed, never hardcoded** (`EVAL2`/`LEAK4`).

## Segment 6 — Receipts ≤ $50 (~45s) — `VID2`/`VID3`
- Show the redacted `receipts/*.json` (per-call `cost_usd`) and the ledger snapshot: **cumulative
  spend ≤ $50** (the hard cap). Reconcile: receipt figure == provider-reported cost (`SEC5`/`LIVE3`).
- Close: *"Real call, real booking, full governance, ~$X of the $50 spent — verifiable from the
  receipts and the calendar, not asserted."*

---

## Pre-record checklist
- [ ] `make preflight` → PASSED (rehearse so no secret is ever on screen — names only).
- [ ] One successful live call recorded + its receipt captured (the fallback).
- [ ] Cal.com event visible.
- [ ] Eval summary + receipts figures match their sources (verify before recording — `VID3`).
- [ ] Hide/scrub: `.env`, real numbers (mask all but last 2), the card number — none on screen.
- [ ] Length within ~6–8 min.
