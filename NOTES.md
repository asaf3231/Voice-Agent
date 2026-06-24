# NOTES.md — Decisions, Verified Facts, Open Questions & Handbacks

Project: **Alta Outbound Voice Agent (codename: "Aria")**
Maintained by: Asaf (PM)

> `CLAUDE.md` defines **how** work is done; `PLAN.md` defines **what** the current stage is;
> `QA_checklist.md` defines **how** each stage is verified; this file records **why** — every
> non-obvious decision, every verified fact, every open question, and every stage handback.
> Do not duplicate long plans here; record decisions and the reasoning behind them.

---

## Decisions log

### 2026-06-23 — Deliverable shape: service repo, NOT a notebook  *(supersession — surfaced, not buried)*
**Decision:** The graded artifact is a **production-style service repo** (app + offline test/eval
suite + scripts + README), not a Jupyter notebook.
**Reason:** Asaf chose "service-only" at reconciliation. The assignment's core artifact is a *live
voice agent* — a running service with telephony/realtime audio — which is structurally incompatible
with a "Restart & Run All" deterministic notebook.
**Impact:** Asaf's original kickoff instruction asked for a "notebook-authoring workflow." That is
**superseded**. The *discipline* it demanded (clean one-command run, deterministic reproducible
outputs, no hidden state, strict top-to-bottom ordering, no dead/scratch artifacts, deterministic
seeds, narrative documentation of each step) is **preserved and re-expressed for a service** in
`CLAUDE.md` §8 — the offline `pytest` test+eval suite is the "Restart & Run All" equivalent. This was
flagged to Asaf explicitly rather than silently dropped.

### 2026-06-23 — Voice platform: Vapi (managed), Retell-swappable
**Decision:** Standardize on **Vapi** as the managed voice platform; isolate all platform calls behind
a thin **provider adapter** (`app/vapi_client.py` implementing a `VoiceProvider` interface) so Retell
is a configuration swap, not a rewrite.
**Reason:** Asaf chose "managed platform." Managed platforms ship telephony + turn-taking/barge-in +
per-call transcripts/recordings/cost — the fastest credible path on a 3-day, $50 budget. The adapter
keeps us from hard-coupling to one vendor's REST shape (mirrors the reference project's pluggable-client
discipline).
**Impact:** `VOICE_PROVIDER="vapi"` named constant; the adapter is the single chokepoint for outbound
call control and assistant config. `OQ-VOICE-2`: confirm Vapi vs Retell on first live integration (Stage 4).

### 2026-06-23 — Agent brain: OpenAI Realtime (speech-to-speech)  *(deliberate deviation)*
**Decision:** The conversational brain is **OpenAI Realtime** (`REALTIME_MODEL`, exact id pinned at
Stage 1 install). STT and TTS are subsumed by the realtime model.
**Reason:** Asaf chose OpenAI Realtime for **lowest latency / most natural turn-taking** in a live
phone conversation. This is a deliberate deviation from the house "default to the latest Claude"
standard, accepted for this voice use case.
**Impact:** No separate STT/TTS components to build; OpenAI key configured in the platform, never
committed. Any *non-realtime* reasoning (e.g. offline eval scoring, lead qualification) may still use a
deterministic rule engine — no second LLM is introduced without a recorded decision. `OQ-VOICE-1`:
confirm the exact realtime model id string at install.

### 2026-06-23 — Budget posture: lean live calling, hard $50 cap
**Decision:** A hard total ceiling of **$50** (`HARD_BUDGET_USD`); a soft live-call reserve of **$15**
(`LIVE_CALL_BUDGET_USD`); a per-call ceiling of **$1** (`MAX_COST_PER_CALL_USD`); at most **6**
(`MAX_LIVE_CALLS`) real calls. Real calls go **only to consented test numbers** on an allowlist; the
lead list, ICP, and value-prop facts are **synthetic/assumed**. Receipts captured per call.
**Reason:** Asaf chose the lean posture. Keeps real spend to a few dollars, well under cap, and
compliant (consent + recording disclosure).
**Impact:** Budget governance (`app/budget.py`) and a consent allowlist gate (`app/consent.py`) are
first-class, tested components. The default test/eval suite places **no** live calls.

### 2026-06-23 — Secrets & PII are the anti-leakage core for this project
**Decision:** "Leakage" here means any of: (a) a secret in a tracked file — **the provided credit-card
number**, OpenAI/Vapi API keys, the Vapi webhook signing secret, calendar OAuth tokens; (b) real PII —
real phone numbers, real recordings, live transcripts containing real numbers; (c) **fabricated call
outcomes** — a hardcoded `booked=True`/canned transcript scored as if it were a real result; (d)
hardcoded real Alta/lead business data inlined into code or prompts; (e) any live outbound at import or
in the default test suite.
**Reason:** Direct adaptation of the reference project's anti-leakage rule to a paid, PII-handling,
outbound-calling system. The card number arriving in plaintext in the assignment email makes (a)
concrete and urgent.
**Impact:** `CLAUDE.md` §5 states each as a non-negotiable; `QA_checklist.md` `SEC*`/`LEAK*`/`CON*`
enforce them by grep + gated tests. The card number is never echoed into any file, commit, log, or
transcript.

### 2026-06-23 — Operating model: native review CLIs, general-purpose executers, compute on Stage 2  *(Asaf)*
**Decision:** Adapt the abstract `ORCHESTRATION.md` roles to this environment (`CLAUDE.md` §1.3): (1)
**executers = `general-purpose` subagents** spawned cold per stage (the named `swe-executer`/
`swe-reviewer` types are not registered here); (2) the **reviewer gate = the native `/code-review`
utility**; (3) the **Stage 7 governance / anti-leakage gate = the native `/security-review` utility**;
(4) **skip the symmetric two-agent plan-debate** in favor of a **single-turn adversarial Red-Team
pass** at Stage 0 (schedule realism + governance contracts); (5) **concentrate cognitive compute on
Stage 2** via a scored A/B persona/dialogue competition rather than spreading debate across the
(conventional, already-locked) plan. PM remains the QA gate (re-runs checks) and is **never** the
reviewer — reviewer ≠ executer ≠ PM-as-QA stays intact.
**Reason:** Cold reviewer/executer spawns are the expensive path (token + agent-loop overhead, methodology
budget rules). Native CLI review tools (`/code-review`, `/security-review`) are purpose-built for diffs,
re-derive less context, and preserve reviewer independence. The plan itself is conventional and its big
forks are already locked by Asaf, so debating it is low-yield; the genuine open product risk is the
persona/dialogue, so that is where an A/B bake-off earns its cost. `/security-review` is a strong fit for
a PII- and secret-handling outbound-calling system.
**Impact:** `CLAUDE.md` §1.3 records the role→mechanism map; `PLAN.md` Stage 0 now carries the Red-Team
pass and Stage 2 the mandated A/B competition; the reviewer-gate trigger points at `/code-review`
(+ `/security-review` at Stage 7). **Open sequencing risk:** the Stage 2 A/B is scored against
`app/eval/rubric.py` (otherwise a Stage-6 artifact) — resolve by landing a *minimal* computed rubric at
the start of Stage 2 and enriching it in Stage 6; do **not** score the bake-off on eyeballed criteria
(`EVAL2`/`LEAK4`). *(Separately considered and declined: adopting an external process/skills framework
like Superpowers — the bespoke spine already encodes equivalent discipline, and a second process source
of truth would cause thrash on a 3-day clock; product deps stay minimal + pinned for import-safety/determinism.)*

### 2026-06-23 — OQ-VOICE-1..4 resolved: final technical determinations  *(Asaf)*
**Decision:** All four open questions are now locked:
- **OQ-VOICE-1 (Stage 1, model id):** `REALTIME_MODEL = "gpt-4o-realtime-preview"` is the core engine
  for the OpenAI Realtime session. (Confirms the prior placeholder — now a locked spec, not a guess.)
- **OQ-VOICE-2 (Stage 4, telephony):** **Vapi** is the primary voice-orchestration platform; the
  **Adapter Pattern is mandatory** in the FastAPI codebase — the `VoiceProvider` interface is the single
  egress so the provider stays swappable (Retell-ready) **without touching core state/dialog logic**.
- **OQ-VOICE-3 (Stage 6, scheduling):** **Cal.com API** for booking, with a **clean deterministic local
  mock of its slot-booking contract** for the offline suite — chosen to avoid Google OAuth setup
  bottlenecks inside the 3-day window. The `CalendarProvider` interface stays the seam; the mock is the
  default in tests (`BOOK1`–`BOOK3`), the live Cal.com client is gated like the other live paths.
- **OQ-VOICE-4 (Stage 8, live numbers):** exactly **3 internal tester numbers**, fully whitelisted with
  explicit consent, are ready for live Stage 8 calls + booking pitch. `MAX_LIVE_CALLS = 6` stays the
  budget ceiling; the consent allowlist is seeded with these 3 numbers only (`CON1`).
**Reason:** Asaf's final determinations, given the tight 3-day clock (Cal.com over Google OAuth) and the
adapter discipline that keeps the vendor a config swap.
**Impact:** Locked into `PLAN.md` Stages 1/4/6/8 and the `REALTIME_MODEL`/calendar references in
`CLAUDE.md`. `REALTIME_MODEL` still verified against the real install at Stage 1 (`ENV2`); a 4th+ live
number would need a new consent decision. Executers spinning up on these stages must adhere strictly.

### 2026-06-23 — Stage 0 Red-Team pass: findings folded into the spine  *(handback)*
**What ran:** the mandated single-turn adversarial Red-Team pass (one `general-purpose` agent; axes =
schedule realism + governance chokepoints; no symmetric debate). **Verdict: conditionally green-light** —
governance *design* is strong; 2 blockers + a disclosure-enforcement gap to close first. Per Asaf's
direction (fix blockers + fold all), all findings were folded into the spine before green-light:
- **BLOCKER — card leak (Finding 1):** `Home_Assignment_email.md` held the PAN in plaintext; repo had no
  git/`.gitignore`. → **Redacted** the card line in the email; created **`.gitignore`** (excludes `.env*`,
  `Home_Assignment_email.md`, `REFERENCE/`, allowlist, recordings/transcripts/raw receipts, `.venv`);
  `SEC1`/`LEAK1` now name the file + scope the grep to the **16-digit PAN, not the bare CVV**.
- **BLOCKER — live provisioning invisible (Findings 2/3):** added **`LIVE0`** (day-1 parallel: Vapi number,
  Cal.com key, Realtime access, public webhook tunnel) to QA + Stage 1; the public HTTPS tunnel + a signed
  smoke test are now a named Stage-4 deliverable.
- **HIGH — disclosure "first" not enforced (Finding 4):** `DISCLOSURE_LINE` is now pinned to Vapi's
  **static first-message** (verbatim), asserted byte-exact in `VOICE1`/`CON2` and verified from the real
  transcript in `LIVE2` — a chokepoint, not a hope (`CLAUDE.md` §5 Policy 2 updated).
- **HIGH — Stage 2 double forward-dep (Finding 5):** Stage 2 now pulls a *minimal* `simulated_callee.py`
  **and** thin rubric forward, with the A/B time-boxed to two variants over a small fixed persona set.
- **MED — demo-call second entry point (Finding 8):** `SEC3`/`CON1` now spy-prove `scripts/place_demo_call.py`
  routes through `budget_permits` + `consent_allows` before `place_call`, like `orchestrate.py`.
- **MED — timezone (Finding 6):** `TOOL1`/`BOOK1` now require lead-tz↔calendar-tz resolution.
- **MED — live buffer (Finding 7):** Stage 8 reserves a half-day live-debug buffer; Stage 9 `VID1` accepts a
  pre-recorded successful real call as a fallback.
- **LOW — allowlist validation (Finding 9):** `CON1` now validates the allowlist source on load (like `LEAD1`).
- **LOW — `REFERENCE/` (Finding 10):** gitignored alongside the email.
**Confirmed solid (don't over-correct):** import-safety + lazy singletons, adapter seams, budget
pre-`place_call` chokepoint with provider-spy, deterministic seeded offline suite. Residual risk is
**execution/provisioning**, not design. **Status:** Red-Team DoD item done; Stage 0 now awaits only Asaf's
green-light.

### 2026-06-23 — Stage 0 green-lit; cadence = autonomous loop; LIVE0 = "you provision, I build"  *(Asaf)*
**Decision:** Asaf **green-lit the (post-Red-Team) spine** at 16:57 (via plan approval) — implementation is
authorized; Stage 0 → ✅. Two operating choices set the cadence for the whole build:
1. **Run Stages 1–9 under the autonomous ORCHESTRATION loop** (not stage-by-stage gating): the PM spawns one
   cold `general-purpose` executer per stage (Sonnet), re-runs that stage's `QA_checklist.md` IDs **itself**,
   fires `/code-review` on contract-touching stages (+ `/security-review` at Stage 7), auto-advances clean
   stages, and **halts only** on (a) a decision/open-question/secret, (b) a graded-contract-change request,
   or (c) a 2nd consecutive QA fail — plus natural coordination at Stage 8 (live calls) and Stage 9 (video).
2. **"You provision, I build" for `LIVE0`:** Asaf owns the real-account provisioning (Vapi number + keys,
   Cal.com key + event type, OpenAI Realtime access, public webhook tunnel) on a **parallel track**, while
   executers build all offline-testable code; Stage 8 live calling runs once both tracks meet.
**Reason:** 3-business-day clock; all big forks already locked, so gating every boundary buys little and
costs many round-trips. Provisioning lead time (Vapi A2P/number) is the #1 schedule risk and only Asaf can
do the signups — so it runs in parallel, not in series, from day 1.
**Impact:** PM pre-flight done this session — `git init` + a CLEAN secret gate. Stage 1 starts now. A 4th+
live number or any graded-contract change still halts to Asaf.

### 2026-06-23 — F1 resolved: budget alarm rounding-margin promoted to a §9 constant  *(Asaf — option a)*
**Decision:** The post-hoc over-cap alarm tolerance in `budget.record_cost` (formerly an inline
`_to_decimal(0.01)` literal flagged by the Stage-1 reviewer gate) is promoted to a **§9-controlled
constant** — `BUDGET_ALARM_ROUNDING_MARGIN = Decimal("0.01")` in `app/config.py`, mirrored in `CLAUDE.md`
§9 and the named-constants table below. `budget.py` consumes it via the same lazy `field(default_factory=…)`
pattern as the other caps (the `alarm_margin` ledger field) — governed + injectable, not inlined.
**Reason:** Asaf chose option (a): no inline magic values / floating tolerances; `Decimal` keeps the
arithmetic exact. This is the reviewer-flagged graded-contract change, now authorized and applied.
**Impact:** No behavior change (margin stays $0.01); the pre-call gate (`budget_permits`) remains exact and
does not use this margin. Suite re-verified **107 green**. The only §9 constant added post-genesis.

### 2026-06-23 — Stage 4 post-commit fix: two HIGH gate findings (dispatch calendar injection + CalCom idempotency)  *(PM-verified)*
**Context (reviewer ≠ PM, vindicated):** after the Stage-4 baseline was committed (`013c395`), an **independent
reviewer gate** found **two HIGH issues** the prior PM's *inline* `/code-review` missed — exactly why the methodology
forbids the PM being its own reviewer. This session **independently re-verified both against the running code, then
fixed both** (Asaf-directed: "verify his findings, check also by yourself, and fix it").
- **HIGH #1 (blocking — broke the core deliverable):** the webhook calls `tools.dispatch(name, **args)` with ONLY the
  model's args, but `check_availability` / `book_meeting` require an injected `calendar` (and `check_availability` a
  `now`) the server never supplied → **every booking webhook returned `invalid_input` → no meeting could ever be booked
  over the wire.** The offline suite missed it because the tool tests call the functions directly with a calendar
  injected, never through `dispatch`. **Confirmed empirically** (`dispatch('book_meeting', …)` → "missing keyword-only
  argument 'calendar'"). **Fix:** `dispatch` now injects the calendar/clock for the two booking tools — an explicit
  `calendar=` (offline suite passes `MockCalendar`) or the lazy live `_get_calendar()`; a missing live key →
  structured `calendar_unavailable`, never a crash. **The 5 graded tool signatures are unchanged** — only *how dispatch
  supplies* the dependency changed (an internal router fix, not a graded-contract change). New tests prove a real
  booking end-to-end **over the signed HTTP webhook** (`tests/test_server.py::TestVoice3BookingOverWebhook`).
- **HIGH #2 (live-only, Stage-8-reachable):** `CalComCalendar.create_event` POSTed unconditionally (the `MockCalendar`
  is idempotent; the contract docstring + Policy 5 mandate idempotency) → a retry / webhook redelivery would
  **double-book**. **Fix:** an in-process idempotency cache (`lead_id|slot_key → event_id`) on the long-lived client
  instance — a repeat call returns the same id without re-POSTing. New test proves only one POST for two identical calls.
- **Lower (deferred to Stage-6 eval rework, independently confirmed — NOT fixed here):** `rubric._find_invented_claim`
  dead `claims` param + overclaiming docstring; `simulated_callee._rng` unused; `eval/__init__` stage-order docstring.
  These were already logged in the Stage-2 handback's "2 minor findings" carry-forward; Stage 6 closes them.
**Confirmed CLEAN by the gate (don't re-touch):** import-safety (ENV4, lazy singletons None), Voice/Calendar interface
signatures (intact, sole egress), dispatch identity (== AGENT_TOOLS), byte-exact literals (consumed by identity), the
webhook HMAC verify (fail-closed, constant-time, raw-body — no bypass), budget/consent boundaries, anti-leakage
(no secret/PAN/key), PII masking, LEAK3, eval integrity (computed, no winner), OS-agnostic paths.
**Lesson recorded:** Stage 4 was committed on the PM's inline review alone; an independent gate then caught a
deliverable-breaking bug. **Going forward, contract-touching stages get a genuinely independent reviewer pass (not the
PM's own eyes) before the stage is marked ✅/committed** — the inline shortcut is retired for graded stages.

---

## Named constants (single source of truth — mirrored in `app/config.py`)

| Constant | Value | Meaning |
|---|---|---|
| `HARD_BUDGET_USD` | `50.00` | Absolute spend ceiling (the provided card limit) — never exceed |
| `LIVE_CALL_BUDGET_USD` | `15.00` | Soft reserve for live calls (lean posture) |
| `MAX_COST_PER_CALL_USD` | `1.00` | Per-call projected-cost ceiling; abort beyond |
| `MAX_LIVE_CALLS` | `6` | Lean live eval-set ceiling |
| `BUDGET_ALARM_ROUNDING_MARGIN` | `Decimal("0.01")` | Post-hoc over-cap alarm tolerance in `record_cost` (not the pre-call gate, which is exact); F1 2026-06-23 |
| `MAX_CALL_DURATION_S` | `300` | Hard per-call wall-clock (5 min) |
| `MAX_AGENT_TURNS` | `40` | Anti-loop cap on conversation turns |
| `DAILY_CALL_CAP` | `25` | Outbound throttle per day |
| `CALL_RETRY_MAX` | `2` | Retries on no-answer |
| `VOICEMAIL_MAX_S` | `30` | Leave-voicemail cap |
| `ANSWER_DETECTION_S` | `20` | Ring/answer timeout |
| `BOOKING_SLOT_MINUTES` | `30` | Meeting length |
| `BOOKING_LOOKAHEAD_DAYS` | `10` | How far ahead booking offers slots |
| `REALTIME_MODEL` | `"gpt-realtime-2025-08-28"` | OpenAI Realtime id; reconciled 2026-06-24 to Vapi's accepted set (was `gpt-4o-realtime-preview`, rejected by Vapi `/call`) — `OQ-VOICE-1`/`ENV2` |
| `VOICE_PROVIDER` | `"vapi"` | Managed platform; Retell-swappable via the adapter |
| `RANDOM_SEED` | `42` | Determinism seed for all stochastic offline components |

### Byte-exact graded literals
- `DISCLOSURE_LINE` = `"Hi, this is Aria, an AI assistant calling on behalf of Alta. This call may be recorded for quality. Do you have a quick minute?"`
  — must be the **first** thing spoken on every call (compliance + the project's one byte-exact contract; analog to the reference's `FALLBACK_MESSAGE`). Verified by `CON2`.
- `FAILSAFE_HANGUP_LINE` = `"Thanks for your time — I'll follow up by email. Goodbye."`
  — the safe terminal said on turn-cap, error, or voicemail-timeout. Verified by `CONV6`.

*(Exact wording is reviewable; if Asaf revises a literal, update the constant + the QA check together.)*

---

## Open questions

| ID | Question | Owner | Status |
|---|---|---|---|
| `OQ-VOICE-1` | Exact OpenAI realtime model id string (`REALTIME_MODEL`) | Asaf/PM | ✅ Resolved 2026-06-23; **`ENV2` reconciled 2026-06-24 → `gpt-realtime-2025-08-28`** (Vapi rejected the undated `gpt-4o-realtime-preview`) |
| `OQ-VOICE-2` | Vapi vs Retell final pick (adapter keeps it cheap) | PM | ✅ Resolved 2026-06-23 — **Vapi** primary; Adapter Pattern mandatory (Retell-ready) |
| `OQ-VOICE-3` | Calendar backend for booking: Cal.com vs Google Calendar | Asaf | ✅ Resolved 2026-06-23 — **Cal.com API** + deterministic local mock (avoid Google OAuth) |
| `OQ-VOICE-4` | Are consented test numbers available, and how many? | Asaf | ✅ Resolved 2026-06-23 — **3** internal numbers, whitelisted with consent |

---

## Verified facts
*(populated as stages are PM-verified against running code, never from a handback's word)*

- **2026-06-23 16:57 — secret pre-flight CLEAN (PM-run, partial `SEC1`/`LEAK1`):** after `git init`, the only
  would-be-tracked files are the 9 spine/management files (`.gitignore` + `CLAUDE.md` + `PLAN.md` +
  `QA_checklist.md` + `NOTES.md` + `PM_LOG.md` + `PM_Methodology_Prompt.md` + `ORCHESTRATION.md`).
  `git check-ignore` confirms `Home_Assignment_email.md`, `REFERENCE/`, `.env`, `.env.*`, `consent_allowlist.*`
  are all ignored. A secret-pattern grep (`sk-…`, PEM headers, 4-4-4-4 / 16-digit PAN, `*_API_KEY=`,
  `WEBHOOK_SECRET=`) over the candidate set returned **zero hits**. Full `SEC1`/`LEAK1` re-runs at Stage 1/7
  against the real `.env.example` + `app/` tree.

- **2026-06-23 17:45 — Stage 1 verified (PM-run against live code, post-recovery):**
  - **Stage-1 suite: 105 passed, 0 failed** (`pytest tests/`, offline, venv CPython 3.13.2 / pytest 9.1.1).
  - **Byte-exact literals == CLAUDE.md §9** (verified programmatically, not against the test): `DISCLOSURE_LINE`
    pure ASCII; `FAILSAFE_HANGUP_LINE` non-ASCII = only em-dash U+2014. The crash-introduced curly apostrophe
    (U+2019) was eliminated; a smart-quote regression guard now prevents recurrence.
  - **ENV4 import-safe from an empty cwd** (`/private/tmp`): `app.config`/`budget`/`consent` import with both
    lazy singletons `None`; no `.env`/client/network at import.
  - **SEC1 scans the git-true tracked set (27 files), 0 secret hits.** `git check-ignore` confirms `.env`,
    `Home_Assignment_email.md`, `REFERENCE/`, real `consent_allowlist.json`, `briefs/`, `handbacks/`,
    `.claude/settings.local.json` are IGNORED; `.env.example` + `consent_allowlist.example.json` trackable.

- **2026-06-23 18:40 — Stage 2 verified (PM-run against live code):** full suite **150 passed / 0 failed**;
  `run_bakeoff()` **PM-reproduced + deterministic across runs**; the four mandated A/B criteria (book 0.2 /
  disclosure 0.8 / objection 1.0 / compliance 1.0) **tie**, B leaner on avg_turns (2.6 vs 3.2) → **provisional
  winner B (Direct)**; all modules import-safe from an empty cwd; both literals byte-exact == §9 and **consumed
  from `config` in `persona.py`** (verified by identity). The bake-off is non-decisive on the core hypothesis
  until Stage-6 enrichment (recorded above).

- **2026-06-23 19:16 — Stage 4 verified (PM-run against live code, post-crash recovery):**
  - **Full suite: 245 passed / 0 failed** (`pytest tests/`, offline, venv CPython 3.13.2 / pytest 9.1.1) — matches
    the executer's handback claim exactly; deterministic across runs.
  - **ENV4 import-safe from an empty cwd** (`/private/tmp`) across **all 7 app modules** (config/budget/consent/tools/
    calendar_client/**vapi_client/server**): `_vapi` and `_calendar` lazy singletons both `None`; **httpx NOT in
    `sys.modules`** after import (genuinely lazy); FastAPI `app` constructed at module level is side-effect-free
    (`.env` loaded only in the `lifespan` at startup, never at import).
  - **Both graded literals byte-exact == CLAUDE.md §9 and identity-equal to config** (`persona.X is config.X`):
    `DISCLOSURE_LINE` pure ASCII; `FAILSAFE_HANGUP_LINE` only non-ASCII = em-dash U+2014. `REALTIME_MODEL ==
    "gpt-4o-realtime-preview"`.
  - **`VoiceProvider` interface intact** — exactly the 3 graded methods (`configure_assistant` / `place_call` /
    `fetch_call_cost`); `configure_assistant` is a pure offline builder wiring the realtime model + 5 tools (names
    asserted == `AGENT_TOOLS`) + `DISCLOSURE_LINE` in the static `firstMessage` byte-exact + `recordingEnabled` (CON3).
  - **Webhook auth (VOICE2):** `verify_signature` = HMAC-SHA256 over the **raw body**, constant-time
    (`hmac.compare_digest`), **fails closed** on missing secret/sig; unverified → 401 never processed (read-verified +
    test-verified). **VOICE3:** dispatch routes to `app.tools.dispatch`; unknown tool / bad args / no-tool-call →
    structured error at HTTP 200, no traceback; phone masked.
  - **Diff is additive + no graded contract changed:** the only deletions are the legitimate `ENV4` subprocess
    import-list extension to cover `vapi_client` + `server`.

- **2026-06-23 19:32 — Stage 4 HIGH-findings fix verified (PM-run against live code):**
  - **Full suite: 251 passed / 0 failed** (245 + 6 new regression tests). Deterministic.
  - **Finding #1 empirically reproduced before the fix** (`dispatch('book_meeting', lead_id=…, slot_start_iso=…)` →
    `invalid_input` "missing keyword-only argument 'calendar'"; `check_availability` → missing 'calendar' and 'now')
    and **closed after** (with an injected/auto-resolved calendar both tools return ok=True with slots/event_id).
  - **End-to-end over the signed HTTP webhook:** `POST /webhook/tool` for `check_availability` then `book_meeting`
    (model args only; `_get_calendar` monkeypatched to a shared `MockCalendar`) → a real `event_id` is returned — the
    core deliverable now works over the wire.
  - **Finding #2:** two identical `CalComCalendar.create_event` calls (stubbed client) → same `event_id`, **exactly one
    POST** (no double-book).
  - **No regression to graded contracts:** ENV4 import-safe across 7 modules; httpx still not pulled; both lazy
    singletons `None`; `TOOL_REGISTRY` == `AGENT_TOOLS`; the 5 tool signatures unchanged (only `dispatch`'s internal
    injection changed).

- **2026-06-23 ~19:55 — Stage 5 verified (PM-run against live code) + first INDEPENDENT reviewer gate:**
  - **Full suite: 287 passed / 0 failed** (251 + 36 new). Deterministic.
  - **ENV4 import-safe across all 8 modules** from an empty cwd (now incl. `app.orchestrate`): budget + consent lazy
    singletons `None`; httpx not pulled.
  - **Chokepoint integrity (the graded core):** the independent reviewer traced every branch — **no path reaches
    `place_call` without `consent_allows()` then `budget_permits()`**, in BOTH `orchestrate.py` (consent in `run()` →
    budget at the top of every `_dial_one` retry attempt) AND `scripts/place_demo_call.py` (consent → budget → dial,
    all in `main()`). Provider-spy tests prove `place_call` is unreached when either gate fails.
  - **No graded-contract module touched** (`git status` clean for config/consent/budget/tools/vapi_client/
    calendar_client/persona/server); the new `PROJECTED_COST_PER_CALL` is a local module constant (not §9).
  - **Independent reviewer verdict: APPROVE**; 2 MINOR findings, **both PM-fixed before commit** (a §8 dead import +
    a trivially-passing `test_budget_guard_runs_before_each_retry` — rewritten to genuinely prove the retry guard).

---

## Stage handbacks
*(appended by the executer per stage; the PM verifies independently before honoring)*

### 2026-06-23 17:45 — Stage 1 handback (PM-led crash recovery)  *(PM-verified, not the executer's word)*
**Context:** the original Stage-1 executer crashed (Anthropic 500) after writing code but before any
handback/commit. This session audited every on-disk artifact, fixed defects, hardened the graded checks,
and re-ran QA. No fresh executer spawned (surgical fixes — budget rule). Full handback: `handbacks/stage-1.md`.
**Fixed/added:** byte-exact `FAILSAFE_HANGUP_LINE` (curly U+2019 → straight U+0027, conforming to the locked
CLAUDE.md §9 literal — a conformance fix, *not* a contract change); brief-mandated lazy `load_env()`; replaced
a no-op LEAD3 test with a real one; strengthened `SEC1` to the git-true tracked set; added an AST-based `ENV2`
cross-check, a smart-quote regression guard, and `load_env` coverage; deleted scratch `run_tests.sh`.
**QA (run, not inspected):** **105 passed / 0 failed** (see Verified facts 17:45). Reviewer gate (PM-inline):
3 LOW findings, none blocking.
**Open for Asaf — finding F1:** `app/budget.py` `record_cost` uses an inline magic `0.01` rounding margin
(§8 "no magic values inline"); it tolerates ~1¢ silent overspend on the *post-hoc* alarm (the real gate is
`budget_permits`, pre-call). Naming it as a config constant touches the §9-controlled set, so it is **held**
for your decision: (a) name it in `config.py`, or (b) accept as-is.

### 2026-06-23 18:40 — Stage 2 handback + PM bake-off adjudication  *(PM-verified, not the executer's word)*
**Built by:** one cold `general-purpose` executer (operating model "Executer builds, PM scores", Asaf-chosen).
**Files:** `app/eval/{__init__,simulated_callee,rubric,bakeoff}.py`, `app/persona.py` (A/B via `build_policy`),
`tests/test_conversation.py`; + a `config.value_prop_path()` lazy path-resolver helper.
**PM verification (run, not inspected):** full suite **150 passed / 0 failed** (PM re-ran); ENV4 import-safe
(all modules, empty cwd, lazy singletons None); both literals still byte-exact == CLAUDE.md §9 **and consumed
from config in persona.py** (`persona.DISCLOSURE_LINE is config.DISCLOSURE_LINE`); rubric genuinely **computed**
(negative guards flip compliance False for an injected `$499` price, a phantom booking, and a curly-apostrophe
failsafe drift); LEAK3 clean; **PM independently re-ran `run_bakeoff()` — reproduced the executer's table exactly
and deterministic across runs** (the bake-off-integrity check).
**Computed bake-off table (PM-reproduced):**
```
variant | name                         | book | disclosure | objection | compliance | avg_turns
A       | Consultative / discovery-led | 0.2  | 0.8        | 1.0       | 1.0        | 3.2
B       | Direct / value-first         | 0.2  | 0.8        | 1.0       | 1.0        | 2.6
```
**PM adjudication:** the **four mandated criteria (book / disclosure / objection / compliance) TIE.** The only
computed separator is `avg_agent_turns` (B leaner — A's discovery turn adds a turn without changing the outcome
*in the minimal model*). → **Provisional winner: Variant B (Direct / value-first)** — equal quality/compliance,
leaner (shorter/cheaper calls; lean-budget aligned). Both variants stay available via `build_policy` — reversible.
**⚠ Non-decisive — Stage-6 dependency:** the bake-off CANNOT yet evaluate the core hypothesis (does discovery-led
booking beat value-first?) because the minimal `simulated_callee` books the cooperative persona regardless of
discovery. **Stage 6 MUST enrich the callee so discovery-responsiveness is modeled, then re-run the bake-off
before the persona is locked for live (Stage 4/8).**
**2 minor non-blocking findings (deferred to Stage-6 cleanup):** (1) `SimulatedCallee._rng` is seeded but unused
(determinism comes from fixed scripts + sequential indices) — §8; (2) `rubric._find_invented_claim(…, claims)`
ignores `claims` and its docstring overclaims a file-grounding check it doesn't perform (works now: agent content
carries no $/%/Nx). Neither affects correctness or any score.
**Executer decisions (PM-reviewed, accepted):** added `config.value_prop_path()` — a lazy resolver (NOT a §9
magic-value constant; mirrors `_resolve_allowlist_path`), needed because the Stage-1 LEAD3 test forbids the
`value_prop.md` literal in app code; tightened `pitch_delivered` to exclude the OPENING disclosure. Both sound.

### 2026-06-23 18:55 — Stage 3 handback + PM verification  *(PM-verified, not the executer's word)*
**Built by:** cold executer (Executer builds, PM verifies). **Files:** `app/calendar_client.py` (`CalendarProvider`
Protocol [`list_slots`/`create_event` unchanged] + `MockCalendar` offline default + lazy/gated `CalComCalendar` httpx
client), `app/tools.py` (5 tools + `TOOL_REGISTRY` + import-time `assert keys == AGENT_TOOLS`), `tests/test_tools.py`,
`tests/test_booking.py`; `tests/test_env.py` extended (ENV4 now covers tools/calendar_client). **No graded contract
changed; no DECISION-NEEDED.**
**PM verification (run, not inspected):** full suite **201 passed / 0 failed** (PM re-ran); ENV4 import-safe from an
empty cwd; **httpx is genuinely lazy** (not loaded by importing `calendar_client`); **dispatch identity holds**
(`TOOL_REGISTRY` keys == `AGENT_TOOLS`); `AGENT_TOOLS` + literals + `CalendarProvider` signature **intact**; PM read
both modules — tz resolution (each slot carries `start_utc` + `start_lead_local`; bad tz degrades to the calendar tz,
no crash), idempotent `create_event` (same lead+slot → same `event_id`), conflict → `slot_taken` (no overwrite/phantom),
`log_disposition` phone **always masked** (no full E.164 in the record) — all real, not just claimed.
**Decisions (PM-reviewed, accepted; none graded):** `SALES_CALENDAR_TZ = timezone.utc` (module-local OS-agnostic
default; live event type carries its own tz); MockCalendar business-hours grid kept local to the mock (NOT promoted
to §9 — mock-shaping, not governance). **Live note:** `CalComCalendar` idempotency relies on Cal.com's 409 (not
self-dedup) — validate in Stage 8. **Resolves OQ-VOICE-3.** Committed on `main`.

### 2026-06-23 19:16 — Stage 4 handback + PM verification (crash recovery)  *(PM-verified, not the executer's word)*
**Context:** the prior (Stage-3→4) PM session spawned the Stage-4 executer, which **ran to completion and wrote
`handbacks/stage-4.md`**, but the PM session **crashed before** verification/review/commit/log — leaving Stage-4 code
on disk, PM-unverified, uncommitted, with `PLAN.md` still ⬜. This session recovered it **PM-led, no executer respawn**
(surgical/verification only — budget rule), identical in shape to the Stage-1 recovery.
**Built by (recovered):** the cold Stage-4 executer. **Files:** `app/vapi_client.py` (`VoiceProvider` Protocol [3
graded methods] + `VapiVoiceProvider`: pure offline `configure_assistant` builder + lazy-httpx `place_call`/
`fetch_call_cost` returning structured `CallResult`/`CostResult`), `app/server.py` (import-safe FastAPI; `verify_signature`
HMAC-SHA256 fail-closed; `/webhook/tool` → `tools.dispatch`, `/webhook/status`, `/health`), `app/persona.py`
(+`build_system_prompt` — live prompt assembled at runtime from the value-prop, both literals from config, LEAK3-clean),
`tests/test_voice.py` (28) + `tests/test_server.py` (24) + `tests/conftest.py` (+`FakeVoiceProvider`) +
`tests/test_env.py` (ENV4 extended to 7 modules). **No graded contract changed; no DECISION-NEEDED.**
**PM verification (run, not inspected):** see Verified facts 2026-06-23 19:16 — **245 passed / 0 failed**; ENV4
import-safe across all 7 modules (httpx not pulled); both literals byte-exact == §9 from config; `VoiceProvider`
signatures intact; disclosure pinned to static `firstMessage` byte-exact; webhook fails-closed; dispatch structured-error
safe; diff additive.
**Reviewer gate (`/code-review`, PM-inline per the no-cold-spawn budget rule — contract-touching: provider interface +
webhook auth + import-safety):** **APPROVE.** 0 Critical/Important. **2 LOW (non-blocking, live-carry, already
documented):** (1) the exact Vapi signature header name/scheme + assistant payload field shapes (`firstMessage`,
`recordingEnabled`, `model.tools`) are assumptions to reconcile against the real Vapi API at Stage 8 — `verify_signature`
+ `configure_assistant` are isolated for a one-spot fix; (2) `_extract_tool_call` checks the flat `name` form before the
nested Vapi form (theoretical mis-route only if a provider sent both at once; unreachable with real Vapi/test payloads).
**Executer decisions (PM-reviewed, accepted; none graded):** HMAC over raw body + constant-time + fail-closed; payload
tolerance (flat `{name,arguments}` AND Vapi `message.toolCalls[].function`/legacy `functionCall`); `FastAPI(lifespan=…)`
over deprecated `on_event` (import-safe + clean tree, §8); tool JSON-schemas mirror each tool's kwargs with a
names-==-`AGENT_TOOLS` assert; `build_system_prompt` default variant "B" (provisional winner, kept a parameter).
**Deviations:** none on offline scope — the public-HTTPS-tunnel signed end-to-end webhook smoke test was deliberately
**not** attempted (live/gated, coordinated with `LIVE0`/Stage 8). **Carry-forward (unchanged):** Stage-6 must enrich
`simulated_callee` + re-run the A/B before locking the persona for live. Committed on `main`.

### 2026-06-23 ~19:55 — Stage 5 handback + PM verification + first independent reviewer gate  *(PM-verified)*
**Built by:** one cold `general-purpose` executer (Sonnet), brief `briefs/stage-5.md`. **Files:** `app/orchestrate.py`
(new — campaign runner + promoted `load_leads`/`load_icp`), `scripts/place_demo_call.py` (new — gated second entry
point), `tests/test_orchestrate.py` (new, 36 tests); modified `tests/test_leads.py` (imports the promoted loader, no
duplication), `tests/test_env.py` (ENV4 → 8 modules), `Makefile` (`call` target wired to the script).
**Design (PM-read + reviewer-traced):** `run()` order per lead = DNC suppress (CON5) → `consent_allows` (CON1) →
daily-cap defer (CALL3) → `_dial_one`; `_dial_one` runs `ledger.budget_permits` at the top of EVERY retry attempt
(CALL4/SEC3) before `place_call`, retries only on `no_answer` up to `CALL_RETRY_MAX`, records actual cost after a
placed call, and surfaces every error/exception as a structured `CallDisposition` (CALL1, never raises). Over-budget →
`budget_halted` + clean campaign halt. `place_demo_call.py` mirrors the gates inside `main()` (import-safe).
**PM verification (run, not inspected):** 287 passed/0 failed; ENV4 import-safe across 8 modules; Stage-5 classes
(test_orchestrate + test_leads) 58 passed; **no graded-contract module changed**.
**Reviewer gate — the corrected process (FIRST genuinely independent pass, not PM-inline):** a cold read-only reviewer
(general-purpose, Sonnet) traced the chokepoint in both entry points (no bypass), checked CALL1–4/CON1/4/5/SEC3/ENV4 +
graded-contract integrity + test honesty. **Verdict: APPROVE.** 2 MINOR (non-blocking) findings, **both PM-fixed before
commit:** (1) `orchestrate.py` dead imports `budget_permits`/`record_cost` (only instance methods are used) — §8 clean
tree; (2) `test_budget_guard_runs_before_each_retry` passed trivially (budget failed on attempt 1, never exercising the
retry guard) — rewritten so attempt 1 is permitted + returns `no_answer`, its recorded cost exhausts the budget, and the
RETRY is blocked → asserts exactly one dial + `budget_halted` (now a real regression catcher). Re-ran: 287 green.
**Decisions (PM-reviewed, accepted; none graded):** `PROJECTED_COST_PER_CALL = MAX_COST_PER_CALL_USD` (local module
constant, conservative pre-dial estimate); `run()` accepts injected `ledger=`/`allowlist=` for test isolation (falls
back to the singletons); governance-level disposition statuses (`suppressed`/`consent_refused`/`budget_halted`/
`daily_cap_deferred`/`placed`) are a runner-local superset and do NOT change `tools.VALID_DISPOSITIONS`.
**Known limitation (carry to Stage 8):** `place_demo_call.py` uses a fresh in-process `BudgetLedger` per invocation —
cumulative live spend across separate `make call` runs is reconciled via **receipts** (SEC5/LIVE3), not in-memory (an
in-memory ledger resets each process regardless). **Deviations:** none. **DECISION-NEEDED:** none.

### 2026-06-23 — Stage 6 handback (executer)  *(awaiting PM verification)*
**Built by:** cold SWE executer. **Files touched:** `app/eval/__init__.py` (docstring fix), `app/eval/rubric.py` (dead param removed), `app/eval/simulated_callee.py` (discovery-responsiveness enrichment + `_rng` usage), `app/eval/harness.py` (new), `tests/test_eval.py` (new, 48 tests), `fixtures/transcripts/cooperative_booked.json` (new), `fixtures/transcripts/no_disclosure_regression.json` (new), `fixtures/transcripts/phantom_booking_regression.json` (new). No graded contracts changed; no DECISION-NEEDED.

**3 carry-forward findings closed:**
1. `rubric._find_invented_claim(transcript, claims)` dead `claims` param → **removed**. Signature is now `_find_invented_claim(transcript)`. Docstring corrected to honestly describe what it does (flags $/%/Nx numeric shapes — forbidden by the value-prop file regardless of the claims set). Call site in `_compute_compliance_ok` updated. Verified by EVAL3 signature test.
2. `simulated_callee._rng` seeded but unused → **now used** in `_slot_turn` for stochastic slot acceptance. The per-instance seeded RNG governs discovery-responsive acceptance for COOPERATIVE (no-discovery path, threshold 0.85) and PROBING (post-discovery path, threshold 0.70). Verified by EVAL4 rng_used test.
3. `app/eval/__init__.py` Stage docstring "PITCH → DISCOVERY" wrong order → **corrected** to "OPENING → {A: DISCOVERY → PITCH | B: PITCH} → OBJECTION* → PROPOSE_SLOT → CLOSE → DONE" (matches persona.py state machine). Verified by ENV4 docstring test.

**Stage-6 enrichment decisions (none graded):**
- `_saw_discovery` flag on `SimulatedCallee` tracks whether the agent passed through `Stage.DISCOVERY` before `PROPOSE_SLOT`. Used in `_slot_turn` to route PROBING and COOPERATIVE personas through discovery-responsive acceptance logic.
- Acceptance thresholds (`_ACCEPT_THRESHOLD_COOPERATIVE_NO_DISCOVERY = 0.85`, `_ACCEPT_THRESHOLD_PROBING_WITH_DISCOVERY = 0.70`) are class-level constants on `SimulatedCallee`. With `RANDOM_SEED=42`, the first draw is 0.6394 → both thresholds pass (0.639 < 0.85 for cooperative-without-discovery; 0.639 < 0.70 for probing-with-discovery). Fully deterministic.
- New reply texts added (`_SLOT_REPLY_POST_DISCOVERY`, `_SLOT_REPLY_NO_DISCOVERY`) — all contain "tuesday" so `_callee_accepted` recognizes them without changing `persona.py`. The `Persona`/`Stage`/`Disposition`/`Turn` shared vocab shape is UNCHANGED.
- `harness.py` wraps `bakeoff.run_cells` so harness and bake-off share the same runner; harness adds aggregate machinery + fixture loading on top.

**Re-run A/B bake-off (enriched, computed — PM must re-run to verify):**
```
variant | name                         | book_rate | disclosure_rate | objection_handled_rate | compliance_rate | avg_agent_turns
--------+------------------------------+-----------+-----------------+------------------------+-----------------+----------------
A       | Consultative / discovery-led | 0.4       | 0.8             | 1.0                    | 1.0             | 3.4
B       | Direct / value-first         | 0.2       | 0.8             | 1.0                    | 1.0             | 2.6
```
**Recommended winner (on the numbers): Variant A (Consultative / discovery-led).** Reason: after enrichment, the core hypothesis is now testable. A's book_rate (0.4) is double B's (0.2); disclosure, objection-handling, and compliance still tie. The discovery stage earns a booking from the probing persona (which keeps declining without discovery). Avg_turns are higher for A (3.4 vs 2.6) — a cost tradeoff — but the book-rate advantage is decisive. **PM must adjudicate and lock the persona** (do not change `build_system_prompt`'s default variant without PM decision).

**QA results (run, not inspected):**
- Baseline held: 287 passed (pre-Stage-6)
- Stage-6 additions: 48 new tests in `tests/test_eval.py` — all 48 passed
- Full suite: **335 passed, 0 failed** (run twice — deterministic)
- ENV4 import-safety from empty cwd (`/tmp`): all 7+1 (eval.harness) modules import-safe; httpx NOT in sys.modules

**Deviations:** none. **DECISION-NEEDED:** none. **Blockers/risks:** none (pure-eval stage, no live paths).

### 2026-06-23 — Stage 6 PM verification + persona-lock decision surfaced  *(PM-verified, not the executer's word)*
**PM verification (run, not inspected):** full suite **335 passed / 0 failed, deterministic across two runs**; ENV4
import-safe (eval package + `app.eval.harness` from an empty cwd, httpx not pulled); **PM independently re-ran
`run_bakeoff()` and reproduced the table exactly** (A book 0.4 / B book 0.2; disclosure 0.8 / objection 1.0 /
compliance 1.0 tie; avg_turns A 3.4 / B 2.6); the 3 findings are genuinely fixed (`_find_invented_claim(transcript)` —
dead `claims` param gone; `self._rng` now consumed in `_slot_turn`; `eval/__init__` Stage docstring corrected). No
graded contract changed; pure-eval ⇒ no reviewer gate (PM QA suffices). Stage 6 is **code-complete & PM-verified**.
**⚠ OPEN DECISION (surfaced to Asaf — the provisional persona winner FLIPPED):** the Stage-2 bake-off TIED on the four
criteria and B (Direct) won only on the efficiency tiebreak — *provisional, pending enrichment*. Now that
`simulated_callee` models discovery-responsiveness, the computed re-run gives **A (Consultative) a 2× book-rate
(0.4 vs 0.2)**, tying on disclosure/objection/compliance, costing only ~0.8 more avg turns. **On the numbers, A is the
winner** (exactly the data-driven call Stage 2 was designed to make). Locking A means flipping the live default
`variant="B"→"A"` in `persona.build_system_prompt` + `vapi_client.configure_assistant` (+ conftest fake default +
docstrings) — it changes the **live demo persona** (the video), so per "surface decisions, don't bury them" the PM did
**NOT** auto-flip it inside the Stage-6 commit. **Recommendation: lock A.** Not blocking Stage 7 (anti-leakage/packaging
doesn't depend on the persona); must be locked before Stage 8 (live).

### 2026-06-23 — Persona LOCKED = Variant A (Consultative / discovery-led)  *(Asaf — confirmed the computed winner)*
**Decision:** Asaf confirmed **lock A**. The live default `variant` is now **"A"** in `persona.build_system_prompt`,
`vapi_client.VoiceProvider.configure_assistant` + `VapiVoiceProvider.configure_assistant` (and the conftest
`FakeVoiceProvider`), plus docstrings + the `_VARIANT_PROMPT_GUIDANCE` fallback. `build_policy` already defaulted to A.
**Reason:** the enriched Stage-6 A/B re-run gave A a **2× book-rate (0.4 vs 0.2)**, tying on disclosure/objection/
compliance, at ~0.8 more avg turns — well within caps. Data-driven, exactly the call Stage 2 designed. **Both variants
stay available via `build_policy("A"|"B")` — reversible.** **Impact:** PM-verified the suite stays **335 green** after
the flip (no test depended on B-as-default); `configure_assistant()` now emits `metadata.variant == "A"`. This is NOT a
graded-contract change (the default variant is product config, not a §9 constant/literal). Stage-6 open decision →
**RESOLVED**.

### 2026-06-23 — Stage 7 PM verification + independent security gate (CHANGES-REQUIRED → Mediums fixed; High → Stage-8 blocker)
**Built by:** cold executer (`tests/test_leakage.py` [LEAK1–5 + PKG1–4 over the git-true tracked set] + `MANIFEST.in`).
**PM verification (run, not inspected):** full suite **387 passed / 0 failed**; my **own** secret/PAN sweep over
`git ls-files` → zero hits (only `.env.example`, confirmed placeholders-only); `.env`/`Home_Assignment_email.md`/
`REFERENCE/`/`consent_allowlist.json` git-ignored (`git check-ignore`); MANIFEST prunes the sensitive paths;
ENV4 import-safe. No graded contract changed.
**Independent security gate:** the native `/security-review` CLI **could not run** (it hardcodes a diff vs `origin/HEAD`;
this repo is local-only, no remote) — a tooling limit, logged. Substituted a **cold independent security reviewer**
(general-purpose, read-only) over the Stage-7 diff + the whole pre-live governance surface. **Verdict: CHANGES-REQUIRED.**
It independently re-confirmed the chokepoints CLEAN (HMAC fail-closed/constant-time/raw-body; consent+budget before
`place_call` in both entry points; masking everywhere; import-safety; no secret/PAN/PII/hardcoded-data/abs-path in the
tracked set). Findings:
- **[Medium → FIXED]** `MANIFEST.in` ordering: `exclude consent_allowlist.*.json` clobbered the explicit
  `include consent_allowlist.example.json` (later rule wins) → example dropped from the sdist (PKG3). **Fixed:** re-include
  the placeholder AFTER the broad excludes; real allowlists stay excluded. 
- **[Medium → FIXED]** `tests/test_leakage.py` secret patterns were blind to **PEM private-key blocks** and **JWT bearer
  tokens**. **Fixed:** added both patterns + an assembled-from-parts self-check (no literal PEM/JWT in source). Suite 387 green.
- **[HIGH → DEFERRED to Stage 8 as a hard entry blocker; Asaf decision]** the `BudgetLedger` is **in-memory only**, so
  `place_demo_call.py` (fresh ledger per `make call`) and the `orchestrate` singleton across separate processes both see
  `cumulative=$0` — the **cumulative HARD_BUDGET_USD=$50 cap is illusory across invocations** (the per-call $1 ceiling
  still holds, and there is no path *around* the guard — the guard just sees no history). Impact is **strictly Stage-8**
  (no live call before Stage 8 + LIVE0 + Asaf). **Recommended fix (pairs with Stage-8 `capture_receipts.py`):** make the
  ledger **persist cumulative spend to a gitignored state file** (opt-in `persist_path`; `get_ledger()` uses it,
  `BudgetLedger()` stays in-memory for isolated tests) so both live entry points and receipts reconcile against one real
  cumulative total. **This is a Stage-8 entry gate — no live call until the cumulative cap is genuinely persistent.**
- **[Low ×2, noted]** Cal.com v1 sends the API key as a URL query param (`apiKey=`) — architectural (v1 has no Bearer at
  `/slots`); no key is currently logged (httpx errors don't include the URL here). Webhook `SIGNATURE_HEADER`
  (`x-vapi-signature`) name is unverified until Stage-8 live (fail-closed if wrong — no breach, just deaf). Both carry to Stage 8.

### 2026-06-23 — Stage 8 (build half) PM verification + independent review (Critical caught & fixed)  *(PM-verified)*
**Asaf decisions:** fix the budget-persistence HIGH **now**; **LIVE0 is READY**, proceed to Stage 8. Persona already locked A.
**Built by:** cold executer — opt-in persistent `BudgetLedger` (`persist_path`; atomic temp+`os.replace` save; missing/corrupt
→ $0 + warning, never crash); `get_ledger()` uses a gitignored default state file (`receipts/.budget_ledger.json`) so the
live entry points accumulate across invocations; `scripts/capture_receipts.py` (redacted per-call receipts, SEC5);
`place_demo_call.py` switched to the persistent singleton. Caps/§9/`budget_permits`/`record_cost` signatures UNCHANGED
(additive — not a graded-contract change).
**PM verification (run, not inspected):** I reproduced the cross-instance behavior myself — a 2nd ledger on the same path
loads the prior cumulative; once cumulative+projected would exceed the cap, `budget_permits` returns False **across
instances**; state file holds numeric spend only; ENV4 import-safe (no file I/O at import); the real ledger file is absent
after the suite (no pollution).
**Independent reviewer gate (corrected process — budget is contract-adjacent governance + a security fix): VERDICT
CHANGES-REQUIRED.** It re-confirmed the atomic write, corruption resilience, redaction, import-safety, and unchanged
signatures — and caught what my own pass missed:
- **[CRITICAL → FIXED + PROVEN]** `place_demo_call.py` read the ledger (`budget_permits`) but **never called `record_cost`**
  after a successful call → the persistent cumulative never advanced via `make call` → the cap was still illusory for THAT
  entry point (the HIGH fix only worked for `orchestrate.py`, which does record). **Fix:** the demo script now records the
  actual cost (or a conservative `PROJECTED_COST_PER_CALL` fallback if cost-fetch fails) into the persistent singleton,
  with an over-cap alarm. **Regression test added** (`test_persistent_ledger_advances_across_invocations`): two simulated
  invocations advance cumulative 0.30→0.60. Suite **414 green**.
- **[MEDIUM → FIXED]** module-level convenience tests wrote to the REAL `receipts/.budget_ledger.json` and cleaned up
  inline (a failing assert would leave it polluted). **Fix:** they `monkeypatch` the state path to `tmp_path` + use
  `try/finally` — they never touch the real file (verified: real file absent post-suite).
- **[HIGH → ACCEPTED as a documented limitation]** cross-process TOCTOU: two *simultaneous* processes can both load stale
  state and overspend (no file lock). **Decision:** accept for the lean live demo — single operator, **sequential** `make
  call`, `MAX_LIVE_CALLS=6`, no parallel `orchestrate` against the live budget; a clean cross-platform file lock conflicts
  with the graded **OS-agnostic** requirement (`fcntl` is Unix-only). **Operating constraint (Stage 8):** run live calls
  sequentially; do not run the campaign runner concurrently with `make call` against the live budget. Surfaced to Asaf.
- **[LOW]** `_LEDGER_STATE_PATH` resolved at import (path construction only, no I/O) — cosmetic, no action.
The Critical + Medium were PM-fixed surgically (no executer respawn — budget rule) and re-verified with a dedicated test;
the residual High is an accepted, documented operating constraint, not a code defect.
**⏭ Remaining for Stage 8 (human-coordinated, real money):** the actual live calls (LIVE1–LIVE2 — disclosure-first,
pitch, book a real meeting), `LIVE3`/`SEC5` cost reconciliation from receipts, and the Stage-4 public-tunnel signed-webhook
smoke test. These need the real `.env` + Asaf running `make call` to the 3 consented numbers — **the PM will not place live
calls autonomously.**

### 2026-06-23 — Live-readiness prep: webhook-auth reconciliation + preflight + runbook/storyboard  *(PM-verified)*
**Asaf completed external setup:** Twilio Israeli number `+972 53-563-6788` imported into Vapi; `.env` aligned
(`CALCOM_API_KEY`, `CALCOM_EVENT_TYPE_ID`, `VAPI_PHONE_NUMBER_ID`); set an **`x-vapi-secret`** header in the Vapi
dashboard (Server → Authorization); `consent_allowlist.json` prepared with the 3 consented numbers.
**Webhook auth reconciled (VOICE2 graded contract — CONFIRMED live scheme):** Vapi authenticates server messages with a
**static shared secret** in the `x-vapi-secret` header, NOT HMAC. `server.py` `verify_signature` (HMAC over raw body,
`x-vapi-signature`) → **`verify_secret`** (constant-time `hmac.compare_digest` of the `x-vapi-secret` header vs
`VAPI_WEBHOOK_SECRET`, fail-closed). This was the pre-flagged "live reconciliation" the isolated verify fn existed for —
the graded behavior (reject-bad/accept-good, 401-never-processed, both routes gated) is preserved + tested. Removed the
dead `hashlib`/`_expected_signature`; updated `tests/test_server.py` to the static-secret scheme. **Without this, every
real Vapi webhook would 401 → no tool calls → no booking; this was a live blocker.**
**Preflight built (Asaf ask #1):** `scripts/preflight.py` + `make preflight` + `tests/test_preflight.py` — confirms the 5
required settings are present + the consent allowlist loads, prints **names + PRESENT/MISSING + spend totals only, never a
secret value** (test-asserted). Also fixed a real bug: the scripts (`preflight`/`place_demo_call`/`capture_receipts`)
couldn't `import app` when run directly (`make call`/`make preflight` failed) — added an in-`main()` repo-root `sys.path`
bootstrap (OS-agnostic, no import-time side effect).
**Docs (Asaf ask #2):** `docs/LIVE_RUNBOOK.md` (preconditions → preflight → serve+tunnel+smoke test → sequential
`make call` → capture receipts → failure modes) and `docs/STAGE9_STORYBOARD.md` (architecture → governance → live
booking → eval numbers → receipts ≤ $50).
**Independent security review (corrected process — VOICE2 is the security contract): VERDICT APPROVE.** Re-confirmed
`verify_secret` fail-closed + constant-time + no bypass + both routes gated + HMAC fully removed + preflight prints no
secret + the script bootstraps are import-safe. 3 minor findings, **all PM-fixed:** stale HMAC docstrings → corrected;
the test phone `+972…` → canonical fictitious `+1555…`; the no-leak test strengthened (asserts names present AND values
absent). Suite **419 green**.
**⚠ Preflight caught 2 real gaps in Asaf's local setup (surfaced — these are .env/allowlist, not code):**
(1) `VAPI_WEBHOOK_SECRET` reads as **MISSING** (likely still commented / misnamed / spaces around `=`); (2) the consent
allowlist isn't found at the repo-root default path (place `consent_allowlist.json` at the root or set
`CONSENT_ALLOWLIST_PATH`). **`make preflight` must say PASSED before any live call.**

### 2026-06-24 — REALTIME_MODEL reconciled at live install: `gpt-4o-realtime-preview` → `gpt-realtime-2025-08-28`  *(Asaf — §9 graded-constant change)*
**Decision:** The first live `make call` returned **HTTP 400 from Vapi `/call`**: *"assistant.model.model must be one of …"* — Vapi only accepts **dated** realtime ids; our locked `OQ-VOICE-1` value `"gpt-4o-realtime-preview"` (an undated pre-install guess) is **not accepted**. This is exactly the reconciliation `ENV2` was designed to force. Asaf chose the **current GA** realtime model **`gpt-realtime-2025-08-28`** (over the dated `gpt-4o-realtime-preview-2024-12-17` and the cheaper `gpt-realtime-mini-2025-12-15`).
**Why GA:** newest + most capable, best latency/quality for a live voice demo; per-minute cost is modest, a 2–3 min test call stays well under the $1/call cap. We stay on a **realtime (speech-to-speech)** id — the standard chat models in Vapi's list (gpt-5.x / gpt-4o / o3 …) are not speech-to-speech and would break the low-latency turn-taking that OQ-VOICE-1 chose.
**Applied (graded constant — Asaf-authorized):** `app/config.py` + `CLAUDE.md` §9 + this NOTES table + the OQ-VOICE-1 row; tests updated (`test_env.py` realtime-constant, `test_voice.py` VOICE1 model assertion). Also **widened `place_call`'s Vapi-error capture** (status line → response body, 2000 chars) so any *further* payload-validation errors surface in full on the next attempt. **No other graded contract touched** (disclosure-first byte-exact, recording-gated CON3, the 5 tools, the interface signatures all unchanged).
**Watch:** Vapi validates strictly and the 400 body was truncated — there may be 1–2 more payload tweaks after the model (e.g. `recordingEnabled`/`metadata` placement). The widened capture will reveal them; any such fix stays within the VOICE1 graded contract + independent review before retry.

### 2026-06-24 — First live call diagnosed: conversation worked, booking failed (Vapi tool-result envelope) — fixed  *(PM, from the live Vapi record)*
**Call `019ef86c-…5cc5`** (read-only from Vapi API): ended `customer-ended-call`, ~2 min, **cost $0.4488** (≤ $1 cap), 23 messages.
**What worked:** disclosure spoken FIRST, discovery → value-prop pitch → on "set up the meeting" Aria called
`check_availability`; on tool failure it gracefully degraded to the failsafe-style close + ended safely (governance held).
**Root-cause bug (booking failed — LIVE1 ✗):** every tool call returned Vapi's *"No result returned"* error — our
`/webhook/tool` answered `{"ok":…,"data":…}` but **Vapi requires `{"results":[{"toolCallId":<id>,"result":<string>}]}`**.
So Vapi never saw the slots → no booking. (My earlier smoke test only checked HTTP 200 + dispatch, not Vapi's result
envelope — same "only-verifiable-live" class as the `x-vapi-secret` + model-id reconciliations.) **Fix (VOICE3):**
`_extract_tool_call` now also captures the `toolCallId`; added `_tool_results(...)` returning Vapi's envelope (result =
JSON-encoded tool payload); `tool_webhook` wraps every response (success / no_tool_call / error). Auth + dispatch +
masking unchanged. Tests rewritten to the envelope (+ a toolCallId-echo test). Suite **420 green**; local smoke returns
the exact `{"results":[{"toolCallId":…,"result":…}]}` shape. **Verification of LIVE1 is the live re-test** (the real Vapi
contract), then an independent review of the combined webhook changes.
**Second issue (demo quality, not a code bug):** the disclosure TTS pronounced **"Alta" as "Ulta"** — the `firstMessage`
text is byte-exact/correct; this is a **voice pronunciation** matter (fix in Vapi voice settings / a phonetic hint, or a
`replacements` rule). Flag for the demo; doesn't affect LIVE2's byte-exact text contract.
**Cost/ledger nuance:** the persistent ledger under-recorded ($0) because `place_demo_call` queried cost the instant Vapi
*accepted* the call (cost is finalized only after it ends). Real cost is $0.4488 (from the API/receipt). **Follow-up fix
needed:** capture cost post-call (via `capture_receipts.py`) and reconcile it into the ledger, or don't trust an immediate
`cost=0`.

### 2026-06-24 — Cal.com v1 DECOMMISSIONED → migrated CalComCalendar to API v2 (verified live, no phone call)  *(PM)*
**Found by testing the tool directly against live Cal.com (Asaf's point — verify tools WITHOUT calling the prospect):**
`GET api.cal.com/v1/slots` → **HTTP 410 "API v1 has been decommissioned. Please migrate to API v2."** Our `CalComCalendar`
used v1 → every `check_availability`/`book_meeting` failed. (And `list_slots` swallowed the 410 to `[]`, so it looked like
"0 slots" — a diagnosability gap, now logged.)
**Migration (live-verified formats, not guessed):** base `https://api.cal.com/v2`; **Bearer** auth header (v1 used an
`apiKey` query param); **per-endpoint version header** — `/slots` needs `cal-api-version: 2024-09-04`, `/bookings` needs
`2026-02-25` (both confirmed against the live API; 2026-02-25 on /slots → 404). `/slots` params `eventTypeId/start/end
(YYYY-MM-DD)/timeZone`, response `{"data":{"YYYY-MM-DD":[{"start":"ISO±off"}]}}` (rewrote `_parse_calcom_slots`).
`/bookings` body `{start(UTC ISO), attendee{name,email,timeZone}, eventTypeId}`, response `{"data":{"id","uid"}}`.
**Attendee:** v2 requires one; the synthetic lead data has no email, so it defaults to a synthetic per-lead address —
overridable via env `CALCOM_ATTENDEE_EMAIL`/`_NAME`/`_TIMEZONE` (set a real inbox for the live demo). The
`CalendarProvider` interface signature is **unchanged** (the attendee is derived inside the impl).
**Live verification (read + write, NO phone call):** `check_availability` → **239 real slots** (UTC + lead-local tz);
`book_meeting` → created a real Cal.com event (`uid hNvdynrtijmtAnQS4V7b6n`) → **cancelled it (HTTP 200)** to keep the
calendar clean. Idempotency cache + 409→slot_taken preserved; non-2xx now returns the Cal.com error body (no silent
swallow). Offline suite **420 green** (MockCalendar default unchanged; the Stage-8 idempotency test's fake updated to the
v2 `{"data":{...}}` shape). **All booking blockers resolved** (Vapi result-envelope + Cal.com v2). Remaining: independent
review of the live-path changes, the cost/ledger post-call reconciliation, and a final end-to-end live phone demo.
