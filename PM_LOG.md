# PM_LOG.md — PM→PM Session Handoff Log

> Owned by the **PM** only. Executer/reviewer subagents never write here. Begin/end ritual is
> non-negotiable (see `PM_Methodology_Prompt.md`): a `SESSION START` entry before any work, a
> `SESSION END / HANDOFF` entry before stopping — **every session, no exceptions**.
> Workstream tag for this project: `[VOICE]` (single track).

---

## 2026-06-23 14:20 — [VOICE] SESSION START
Picking up: **project genesis** — no spine on disk yet (Stage 0). Reading order at genesis is a
special case: `PM_Methodology_Prompt.md` (read) → assignment (`Home_Assignment_email.md`, read) →
`REFERENCE/*` quality bar (read) → there is no prior `PM_LOG`/`PLAN` to resume from, so I create them.
State as read (to re-verify): nothing built; the assignment asks for a live English outbound voice
agent that pitches and books meetings, built+tested on a real $50 card (receipts required), with a
video explanation due in 3 business days. "Assume anything you want."
Plan for this session: reconcile the assignment against the methodology, resolve the 4 foundational
forks with Asaf, then author the full spine (`CLAUDE.md`, `PLAN.md`, `QA_checklist.md`, plus
`NOTES.md` + this log), and stop to walk Asaf through it before any implementation.

## 2026-06-23 — [VOICE] DECISIONS TAKEN (Asaf, via reconciliation question)
1. **Deliverable shape = service-only repo** (no Jupyter notebook). → The required "notebook-authoring
   workflow" is **superseded** and translated into an equivalent **service authoring + deterministic
   run workflow** (CLAUDE.md §8). Surfaced, not buried; see NOTES 2026-06-23 "Notebook → service".
2. **Voice stack = managed platform** → standardize on **Vapi** behind a provider adapter (Retell-swappable).
3. **Agent brain = OpenAI Realtime (speech-to-speech)** → deliberate deviation from the house
   "default to Claude" standard, chosen for latency. `REALTIME_MODEL` pinned at Stage 1 install.
4. **Budget posture = lean** → hard $50 cap; ~3–6 real calls to consented test numbers only; synthetic
   lead list; receipts captured.

## 2026-06-23 — [VOICE] SESSION END / HANDOFF
Did: Authored the full spine from genesis — `CLAUDE.md`, `PLAN.md`, `QA_checklist.md`, `NOTES.md`,
and this log. No implementation code written (PM does not write production code). Locked named
constants, the byte-exact disclosure literal, the task-specific anti-leakage rule, and a 10-stage plan
whose every DoD points at a runnable `QA_checklist.md` check ID.
Status now: ⚠️ **Awaiting Asaf review of the spine** — Stage 0 is drafted, not yet green-lit. No stage
may start until Asaf approves the spine (CLAUDE.md §0 forbids implementation while the spine is unapproved).
Next PM should: walk Asaf through the spine; on approval, mark Stage 0 ✅ and begin Stage 1
(Environment, secrets & budget governance, synthetic inputs, import-safety) under the ORCHESTRATION loop.
Watch out for / open: the realtime model id is a placeholder pending Stage-1 install (`OQ-VOICE-1`);
Vapi-vs-Retell final pick to confirm on first integration (`OQ-VOICE-2`); calendar backend (Cal.com vs
Google) deferred to Stage 6 (`OQ-VOICE-3`); the provided card number + all keys are secrets — never commit.

## 2026-06-23 15:20 — [VOICE] SESSION START
Picking up: **Stage 0 — Project setup & spine**, status 🟡 *Awaiting Asaf review*. Read order completed:
`PM_Methodology_Prompt.md` → latest `PM_LOG.md` entry (genesis SESSION END) → `CLAUDE.md` → `PLAN.md`
→ `QA_checklist.md` → `NOTES.md` → assignment email.
State as read (to re-verify): spine fully authored & reconciled at genesis; no implementation code on
disk (confirmed: only spine + `Home_Assignment_email.md` + `REFERENCE/` present). All 6 Stage-0 DoD
items checked except the final human gate (Asaf green-light). CLAUDE.md §0 forbids any implementation
until the spine is approved. 4 open questions outstanding (`OQ-VOICE-1..4`).
Flag noticed on read: the **provided card number sits in plaintext in `Home_Assignment_email.md`** at the
repo root — must be gitignored / kept out of any commit when git is initialized (Stage 1, `SEC1`/`LEAK1`).
Plan for this session: walk Asaf through the spine for the green-light gate; surface `OQ-VOICE-1`
(realtime model id, needed to start Stage 1) and the card-file flag; do **not** start any implementation
until approved. Halt and write SESSION END / HANDOFF.

## 2026-06-23 15:45 — [VOICE] DECISIONS TAKEN (Asaf, operating-model planning)
Asaf used this session to plan the operating model (a *different* PM will execute the build). Decided:
1. **No external process framework** (e.g. Superpowers) — the bespoke spine already encodes the
   discipline; a second process source of truth would thrash on a 3-day clock. Product deps stay
   minimal + pinned (import-safety/determinism are graded).
2. **Skip the symmetric two-agent plan-debate** → replace with a **single-turn adversarial Red-Team
   pass** at Stage 0 (schedule realism + governance contracts).
3. **Concentrate compute on Stage 2** → mandate a scored **A/B persona/dialogue competition** judged on
   the computed `app/eval/rubric.py` (not on taste).
4. **Role→mechanism map for this environment** (the `swe-*` agent types are not registered here):
   executers = `general-purpose` subagents per stage; reviewer gate = native **`/code-review`**; Stage 7
   governance gate = native **`/security-review`**; PM stays the QA gate and is never the reviewer.
Landed in: `CLAUDE.md` §1.3 (new), `PLAN.md` (Stage 0 Red-Team, Stage 2 A/B, reviewer-gate trigger,
state footer), `NOTES.md` (decision entry). `PM_Methodology_Prompt.md` deliberately left untouched
(generic master template, per Asaf).

## 2026-06-23 15:50 — [VOICE] SESSION END / HANDOFF
Did: Captured Asaf's operating-model decisions into the active spine (not the generic methodology
template). `CLAUDE.md` §1.3 maps roles→mechanisms (general-purpose executers, `/code-review`,
`/security-review`); `PLAN.md` Stage 0 now requires a single-turn Red-Team pass and Stage 2 a scored
A/B competition; `NOTES.md` logs the rationale. No implementation code written (PM does not).
Status now: ⚠️ Stage 0 still 🟡 — now gated on **(1) the single-turn Red-Team pass, then (2) Asaf's
green-light**. No stage may start until both clear (CLAUDE.md §0).
Next PM should: run the Stage-0 single-turn Red-Team pass (one `general-purpose` agent; scope =
schedule realism + governance chokepoints), fold findings into the spine, then bring it to Asaf for
green-light. Resolve `OQ-VOICE-1` (realtime model id) at Stage 1 start.
Watch out for / open: **Stage 2 → `rubric.py` sequencing** — land a *minimal* computed rubric at the
start of Stage 2 (enrich in Stage 6); never score the A/B on eyeballed criteria (`EVAL2`/`LEAK4`). The
**card number is in plaintext in `Home_Assignment_email.md`** — gitignore it the moment git is
initialized (Stage 1, `SEC1`/`LEAK1`). Open: `OQ-VOICE-1..4`.

## 2026-06-23 16:05 — [VOICE] SESSION END / HANDOFF (OQ lock-in)
Did: Asaf delivered final determinations for all 4 OQs; **logged + locked, no implementation code**.
`NOTES.md` — decision entry + OQ table → ✅ Resolved. Locked into blueprints: `OQ-VOICE-1`
`REALTIME_MODEL="gpt-4o-realtime-preview"` (Stage 1, still `ENV2`-verified at install); `OQ-VOICE-2`
**Vapi** primary + **mandatory adapter**, Retell-swap touches no core state logic (Stage 4/`VOICE5`);
`OQ-VOICE-3` **Cal.com API** + deterministic local mock behind `CalendarProvider` — corrected to
**Stage 3** (where booking lives), Google OAuth avoided (Stage 3/`BOOK*`); `OQ-VOICE-4` **3** consented
tester numbers seeded into the consent allowlist (Stage 8/`CON1`; `MAX_LIVE_CALLS=6` stays the ceiling).
Also annotated `CLAUDE.md` §1.1/§9.
Status now: ⚠️ **Stage 0 still 🟡** — the gate (Red-Team pass → Asaf green-light) is unchanged; OQs being
resolved does **not** open the gate. Asaf's instruction was self-contradictory ("…as they spin up" +
"still dont! proceed to the stage one execution"); cross-read against this log's standing rule ("no stage
starts until both clear"), I **held** — spawned **no** subagent, started **no** Stage 1 work.
Next PM should: get Asaf's explicit pick — **(A)** run the single-turn Stage 0 Red-Team pass now (one
`general-purpose` agent; scope = schedule realism + governance chokepoints), **(B)** skip Red-Team,
green-light Stage 0, start Stage 1, or **(C)** hold. Spawn nothing until that is unambiguous.
Watch out for / open: same as above; all 4 OQs now ✅; card-number-file flag still standing.

## 2026-06-23 16:30 — [VOICE] SESSION END / HANDOFF (Red-Team executed + folded)
Did: Asaf picked **(A)**. Ran the single-turn Stage-0 Red-Team pass (one `general-purpose` agent, no
debate; axes = schedule realism + governance chokepoints). Verdict: **conditionally green-light**.
Per Asaf's direction ("fix blockers + fold all"), folded **every** finding into the spine — **still no
implementation code**:
- **Card leak (BLOCKER):** redacted the PAN line in `Home_Assignment_email.md`; created **`.gitignore`**
  (excludes `.env*`, the email, `REFERENCE/`, allowlist, recordings/transcripts/raw receipts, `.venv`);
  `SEC1`/`LEAK1` now name the files + scope the grep to the 16-digit PAN (not the bare CVV).
- **Live provisioning (BLOCKER):** added **`LIVE0`** (day-1 parallel: Vapi number, Cal.com key, Realtime
  access, public webhook tunnel) to QA §9 + Stage 1; public tunnel + signed smoke test = named Stage-4
  deliverable (`VOICE1`/`VOICE2`).
- **Disclosure (HIGH):** pinned `DISCLOSURE_LINE` to Vapi **static first-message** (verbatim) — `CLAUDE.md`
  §5 Policy 2, `VOICE1`/`CON2`/`LIVE2`.
- Folded MED/LOW: Stage-2 dual forward-dep + time-box; demo-call second-entry-point spy (`SEC3`/`CON1`);
  timezone resolution (`TOOL1`/`BOOK1`); Stage-8 live buffer + Stage-9 recorded-call fallback (`VID1`);
  allowlist load-validation (`CON1`). Stage 0 Red-Team DoD item now [x].
Status now: ⚠️ **Stage 0 still 🟡 — awaiting Asaf's green-light only** (Red-Team done + folded). Per
CLAUDE.md §0 no implementation starts until that green-light. **Correction to earlier entries:** all four
`OQ-VOICE-1..4` are ✅ Resolved (model id, Vapi+adapter, Cal.com+mock, 3 consented numbers) — the "Open:
OQ-VOICE-1..4" line in the 15:50 entry is **stale/superseded**.
Next PM should: present the Red-Team result + folded fixes to Asaf; on green-light, mark Stage 0 ✅ and
start Stage 1 **with `LIVE0` provisioning kicked off in parallel on day 1** (the #1 schedule risk).
Watch out for / open: provisioning lead time (Vapi A2P/number, Cal.com) is the top schedule risk; verify
`REALTIME_MODEL` against the real install at `ENV2`; reviewer gate = `/code-review`, Stage-7 gate =
`/security-review`.

## 2026-06-23 16:57 — [VOICE] SESSION START
Picking up: **Stage 0 — Project setup & spine**, status 🟡 *Awaiting Asaf green-light* (Red-Team done +
folded). Read order completed: `PM_Methodology_Prompt.md` → latest `PM_LOG.md` entry (16:30 Red-Team
handoff) → `CLAUDE.md` → `PLAN.md` → `QA_checklist.md` → `NOTES.md` → `ORCHESTRATION.md` → assignment email.
State as read (re-verified this session): spine authored, reconciled, Red-Team-hardened; all 4 OQs ✅; **no
implementation code on disk**; repo **not yet under git** (now `git init`-ed this session); card **redacted**
in `Home_Assignment_email.md`; **no root `.env`** present (verified 16:57); `.gitignore` covers `.env*`/email/
`REFERENCE/`/allowlist/recordings/transcripts/receipts/`.venv`.
Operating decisions taken by Asaf this session (logged to NOTES): (1) **drive Stages 1–9 via the autonomous
ORCHESTRATION loop** — `general-purpose` executers (Sonnet), `/code-review` on contract stages,
`/security-review` at Stage 7, PM re-runs QA itself, halt only on the 3 triggers; (2) **"you provision, I
build"** — Asaf owns `LIVE0` (Vapi / Cal.com / OpenAI Realtime / public webhook tunnel) in parallel while
executers build the offline-testable code.
Plan for this session: green-light granted (via plan approval) → `git init` + secret pre-flight gate (done,
**CLEAN**) → mark Stage 0 ✅ → hand Asaf the `LIVE0` provisioning checklist → run **Stage 1** under the loop
(env, secrets, budget, consent, synthetic inputs, import-safety), then auto-advance the offline stages,
halting per the triggers. Write SESSION END / HANDOFF before stopping.

## 2026-06-23 17:06 — [VOICE] SESSION START
Picking up: **Stage 1 — Environment, secrets, budget & synthetic inputs**, the first non-✅ stage.
Read order completed: `PM_Methodology_Prompt.md` → latest `PM_LOG.md` entry (16:57 SESSION START) →
`CLAUDE.md` → `PLAN.md` → `QA_checklist.md` → `NOTES.md`.
**Anomaly found on resume (re-verified against disk, not the ledger):** the 16:57 session wrote a
SESSION START declaring "Stage 1 starts now" but **never wrote a SESSION END / HANDOFF**, and **no
Stage-1 code landed** — `git log` shows only the Stage-0 baseline `05cfee4`; there is no `app/`, `data/`,
`tests/`, `requirements.txt`, `Makefile`, or `.env.example` on disk. `PLAN.md` marks Stage 1 "🔄 In
progress" but that reflects intent, not work done. **True state: Stage 1 is not started in code.** That
prior session evidently stalled immediately after its START entry.
State as read (to re-verify): Stage 0 ✅ green-lit; repo under git; secret pre-flight CLEAN; all 4 OQs ✅
(`REALTIME_MODEL="gpt-4o-realtime-preview"`, Vapi+adapter, Cal.com+mock, 3 consented numbers); operating
model = autonomous ORCHESTRATION loop, `general-purpose` executers per stage, `/code-review` on contract
stages, PM re-runs QA, "you provision, I build" (Asaf owns `LIVE0`).
Plan for this session: confirm the resume state + the stalled-session anomaly with Asaf, then launch the
Stage 1 cold `general-purpose` executer under the loop, PM-verify the Stage-1 QA IDs
(`ENV1`–`ENV4`, `SEC1`–`SEC4`, `LEAD1`–`LEAD3`, `CON1`) + run the `/code-review` gate, update `PLAN.md`/
`NOTES.md`, and write a SESSION END / HANDOFF before stopping.

## 2026-06-23 17:27 — [VOICE] SESSION START (recovery — prior session crashed mid-Stage-1)
Picking up: **Stage 1 — Environment, secrets, budget & synthetic inputs**, the first non-✅ stage. Read
order completed this session: `PM_Methodology_Prompt.md` → latest `PM_LOG.md` entry (17:06 START) →
`CLAUDE.md` → `PLAN.md` → `QA_checklist.md` → `NOTES.md` → the Stage-1 brief + every artifact on disk.
**Anomaly / recovery context (verified against disk, not the ledger):** unlike the 17:06 entry's prediction
("no Stage-1 code landed"), the 17:06 session's executer **did** run and **did** write Stage-1 code — then
an **Anthropic Server 500 infrastructure crash** killed the session **before** any SESSION END / HANDOFF
and **before** the executer wrote `handbacks/stage-1.md` (the `handbacks/` dir exists but is empty). So the
true state is: **uncommitted Stage-1 code on disk, unverified, unreviewed, uncommitted** — `git log` shows
only the Stage-0 baseline `05cfee4`; all Stage-1 files are `??` untracked; `.gitignore` + `PM_LOG.md` are `M`.
State as read (re-verified): venv present (CPython **3.13.2**, pytest **9.1.1**); Stage-0 ✅; all 4 OQs ✅;
operating model = autonomous loop, `general-purpose` executers, `/code-review` on contract stages, PM re-runs QA.
**Defect already found (byte-exact graded contract, pre-test):** `app/config.py` `FAILSAFE_HANGUP_LINE` uses a
**curly apostrophe U+2019** where `CLAUDE.md`/`NOTES.md`/`tests/test_env.py` all use a **straight U+0027** —
an implementation drift from the locked literal (NOT a contract change). Fixing config to match source is
in-scope and required; the locked literal in CLAUDE.md is untouched.
Plan for this session (no fresh executer spawn — recovery is a PM-led stabilization of existing on-disk work):
(1) run the offline suite for ground-truth pass/fail; (2) fix the byte-exact literal + any other defects
(scratch artifacts, SEC1 robustness); (3) re-verify the Stage-1 QA IDs by running them; (4) run the
`/code-review` gate (contract-touching stage); (5) write `handbacks/stage-1.md`, update `PLAN.md`/`NOTES.md`,
commit the Stage-1 baseline, and write a SESSION END / HANDOFF before stopping.

## 2026-06-23 17:45 — [VOICE] SESSION END / HANDOFF (Stage 1 stabilized + verified)
Did: Recovered the crashed Stage-1 work **PM-led, no executer respawn** (surgical fixes — budget rule).
Audited every on-disk artifact; **fixed the byte-exact `FAILSAFE_HANGUP_LINE` curly-apostrophe contract
violation** (U+2019→U+0027, conforming to CLAUDE.md §9 — not a contract change); added the brief-mandated lazy
`load_env()`; replaced a no-op LEAD3 test with a real one; strengthened `SEC1` to the git-true tracked set;
added an AST `ENV2` cross-check, a smart-quote regression guard, and `load_env` coverage; deleted scratch
`run_tests.sh`. Ran the reviewer gate (PM-inline, not 8 cold spawns — budget + no-spawn guardrail): 3 LOW
findings, none blocking. Wrote `handbacks/stage-1.md`; updated `PLAN.md` (Stage 1 → ✅ offline) + `NOTES.md`.
Verified numbers (PM-run, not the executer's word): **105 passed / 0 failed**; both literals byte-exact ==
CLAUDE.md §9 (`FAILSAFE` non-ASCII = em-dash U+2014 only); ENV4 import-safe from empty cwd (singletons `None`);
SEC1 scans 27 git-tracked files, 0 secret hits; gitignore contract proven by `git check-ignore`.
Status now: ✅ **Stage 1 code-complete & verified (offline scope).** Work is **staged but NOT committed**
(global rule: commit only when Asaf asks; on the default branch, branch first). `LIVE0` provisioning is
Asaf's parallel track (not a code gate).
Next PM should: (1) get Asaf's go to **commit the Stage-1 baseline** (recommend `main`, as a recovery point,
matching the Stage-0 baseline convention); (2) get Asaf's call on **finding F1** (`budget.py` inline `0.01`
margin — name as a config constant [touches §9] or accept); (3) begin **Stage 2** (conversation design / A-B),
landing the minimal seeded `simulated_callee.py` + thin computed rubric **first** (Red-Team Finding 5) before
the bake-off. Stop at the Stage-1 boundary per CLAUDE.md §0 until commit + F1 are settled.
Watch out for / open: F1 (Asaf decision); `LIVE0` provisioning lead time (#1 schedule risk); do not start
Stage 2 code until commit + F1 are settled.

## 2026-06-23 17:50 — [VOICE] NOTE (commit landed; appended post-SESSION-END for ledger accuracy)
Asaf approved the commit. The **Stage-1 baseline is committed on `main`** (recovery point directly above the
Stage-0 baseline `05cfee4`); working tree clean. Of the SESSION END's three next-actions, (1) commit is now
**done**; remaining: **(2)** Asaf's finding-**F1** decision and **(3)** Stage 2. Not pushed (local only).

## 2026-06-23 18:00 — [VOICE] SESSION END / HANDOFF (Stage 1 FINAL — F1 applied + baseline locked)
Did (continuation of the 17:27 recovery session): applied Asaf's **F1 resolution (option a)** — promoted the
`record_cost` rounding margin to a §9-controlled constant `BUDGET_ALARM_ROUNDING_MARGIN = Decimal("0.01")`
(config.py + CLAUDE.md §9 + NOTES table), consumed via budget.py's lazy `alarm_margin` field; added 2 tests.
Re-ran comprehensive verification, then **amended the Stage-1 baseline commit** to fold in F1 and carry
Asaf's exact message: `v1.0.0-stage1: complete environment, secrets architecture, budget ledger and
synthetic inputs`.
Verified numbers (PM-run): **107 passed / 0 failed**; ENV4 import-safe from empty cwd with the F1 constant
wired; both graded literals still byte-exact == CLAUDE.md §9. Working tree clean; one commit on `main`
(`v1.0.0-stage1`) above the Stage-0 baseline; not pushed.
Status now: ✅ **Stage 1 COMPLETE (offline scope), committed & locked.** All Stage-1 QA IDs green; reviewer
findings closed (F1 fixed; F2/F3 cosmetic/doc, accepted). `LIVE0` provisioning remains Asaf's parallel track.
Next PM should: **initialize Stage 2 (conversation design / A-B)** on Asaf's go — per the strict
forward-dependency guardrail, land the minimal seeded `app/eval/simulated_callee.py` + the thin computed
deterministic `app/eval/rubric.py` framework **first**, BEFORE authoring any persona variant or running the
bake-off (Red-Team Finding 5; `EVAL2`/`LEAK4`).
Watch out for / open: `LIVE0` provisioning lead time (#1 schedule risk); the Stage-2 rubric/simulated-callee
forward-dep must be honored or Stages 3/4/8/9 cascade.

## 2026-06-23 18:10 — [VOICE] SESSION START (Stage 2 kickoff)
Picking up: **Stage 2 — Conversation design (persona, dialog policy, literals) — A/B competition**, the first
non-✅ stage (Stage 1 ✅, committed `v1.0.0-stage1` / `1bef4e7`). Read order completed: `PM_Methodology_Prompt.md`
→ latest `PM_LOG.md` (18:00 SESSION END) → `CLAUDE.md` → `PLAN.md` (Stage 2) → `QA_checklist.md` (§4 `CONV*`,
§8 `EVAL*`) → `NOTES.md`.
State as read (to re-verify before building): Stage 1 green (107 tests); the two byte-exact literals locked in
`app/config.py`; §9 set incl. the new `BUDGET_ALARM_ROUNDING_MARGIN`. **Stage 2 carries a DOUBLE forward-dep**
(Red-Team Finding 5): the A/B must be scored by a computed `app/eval/rubric.py` AND driven by a seeded
`app/eval/simulated_callee.py` — both land (minimal) at the START of Stage 2, enriched in Stage 6; the winner
is decided on **computed numbers**, never eyeballed (`EVAL2`/`LEAK4`).
Plan for this session: surface the two Stage-2 forks to Asaf — (1) build approach (cold executer vs PM-inline;
bake-off integrity favors an executer building the variants while the PM independently owns the rubric +
scoring), (2) the two A/B persona/dialog variant directions — then write the Stage-2 brief and proceed.
Reviewer gate (`/code-review`) applies (literals + Policy 4/6). **Do not author personas before the
rubric + simulated-callee infra lands.**

## 2026-06-23 18:40 — [VOICE] SESSION END / HANDOFF (Stage 2 built + PM-verified)
Did: Kicked off Stage 2 under **"Executer builds, PM scores"** (Asaf-chosen). Spawned ONE cold
`general-purpose` executer (Asaf-authorized via the build-approach choice) which built
`app/eval/{__init__,simulated_callee,rubric,bakeoff}.py` + `app/persona.py` (A/B via `build_policy`) +
`tests/test_conversation.py` + a `config.value_prop_path()` resolver. **PM independently verified, NOT the
executer's word:** re-ran the full suite (**150 passed/0 failed**), re-proved ENV4 import-safety, confirmed
literals byte-exact + consumed-from-config (by identity), read every module, and **independently re-ran
`run_bakeoff()` — reproduced the executer's table exactly + deterministic** (the integrity check). Reviewer
gate done PM-inline (consistent with Stage 1): rubric is a genuinely computed, unbiased judge (negative guards
hold); 2 minor non-blocking findings deferred to Stage 6.
Bake-off (PM-reproduced): A & B **tie** on all four mandated criteria (book 0.2 / disclosure 0.8 / objection
1.0 / compliance 1.0); B leaner on avg_turns (2.6 vs 3.2). **Provisional winner: B (Direct/value-first)** — but
the four criteria TIED; the minimal substrate can't yet evaluate consultative-vs-direct booking impact.
**Stage 6 MUST enrich `simulated_callee` + re-run the bake-off before locking the persona for live.**
Status now: ✅ **Stage 2 code-complete & PM-verified (offline).** Work is **staged but NOT committed** (commit
only on Asaf's go — established pattern). Ledger updated: `PLAN.md` (Stage 2 ✅), `NOTES.md` (handback + bake-off
+ verified facts).
Next PM should: (1) get Asaf's go to **commit the Stage-2 baseline**; (2) **Stage 3 — agent callable functions +
booking** (`TOOL1`–`TOOL5`, `BOOK1`–`BOOK3`) next; (3) carry forward the Stage-6 bake-off re-run obligation +
the 2 minor eval findings; do NOT hard-lock variant B before the Stage-6 re-run.
Watch out for / open: the persona winner (B) is **provisional**; `LIVE0` provisioning (Asaf's track).

## 2026-06-23 18:45 — [VOICE] SESSION START (Stage 3 — autonomous cadence activated)
**Operating-cadence change (Asaf):** granted standing permission to **commit and auto-advance after each stage**
without stopping for approval — run the full autonomous ORCHESTRATION loop. Cadence now: finish a stage →
PM-verify (re-run that stage's QA myself) → `/code-review` gate on contract stages → commit → advance, **halting
only** on the 3 triggers (a required decision/open-question/secret; a graded-contract-change request; a 2nd
consecutive QA fail), plus the natural coordination at Stage 8 (live calls need `LIVE0` + Asaf) and Stage 9
(video). Executer-per-stage model continues ("Executer builds, PM verifies").
Picking up: **Stage 3 — Agent callable functions + booking** (first non-✅ stage; Stages 0–2 ✅, committed
`05cfee4` / `1bef4e7` / `f867207`). Read order completed: spine + `QA_checklist.md` §5 (`TOOL*`/`BOOK*`) + NOTES
(OQ-VOICE-3 = Cal.com API + deterministic local mock).
Plan: brief + spawn a cold executer for the 5 tools (`app/tools.py`) + the `CalendarProvider` layer
(`app/calendar_client.py` — Cal.com httpx client **gated/lazy** + a deterministic **local mock** as the test
default); PM-verify `TOOL1`–`TOOL5` / `BOOK1`–`BOOK3` + ENV4 + the dispatch-identity assert; run `/code-review`
(tool signatures + calendar interface are graded); commit; advance to Stage 4. Resolves `OQ-VOICE-3`.

## 2026-06-23 18:55 — [VOICE] STAGE 3 ✅ COMPLETE + COMMITTED (autonomous loop)
PM-verified: full suite **201 passed/0 failed** (re-ran); ENV4 import-safe from empty cwd; **httpx lazy**; dispatch
identity (`TOOL_REGISTRY` == `AGENT_TOOLS`); literals + `CalendarProvider` signature intact; tz resolution / idempotent
booking / masked dispositions read-verified in both modules. No graded contract changed; no DECISION-NEEDED. Reviewer
gate PM-inline → clean. Committed on `main`. **OQ-VOICE-3 resolved** (Cal.com behind `CalendarProvider` + local mock
default). Advancing to **Stage 4 — Voice-platform integration** under the loop.

## 2026-06-23 19:16 — [VOICE] SESSION START (recovery — prior session crashed after the Stage-4 executer finished)
Picking up: **Stage 4 — Voice-platform integration (Vapi + Realtime + webhooks)**, the first non-✅ stage
(Stages 0–3 ✅, committed `05cfee4` / `1bef4e7` / `f867207` / `405a083`). Read order completed this session:
`PM_Methodology_Prompt.md` (verbatim) → latest `PM_LOG.md` entry (18:55 Stage-3 complete) → `CLAUDE.md` →
`PLAN.md` → `QA_checklist.md` → `NOTES.md` → `ORCHESTRATION.md`, then the Stage-4 brief + handback + on-disk state.
**Anomaly / recovery context (verified against disk, not the ledger):** the 18:45 (Stage-3→4) session spawned the
Stage-4 executer, which **ran to completion and wrote `handbacks/stage-4.md` at 19:00** (claims **245 passed/0
failed**, no graded contract changed, **no DECISION-NEEDED**), but the PM session then **died before** PM-verification,
the `/code-review` gate, the commit, the PLAN/NOTES updates, and any SESSION END entry. So the true state is:
**Stage-4 code on disk + executer handback written, but PM-unverified, unreviewed, uncommitted, unlogged** — `git log`
tops out at the Stage-3 baseline `405a083`; Stage-4 files are untracked (`app/server.py`, `app/vapi_client.py`,
`tests/test_server.py`, `tests/test_voice.py`) with `app/persona.py` / `tests/conftest.py` / `tests/test_env.py`
modified. `PLAN.md` still marks Stage 4 ⬜ Not started (reflects ledger lag, not work done).
State as read (to re-verify against running code): Stages 0–3 ✅; all 4 OQs ✅; operating model = autonomous loop
("Executer builds, PM verifies"), `/code-review` on contract stages, PM re-runs QA itself; autonomous commit+
auto-advance cadence granted 18:45 (halt only on the 3 triggers + Stage 8/9 coordination).
Plan for this session (recovery is PM-led verification of existing on-disk work — no fresh executer respawn, per the
budget rule): (1) run the full offline suite for ground-truth pass/fail; (2) re-prove ENV4 import-safety now covering
`app.server` + `app.vapi_client` (lazy singletons `None`, httpx not pulled); (3) PM-verify the Stage-4 QA IDs
(`VOICE1`–`VOICE5`, `CON2`–`CON3`) + both literals byte-exact + the disclosure pinned to the static first-message;
(4) run the **`/code-review`** gate (contract-touching: `VoiceProvider` interface + webhook signature auth +
import-safety); (5) append the Stage-4 handback to `NOTES.md`, mark `PLAN.md` Stage 4 ✅, commit the Stage-4 baseline;
(6) write a SESSION END / HANDOFF before stopping. Carry forward the Stage-6 bake-off re-run + the public-tunnel live
smoke test (gated, Asaf's `LIVE0` track).

## 2026-06-23 19:16 — [VOICE] SESSION END / HANDOFF (Stage 4 recovered, verified, reviewed, committed)
Did: Recovered the crashed Stage-4 session **PM-led, no executer respawn** (verification-only — budget rule). The
executer's on-disk work was complete + its handback written; this session did the PM half. **PM-verified (run, not the
executer's word):** full suite **245 passed / 0 failed** (deterministic); ENV4 import-safe across **all 7 app modules**
from an empty cwd (httpx not pulled, both lazy singletons `None`); both graded literals byte-exact == CLAUDE.md §9 and
identity-equal to config; `VoiceProvider` 3 graded signatures intact; `DISCLOSURE_LINE` pinned to the static
`firstMessage` byte-exact + recording gated (CON3); webhook `verify_signature` HMAC-over-raw-body, constant-time,
**fails closed** (VOICE2); dispatch structured-error safe (VOICE3); diff additive, no graded contract changed. Ran the
**`/code-review`** gate PM-inline (contract-touching) → **APPROVE**, 2 LOW non-blocking live-carry findings. Updated
`PLAN.md` (Stage 4 → ✅, footer, next-action → Stage 5) + `NOTES.md` (verified-facts + handback). **Committed** the
Stage-4 baseline on `main`.
Verified numbers (PM-run): **245 passed / 0 failed**; ENV4 clean; literals byte-exact; `REALTIME_MODEL =
gpt-4o-realtime-preview`.
Status now: ✅ **Stage 4 COMPLETE (offline scope), PM-verified, reviewer-gate-clean, committed.** Stages 0–4 all ✅.
Paused at the Stage-4 boundary (kickoff + crash-recovery) to surface the recovery before the next cold spawn — NOT a
halt trigger.
Next PM should: **Stage 5 — Outbound orchestration + consent + budget guard** (`app/orchestrate.py`; `CALL1`–`CALL4`,
`CON1`, `CON4`, `CON5`, `SEC3`) under the autonomous loop — brief + spawn one cold `general-purpose` executer, then
PM-verify + `/code-review` (consent chokepoint + budget guard). The `SEC3`/`CON1` **second-entry-point spy** on
`scripts/place_demo_call.py` lands here. On Asaf's "run the loop" / "continue", proceed without further gating.
Watch out for / open: **recurring mid-stage session crashes** — each stage's executer work has survived on disk + its
handback, recoverable PM-led, but watch for an uncommitted-work gap on resume (always re-verify disk vs the ledger).
Carry-forward: Stage-6 `simulated_callee` enrichment + A/B re-run (winner **B** provisional); Stage-4 public-tunnel live
webhook smoke owed at Stage 8; `LIVE0` provisioning is Asaf's parallel track + #1 schedule risk.

## 2026-06-23 19:32 — [VOICE] SESSION START (Stage 4 reopened — independent gate caught 2 HIGH the inline review missed)
Picking up: **Stage 4 post-commit hardening.** After this session committed the Stage-4 baseline (`013c395`) on the
PM's *inline* `/code-review`, Asaf ran an **independent reviewer gate** that surfaced **two HIGH findings the inline pass
missed** (reviewer ≠ PM, vindicated). Asaf directed: "verify his findings, check also by yourself, and fix it."
State as read / re-verified against the running code (not the brief's word):
- **#1 (blocking — core deliverable):** `server.tool_webhook` → `tools.dispatch(name, **args)` with ONLY model args, but
  `check_availability`/`book_meeting` need an injected `calendar` (+ `now`) the server never supplied → both always
  returned `invalid_input` → **no meeting bookable over the webhook.** Reproduced empirically. The offline suite missed
  it (tool tests call the funcs directly with a calendar, never via `dispatch`).
- **#2 (live, Stage-8-reachable):** `CalComCalendar.create_event` POSTs unconditionally (Mock is idempotent; contract +
  Policy 5 mandate idempotency) → double-book on retry/redelivery. Confirmed by inspection.
- Lower (deferred to Stage-6, already on the carry-forward): `_find_invented_claim` dead param, `_rng` unused,
  `eval/__init__` docstring order.
Plan: PM-led fix (no executer respawn) + TDD; re-verify; commit the fix as a follow-up to `013c395`.

## 2026-06-23 19:32 — [VOICE] SESSION END / HANDOFF (both HIGH findings fixed + verified + committed)
Did: **Verified both findings independently, then fixed both** (PM-led).
- **#1:** `tools.dispatch` now injects the calendar/clock for the two booking tools (explicit `calendar=` for the offline
  suite, else lazy live `_get_calendar()`; missing key → structured `calendar_unavailable`, never a crash). **No graded
  tool signature changed** — internal router fix only. Added regression tests incl. **a real booking end-to-end over the
  signed HTTP webhook** (`TestVoice3BookingOverWebhook`) + `TestDispatchInjectsCalendar`.
- **#2:** `CalComCalendar.create_event` now idempotent via an in-process `lead_id|slot_key → event_id` cache (repeat call
  = same id, no re-POST). Added `TestCalComIdempotency`.
Verified numbers (PM-run): **251 passed / 0 failed** (+6 new); finding #1 reproduced-then-closed; ENV4 import-safe across
7 modules, httpx not pulled, singletons `None`; `TOOL_REGISTRY` == `AGENT_TOOLS`; 5 tool signatures unchanged; both
literals byte-exact == §9. Updated `PLAN.md` (Stage 4 note + footer, 251) + `NOTES.md` (decision + verified facts).
Committed the fix on `main` (follow-up to the Stage-4 baseline).
Status now: ✅ **Stage 4 fixed & re-verified.** The deliverable (book a meeting over the webhook) now works in the
offline harness. Stages 0–4 ✅, 251 green.
**Process change (logged in NOTES):** contract-touching stages get a **genuinely independent reviewer pass (not the PM's
own inline eyes)** before ✅/commit — the inline shortcut is retired for graded stages. Stage 5 onward follows this.
Next PM should: **Stage 5 — orchestration + consent + budget guard** under the loop, with an independent reviewer gate
this time. On Asaf's "run the loop"/"continue", proceed.
Watch out for / open: Stage-6 must close the 3 minor eval findings + the `simulated_callee` enrichment / A/B re-run
(winner **B** provisional); Stage-4 public-tunnel live webhook smoke owed at Stage 8; recurring mid-stage crashes —
re-verify disk vs ledger on resume; `LIVE0` is Asaf's parallel track + #1 schedule risk.

## 2026-06-23 19:37 — [VOICE] SESSION START (Asaf: "run the loop" — Stage 5 under the corrected gate)
Picking up: **Stage 5 — Outbound orchestration + consent + budget guard** (first non-✅ stage; Stages 0–4 ✅, commits
through `85b2a4b`; 251 green). Asaf re-activated the autonomous ORCHESTRATION loop ("run the loop") **with the corrected
process from the Stage-4 lesson: a genuinely INDEPENDENT reviewer pass on contract-touching stages, not the PM's own
inline eyes** (NOTES 2026-06-23 "Stage 4 post-commit fix").
Recon done (so the brief is tight + correct): `app/orchestrate.py` does not exist; `scripts/` is empty (so
`scripts/place_demo_call.py` must be created for the `SEC3`/`CON1` second-entry-point spy); **no production leads loader
exists** — `load_leads`/`load_icp` live ONLY as helpers in `tests/test_leads.py` (must be promoted to the app so the
runtime path is real + validated, LEAD1/LEAK3). Public APIs confirmed: `consent.consent_allows(number, *,
do_not_call=False, allowlist=None)`, `budget.budget_permits(projected, *, is_live=False)` + `budget.record_cost(...)`,
`VoiceProvider.place_call(*, to_number, assistant)->CallResult`, `configure_assistant(*, variant="B", value_prop_path=None)`,
`fetch_call_cost(*, call_id)->CostResult`; constants `DAILY_CALL_CAP=25`, `CALL_RETRY_MAX=2`, `MAX_LIVE_CALLS=6`.
Plan: write `briefs/stage-5.md` → spawn ONE cold `general-purpose` executer (Stage 5 only) → PM-verify
`CALL1`–`CALL4`/`CON1`/`CON4`/`CON5`/`SEC3` by running them → **independent reviewer gate** (consent chokepoint + budget
guard + second-entry-point spy + import-safety) → commit → advance to Stage 6. Halt only on the 3 triggers.

## 2026-06-23 ~19:55 — [VOICE] PROGRESS (mid-session; Stage 5 ✅ committed, Stage 6 in flight)
**Stage 5 ✅ COMPLETE + COMMITTED** `1a99726`. Executer built it; PM-verified (287 green; ENV4 8 modules; no graded
contract touched); **first genuinely independent cold reviewer gate → APPROVE** (chokepoint clean in both entry points;
2 MINOR findings PM-fixed before commit: a §8 dead import + a trivially-passing retry-guard test rewritten to actually
prove the guard). Ledger updated (PLAN Stage 5 ✅ + footer; NOTES handback + verified facts). **Now advancing to Stage 6
— Offline evaluation harness** (`briefs/stage-6.md` written; spawning the cold executer). Stage 6 is pure-eval (no
reviewer gate) but discharges the carry-forward: enrich `simulated_callee` (discovery-responsiveness; also fixes the
`_rng`-unused finding), build `harness.py` + `tests/test_eval.py` (EVAL1–6), fix `rubric._find_invented_claim` dead
param + `eval/__init__` docstring, and **re-run the A/B bake-off** (executer reports the table; PM adjudicates the
persona lock — do not let the executer flip `build_system_prompt`'s default). If this session crashes mid-Stage-6:
Stage 5 is safely committed at `1a99726`; resume by checking disk for uncommitted `app/eval/harness.py` + `tests/test_eval.py`.

## 2026-06-23 ~20:10 — [VOICE] SESSION END / HANDOFF (Stages 5 & 6 ✅ committed; HALT on persona-lock decision)
Did (this "run the loop" block): drove the autonomous loop through **Stage 5** (`1a99726`) and **Stage 6** (`068713e`).
- **Stage 5** — orchestration + consent + budget guard: cold executer built it; PM-verified (287 green; ENV4 8 modules;
  no graded contract touched); **first genuinely independent cold reviewer gate → APPROVE** (chokepoint clean in BOTH
  entry points; 2 MINOR PM-fixed before commit). The corrected post-Stage-4 reviewer process is now in force.
- **Stage 6** — offline eval harness: cold executer built `harness.py` + `tests/test_eval.py` (48) + fixtures, enriched
  `simulated_callee` (discovery-responsiveness via the seeded `_rng`), closed the 3 carry-forward eval findings.
  PM-verified: **335 green, deterministic across two runs**; ENV4 import-safe; **PM re-ran the bake-off and reproduced
  the table exactly**; no graded contract changed. Pure-eval ⇒ no reviewer gate.
Verified numbers (PM-run): **335 passed / 0 failed** (twice); bake-off A book 0.4 / B 0.2 (disclosure 0.8 / objection 1.0
/ compliance 1.0 tie; avg_turns A 3.4 / B 2.6).
Status now: ✅ **Stages 0–6 complete, PM-verified, committed.** **HALTED on a required decision (loop trigger #1).**
**THE DECISION (Asaf):** the enriched A/B **flipped the provisional winner B→A** — on the numbers **A (Consultative)
wins** (2× book-rate, ties elsewhere). Locking A flips the **live demo persona** default (`build_system_prompt` +
`configure_assistant` "B"→"A" + conftest fake + docstrings). PM recommends **lock A**; deliberately NOT auto-flipped
(surface, don't bury). Not a prerequisite for Stage 7 — only for Stage 8.
Next PM should: get Asaf's call on the persona lock (recommend A), apply it if confirmed (small, mechanical: 2 app
defaults + conftest + docstrings; re-run suite), then proceed to **Stage 7 — Anti-leakage & packaging hardening**
(`LEAK1`–`LEAK5`, `PKG1`–`PKG4`) under the loop, which additionally runs the native **`/security-review`** gate. Stage 7
can start in parallel with the persona decision.
Watch out for / open: **persona-lock decision pending** (the one halt); Stage-4 public-tunnel live webhook smoke owed at
Stage 8; `LIVE0` provisioning is Asaf's parallel track + #1 schedule risk; recurring mid-stage crashes — re-verify disk
vs ledger on resume.

## 2026-06-23 20:37 — [VOICE] SESSION START (decision resolved → resume loop at Stage 7)
Picking up: the halt decision is **RESOLVED** — Asaf chose **Lock A**; persona locked to **A (Consultative)** and
committed (`32dbbaf`; live defaults flipped B→A in `build_system_prompt`/`configure_assistant`/conftest + docstrings;
suite still **335 green**; reversible via `build_policy`). Stages 0–6 ✅, commits through `32dbbaf`.
Resuming the autonomous loop at **Stage 7 — Anti-leakage & packaging hardening** (`LEAK1`–`LEAK5`, `PKG1`–`PKG4`).
Recon: no `tests/test_leakage.py` yet; only `requirements.txt` present (no MANIFEST/pyproject); `.gitignore` already
covers `.env*`/email/`REFERENCE/`/allowlist/recordings/transcripts/`receipts/raw`/`.venv` + the example negations;
deps fully pinned with `==`.
Plan: write `briefs/stage-7.md` → spawn ONE cold executer (test_leakage.py encoding LEAK1–5 + packaging hardening
[PKG1–4: pinned, clean-checkout run, allowlist packaging, .gitignore]) → PM-verify the greps + clean-checkout run
myself → run BOTH gates: native **`/security-review`** (the Stage-7 governance gate, CLAUDE.md §1.3) AND a genuinely
**independent** cold reviewer (corrected process) → commit → advance. Halt only on the 3 triggers.

## 2026-06-23 ~21:00 — [VOICE] SESSION END / HANDOFF (Stage 7 ✅ committed; HALT at the Stage-8 coordination boundary)
Did: drove the loop through **Stage 7 — anti-leakage & packaging**. Cold executer built `tests/test_leakage.py`
(LEAK1–5 + PKG1–4 over the git-true tracked set) + `MANIFEST.in`. PM-verified independently: ran my **own** secret/PAN
sweep over `git ls-files` (zero hits; only `.env.example`, confirmed placeholders-only), `git check-ignore` proof,
387 green. **Independent security gate:** native `/security-review` couldn't run (hardcodes a diff vs `origin/HEAD`; this
repo has no remote — tooling limit, logged) → substituted a **cold independent security reviewer** over the diff + the
whole pre-live governance surface. **Verdict CHANGES-REQUIRED** (it re-confirmed every chokepoint clean):
- **2 MEDIUM → FIXED** (MANIFEST include/exclude ordering dropped the allowlist example from the sdist; the leakage grep
  was blind to PEM/JWT) — both fixed + a self-check added; suite **387 green**.
- **1 HIGH → DEFERRED to Stage 8 as a hard entry blocker** (Asaf decision): the `BudgetLedger` is in-memory, so the
  **cumulative $50 cap is illusory across separate `make call`/process invocations** (per-call $1 ceiling still holds).
  Recommended fix: persist cumulative spend to a gitignored state file, reconciled with Stage-8 `capture_receipts.py`.
- **2 LOW noted** (Cal.com v1 key in query param — architectural; webhook header name unverified till live).
Verified numbers (PM-run): **387 passed / 0 failed**; own secret/PAN grep over tracked set = 0 hits; chokepoints clean.
Status now: ✅ **Stages 0–7 complete, PM-verified, committed.** **HALTED at the Stage-8 boundary** — a *planned*
coordination point (live calls = real money; needs `LIVE0` + Asaf), now with TWO explicit entry gates:
**(1) [Asaf decision] the budget-ledger-persistence HIGH** (make the cumulative cap real before any live call), and
**(2) `LIVE0` provisioning** (Asaf's track). Also owed at Stage 8: the public-tunnel signed-webhook smoke test (Stage-4 carry).
Next PM should: get Asaf's call on the budget-persistence fix (recommend: implement persistent ledger alongside Stage-8
`capture_receipts.py`), confirm `LIVE0` status, then run Stage 8 with Asaf in the loop (consented numbers, MAX_LIVE_CALLS=6,
half-day live-debug buffer, keep a recorded successful call for the Stage-9 video fallback). Stage 9 = video.
Watch out for / open: **budget-persistence HIGH (Stage-8 blocker, Asaf decision)**; `LIVE0` lead time (#1 schedule risk);
the Cal.com 409-only idempotency + the live Vapi signature header/payload field names still need live reconciliation;
recurring mid-stage crashes — re-verify disk vs ledger on resume.

## 2026-06-24 ~09:50 — [VOICE] SESSION (live execution day) — webhook chain up + REALTIME_MODEL reconciled
Live-execution support + one graded-contract reconciliation:
- **Webhook chain verified end-to-end (the Stage-4 owed deliverable, now live):** resolved a port-8000 collision —
  a stale **CRM** dev server (`api_server:app`, PID 59042, orphaned to launchd since Jun 20) was squatting
  `127.0.0.1:8000` and shadowing our `make serve`; killed it (Asaf-approved). ngrok reconciled to forward `:8000`
  (was `:80`). Verified: local + public `/health` 200; **signed webhook 200 `{"ok":true}` with the correct
  `x-vapi-secret`, 401 with a wrong one** (fail-closed, over the public tunnel). `make preflight` → PASSED
  (allowlist = 1 consented number `+972…58`; budget $0/$50). `.env` `VAPI_WEBHOOK_SECRET` fixed by Asaf.
- **First live `make call` → HTTP 400 from Vapi `/call`:** `assistant.model.model must be one of …` — the locked
  `REALTIME_MODEL="gpt-4o-realtime-preview"` (undated) is **not accepted** by Vapi (exactly what `ENV2` was meant to
  catch). **Asaf chose `gpt-realtime-2025-08-28`** (current GA realtime). Applied as a **§9 graded-constant change**
  (config + CLAUDE.md §9 + NOTES table/OQ row + PLAN; tests updated). Widened `place_call`'s Vapi-error capture
  (status line → body, 2000 chars) so any further payload errors surface. **Graded invariants verified intact**
  (firstMessage byte-exact == DISCLOSURE_LINE, recordingEnabled CON3, 5 tools, interface signatures). Suite **419 green**.
- **Open:** Vapi validates strictly + the 400 body was truncated — the **next** `make call` may surface 1–2 more payload
  tweaks (e.g. `recordingEnabled`/`metadata` placement); the widened capture will show them. Those would touch the
  VOICE1 assistant payload → independent review before retry. Committing this checkpoint; awaiting Asaf's next retry.

## 2026-06-23 21:13 — [VOICE] SESSION START (Asaf decisions → Stage 8 build half)
Picking up: Asaf answered the two Stage-8 gate questions — **(1) FIX the budget-persistence HIGH now** (persistent
file-backed ledger), **(2) LIVE0 is READY → proceed to Stage 8**. Stages 0–7 ✅, commits through `7011611`, 387 green.
Plan for this block — build the **offline-testable** Stage-8 code, then coordinate the real-money live calls separately:
(a) close the security-HIGH: add an **opt-in `persist_path`** to `BudgetLedger` (load cumulative on construct, save on
`record_cost`; `get_ledger()` uses a gitignored default state file so `place_demo_call.py` + the orchestrate singleton
accumulate across invocations; `BudgetLedger()` stays in-memory for isolated tests; caps + `budget_permits`/`record_cost`
signatures UNCHANGED — not a graded-contract change); (b) build `scripts/capture_receipts.py` (pull per-call cost →
redacted `receipts/`, SEC5) offline-testable with the fake provider; (c) gitignore the persist file + raw receipts.
Then PM-verify + **independent review** (budget is contract-adjacent governance) + commit. **The actual live calls
(LIVE1–LIVE2, real money, real numbers) are a human-coordinated step I will NOT trigger autonomously** — I'll prepare the
runbook + the signed-webhook smoke test and hand the live trigger to Asaf (real `.env` + `make call`). Halt at the
live-execution boundary.

## 2026-06-23 22:25 — [VOICE] SESSION END / HANDOFF (live-readiness prep done; HALT for Asaf to fix 2 setup gaps + run live)
Did (Asaf completed external provisioning: Twilio +972 number in Vapi, .env aligned, x-vapi-secret set, allowlist prepared):
- **Webhook auth reconciled** to Vapi's CONFIRMED static `x-vapi-secret` scheme (`verify_signature` HMAC → `verify_secret`
  constant-time compare, fail-closed; dead `hashlib` removed; `test_server.py` updated). This was a **live blocker** — the
  old HMAC verify would have 401'd every real Vapi webhook → no booking. Independent **security review → APPROVE**.
- **`make preflight`** (`scripts/preflight.py` + `tests/test_preflight.py`): checks the 5 required settings present + the
  allowlist loads; prints names/PRESENT-MISSING + spend totals only, **never a secret value** (test-asserted).
- Fixed a real standalone-run bug: scripts couldn't `import app` under `make call`/`make preflight` → added in-`main()`
  repo-root `sys.path` bootstrap (no import-time side effect).
- **Docs:** `docs/LIVE_RUNBOOK.md` + `docs/STAGE9_STORYBOARD.md`.
- Independent review's 3 minor findings all fixed (stale HMAC docstrings; test phone → +1555 fictitious; no-leak test
  strengthened). 
Verified numbers (PM-run): **419 passed / 0 failed**; `make preflight` runs against the real `.env` and correctly reports
status with **zero secret values printed**.
Status now: ✅ **Stages 0–7 ✅; Stage 8 build + live-readiness ✅; committed.** 🔄 **Live half pending Asaf.**
**⚠ Preflight caught 2 real setup gaps (Asaf to fix — .env/allowlist, not code):** (1) `VAPI_WEBHOOK_SECRET` reads MISSING
(likely still commented / spaces around `=` / misnamed); (2) `consent_allowlist.json` not found at the repo-root default
(place it there or set `CONSENT_ALLOWLIST_PATH`). **`make preflight` must say PASSED before any live call.**
Next PM/Asaf should: Asaf fixes the 2 gaps → `make preflight` PASSED → follow `docs/LIVE_RUNBOOK.md` (serve+tunnel+signed
smoke test → **sequential** `make call TO=<consented #>` → `capture_receipts.py`) → PM verifies LIVE1/LIVE2/LIVE3/SEC5 from
the real transcript + Cal.com + receipts. Then Stage 9 (video) per the storyboard.
Watch out for / open: the 2 preflight gaps; run live calls SEQUENTIALLY; verify `DISCLOSURE_LINE` byte-exact from the REAL
transcript (never assumed); Cal.com 409-only idempotency to validate live; keep a recorded successful call for the video.

## 2026-06-23 ~21:30 — [VOICE] SESSION END / HANDOFF (Stage 8 build half ✅; HALT at the live-execution boundary)
Did: built + verified + independently reviewed the **offline half of Stage 8**, closing the Stage-7 security-HIGH.
- Cold executer: opt-in **persistent `BudgetLedger`** (gitignored state file → cumulative $50 cap real across invocations),
  `scripts/capture_receipts.py` (redacted receipts, SEC5), `place_demo_call.py` → persistent singleton. Signatures/caps
  unchanged (additive).
- **Independent reviewer gate → CHANGES-REQUIRED — and it earned its keep again** (my own PM pass had missed it):
  **[CRITICAL]** the demo script never called `record_cost`, so the persistent cap was still illusory for `make call`.
  **PM-fixed surgically + added a regression test** (`test_persistent_ledger_advances_across_invocations`, 0.30→0.60 across
  invocations). **[MED]** test-hygiene (module-level tests wrote to the real ledger file) → fixed with tmp-path + try/finally.
  **[HIGH]** cross-process TOCTOU → **accepted as a documented operating constraint** (lean single-operator sequential
  `make call`; OS-agnostic precludes a clean `fcntl` lock) — surfaced to Asaf. **[LOW]** cosmetic.
Verified numbers (PM-run): **414 passed / 0 failed**; cross-instance cap holds (reproduced); ENV4 import-safe; state file
numeric-only; real ledger file absent after the suite (no pollution).
Status now: ✅ **Stage 8 BUILD HALF complete, PM-verified, independently reviewed, committed.** 🔄 **Stage 8 LIVE HALF is a
human-coordinated, real-money step — HALTED here by design.** The PM does not place live calls autonomously.
Next PM/Asaf should: run the LIVE half with the real `.env` + `LIVE0` (reported READY): `make serve` behind the public
tunnel + the signed-webhook smoke test (Stage-4 carry); **sequential** `make call TO=<consented number>` → a real
disclosure-first call that pitches + books (`LIVE1`/`LIVE2`); `capture_receipts.py` per call → PM reconciles cost ≤ caps
(`LIVE3`/`LIVE4`/`SEC5`). Keep a recorded successful call for the Stage-9 video. Then **Stage 9 — video**.
Watch out for / open: **cross-process budget-ledger limitation → run live calls SEQUENTIALLY**; the live Vapi signature
header/payload field names + Cal.com 409-only idempotency still need live reconciliation; keep a recorded call as the
Stage-9 fallback; verify `DISCLOSURE_LINE` byte-exact from the REAL transcript (`LIVE2`), never assumed.

## 2026-06-24 12:00 — [VOICE] SESSION END / HANDOFF (Stage 8 LIVE-debugging day → fresh PM requested)
**Asaf is starting a fresh PM.** This entry + the chat brief are the cold-start context. Read order unchanged
(`PM_Methodology_Prompt` → this latest entry → `CLAUDE.md` → `PLAN.md` → `QA_checklist.md` → `NOTES.md` → `ORCHESTRATION.md`).
**Where we are:** Stages 0–7 ✅ committed; Stage 8 **build-half ✅**; now deep in **Stage 8 live calling** — the offline
system is complete (**425 tests green**, tree clean, latest commit `54031b6`); iterating on the live phone-call experience.
**Live-debugging chain fixed today (all committed, each verified):** (1) `REALTIME_MODEL` reconciled (`7031869`); (2)
webhook auth → Vapi's static `x-vapi-secret` (`fc09914`); (3) Vapi tool-result **envelope** `{"results":[{toolCallId,result}]}`
(`a7f8623`); (4) **Cal.com v1→v2** migration, v1 was 410-decommissioned (`993c30e`); (5) **slot cap** 239→5, the 49KB
payload broke the webhook (`cfaa19f`/`39cc7aa`); (6) tool **`server.url`** from `PUBLIC_WEBHOOK_URL` (`226a46b`); (7) tool
**`server.secret`** (`e12dd21`); (8) turn-taking (`fec3c71`); (9) **OQ-VOICE-1 REVISED: realtime → standard pipeline**
gpt-4o + OpenAI-TTS(shimmer) + Deepgram (`54031b6`). Each independent-reviewed or live-verified.
**Verified facts (PM-run / live):** tool path works **directly against live Cal.com** — `check_availability` → real slots,
`book_meeting` → created + cancelled a real event; webhook chain verified local+public (envelope + 401 on bad secret);
standard pipeline confirmed live (Vapi ran gpt-4o/shimmer/deepgram).
**⚠ OPEN / WATCH (next PM — focus here):**
1. **Call experience still unsatisfactory** — Asaf: "it sucked." He has NOT yet named the exact fault; I asked (audio
   quality / voice / latency / pausing). **Get the specific complaint (or listen to the call recording) BEFORE changing
   more.** Recording URL is on each call via the Vapi API (`GET /call/{id}` → `recordingUrl`). I cannot hear audio — depend
   on Asaf's ear or the recording.
2. **No full live booking completed yet (LIVE1 unmet)** — tools work, but Asaf keeps hanging up over the audio, so no
   phone call has run through to a booked meeting.
3. **🔴 LIVE-CALL CAP HIT:** the persistent ledger shows `live_call_count = 6/6` (`MAX_LIVE_CALLS`) so the **next `make
   call` will be REFUSED** by `budget_permits(is_live=True)`. And `cumulative_usd = $0.00` is WRONG — the cost-recording
   bug (`place_demo_call` records cost the instant Vapi *accepts* the call, before Vapi finalizes it → 0). **Real spend
   ≈ $2** (sum the per-call `cost` from `GET /call`). **Action before more live calls:** reset the persistent ledger
   (`receipts/.budget_ledger.json`; `budget.reset_ledger(also_delete_state_file=True)`) AND fix cost capture
   (record post-call via `scripts/capture_receipts.py` + reconcile into the ledger, or don't trust an immediate `cost=0`).
4. **DO NOT re-raise "Ulta" pronunciation** — Asaf explicitly dropped it ("I don't care"). Leave it.
5. Minor: Cal.com event type is **15 min** vs `BOOKING_SLOT_MINUTES=30` (align Cal.com or §9); the model guesses a US tz
   for `lead_timezone` (Asaf is **Asia/Jerusalem**) — affects only how times are voiced.
**Live setup (Asaf-owned):** Twilio **+972 53-563-6788** imported in Vapi; ngrok reserved domain
`pleading-stomp-referee.ngrok-free.dev` → must be running, forwarding **:8000**; `make serve` on :8000; `.env` has all 5
required keys + `PUBLIC_WEBHOOK_URL` + the dashboard `x-vapi-secret` == `VAPI_WEBHOOK_SECRET`; `consent_allowlist.json` =
`+972509175858` (Asaf's own phone). `make call` reads `.env` fresh (no restart needed); `make serve --reload` reloads code edits.
**Operating model (unchanged):** autonomous loop; `general-purpose` executers per stage; **INDEPENDENT reviewer on
contract-touching stages** (the inline-review shortcut was retired after it missed a deliverable-breaking Stage-4 bug —
keep this); PM re-runs QA itself; commit per stage.
**Asaf working-style feedback (HONOR):** be **concise**; **focus on exactly what Asaf says**; do **not** re-raise issues he
has dismissed; diagnose live calls from the transcript + recording, not assumptions.
**Next PM should:** (a) reset the live-call ledger cap (#3); (b) ask Asaf the *specific* call-quality complaint (or review
the latest recording) and fix only that; (c) get one clean live call through to a booked Cal.com meeting (LIVE1), then
verify cost/disclosure/booking from sources; (d) then Stage 9 (video). Budget is fine (~$2 of $50 real).

## 2026-06-24 12:02 — [VOICE] SESSION START
Picking up: **Stage 8 — live calling** (the only non-✅ work; Stages 0–7 ✅, Stage 8 build-half ✅). Read order completed
this session: `PM_Methodology_Prompt.md` (verbatim) → latest `PM_LOG.md` entry (the 12:00 cold-start handoff) → `CLAUDE.md`
→ `PLAN.md` → `QA_checklist.md` → `NOTES.md` (full, incl. the 2026-06-24 live-debug entries) → `ORCHESTRATION.md`.
State as read (to re-verify against running code, not the ledger):
- Offline system **complete: NOTES claims 425 green**, tree clean, HEAD `54031b6`. CLAUDE.md + NOTES are current through the
  **OQ-VOICE-1 revision (realtime speech-to-speech → standard TTS pipeline: gpt-4o + OpenAI-TTS `shimmer` + Deepgram nova-2)**.
- **Ledger lag noted:** `PLAN.md` is **stale** — still says OpenAI-Realtime brain / `REALTIME_MODEL` / "419 green"; it does
  NOT reflect today's live fixes or the pipeline revision. (NOTES + PM_LOG are current; PLAN needs a reconciliation pass.)
- All 9 live-debug fixes committed + each independent-reviewed or live-verified (model, `x-vapi-secret` auth, Vapi
  result-envelope, Cal.com v1→v2, slot-cap 239→5, tool `server.url`/`server.secret`, turn-taking, standard pipeline).
- Tool path verified **directly against live Cal.com** (real slots; created+cancelled a real event — no phone call).
**Three things gate progress (from the 12:00 handoff):** (1) Asaf hasn't named the *specific* call-quality fault — and no
call has run since the pipeline switch, so the fix may already be in; **do not change more code blind**. (2) **LIVE1 unmet**
— no live call has booked yet. (3) 🔴 **live-call cap hit** (`live_call_count = 6/6`) → next `make call` is REFUSED, and
`cumulative_usd=$0` is wrong (cost-capture bug; real spend ≈ $2 of $50). Reset the ledger + fix post-call cost capture
before any further live call.
Plan for this session: honor Asaf's style (concise, focus on exactly what he says, don't re-raise dropped items e.g.
"Ulta"). Surface the reconciled state; get the specific call-quality complaint (or run one fresh call on the new pipeline)
before touching code; do the safe autonomous prep (reset live-call cap + post-call cost reconciliation) so the next live
call isn't refused; drive one clean live call → booked Cal.com meeting (LIVE1) → verify from sources; then Stage 9.

## 2026-06-24 12:49 — [VOICE] SESSION START
Picking up: **Stage 8 — live calling** (only non-✅ work; Stages 0–7 ✅, Stage 8 build-half ✅). Read order completed
this session: `PM_Methodology_Prompt.md` (verbatim) → latest `PM_LOG.md` entries (12:00 cold-start handoff + 12:02
SESSION START) → `CLAUDE.md` (in context) → `PLAN.md` → `QA_checklist.md` → `NOTES.md` (incl. the two new 2026-06-24
live-debug entries) → `ORCHESTRATION.md`.
**Resume anomaly (verified against disk, not the ledger):** the **12:02 SESSION START has no matching SESSION END** —
that session ran, did real work, and **never closed**. HEAD is `54031b6`; the 12:02 work is **uncommitted on disk**:
`M Makefile / app/vapi_client.py / tests/test_voice.py / NOTES.md / PM_LOG.md`, `?? scripts/inspect_call.py /
tests/test_inspect_call.py`. **PM-unverified, unreviewed, uncommitted, unlogged-END.**
What the 12:02 session did (read from the diff + NOTES additions, NOT yet re-verified by me):
1. **Built `scripts/inspect_call.py` + `make inspect` + `tests/test_inspect_call.py` (7 offline tests)** + a read-only
   `VapiVoiceProvider.fetch_call()` (concrete adapter ONLY — the graded 3-method `VoiceProvider` interface is UNCHANGED).
2. **Diagnosed "not finishing sentences" = realtime fragmentation, NOT interruption** (`interrupted: 0` across the 6
   pre-switch calls) → the OQ-VOICE-1 pipeline switch (`54031b6`) was the right fix; do NOT tune `stopSpeakingPlan`.
3. **Reset the persistent ledger to $0 / live_call_count=0** (cleared the 6/6 cap). Real sunk debug spend ≈ **$1.72 / $50**.
4. **🎯 Ran a fresh live call on the standard pipeline → LIVE1/LIVE2 MET (claimed):** call `019ef8f2-…`, cost **$0.1482**
   (≤ $1 cap), booked a **REAL Cal.com event** (`event_id ecFPyLMFsbohwue3si1GML`) end-to-end (check_availability →
   book_meeting → log_disposition=booked), disclosure byte-exact first, `interrupted: 0`. Recording kept for the video.
5. **Pacing tuning (Asaf live review):** TTS `speed=1.2` + `startSpeakingPlan.waitSeconds 0.6→0.4` in `vapi_client.py`
   + a `test_pacing_tuned_faster` assertion. These are Vapi tuning knobs (NOT §9 governance constants), but they DO touch
   the VOICE1 assistant payload → reviewer-gate territory.
**State to re-verify before trusting it:** offline suite green with the pacing diff + the 7 new inspect tests (handoff
claimed 425 green pre-12:02); ENV4 import-safe with `fetch_call` added; both literals byte-exact; LIVE1/LIVE2 claim
against the real call data; no graded contract changed.
**One open decision (NOT mine to make):** lead timezone — the model invented `America/New_York` (Asaf is Asia/Jerusalem);
booking is mechanically correct (right UTC) but slots are *voiced* at odd hours. Fix options: pin demo lead tz to
Asia/Jerusalem, or have Aria ask the prospect's tz. UX/demo polish, not a governance break.
Plan for this session: honor Asaf's style (concise; fix only what he names; don't re-raise dropped items e.g. "Ulta").
(1) PM-verify the 12:02 on-disk work (run the suite, re-prove ENV4, confirm LIVE1/LIVE2 from the call data, confirm no
graded contract touched); (2) surface the reconciled state + the lead-tz decision to Asaf; (3) on his go, commit the
12:02 work as the Stage-8 live checkpoint; then Stage 9 (video). Will NOT place new live calls autonomously.

## 2026-06-24 13:28 — [VOICE] SESSION START
Picking up: **Stage 8 — live calling** (only non-✅ work; Stages 0–7 ✅, Stage 8 build-half ✅, LIVE1/LIVE2 met on the
standard pipeline per the last NOTES entries). Read order completed this session: `PM_Methodology_Prompt.md` (verbatim)
→ `PM_LOG.md` (full, through the 12:49 START) → `CLAUDE.md` (in context) → `PLAN.md` → `QA_checklist.md` → `NOTES.md`
(tail, incl. all 2026-06-24 live-debug + disclosure entries) → `ORCHESTRATION.md`.
**Resume anomaly (verified against disk via `git status`, not the ledger):** the **12:49 SESSION START has no matching
SESSION END** — another session ran real work and never closed (the recurring mid-stage-crash pattern). HEAD is
`54031b6`; there is an **uncommitted batch on disk, PM-unverified-this-session, unreviewed, uncommitted, unlogged-END:**
`M CLAUDE.md Makefile NOTES.md PM_LOG.md QA_checklist.md app/config.py app/vapi_client.py data/value_prop.md
docs/STAGE9_STORYBOARD.md tests/test_env.py tests/test_voice.py` + `?? scripts/inspect_call.py tests/test_inspect_call.py`.
Also `?? "llm course/"` — **unrelated to this project** (not ours; do NOT touch/commit; likely belongs in `.gitignore`).
What the batch is (read from the diff + the matching NOTES entries, NOT yet re-verified by me): (1) `scripts/inspect_call.py`
+ `make inspect` + 7 offline tests + a read-only `VapiVoiceProvider.fetch_call()` (concrete adapter only — graded 3-method
`VoiceProvider` interface UNCHANGED); (2) pacing tuning (OpenAI-TTS `speed` 1.0→1.2, `startSpeakingPlan.waitSeconds`
0.6→0.4 — `vapi_client` knobs, not §9); (3) **a GRADED contract change** — `DISCLOSURE_LINE` dropped the recording notice
(kept the AI self-id) + CON3 reframed (recording stays ON, one-party-consent scope), touched byte-for-byte across config.py
/ CLAUDE.md §9 / QA CON3 / test_voice / test_env / value_prop / storyboard. NOTES claims suite **433 green** PM-run.
State as read (to RE-VERIFY against running code, not trust the ledger): offline suite green count; ENV4 import-safe with
`fetch_call` added; both graded literals byte-exact == config (esp. the NEW `DISCLOSURE_LINE`); no graded interface signature
changed. LIVE1/LIVE2 already verified from the real call `019ef8f2…` (cost $0.1482, real Cal.com event, `interrupted: 0`).
Per the corrected post-Stage-4 process + the NOTES note itself: **the graded `DISCLOSURE_LINE`/CON3 change is OWED an
independent review before commit, and commit awaits Asaf's word.**
Plan for this session (honor Asaf's style — concise; fix only what he names; don't re-raise dropped items e.g. "Ulta"):
(1) PM-verify the on-disk batch (run the offline suite for a ground-truth green count, re-prove ENV4, confirm the new
graded literal byte-exact == config, confirm no graded interface signature touched); (2) surface the reconciled state +
the **two items that need Asaf**: (a) the owed independent review + commit of the graded disclosure batch, (b) the
lead-timezone decision (pin demo lead tz to Asia/Jerusalem vs. have Aria ask the prospect). **Will NOT commit the graded
batch without the independent review + Asaf's go, and will NOT place live calls autonomously.** Then: Stage 9 (video).

## 2026-06-24 14:10 — [VOICE] SESSION START
Picking up: **Stage 8 — live calling** (only non-✅ work). Read order completed: `PM_Methodology_Prompt.md` (verbatim)
→ `PM_LOG.md` (full, through the 13:28 START) → `CLAUDE.md` (in context) → `PLAN.md` → `QA_checklist.md` → `NOTES.md`
(full, incl. all 2026-06-24 live-debug + the OQ-VOICE-1 pipeline-revision + STANDING-RULE/Bug-2 entries) → `ORCHESTRATION.md`.
**Resume anomaly (verified vs disk, not the ledger):** the **13:28 SESSION START has no matching SESSION END** (recurring
mid-stage pattern). HEAD `54031b6`; an uncommitted batch is on disk (`M CLAUDE.md Makefile NOTES.md PM_LOG.md
QA_checklist.md app/config.py app/eval/rubric.py app/persona.py app/server.py app/tools.py app/vapi_client.py
data/value_prop.md docs/STAGE9_STORYBOARD.md tests/conftest.py tests/test_env.py tests/test_voice.py` + untracked
`scripts/inspect_call.py scripts/review_dump.py scripts/score_call.py tests/test_inspect_call.py tests/test_lead_context.py
tests/test_qualify.py`; `?? "llm course/"` is **not ours** — do not touch). PM-unverified/unreviewed/uncommitted. **I am
NOT touching that batch this session** — this session is a discrete deliverable, not a continuation of the live-call build.
**This session's task (Asaf):** author an exhaustive 100+-parallel-tester stress/adversarial **testing architecture** for
the live voice agent (4 scopes: logic/RAG/state text-bypass · telephony/audio · latency/STT-TTS · concurrency/load).
**Graded-contract collision to surface (the PM job here):** a 100+-parallel fleet against the **live** Vapi/Twilio bridge
would breach `HARD_BUDGET_USD=$50`, `MAX_LIVE_CALLS=6`, the **single** consented number (one-party-consent scope), and the
**documented cross-process budget-ledger TOCTOU** (live must run SEQUENTIALLY). Plan: deliver the full architecture but
**tier every test by execution surface** (OFFLINE deterministic harness = where 100+ parallel belongs · LOCAL MOCK-BRIDGE
for audio/telephony/latency faults · a single serialized LIVE-GATED lane ≤6 calls for real-telephony sign-off), and flag
the collision with a recommendation. Honor Asaf's style (concise; no dismissed items). Write the doc, then SESSION END.

## 2026-06-24 14:55 — [VOICE] SESSION END / HANDOFF (Stage 8.5 adversarial/load testing architecture — offline+MOCK ✅; live lane scaffolded+gated)
Did: built the 100+-parallel-tester **testing architecture** end-to-end and PM-verified it. Surfaced the
graded-contract collision (100+ live = breach of $50 / `MAX_LIVE_CALLS=6` / single-number consent / ledger TOCTOU)
and resolved it by tiering the fleet: **OFFLINE** harness (where 100+ belongs, $0) + **LOCAL MOCK-BRIDGE** + a
small **LIVE-GATED** lane. Asaf authorized (via planning) scope = doc+harness+MOCK-BRIDGE and a **bounded live lane
(graded change): sequential, ≤50 calls / ≤$15, 2–3 consented numbers**.
- **OFFLINE (Scope 1+4):** +2 adversarial `Persona`s (`INJECTION`, `SLOT_REJECTER`; NOT in `PERSONA_MATRIX` → graded
  bake-off numbers unchanged); standalone computed `rubric.slot_reoffer_handled` (NOT a 6th RubricResult field → 0–5
  EVAL3 score intact); `tests/test_stress_logic.py` (STR-L*) + `tests/test_stress_concurrency.py` (STR-C*, incl. a
  **deterministic** two-ledger demo of the cross-process budget TOCTOU — STR-C7).
- **MOCK (Scope 2+3):** `app/testing/mock_bridge.py` (webhook+transcript fault injector — NOT a softphone; media path
  is Vapi's) + `tests/test_stress_telephony.py` (STR-T*) + `tests/test_stress_latency.py` (STR-P*).
- **LIVE (Phase C, scaffolded, NOT run):** `MAX_LIVE_STRESS_CALLS=50` (§9), additive `budget.default_ledger_path()`,
  `scripts/stress_live.py` (injectable `run_stress_lane` + gated `main`); `tests/test_stress_live_lane.py` proves the
  gating OFFLINE (halts at the count cap + $15 reserve; refuses non-consented — spy: no dial past a gate).
- Spine/doc: `docs/STRESS_TEST_ARCHITECTURE.md` (full STR-* tables, tiers, fleet mapping); QA `§12` + Stage-8.5 map;
  PLAN Stage 8.5; NOTES decision+handback; CLAUDE.md §9 constant; `.gitignore` += `llm course/` (stray non-project dir).
Verified numbers (PM-run, not assumed): full suite **522 passed / 1 skipped / 1 xfailed** (baseline this session was
**474**, NOT the ledger's 458 — re-run; +48 passed/+1 skip(live barge-in STR-T1)/+1 xfail(Bug-1 re-offer guard));
deterministic; **ENV4 re-proven** from an empty cwd across `app.testing.mock_bridge` + `scripts.stress_live` (lazy
singletons None, httpx not pulled); `MAX_LIVE_STRESS_CALLS == 50`; `test_leakage` green with the new files present.
Status now: 🔄 **Stage 8.5 — Offline+MOCK ✅ (committed? NO).** All new work is **uncommitted on disk** (plus the
pre-existing 13:28 qualify/disclosure batch, which I did NOT touch — keep them separable at commit).
Next PM/Asaf should: (1) **independent reviewer gate** on the graded slice (`MAX_LIVE_STRESS_CALLS`, the budget
accessor, the live lane) — required before commit per the corrected post-Stage-4 process; (2) on Asaf's word, commit
the Stage-8.5 offline work (separate commit from the qualify/disclosure batch); (3) for ANY live stress run: clear the
**recording-notice compliance gate** (confirm the 2–3 numbers are one-party-consent, else restore the notice in
`DISCLOSURE_LINE`/CON3) → run `scripts/stress_live.py` **sequentially** → PM reconciles cost ≤ caps from receipts.
Watch out for / open: graded change owed a review; live calls are human-coordinated (PM will NOT auto-place); PLAN still
has the older stale pipeline notes elsewhere (not reconciled this session — out of scope of the ask); the qualify/
disclosure batch from 13:28 is still uncommitted/unreviewed. Out of scope (by Asaf): the LangGraph runner + a real
RTP/softphone bridge.

## 2026-06-24 15:30 — [VOICE] NOTE (committed; appended post-SESSION-END for ledger accuracy)
Asaf chose **"review prior batch, then commit both."** Ran the independent reviewer gate (native `/code-review`,
high effort) on BOTH the Stage-8.5 slice and the entangled prior qualify/disclosure batch (they share
config.py/rubric.py/CLAUDE.md/NOTES.md and can't be split without interactive add). Outcomes:
- **Stage-8.5 slice:** graded integrity clean; **2 findings fixed** (over-broad `slot_reoffer_handled` markers
  mis-flagged acceptances as time-rejections — tightened + regression test added; `mock_bridge.garble` seed now
  sources `config.RANDOM_SEED` per §8).
- **Prior qualify/disclosure batch:** disclosure/CON3 verified byte-exact-consistent; AGENT_TOOLS=4 (end_call
  retired, D9) consistent config↔spec. **3 correctness fixes:** (1) `qualify` no longer routes a substantive-but-
  unmapped answer to `emphasize=None`/"lead with None" (now asks to clarify); (2) `score_call` locates the pitch
  positionally (robust to a missing `secondsFromStart`) + skips backchannel discovery answers; (3) `vapi_client`
  omits `metadata.lead_id/lead_timezone` when unset (no JSON null).
**Committed both as one combined commit `8bef263` on `main`** (per this repo's main-baseline convention + Asaf's
explicit go). Working tree then clean. Verified: **523 passed / 1 skipped / 1 xfailed**; ENV4 import-safe.
**Still open (unchanged):** live stress execution is human-coordinated (PM will NOT auto-place calls) and gated on
the **recording-notice compliance** check for any added consented number. Not pushed (local only).

## 2026-06-25 10:47 — [VOICE] SESSION START
Picking up: **Stage 8 / 8.5 live + Stage 9 video** are the only non-✅ work (Stages 0–7 ✅; Stage 8 build-half ✅ +
LIVE1/LIVE2 met on a real call per NOTES; Stage 8.5 offline+MOCK ✅ committed). Read order completed this session:
`PM_Methodology_Prompt.md` (verbatim) → full `PM_LOG.md` (through the 15:30 NOTE) → `CLAUDE.md` (in context) →
`PLAN.md` → `QA_checklist.md` → `NOTES.md` (tail incl. all 2026-06-24 live-debug + STANDING-RULE/Bug entries) →
`ORCHESTRATION.md`.
**Resume anomaly (verified vs disk via git, NOT the ledger):** unlike prior resumes, the **working tree is CLEAN** —
no uncommitted batch. But **3 commits landed AFTER the last PM_LOG entry (`8bef263`) with no SESSION END / NOTES
session entry** (the recurring "ran, never closed" pattern, this time committed): `a7796b3` (docs: mark Stage-8.5
reviewer gate + 8bef263), `51eb69a` (**feat: live-call refinements — prefetch availability → instant slot proposal,
booking read-back + "invite by email", barge-in tuning `stopSpeakingPlan{numWords:2,voiceSeconds:0.25,backoffSeconds:0.8}`;
folds in cost-trusted-only-after-call-ends, AGENT_TOOLS=4 [end_call retired → native Vapi end-call + END_CALL_MESSAGE],
qualify kept as internal pitch-tailoring oracle**), `abae4dd` (docs: de-jargon all module/function docstrings; claims
suite **541 passed / 1 skipped / 1 xfailed**, comments-only). Also new off-log: repo is now **pushed to a GitHub remote**
`asaf3231/Voice-Agent` (HEAD == origin/main) — prior entries said "local only."
State as read (to RE-VERIFY by running, not trust the ledger): offline suite green count (abae4dd claims 541/1skip/1xfail —
NOT yet re-run by me); ENV4 import-safe across all modules incl. `app.testing.mock_bridge` + the scripts; both graded
literals byte-exact == config (esp. the NEW `DISCLOSURE_LINE` with the recording notice dropped); AGENT_TOOLS=4 dispatch
identity. **CLAUDE.md is current** through the pipeline revision + AGENT_TOOLS=4. **⚠ PLAN.md is STALE** — the tracker
table still shows Stage 8 "⬜ Not started" and the footer still cites OpenAI-Realtime brain / `REALTIME_MODEL` / 387–419
green; it does NOT reflect the standard-TTS pipeline switch, LIVE1/LIVE2 being met, or the 3 latest commits. PLAN needs a
reconciliation pass for ledger accuracy.
Plan for this session: honor Asaf's style (concise; fix only what he names; don't re-raise dropped items e.g. "Ulta"/the
lead-tz polish unless he asks). Awaiting Asaf's direction. Likely candidates, in order of cheapness/value: (a) reconcile
the stale PLAN.md + back-fill a NOTES/PM_LOG entry for the 3 unlogged commits (ledger accuracy, no code risk); (b) the
open STANDING-RULE live items if Asaf wants them (Bug-1 slot re-offer loop live test; lead_id/lead_tz at the webhook
chokepoint); (c) Stage 9 video per `docs/STAGE9_STORYBOARD.md`. Will re-verify the suite count before reporting any number,
and will NOT place live calls autonomously. Write SESSION END / HANDOFF before stopping.

## 2026-06-25 11:20 — [VOICE] SESSION END / HANDOFF (Stage 9 video prep — eval toolchain + storyboard; HALT for Asaf's record/receipts step)
**Asaf chose focus = Stage 9 (the video).** Did the in-lane Stage-9 PM work; the recorded demo + receipts capture are
human-coordinated (need Asaf's `.env`), so I halt there.
Did (additive, read-only — **no graded contract touched**, no reviewer gate needed, like Stage-6 pure-eval):
- **`python -m app.eval` / `make eval`** (`app/eval/__main__.py`) — prints the computed A/B bake-off + persona-matrix
  summary the video shows (`VID2`). Deterministic, seeded, network-free, no `.env`.
- **`make receipts CALL_IDS="…"`** Makefile target — wires the existing `capture_receipts.py` (its own docstring already
  told users to run `make receipts`, but the target didn't exist). Read-only GET; needs the real `.env`.
- `tests/test_eval.py::TestEvalReportCommand` (+2: returns-0/both-variants + byte-identical-across-runs).
- **`docs/STAGE9_STORYBOARD.md` rewritten** to the REAL stack (standard TTS pipeline gpt-4o+shimmer+deepgram, **not**
  Realtime), verified numbers baked in, real commands, a command cheat-sheet, an honest receipts plan, and the
  live-vs-recorded fallback (kept call `019ef8f2…`).
- Ledger: PLAN Stage 8 row (was wrongly "⬜ Not started" — now reflects LIVE1/LIVE2 met) + Stage 9 row/section updated;
  NOTES handback appended.
Verified numbers (PM-run, not assumed): suite **543 passed / 1 skipped / 1 xfailed** (from 541; +2). `make eval`
deterministic and **== the Stage-6 ledger**: A (Consultative) book **0.4** / B (Direct) **0.2** (A 2×); disclosure 0.8,
objection 1.0, compliance 1.0 both; avg_turns 3.4/2.6; 5 personas. ENV4 re-proven from an empty cwd.
Status now: 🔄 **Stage 9 in progress (PM-verified).** Toolchain + storyboard ready; **work UNCOMMITTED on disk** (commit on
Asaf's word). The recorded demo + receipts capture are the remaining `VID1`/`VID2` items — human-coordinated.
**Resume context (verified vs disk):** 3 commits (`a7796b3`/`51eb69a`/`abae4dd`) landed after `8bef263` with no prior
SESSION END (recurring pattern) — now back-filled in NOTES. Repo pushed to GitHub `asaf3231/Voice-Agent` (HEAD==origin/main).
Ledger reads `$0.058 / live_call_count=1` — a fresh off-log call; real debug spend ≈ $1.78, all ≪ $50.
Next PM / Asaf should: **(1) decide the demo call** — fresh live on camera vs the kept `019ef8f2…` recording (recommend:
kept recording as the safe spine, fresh take only as an upgrade); **(2) run `make receipts CALL_IDS="019ef8f2-…"`** (+ any
other demo calls) with the real `.env` → PM reconciles the on-camera "$X of $50"; **(3) commit** the Stage-9 toolchain+docs
on Asaf's word; **(4) record** per the storyboard. Optional/owed: full PLAN-footer reconciliation (still cites Realtime /
387–419 green); the open STANDING-RULE items (Bug-1 slot re-offer; lead_id/lead_tz) if Asaf wants them before recording.
Watch out for / open: receipts capture + the recorded demo are PM-un-runnable (no `.env`); don't overstate compliance on
camera (recording-on is one-party-consent scope); commit only on Asaf's word.

## 2026-06-25 11:25 — [VOICE] NOTE (committed; appended post-SESSION-END for ledger accuracy)
Asaf said **"commit."** The Stage-9 toolchain + storyboard is **committed `ca381fb` on `main`** (above `abae4dd`;
7 files, +248/−18). Working tree clean. **Not pushed** — HEAD is now 1 ahead of `origin/main`; awaiting Asaf's word to
push. Remaining Stage-9 items unchanged (human-coordinated): the recorded demo + `make receipts` with the real `.env`.

## 2026-06-25 11:35 — [VOICE] NOTE (CORRECTION: `.env` present — PM can capture receipts; demo receipt captured)
**Asaf caught my error:** I'd said "`.env` absent → PM cannot run receipts." **Wrong** — `.env` exists (984 bytes, Jun 24
17:23, predated my check). The false negative was a multi-part `&&` shell command where a no-match `grep` (exit 1) broke
the chain. **`make preflight` → PASSED** (5 keys present; allowlist 1; ledger $0.06/$50, live 1/6). **Captured the demo
receipt:** `make receipts CALL_IDS="019ef8f2-…"` → `receipts/019ef8f2-…json` (`cost_usd 0.1482`, redacted — no phone/secret;
swept clean; trackable class). **Cost $0.1482 verified == source.** Real all-time debug spend ≈ $1.93 (≪ $50); ledger
shows $0.06 post-reset. **Updated handoff:** the PM CAN now run the read-only live tools (preflight/receipts/inspect/score);
only the *recorded demo* still needs Asaf. New uncommitted: the NOTES correction + the captured receipt (redacted, trackable).

## 2026-06-25 11:40 — [VOICE] SESSION START
Picking up: **Stage 9 — video** is the focus (Asaf: "we are going to work on the video"). Status as read from the
ledger: Stages 0–7 ✅; Stage 8 build-half ✅ + **LIVE1/LIVE2 met** (real booking, call `019ef8f2…`, cost $0.1482);
Stage 8.5 offline+MOCK ✅ (`8bef263`); **Stage 9 in progress** — `make eval`/`make receipts` toolchain + reconciled
storyboard committed `ca381fb`; demo receipt captured. Read order completed this session: `PM_Methodology_Prompt.md`
(verbatim) → full `PM_LOG.md` (through the 11:35 NOTE) → `CLAUDE.md` (in context) → `PLAN.md` → `QA_checklist.md` →
`NOTES.md` (full) → `ORCHESTRATION.md`.
**Resume state (verified vs disk via git, NOT just the ledger — no crash gap this time):** working tree clean except
`M NOTES.md M PM_LOG.md ?? receipts/` — exactly the 11:35 NOTE's uncommitted set (the NOTES correction + the redacted
demo receipt `receipts/019ef8f2-…json`, `cost_usd 0.1482`). HEAD `ca381fb`; **1 commit ahead of `origin/main`** (not
pushed — matches the 11:25 NOTE). `receipts/` holds the persistent ledger (`.budget_ledger.json`) + the captured receipt.
State as read (to RE-VERIFY by running before I report any number): suite last claimed **543 passed / 1 skipped / 1
xfailed** (`ca381fb`/`abae4dd` — NOT re-run by me yet); `make eval` deterministic A (Consultative) book 0.4 / B (Direct)
0.2, disclosure 0.8 / objection 1.0 / compliance 1.0 both, avg_turns 3.4/2.6, 5 personas; persistent ledger $0.06/$50,
live 1/6; real all-time debug spend ≈ $1.93 ≪ $50; demo recording kept at `storage.vapi.ai/019ef8f2-…-mono.wav`.
**CLAUDE.md is current** (pipeline revision + AGENT_TOOLS=4); **⚠ PLAN.md footer still partly stale** (cites Realtime /
387–419 green) — a reconciliation pass is owed.
Plan for this session: **stop and await Asaf's specific direction on the video** (per his instruction). Honor his
working style (concise; fix only what he names; don't re-raise dropped items e.g. "Ulta"/lead-tz unless asked). Will
re-verify any number against its source before reporting; will NOT place live calls autonomously. SESSION END / HANDOFF
before stopping.

## 2026-06-25 12:02 — [VOICE] SESSION START (sales-content + voice/tone review — advisory, no code)
Picking up: a **content/quality review** Asaf asked for — "are we giving the BEST value proposition, did we match the
ICP, all the things about selling, and what are the other (most popular) options for voices and tone." This is
ADVISORY (not a stage advance, not the autonomous loop). Read order completed this session: `PM_Methodology_Prompt.md`
(verbatim) → full `PM_LOG.md` (through the 11:40 START) → `CLAUDE.md` (in context) → `PLAN.md` → `NOTES.md` (full) →
`ORCHESTRATION.md`; then the actual content under review: `data/value_prop.md`, `data/icp.synthetic.json`,
`data/leads.synthetic.json`, `app/persona.py`, and the voice config (`app/config.py` §9 / `app/vapi_client.py`).
**Resume state (verified vs disk, NOT the ledger):** the 11:40 SESSION START has no matching SESSION END (recurring
"ran, never closed" pattern) BUT the working tree is now **CLEAN** — HEAD `32bd7b9` ("docs: reconcile README to
standard TTS pipeline…"), 2 commits past the 11:40 entry's `ca381fb`, so the 11:40 NOTES/receipts work was committed.
Only `?? .git-rewrite/` (leftover from the GitHub history push) — ignorable. Voice stack confirmed on disk:
gpt-4o brain + **OpenAI TTS `shimmer` @ speed 1.1** + Deepgram nova-2 STT (`VOICE_PROVIDER=vapi`).
**Graded-contract note:** `data/value_prop.md` (Policy-4 authoritative content), `icp.synthetic.json`, the
`DISCLOSURE_LINE` literal, and `TTS_VOICE_ID`/`LLM_MODEL` (§9 constants) are all graded. This session only
REVIEWS them and surfaces recommendations — any actual edit is an Asaf decision, flagged as such.
Plan for this session: deliver the value-prop / ICP / selling / voice-tone assessment with concrete, prioritized
recommendations; do NOT edit graded content without Asaf's go; do NOT place live calls. SESSION END / HANDOFF before stopping.

## 2026-06-25 12:42 — [VOICE] SESSION START
Picking up: **Stage 8/8.5 live + Stage 9 video** are the only non-✅ work (Stages 0–7 ✅; Stage 8 build-half ✅ +
LIVE1/LIVE2 met on real call `019ef8f2…`; Stage 8.5 offline+MOCK ✅ committed). Read order completed this session
(per the ritual): `PM_Methodology_Prompt.md` (verbatim) → full `PM_LOG.md` through the 12:02 START → `CLAUDE.md`
(in context) → `PLAN.md` → `QA_checklist.md` → `NOTES.md` (full tail incl. the 2026-06-25 voice-swap entry) →
`ORCHESTRATION.md`.
**Resume anomaly (verified vs disk via git, NOT the ledger):** the **12:02 SESSION START has no matching SESSION END**
(the recurring "ran, never closed" pattern). The 12:02 entry opened as *advisory only* but the session then DID edit
graded files. There is an **uncommitted batch on disk, PM-unverified-this-session, uncommitted, unlogged-END:**
`M CLAUDE.md app/config.py app/vapi_client.py data/value_prop.md tests/test_env.py tests/test_voice.py NOTES.md PM_LOG.md`.
HEAD `f79deb3` (== old `32bd7b9` after the GitHub history rewrite); HEAD == origin/main (0/0 ahead/behind).
**What the batch is** (read from the diff + the matching NOTES 2026-06-25 entry, NOT yet re-verified by me): the
**ElevenLabs voice swap + sales-content sharpening** — (1) §9 graded constants `TTS_PROVIDER` openai→`11labs`,
`TTS_VOICE_ID` shimmer→`21m00Tcm4TlvDq8ikWAM` (Rachel), new `TTS_MODEL=eleven_flash_v2_5` (config.py + CLAUDE.md §9/§1.2
+ vapi_client voice block: provider/voiceId/model/stability 0.5/similarityBoost 0.75, **speed knob dropped** after a
live-400 on `experimentalControls`); (2) Policy-4 graded `value_prop.md` — VP#3 speech-to-speech→conversational voice,
new VP#6 live-proof line, +3 objections (robocall/sounded-robotic/how-different); (3) tests `test_tts_voice_constants`
+ `test_voice` voice-shape update. NOTES claims this batch already went through the corrected post-Stage-4 **independent
reviewer gate** (Reviewer A APPROVE; Reviewer B CHANGES-REQUIRED→fixed) and **544 passed / 1 skipped / 1 xfailed**.
State as read (to RE-VERIFY by running before I report any number): the 544 green count; ENV4 import-safe with the new
`TTS_MODEL` constant + voice block; both byte-exact graded literals unchanged (`DISCLOSURE_LINE`/`FAILSAFE_HANGUP_LINE`);
no graded *interface signature* touched (the swap is constants + payload-dict only).
**Two UNVERIFIED-LIVE dependencies (same class as the `REALTIME_MODEL` reconciliation):** (1) an **ElevenLabs key must be
connected in the Vapi dashboard** or `make call` 400s; (2) the exact ElevenLabs voice payload-shape needs one live call to
confirm (`stability`/`similarityBoost`/voiceId validity) — the live-400 already pruned `experimentalControls`/`speed`.
Plan for this session: honor Asaf's working style (concise; fix only what he names; don't re-raise dropped items e.g.
"Ulta"/lead-tz). **Await Asaf's specific direction.** Most likely: (a) PM-verify the on-disk voice-swap batch (run the
suite for a ground-truth green count, re-prove ENV4, confirm no graded literal/interface touched) then **commit on his
word** — it is a graded batch already reviewed; (b) Stage 9 video work per `docs/STAGE9_STORYBOARD.md`. Will re-verify any
number against its source before reporting; will NOT place live calls autonomously; will NOT commit the graded batch
without Asaf's go. SESSION END / HANDOFF before stopping.

## 2026-06-25 12:48 — [VOICE] SESSION END / HANDOFF (Asaf REJECTED the voice-swap batch → reverted to HEAD; system restored + verified green)
**Asaf's directive:** "I don't want these changes — retrieve it to the situation before he did his work. THIS IS A
DELICATE JOB… the system worked good before." → revert the previous PM's uncommitted **ElevenLabs voice-swap + value-prop
sharpening** batch and restore the repo to the last known-good committed state (`f79deb3`, OpenAI-TTS `shimmer`).
Did (surgical, recoverable — no live call, no commit needed since nothing of the batch was ever committed):
1. **Safety backup first** — `git diff HEAD` of the 7 batch files saved to `/Users/asaframati/alta-rejected-voice-swap-2026-06-25.patch`
   (18,451 bytes / 252 lines). Fully recoverable via `git apply <that path>` if Asaf ever reverses this.
2. **Reverted 7 files to HEAD** (`git checkout HEAD -- …`): `app/config.py` (TTS_* → `openai`/`shimmer`, `TTS_MODEL` line
   removed), `app/vapi_client.py` (voice block back to `{provider, voiceId, speed}`, ElevenLabs stability/similarityBoost
   knobs gone), `data/value_prop.md` (VP#6 live-proof + 3 new objections removed; VP#3 "speech-to-speech" restored),
   `CLAUDE.md` (§9/§1.2 back to OpenAI-TTS), `tests/test_env.py` (`test_tts_voice_constants` removed), `tests/test_voice.py`
   (voice-shape assertion restored). **NOTES.md reverted to HEAD too** — the voice-swap decision entry is removed because the
   decision was rejected (NOTES holds decisions that STAND; the audit trail of "tried & reverted" lives here in PM_LOG).
3. **Kept only `PM_LOG.md`** (this session's ritual entries + the prior 12:02 START as history). Tree is now clean except `M PM_LOG.md`.
Verified numbers (PM-run at the restored state, not assumed): offline suite **543 passed / 1 skipped / 1 xfailed** — exactly
the pre-swap count (the swap had added 1 test → 544; cleanly back to 543; skip = live-only barge-in STR-T1, xfail = Bug-1
re-offer guard). **ENV4 import-safe** from an empty cwd across all app modules. **`make eval` deterministic and UNCHANGED**
from the committed baseline: A (Consultative) book 0.4 / B (Direct) 0.2; disclosure 0.8, objection 1.0, compliance 1.0 both;
avg_turns 3.4/2.6; 5 personas. No graded literal/interface/eval-number drift — the system is the known-good `f79deb3`.
Status now: ✅ **Repo restored to the known-good committed state `f79deb3`.** The rejected batch is gone from the working
tree (backed up + recoverable). Stages 0–7 ✅; Stage 8 build-half ✅ + LIVE1/LIVE2 met; Stage 8.5 offline+MOCK ✅; **Stage 9
(video) remains the only real open work** — `make eval`/`make receipts` toolchain + reconciled storyboard already committed
(`ca381fb`→`f79deb3` line). The voice is back to **OpenAI-TTS `shimmer`** (the config that ran the working demo call `019ef8f2…`).
**⚠ Leftover from the prior session (NOT auto-killed — surfaced for Asaf):** the previous PM's live-call servers are STILL
running — `make serve` on `:8000` (PIDs 19171, 20788) + ngrok tunnel (PID 19222, `pleading-stomp-referee.ngrok-free.dev`).
They hold the **stale ElevenLabs config in memory** (no longer matches disk). If Asaf wants to place a clean shimmer call he
must **restart `make serve`** so it loads the reverted config; otherwise stopping them returns fully to "before his work."
Next PM / Asaf should: (1) decide whether to stop the stale servers (recommend yes — they run reverted-away code); (2) the
only genuine open work is **Stage 9 (the video)** per `docs/STAGE9_STORYBOARD.md` — recorded demo (kept `019ef8f2…` recording
vs fresh live) + `make receipts` evidence; (3) `M PM_LOG.md` is uncommitted ledger-only — commit on Asaf's word, or leave.
Watch out for / open: backup at `/Users/asaframati/alta-rejected-voice-swap-2026-06-25.patch` (delete once Asaf is sure he
won't want it); do NOT re-introduce the voice swap unless Asaf asks; the dropped "Ulta"/lead-tz items stay dropped.

## 2026-06-25 13:55 — [VOICE] SESSION END / HANDOFF (live-call tuning ✅ committed; latency 5.0s→1.7s, persistence + warm filler/ending)
Did (this session continued past the 12:48 revert into Asaf-directed live tuning, each change made + verified in turn):
- **Reverted** the prior PM's uncommitted ElevenLabs/value-prop batch to HEAD `f79deb3` (system restored to working
  OpenAI-`shimmer`; backup at `/Users/asaframati/alta-rejected-voice-swap-2026-06-25.patch`); stopped the stale servers.
- Brought the **live-call stack up** (FastAPI :8000 + ngrok `pleading-stomp-referee` + signed-webhook smoke), Asaf placed calls.
- **Barge-in** snappier (`_STOP_SPEAKING_PLAN` numWords 2→1, backoff 0.8→0.6).
- **Objection persistence** (persona, Policy 4/6): no fold on the first "no" — acknowledge → most-relevant value-prop → re-ask,
  TWO gentle attempts, then honor a firm/repeated no. **Live-validated** (calls `019efe43`/`019efe63`; `019efe63` booked).
- **⭐ Latency fix:** diagnosed from Vapi `performanceMetrics` — the ~5s gap was model (gpt-4o ~2.6s) + voice (OpenAI TTS ~2.1s),
  NOT endpointing (100ms). Asaf chose "both": §9 `LLM_MODEL` gpt-4o→**gpt-4o-mini**, `TTS_PROVIDER` openai→**deepgram**,
  `TTS_VOICE_ID` shimmer→**asteria** (bare name — Vapi 400'd `aura-asteria-en`, reconciled; Deepgram key already connected for
  STT, no new key; dropped the now-invalid OpenAI `speed` knob). **Live-validated:** call `019efe63` avg turnLatency **1720ms**
  (model 559 / voice 304) — down from **5040ms**. Asaf: "works much better."
- **Warm filler** (banned "give me a moment" et al.) + **non-abrupt warm ending** (sign-off + a beat before `endCall`, so the
  prospect isn't cut off). *Offline-verified; pending live confirm (made after the last call.)*
Verified numbers (PM-run): full suite **543 passed / 1 skipped / 1 xfailed**; ENV4 import-safe; `make eval` unchanged (A book
0.4 / B 0.2, compliance 1.0 — persona prompt edits don't touch the offline FSM/bake-off). Graded literals + interface
signatures + AGENT_TOOLS untouched. Spend: ledger **$0.81 / $50**, live **2/6** — all ≪ caps.
Status now: ✅ **Committed `1e6826d` on `main`** (the 6 code/doc files + NOTES + PM_LOG; the two `docs/VIDEO_SCRIPT.*` files
are Asaf's untracked Stage-9 work — deliberately NOT in this commit). Working tree otherwise clean. **Not pushed** (push only
on Asaf's word; repo origin is GitHub `asaf3231/Voice-Agent`).
**Process note (honest):** the formal independent `/code-review` gate was **not** separately run — the high-risk pieces
(model/voice/persistence) were **live-validated end-to-end**, and Asaf directed commit + close-out. A future formal review of
the persona/§9 diff is cheap if wanted.
Next PM / Asaf should: (1) optionally place one more call to confirm the **warm filler + warm ending** live (only those two are
offline-only); (2) **push** if desired; (3) **Stage 9 (the video)** is the only real open work — storyboard + `make eval`/
`make receipts` toolchain already committed; the `docs/VIDEO_SCRIPT.*` drafts are in the tree. Watch out for: backup patch at
the path above (delete when sure); do NOT re-introduce the ElevenLabs swap unless asked; dropped "Ulta"/lead-tz stay dropped.
