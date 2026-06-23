# ORCHESTRATION.md — Autonomous PM ↔ Executer Loop

> How the **PM** (the persistent main Claude Code session) drives **swe-executer**
> subagents through the stages in `PLAN.md` without Asaf in the routine loop.
> `CLAUDE.md` = rules. `PLAN.md` = stage tracker. `QA_checklist.md` = verification.
> `NOTES.md` = decision log. This file = the loop protocol that wires them together.

---

## Roles

| Role | Who | Lifetime | Notes |
|---|---|---|---|
| **PM** | the main session (you talk to it) | the whole project | owns CLAUDE/PLAN/QA/NOTES; reviews; advances |
| **Executer** | a `swe-executer` subagent, spawned per stage | one stage, then dies | **cold every spawn** = a fresh engineer per stage |
| **Reviewer** | a `swe-reviewer` subagent, spawned per graded-contract stage | one review, then dies | **cold, read-only**; independent spec + code-quality pass before ✅ |

The PM does **not** exit and reactivate. It stays running and *spawns* a cold executer
per stage; the executer's handback returns inline. That is what removes Asaf from the loop.

## Shared memory (three layers)

- **Ledger (durable state):** `PLAN.md` (stage + status), `NOTES.md` (decisions/handbacks),
  `QA_checklist.md` (how to verify). These persist across the whole project.
- **Mailbox (per-stage message bus):**
  - `briefs/stage-<N>[-r<k>].md` — PM → executer (one file per attempt; `-r<k>` = retry k).
  - `handbacks/stage-<N>[-r<k>].md` — executer → PM.
- **PM session memory (PM → next PM):** `PM_LOG.md` at repo root — a `[BACKEND]`-tagged
  `SESSION START` entry at the start of every PM session and a `SESSION END / HANDOFF` entry at
  the end (the non-negotiable ritual in `PM_Methodology_Prompt.md`). This is what lets a fresh
  PM resume cold. **Only the PM writes `PM_LOG.md`** — the executer and reviewer never touch it.

No database. Subagents read/write files natively, so the repo files *are* the shared memory.

---

## The loop (PM runs this)

```
current = first stage in PLAN.md whose status is not ✅
attempt = 0
loop:
    write briefs/stage-<current>[-r<attempt>].md       # tight brief (format below)
    spawn swe-executer subagent, prompt = "Execute the brief at <that path>."
    read its returned handback (also on disk at handbacks/...)

    REVIEW (PM does this itself, does not trust the handback blindly):
      - re-run / spot-check the stage's QA check IDs
      - verify any number against the source data file
      - confirm import-safety / no-eval / no-framework / catalog-by-name still hold

    REVIEWER GATE (only if this stage TOUCHES A GRADED CONTRACT — see trigger list below):
      - spawn a swe-reviewer subagent, prompt = "Review the brief at briefs/stage-<current>...
        against the diff from `bash scripts/review-package.sh`."
      - it returns a two-stage review (spec-compliance + code-quality) with findings
        tagged Critical / Important / Minor and a verdict APPROVE | CHANGES-REQUIRED.
      - CHANGES-REQUIRED (≥1 Critical or Important) is treated exactly like a QA failure
        (path C below): it consumes the single auto-retry. Minor findings are logged to
        NOTES.md, they do not block.
      - stages that touch NO graded contract skip this gate (PM's own REVIEW suffices).

    decide:
      A) handback has DECISION-NEEDED, or stage needs an open-question/secret,
         or it requests a tool-signature / schema / policy-constant / loop-contract /
         graded-literal change:
             -> update PLAN/NOTES, **HALT and ask Asaf**          [decision gate]
      B) QA clean:
             -> mark stage ✅ in PLAN.md; append handback to NOTES.md;
                current = next stage; attempt = 0; continue
      C) QA failed, OR reviewer returned CHANGES-REQUIRED:
             attempt += 1
             if attempt < 2: write briefs/stage-<current>-r<attempt>.md with
                             specific corrections (paste the failing QA output and/or the
                             reviewer's Critical/Important findings verbatim); respawn a
                             fresh executer. The corrected brief tells the executer to run
                             the `systematic-debugging` skill.                [auto-retry once]
             else: **HALT and ask Asaf**                          [2×-fail gate]

    if no stages remain: report "project complete", stop.
```

### Halt policy (Asaf's gate — decided 2026-06-18)

The PM auto-advances every clean stage. It **halts and asks Asaf only** on:

1. **Decision / open-question / secret** — e.g. OQ-2 (firecrawl pin), OQ-4 (RRF k/tiers),
   OQ-7 (keys/host), or any unspecified architectural/scope choice.
2. **Contract-change request** — a tool signature, JSON schema, policy constant, the loop
   contract, or a graded literal would have to change.
3. **Second consecutive QA failure** on the same stage (1 auto-retry, then halt).

Everything else proceeds autonomously.

### Reviewer gate — when it fires (decided 2026-06-19)

The PM spawns a **`swe-reviewer`** subagent **only on stages that touch a graded
contract** — to add an independent spec + code-quality pass without paying a reviewer
spawn on every stage. A stage touches a graded contract if its brief changes or adds:

- a tool **signature** or any entry in `TOOL_SCHEMAS` / `TOOL_DISPATCH`, or the 10-tool
  name-identity asserts;
- a **policy constant** (`TOOL_CALL_CAP`, `MAX_ANGLES`, `ICP_TAG_THRESHOLD`,
  `CHUNK_MAX_DOMAINS`, `CHUNK_TIME_BUDGET_S`, `FANOUT_RECOVERY_THRESHOLD`, `DAILY_SEND_CAP`,
  `LATENCY_TARGET_S`, `ICP_ANCHOR_COUNT`);
- the **loop contract** (`answer_question` shape, dispatch, termination precedence);
- the **Tool Gateway**, a policy chokepoint (Policy 4 auth gate, Policy 5 ceiling), or the
  byte-exact `FALLBACK_MESSAGE` / catalog loader + 9-column validation.

Stages that touch only tests, docs, peripheral helpers, or the `frontend/` skip the
reviewer gate — the PM's own QA re-run is enough. When in doubt, fire the gate.

### Budget rule — feed subagents only what they need (decided 2026-06-19)

Both the executer and the reviewer are **cold** and re-read CLAUDE/PLAN/QA/NOTES + brief.
To keep that cost bounded (borrowed from the superpowers context-minimization pattern):

- Keep `briefs/` tight — scope, the exact QA IDs, the files in-lane, nothing else.
- Give the reviewer the **diff only** via `bash scripts/review-package.sh` (working tree)
  or `bash scripts/review-package.sh BASE HEAD` (between tags) — never paste the whole repo
  or the whole plan into a subagent prompt.

---

## Brief format (`briefs/stage-<N>.md`)

```markdown
# Brief — Stage <N>: <name>
Read first: CLAUDE.md → PLAN.md → QA_checklist.md → NOTES.md, then this brief.

Goal: <one sentence from PLAN.md>
Scope (do ONLY this stage): <bullets>
QA checks to PASS (run, not inspect): <IDs, e.g. ENV4, CAT1–CAT6, AG1–AG6>
Constraints (from CLAUDE.md): <the ones that bite this stage>
Inputs / files you may touch: <paths>
Do NOT: advance past this stage; change a tool signature/schema/policy constant/
        loop contract/graded literal — surface those as DECISION-NEEDED.
Deliver: write handbacks/stage-<N>.md in the standard format; return it as your final message.
```

(On a retry, add a top section "Corrections required:" listing exactly what failed and
what must change; keep the rest.)

## Handback format

Defined in `.claude/agents/swe-executer.md` and mirrors `CLAUDE.md` §12 / `PLAN.md`
"Standard stage handback format". Item 5 **DECISION-NEEDED** is the halt trigger.

---

## Kickoff

Start a work block by telling the PM session once:

> "You are the PM. Run the ORCHESTRATION.md loop from the current PLAN.md stage.
>  Auto-advance clean stages; halt only on decision/open-question/secret, a
>  contract-change request, or a 2nd QA failure."

Or run the `/pm-run` command, which says the same thing.

## Defaults (decided 2026-06-18)

- Executer model: **Sonnet** (cheaper); PM stays on its session model.
- Reviewer model: **Sonnet** (cheaper), read-only; fires only on graded-contract stages.
- Retry budget: **1 auto-retry**, then halt (a reviewer CHANGES-REQUIRED consumes it).
- Reviewer independence: the PM **runs** QA checks itself — it never marks a stage ✅
  on the executer's word alone. On graded-contract stages, the `swe-reviewer` adds a
  second, independent set of eyes on top of the PM's own review.

## Caveats

- Each executer is cold and re-reads CLAUDE/PLAN/QA/NOTES + brief — the cost of "fresh
  engineer per stage". Keep briefs tight.
- Subagents are non-interactive: an executer cannot ask mid-stage. It surfaces questions
  via DECISION-NEEDED, which the PM turns into a halt.
- This repo is under git. The reviewer gate's `scripts/review-package.sh` uses `git diff`;
  tagging each ✅ stage lets the PM pass `BASE HEAD` for a clean per-stage review package.
