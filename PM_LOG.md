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
