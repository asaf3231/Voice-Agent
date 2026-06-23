# PLAN.md — Alta Outbound Voice Agent Project Plan

Project: **Alta Outbound Voice Agent ("Aria")**
Maintained by: Asaf

> This file is the live execution tracker. `CLAUDE.md` defines the rules. `QA_checklist.md` defines how
> each stage is verified. `NOTES.md` records decisions, verified facts, open questions, handbacks.

---

## How to use this file
- Work one stage at a time. Do not advance until the current stage's Definition of Done is satisfied.
- Read order for any session: `PM_LOG.md` (latest) → `CLAUDE.md` → `PLAN.md` → `QA_checklist.md` → `NOTES.md`.
- **Every DoD item references a check ID in `QA_checklist.md`.** A stage is done only when every
  referenced check **passes — verified by running it**, not by inspection.
- Non-trivial code is drafted as labelled copy-pasteable blocks for review, then landed. Always state
  *drafted only* vs *written and test-verified*.
- After each stage, append a handback to `NOTES.md`. The **PM** updates the stage status after its own
  verification — never the executer.

Status values: ⬜ Not started · 🔄 In progress · 🟡 Awaiting verification · ⚠️ Blocked · ✅ Complete

---

## Project shape (locked at genesis, 2026-06-23)
- **Deliverable:** a service repo (the running voice agent + offline deterministic test/eval suite) **+
  a video explanation**. No Jupyter notebook (the notebook discipline is re-expressed as the service
  workflow, `CLAUDE.md` §8). *(Asaf decision — NOTES 2026-06-23.)*
- **Stack:** Vapi (managed voice, Retell-swappable adapter) + OpenAI Realtime brain + FastAPI tool
  webhooks + a sandbox calendar for booking.
- **Budget:** hard $50 cap; lean live calling (~3–6 real calls) to consented test numbers only.
- **The build is staged so a demonstrable vertical slice — one real call that pitches and books —
  exists by Stage 8, leaving Stage 9 for the video.**

---

## Stage tracker

| Stage | Name | DoD checks (`QA_checklist.md`) | Reviewer gate | Status |
|---:|---|---|:---:|---|
| 0 | Project setup & spine | meta (this file set) | — | ✅ Complete (green-lit 2026-06-23 16:57) |
| 1 | Environment, secrets, budget & synthetic inputs | `ENV1`–`ENV4`, `SEC1`–`SEC4`, `LEAD1`–`LEAD3` | ✅ | ✅ Complete (2026-06-23, 105 green; offline scope — `LIVE0` Asaf-parallel) |
| 2 | Conversation design (persona, dialog policy, literals) | `CONV1`–`CONV6` | ✅ | ✅ Complete (2026-06-23, 150 green; winner **B** provisional pending Stage-6 re-run) |
| 3 | Agent callable functions + booking | `TOOL1`–`TOOL5`, `BOOK1`–`BOOK3` | ✅ | ✅ Complete (2026-06-23, 201 green; OQ-VOICE-3 resolved) |
| 4 | Voice-platform integration (Vapi + Realtime + webhooks) | `VOICE1`–`VOICE5`, `CON2`–`CON3` | ✅ | ✅ Complete (2026-06-23, 245 green; offline scope — public-tunnel live smoke owed at Stage 8) |
| 5 | Outbound orchestration + consent + budget guard | `CALL1`–`CALL4`, `CON1`, `CON4`, `CON5`, `SEC3` | ✅ | ⬜ Not started |
| 6 | Offline evaluation harness | `EVAL1`–`EVAL6` | — | ⬜ Not started |
| 7 | Anti-leakage & packaging hardening | `LEAK1`–`LEAK5`, `PKG1`–`PKG4` | ✅ | ⬜ Not started |
| 8 | Live calling (lean) + receipts | `LIVE1`–`LIVE4`, `SEC5` | — | ⬜ Not started |
| 9 | Video explanation + demo script | `VID1`–`VID3` | — | ⬜ Not started |

**Reviewer-gate trigger (this project):** on any stage that touches a graded contract — a §9 named
constant, a tool/provider/calendar **interface signature**, the `DISCLOSURE_LINE` /
`FAILSAFE_HANGUP_LINE` literals, a budget cap, the consent-allowlist gate, or the import-safety
contract — run the native **`/code-review`** utility (the reviewer gate; see `CLAUDE.md` §1.3). Pure-eval,
docs, and the video stages skip it (PM's own QA suffices). **Stage 7** additionally runs the native
**`/security-review`** utility as its governance / anti-leakage gate. Executers are `general-purpose`
subagents spawned per stage (no registered `swe-*` agent types in this environment — `CLAUDE.md` §1.3).

---

## Stage 0 — Project setup & spine + Red-Team validation
**Goal:** Create the spine and lock the architecture, stack, constants, literals, governance policies,
and the task-specific anti-leakage rule before any code — then validate it with a **single-turn
adversarial Red-Team pass** before green-light.
**Inputs:** the assignment email, `PM_Methodology_Prompt.md`, the `REFERENCE/` quality bar.
**Outputs:** `CLAUDE.md`, `PLAN.md`, `QA_checklist.md`, `NOTES.md`, `PM_LOG.md`; the Red-Team findings
folded into the spine.
**Definition of Done:**
- [x] `CLAUDE.md` created (env + pinned deps, import-safety, synthetic-input compliance, the 5
  agent functions, governance policies, the anti-leakage rule, service authoring workflow, literals).
- [x] `QA_checklist.md` created (stable IDs for env/secrets/consent/conversation/tools/voice/orchestration/eval/live/anti-leakage/packaging/video, mapped to stages).
- [x] `PLAN.md` created (this file); every stage DoD references QA check IDs.
- [x] `NOTES.md` created with the four genesis decisions, named constants, literals, open questions.
- [x] **Assignment reconciled** (2026-06-23): the notebook-vs-service contradiction surfaced to Asaf and
  resolved (service-only); stack, LLM, and budget posture chosen via the reconciliation question.
- [x] **Red-Team pass** (2026-06-23) — single-turn adversarial review (one `general-purpose` subagent, no
  symmetric debate) on schedule realism + governance chokepoints. Verdict: conditionally green-light;
  2 blockers + 1 HIGH + MED/LOW findings **all folded into the spine** (card leak redacted + gitignored;
  `LIVE0` provisioning + webhook tunnel added; disclosure pinned to static first-message; Stage 2 dual
  forward-dep + time-box; demo-call second-entry-point spy; timezone; live buffer; allowlist validation).
  See NOTES 2026-06-23 "Stage 0 Red-Team pass".
- [x] **Asaf review** — **green-lit 2026-06-23 16:57** (via plan approval); implementation authorized.
**Status:** ✅ Complete — spine authored, reconciled, Red-Team-hardened, and green-lit. PM `git init`-ed the
repo and ran a CLEAN secret pre-flight gate (sensitive files confirmed gitignored; no secret in any
would-be-tracked file — see NOTES verified fact 2026-06-23 16:57).
**Next action:** Stage 1 under the autonomous loop; `LIVE0` provisioning owned by Asaf in parallel.

---

## Stage 1 — Environment, secrets, budget & synthetic inputs
**Goal:** Stand up a clean, import-safe repo: pinned deps, `.env.example`/`.gitignore`, the budget
ledger + caps, the consent allowlist gate, and the validated synthetic inputs — before any call logic.
**Inputs:** `CLAUDE.md` §1/§2/§5/§9; the chosen pins; the synthetic `data/*`.
**Outputs:** `requirements.txt`, `.env.example`, `.gitignore`, `Makefile`, `README.md`; `app/config.py`
(constants/literals/lazy getters), `app/budget.py`, `app/consent.py`; `data/*.synthetic.*`; `tests/`.
**Definition of Done (QA: `ENV1`–`ENV4`, `SEC1`–`SEC4`, `LEAD1`–`LEAD3`):**
- [x] `ENV1`/`ENV2` — venv installs/resolves; every requirement pinned with `==` (+ AST cross-check: every third-party app/ import is pinned); `REALTIME_MODEL` **locked = `"gpt-4o-realtime-preview"`** (`OQ-VOICE-1`).
- [x] `ENV3`/`ENV4` — `make test` clean offline (no `.env`); `import app.config/budget/consent` side-effect-free from an empty cwd (lazy singletons `None`, no `.env`, no call). *(Full six-module `ENV4` re-proven as tools/server/orchestrate land — Stages 3–5.)*
- [x] `SEC1` — no secret / **card number** (16-digit PAN, not the bare CVV) in any tracked file; scan uses the **git-true tracked set** (`git ls-files --cached --others --exclude-standard`); `.env` gitignored; `.env.example` placeholders only; **`Home_Assignment_email.md` (redacted) + `REFERENCE/` gitignored** — all proven by `git check-ignore`.
- [x] `SEC2`–`SEC4` — Decimal budget ledger correct; hard cap + per-call ceiling enforced (`budget_permits`, boundary-tested); live sub-caps wired ((N+1)th refused).
- [x] `LEAD1`–`LEAD3` — synthetic inputs validate on load (missing field → `ValueError`, not `KeyError`); no input value hardcoded in code/prompts.
- [x] `CON1` (allowlist load) — the consent allowlist source validates on load (analogous to `LEAD1`); a malformed/empty allowlist is a clean explicit error, not silent allow-none (Red-Team 2026-06-23, Finding 9).
- [ ] `LIVE0` (provisioning readiness) — **Asaf-owned parallel track (not a code gate):** Vapi account + outbound number (allow for A2P/identity verification lead time), Cal.com account + API key + event type, OpenAI Realtime access verified, a public HTTPS webhook tunnel. **The #1 schedule risk** (Red-Team 2026-06-23, Findings 2/3) — must be green before Stage 8.
**Status:** ✅ **Complete (offline scope) — PM-verified 2026-06-23 17:45** (recovered from the executer's Anthropic-500 crash; 105 tests green; byte-exact literals == CLAUDE.md §9; reviewer gate run, 3 LOW findings, none blocking). **Committed** as the `v1.0.0-stage1` baseline on `main` (above the Stage-0 baseline); finding-F1 **resolved** (option a — `BUDGET_ALARM_ROUNDING_MARGIN` promoted to a §9 constant). · **Reviewer gate:** ✅ (constants + budget/consent contracts).

---

## Stage 2 — Conversation design (persona, dialog policy, literals) — **A/B competition**
**Goal:** Author Aria's system prompt and the dialog state machine (pitch → discovery → objection
handling → propose-slot → close), the guardrails, and the two byte-exact literals — all offline-testable
— via a **full A/B persona + dialogue competition** (this is the stage where the real product risk
lives, so cognitive compute is concentrated here — decision 2026-06-23).
**Inputs:** `CLAUDE.md` §5 (Policy 4/6), §7, §9; `data/value_prop.md`; `SimulatedCallee`; the rubric
signals from `app/eval/rubric.py` (see sequencing note below).
**Outputs:** `app/persona.py` (the **winning** prompt + policy + guardrails); the two candidate variants
+ their scored bake-off recorded in `NOTES.md`; conversation fixtures; `tests/test_conversation.py`.
**Definition of Done (QA: `CONV1`–`CONV6`):**
- [ ] **A/B bake-off (mandated)** — author **two** distinct persona/dialog-policy variants (A and B),
  run **both** through the **computed `app/eval/rubric.py`** rubric over the persona matrix, and select
  the winner on the *numbers* (book-rate, disclosure-compliance, objection-handled, compliance-ok — never
  on taste). The bake-off table + the chosen winner + why are recorded in `NOTES.md`. No symmetric live
  debate — offline scored competition only.
- [ ] `CONV1`–`CONV3` — state machine advances; value-prop pitched from `data/value_prop.md`; objections handled before honoring a hard no.
- [ ] `CONV4` — authoritative-content bound: no invented Alta claim/price elicitable.
- [ ] `CONV5`/`CONV6` — turn cap fires; `FAILSAFE_HANGUP_LINE` byte-exact on cap/error.
- **⚠ Sequencing dependency (DOUBLE — Red-Team 2026-06-23, Finding 5):** the A/B is scored against
  `app/eval/rubric.py` **and** driven by `app/eval/simulated_callee.py` — *both* otherwise Stage-6
  artifacts. Resolve by **landing a minimal seeded `simulated_callee.py` + a thin computed rubric**
  (disclosure/pitch/objection/booking/compliance signals) at the **start** of Stage 2, then enriching
  both in Stage 6 — *not* by scoring the bake-off on un-computed/eyeballed criteria (would violate
  `EVAL2`/`LEAK4`). **Time-box the bake-off** to two variants over a *small fixed* persona set so this
  (the heaviest stage) cannot slip and cascade into Stages 3/4/8/9.
**Status:** ✅ Complete (offline; PM-verified 2026-06-23 — 150 green; A/B fully **computed** + PM-reproduced;
four mandated criteria **tie**, winner **B (Direct)** on the efficiency tiebreak, **provisional pending Stage-6
enrichment + bake-off re-run**). Built by a cold executer under "Executer builds, PM scores"; PM independently
re-ran the rubric/bake-off. · **Reviewer gate:** ✅ (PM inline; literals consumed from config, Policy 4/6 honored).

---

## Stage 3 — Agent callable functions + booking
**Goal:** Implement the 5 deterministic agent functions and the booking layer behind the `CalendarProvider`
interface, test-first, each verified in isolation with fakes.
**Inputs:** `CLAUDE.md` §9 (`AGENT_TOOLS`); `FakeCalendar`; `frozen_clock`.
**Outputs:** `app/tools.py`, `app/calendar_client.py` (**`CalendarProvider` interface; Cal.com impl +
deterministic local mock — `OQ-VOICE-3` locked**; the mock is the test default); `tests/test_tools.py`, `tests/test_booking.py`.
**Definition of Done (QA: `TOOL1`–`TOOL5`, `BOOK1`–`BOOK3`):**
- [ ] `TOOL1`–`TOOL5` — availability/booking/disposition/voicemail/end-call deterministic; idempotent `book_meeting`; dispatch identity assert; no secret/full-number in dispositions. **`check_availability` resolves the lead's `timezone` against the sales calendar's tz** (Red-Team 2026-06-23, Finding 6 — a "3pm in the wrong tz" live booking is a demo failure).
- [ ] `BOOK1`–`BOOK3` — free-slot listing **with explicit timezone resolution**; event creation returns a real id; conflict → re-offer, no phantom booking (Policy 5). Backend is the **Cal.com slot-booking contract** behind `CalendarProvider`; the **local mock** (not Google OAuth) is the offline default; the live Cal.com client is gated like other live paths.
**Status:** ✅ Complete (offline; PM-verified 2026-06-23 — **201 green**; 5 tools + `CalendarProvider` [Cal.com
gated + local mock default]; tz resolution, idempotent booking, masked dispositions, dispatch-identity assert,
lazy httpx all verified; no graded contract changed). · **Reviewer gate:** ✅ (PM inline; `AGENT_TOOLS` +
interface intact). **Resolves `OQ-VOICE-3`** (Cal.com + mock).

---

## Stage 4 — Voice-platform integration (Vapi + Realtime + webhooks)
**Goal:** Wire the `VoiceProvider` adapter (Vapi assistant config with `REALTIME_MODEL`, the disclosure
opener, and the 5 tools) and the signature-verified FastAPI webhook server — import-safe.
**Inputs:** Stages 2–3; `CLAUDE.md` §1.2/§6; `FakeVoiceProvider`.
**Outputs:** `app/vapi_client.py`, `app/server.py`; `tests/test_voice.py`, `tests/test_server.py`.
**Definition of Done (QA: `VOICE1`–`VOICE5`, `CON2`–`CON3`):**
- [ ] `VOICE1` — assistant payload wires the realtime model, persona, 5 tools, and **`DISCLOSURE_LINE` pinned to Vapi's static first-message feature (spoken verbatim, not model-generated)** — asserted byte-exact offline (Red-Team 2026-06-23, Finding 4).
- [ ] `VOICE2`/`VOICE3` — webhook signature verified; tool dispatch routes correctly; unknown tool → structured error. **Deliverable: a public HTTPS webhook tunnel (ngrok/Cloudflare/deployed host) + one signed end-to-end webhook smoke test over the public URL** (Red-Team 2026-06-23, Finding 3 — `make serve` on localhost is unreachable by Vapi).
- [ ] `VOICE4`/`VOICE5` — lazy client (`ENV4` holds); the provider interface is the only egress, swappable.
- [ ] `CON2`/`CON3` — disclosure is the **static first-message** (verbatim, byte-exact), not a prompt the model may paraphrase; recording gated on disclosure; `LIVE2` later verifies from the real transcript.
**Status:** ✅ Complete (offline; PM-verified 2026-06-23 19:16 recovery — **245 green**; `VoiceProvider` adapter
[graded signatures intact] + `VapiVoiceProvider` [pure offline builder + lazy httpx live methods]; signature-verified
FastAPI webhooks [HMAC-SHA256 over raw body, fail-closed]; `DISCLOSURE_LINE` pinned to the static `firstMessage`
byte-exact + recording gated [CON3]; ENV4 import-safe across all 7 modules, httpx not pulled; both literals byte-exact
== §9 from config; no graded contract changed). Recovered PM-led from a prior session's mid-stage crash (executer had
finished + written `handbacks/stage-4.md`; PM did the verify/review/commit/log). · **Reviewer gate:** ✅ (PM-inline,
per the no-cold-spawn budget rule; provider interface + webhook auth + import-safety — APPROVE, 2 LOW live-carry
findings). `OQ-VOICE-2` **locked: Vapi** primary, **Adapter Pattern mandatory** — `VoiceProvider` is the only egress,
swapping to Retell must touch **no** core state/dialog logic (`VOICE5`). **Owed at Stage 8:** the public-HTTPS-tunnel
signed end-to-end webhook smoke test (gated, Asaf's `LIVE0` track).

---

## Stage 5 — Outbound orchestration + consent + budget guard
**Goal:** The campaign runner over the synthetic lead list — consent gate, budget guard before dialing,
retries, voicemail, daily cap — all resilient, no live call in the default suite.
**Inputs:** Stages 1–4; `app/consent.py`, `app/budget.py`, `FakeVoiceProvider`.
**Outputs:** `app/orchestrate.py`; `tests/test_orchestrate.py`.
**Definition of Done (QA: `CALL1`–`CALL4`, `CON1`, `CON4`, `CON5`, `SEC3`):**
- [ ] `CALL1`/`CALL2` — resilient runner; no-answer retries ≤ `CALL_RETRY_MAX` then dispositions.
- [ ] `CALL3`/`CALL4` — ≤ `DAILY_CALL_CAP`/day; budget guard runs before every dial; over-budget halts cleanly.
- [ ] `CON1`/`CON4`/`CON5` — allowlist is the single chokepoint; zero live calls in the default suite; `do_not_call` suppressed.
- [ ] `SEC3`/`CON1` (second entry point) — **`scripts/place_demo_call.py` (`make call`) is spy-proven to route through `budget_permits` + `consent_allows` before `place_call`**, exactly like `orchestrate.py` — it must not construct the provider and dial directly (Red-Team 2026-06-23, Finding 8).
**Status:** ⬜ Not started · **Reviewer gate:** ✅ (consent chokepoint + budget guard).

---

## Stage 6 — Offline evaluation harness
**Goal:** The deterministic, network-free eval over labeled simulated transcripts — the reproducible
core that produces the numbers shown in the video.
**Inputs:** Stages 2–5; `SimulatedCallee`; `fixtures/transcripts/`.
**Outputs:** `app/eval/harness.py`, `app/eval/rubric.py`, `app/eval/simulated_callee.py`; `tests/test_eval.py`.
**Definition of Done (QA: `EVAL1`–`EVAL6`):**
- [ ] `EVAL1`/`EVAL2` — deterministic, offline, seeded; scores **computed**, never hardcoded.
- [ ] `EVAL3`/`EVAL4` — rubric covers disclosure/pitch/objection/booking/compliance; persona matrix yields expected dispositions.
- [ ] `EVAL5`/`EVAL6` — reproducible aggregate metrics; negative fixtures catch disclosure/booking regressions.
**Status:** ⬜ Not started · **Reviewer gate:** — (pure eval).

---

## Stage 7 — Anti-leakage & packaging hardening
**Goal:** Prove no secret/PII/fabricated-outcome/hardcoded-data leak, and that the repo runs from a
clean checkout and packages cleanly.
**Inputs:** the working repo.
**Outputs:** hardened code; `tests/test_leakage.py`; finalized `.gitignore`/`MANIFEST`.
**Definition of Done (QA: `LEAK1`–`LEAK5`, `PKG1`–`PKG4`):**
- [ ] `LEAK1`–`LEAK5` — grep clean for secrets/card/PII/hardcoded data/abs-paths; no fabricated outcomes.
- [ ] `PKG1`–`PKG4` — deps pinned; clean-checkout `make test`+`make serve`; allowlist packaging; `.gitignore` correct.
**Status:** ⬜ Not started · **Reviewer gate:** ✅ (anti-leakage is the highest-leverage gate).

---

## Stage 8 — Live calling (lean) + receipts
**Goal:** Place real calls to the **3 consented internal tester numbers** (`OQ-VOICE-4` locked), book at
least one real meeting, capture receipts, and reconcile spend against the $50 cap.
**Inputs:** Stages 1–7; real keys; the **3 whitelisted, consented tester numbers** seeded into the
consent allowlist (`CON1`); the budget ledger. *(`MAX_LIVE_CALLS = 6` stays the budget ceiling; a 4th+
distinct number would require a new consent decision.)*
**Outputs:** real call recordings/transcripts (local, gitignored), redacted `receipts/`; a live note in `NOTES.md`.
**Definition of Done (QA: `LIVE1`–`LIVE4`, `SEC5`) — gated; SKIPPED in CI without keys/number:**
- [ ] `LIVE1`/`LIVE2` — a real call opens with the byte-exact disclosure, pitches, and books a real event.
- [ ] `LIVE3`/`LIVE4`/`SEC5` — per-call cost ≤ ceiling; cumulative ≤ caps (verified from receipts); redacted receipts captured.
- **⏳ Live-debug buffer (Red-Team 2026-06-23, Finding 7):** reserve ~half a day for live-call failure modes (barge-in, latency, voicemail misclassification, cost surprises). With only 3 numbers / `MAX_LIVE_CALLS=6` and Stage 8→9 back-to-back, do **not** schedule the live session same-day as the video with zero slack. **Capture and keep a recorded successful call** as a fallback for the Stage-9 video.
**Status:** ⬜ Not started · **Reviewer gate:** — (PM verifies live results directly). Resolves `OQ-VOICE-4`.

---

## Stage 9 — Video explanation + demo script
**Goal:** Produce the assignment-mandated video: architecture, governance, a live demo call booking a
meeting, the offline eval summary, and the receipts proving spend ≤ $50.
**Inputs:** the verified system; eval output; receipts.
**Outputs:** a demo script/storyboard; the recorded video; a links/evidence note.
**Definition of Done (QA: `VID1`–`VID3`):**
- [ ] `VID1` — covers architecture → governance (budget/consent/disclosure) → a demo call booking a meeting (**live preferred; a pre-recorded successful real call is an acceptable fallback** if same-day live fails — Red-Team 2026-06-23, Finding 7).
- [ ] `VID2` — shows the offline eval summary and the receipts (spend ≤ $50).
- [ ] `VID3` — within length; every number shown matches its source.
**Status:** ⬜ Not started · **Reviewer gate:** — (PM/Asaf review).

---

## Standard stage handback format
At the end of every stage, the agent reports (also appended to `NOTES.md`):
1. **What changed** — modules/sections drafted vs written; tests added; files touched.
2. **DoD checklist** — each referenced QA ID ✅ / ⚠️; *drafted only* vs *written and test-verified* separated.
3. **QA results** — which check IDs were run and their pass/fail.
4. **Decisions made** — anything not explicitly specified.
5. **Deviations** — anything different from this plan, with reason.
6. **Blockers / risks** — unpinned deps, missing keys/numbers, consent gaps, budget exposure, compliance doubt.
7. **Next recommended action** — one concrete next step.
Do not mark a stage complete if its QA checks were only drafted but not run.

---

## Current project state
- **Status:** **Stages 0–4 ✅ (all offline, PM-verified & committed).** Running the **autonomous loop** (commit +
  auto-advance per stage; halt only on the 3 triggers + Stage 8/9 coordination). Commits: `05cfee4` (spine) ·
  `1bef4e7` (`v1.0.0-stage1`) · `f867207` (Stage 2 A/B) · `405a083` (Stage 3 tools + booking; OQ-VOICE-3 resolved) ·
  Stage 4 (Vapi adapter + Realtime assistant + signature-verified webhooks). **245 tests green.** Stage 4 was
  **recovered PM-led** from a prior session's mid-stage crash (executer finished + wrote its handback; this session
  did verify/review/commit/log). **Carry-forward:** Stage-6 must enrich `simulated_callee` + re-run the A/B (winner
  **B** is provisional) and clear 2 minor eval findings; the Stage-4 public-tunnel live webhook smoke test is owed at
  Stage 8. `LIVE0` provisioning owned by Asaf (not a code gate).
- **Decisions locked:** service-only repo (no notebook); Vapi (Retell-swappable); OpenAI Realtime brain;
  lean live calling under a hard $50 cap; secrets+PII+fabricated-outcomes are the anti-leakage core;
  **operating model — `general-purpose` executers + native `/code-review` & `/security-review` gates;
  plan-debate skipped; Stage 2 runs a scored A/B competition** (`CLAUDE.md` §1.3, NOTES 2026-06-23).
- **Open questions:** all four **✅ resolved 2026-06-23** (NOTES) — `OQ-VOICE-1` `REALTIME_MODEL =
  "gpt-4o-realtime-preview"`; `OQ-VOICE-2` **Vapi** primary + mandatory adapter (Retell-ready);
  `OQ-VOICE-3` **Cal.com API** + deterministic local mock; `OQ-VOICE-4` **3** consented tester numbers.
- **Next action:** **Stage 5 — Outbound orchestration + consent + budget guard** (`app/orchestrate.py` — the campaign
  runner over the synthetic lead list: consent gate + budget guard before dialing, retries, voicemail, daily cap, all
  resilient, zero live calls in the default suite; `CALL1`–`CALL4`, `CON1`, `CON4`, `CON5`, `SEC3`) under the autonomous
  loop; PM verifies + `/code-review` gate (consent chokepoint + budget guard), then auto-advances. **`SEC3`/`CON1`
  second-entry-point spy** (`scripts/place_demo_call.py` must route through `budget_permits` + `consent_allows` before
  `place_call`) lands here. Carry the Stage-6 obligations forward.
