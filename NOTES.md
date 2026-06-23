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

---

## Named constants (single source of truth — mirrored in `app/config.py`)

| Constant | Value | Meaning |
|---|---|---|
| `HARD_BUDGET_USD` | `50.00` | Absolute spend ceiling (the provided card limit) — never exceed |
| `LIVE_CALL_BUDGET_USD` | `15.00` | Soft reserve for live calls (lean posture) |
| `MAX_COST_PER_CALL_USD` | `1.00` | Per-call projected-cost ceiling; abort beyond |
| `MAX_LIVE_CALLS` | `6` | Lean live eval-set ceiling |
| `MAX_CALL_DURATION_S` | `300` | Hard per-call wall-clock (5 min) |
| `MAX_AGENT_TURNS` | `40` | Anti-loop cap on conversation turns |
| `DAILY_CALL_CAP` | `25` | Outbound throttle per day |
| `CALL_RETRY_MAX` | `2` | Retries on no-answer |
| `VOICEMAIL_MAX_S` | `30` | Leave-voicemail cap |
| `ANSWER_DETECTION_S` | `20` | Ring/answer timeout |
| `BOOKING_SLOT_MINUTES` | `30` | Meeting length |
| `BOOKING_LOOKAHEAD_DAYS` | `10` | How far ahead booking offers slots |
| `REALTIME_MODEL` | `"gpt-4o-realtime-preview"` | ⚠ pin exact id at Stage 1 install (`OQ-VOICE-1`) |
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
| `OQ-VOICE-1` | Exact OpenAI realtime model id string (`REALTIME_MODEL`) | Asaf/PM | ✅ Resolved 2026-06-23 — `gpt-4o-realtime-preview` (verify at install, `ENV2`) |
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

---

## Stage handbacks
*(appended by the executer per stage; the PM verifies independently before honoring)*
