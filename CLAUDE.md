# CLAUDE.md — Project Standards & Conventions

Project: **Alta Outbound Voice Agent** — an AI-driven, English-speaking outbound calling agent that
pitches Alta's value proposition and books meetings for the sales team.
Agent persona / codename: **"Aria"**
Deliverable: a production-style **service repo** (the running voice agent + an offline deterministic
test/eval suite + scripts) **and a video explanation** — see §0.2. *(No Jupyter notebook — decision
2026-06-23; the notebook discipline is preserved as a service workflow in §8.)*
Maintained by: Asaf

> Read this file at the start of every Claude Code session before writing or editing any code. It
> defines the **permanent rules**. Execution status belongs in `PLAN.md`; the verification blueprint
> belongs in `QA_checklist.md`; decisions and verified facts belong in `NOTES.md`; PM→PM session
> handoff belongs in `PM_LOG.md`.

---

## 0. Working methodology

This project uses the lightweight file-based PM workflow:

```text
CLAUDE.md                = permanent rules and conventions  (this file)
PLAN.md                  = current stage tracker and Definition of Done
QA_checklist.md          = the Test-Driven-Development blueprint (every DoD points here)
NOTES.md                 = decisions, verified facts, open questions, handbacks
PM_LOG.md                = PM→PM session handoff log (begin/end ritual)
PM_Methodology_Prompt.md = how the PM works (role, budget rules, memory architecture)
ORCHESTRATION.md         = the autonomous PM↔executer loop protocol (optional)
```

**PM session ritual (non-negotiable):** every PM session opens by reading `PM_Methodology_Prompt.md`
+ the latest `PM_LOG.md` entry, writes a `SESSION START` entry to `PM_LOG.md` before working, and
writes a `SESSION END / HANDOFF` entry before stopping. Only the PM writes `PM_LOG.md`.

At the start of every Claude Code session: read `CLAUDE.md` → `PLAN.md` → `QA_checklist.md` →
`NOTES.md`, identify the current stage, work **only** on that stage, stop at the stage boundary and
report back. Do not silently continue into the next stage.

Do **not** change any of the following without surfacing the decision to Asaf first: a named constant
in §9, a tool/function signature, the voice-provider interface, the `DISCLOSURE_LINE` /
`FAILSAFE_HANGUP_LINE` literals, a budget cap, or the consent-allowlist contract. These are graded
contracts.

If `PLAN.md`, `QA_checklist.md`, or `NOTES.md` is missing, do **not** implement. Draft the missing file
and wait for Asaf to approve it.

### 0.1 Autonomous PM ↔ executer mode (`ORCHESTRATION.md`)
When run under `ORCHESTRATION.md`, the PM performs the stage-boundary review and may auto-advance clean
stages by spawning a cold `swe-executer` per stage. The human gate (Asaf) narrows to three triggers:
(1) a required decision / open-question / secret; (2) a request to change a graded contract (above);
(3) a second consecutive QA failure on a stage. The executer never crosses its stage boundary or
changes a contract — it surfaces those as `DECISION-NEEDED`, which the PM converts into a halt.

### 0.2 The two deliverables
1. **The service repo** — graded on the code: it must run from a clean checkout, be import-safe, place
   a real outbound call that pitches and books a meeting, and pass the offline deterministic suite.
2. **The video explanation** (assignment-mandated, due in 3 business days) — walks the architecture,
   shows a **live demo call** booking a meeting, and shows the **offline eval results + the receipts**
   proving the $50 budget was respected. The video is a first-class stage (Stage 9), not an afterthought.

---

## 1. Environment

The service must run in a clean environment with no manual fixups.

- **Python:** 3.11 or higher. **OS-agnostic** (Windows / macOS / Linux): no hardcoded absolute paths;
  build every path with `pathlib` relative to the repo root or `os.getcwd()`.
- **Runtime shape:** a small **FastAPI** server (`app/server.py`) that the voice platform calls for
  tool/function webhooks and call-status events, plus CLI scripts (`scripts/`) to place calls and pull
  receipts. The conversational audio/turn-taking is handled by the **managed voice platform** (Vapi)
  driving the **OpenAI Realtime** model; our service owns the *logic*, *governance*, and *booking*.
- **Reproduce a run from a clean checkout — one command path:**

  ```bash
  python3 -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\Activate.ps1
  pip install -r requirements.txt
  cp .env.example .env          # then fill real values locally — NEVER commit .env
  make test                     # the offline deterministic suite — the "Restart & Run All" equivalent
  make serve                    # starts the FastAPI webhook server (no call placed, no live cost)
  ```

  A real demo call is a separate, explicitly gated command (§5): `make call TO=<consented-number>`.

- **Import-safe (non-negotiable):** `import app.config`, `import app.server`, `import app.tools`,
  `import app.orchestrate`, `import app.budget`, `import app.consent` must succeed with **zero side
  effects** — no network, no platform/OpenAI/calendar client constructed, no `.env` required, no file
  written, **and no call placed**. All clients are lazy singletons (`_get_vapi()`, `_get_calendar()`).
  Enforced by `ENV4`.

### 1.1 Pinned dependencies (non-negotiable)
`requirements.txt` pins **every** non-stdlib import with `==`; a fresh venv must `pip install -r
requirements.txt` cleanly. At minimum:

```text
fastapi              # ⚠ pin exact ==version at Stage 1 install — the webhook/tool server
uvicorn              # ⚠ pin exact — ASGI server
httpx                # ⚠ pin exact — REST client for the Vapi provider adapter
pydantic             # ⚠ pin exact — request/response models for webhooks & tool I/O
python-dotenv        # ⚠ pin exact — loads .env at runtime (inside main/serve, never at import)
pytest               # ⚠ pin exact — the offline deterministic suite
# calendar backend (Stage 3, OQ-VOICE-3 LOCKED): Cal.com API via httpx (+ a deterministic local mock for the offline suite) — pin at install. Google OAuth deliberately avoided for the 3-day window.
```

- `os`, `sys`, `json`, `re`, `csv`, `time`, `random`, `pathlib`, `dataclasses`, `datetime`, `hmac`,
  `hashlib`, `decimal`, `enum`, `importlib` are **standard library** — do not list them.
- The **OpenAI Realtime** model is configured *inside the voice platform* (the OpenAI key lives in the
  platform/env, not our code) — so we do not necessarily import the `openai` SDK; if any module does,
  it is pinned. The realtime model id is the named constant `REALTIME_MODEL` (§9), pinned at install
  (`OQ-VOICE-1`).
- A missing/unpinned transitive that breaks the fresh-venv install is a **Stage 1 blocker**, not a
  Stage 9 surprise. Check `ENV2` fails if any imported module is unpinned.

### 1.2 Providers, models & secrets
| Concern | Choice | Where the secret lives |
|---|---|---|
| Voice platform (telephony, turn-taking, recording, cost) | **Vapi** (`VOICE_PROVIDER`), Retell-swappable behind the adapter | `VAPI_API_KEY` (env) |
| Conversational brain | **OpenAI Realtime** (`REALTIME_MODEL`), speech-to-speech | `OPENAI_API_KEY` (configured in the platform/env) |
| Webhook authenticity | Vapi signing secret | `VAPI_WEBHOOK_SECRET` (env) — verified on every inbound webhook |
| Booking | Calendar backend (Stage 6, sandbox default) | calendar OAuth token (env) |

**Every secret comes from `os.environ` (loaded from an untracked `.env`), never hardcoded, never
committed.** `.env.example` carries placeholders only. The **provided credit-card number from the
assignment email is a secret** — it must never appear in any tracked file, commit, log, transcript, or
prompt. Enforced by `SEC1` / `LEAK1`.

### 1.3 Execution & review tooling (this environment's constraints)
The roles named in `ORCHESTRATION.md` / §0.1 (`swe-executer`, `swe-reviewer`) are **roles, not
registered agent types in this environment**. They map to concrete mechanisms here:

| Role (methodology) | Mechanism in this environment | Notes |
|---|---|---|
| Executer (writes stage code) | a **`general-purpose` subagent**, spawned cold per stage with a tight brief + only the relevant diff | never the PM; one per stage, coarse granularity (budget rule) |
| Reviewer gate (contract-touching stages) | the native **`/code-review`** CLI utility | independent of the executer; replaces a hand-rolled `swe-reviewer` spawn — purpose-built for diffs, re-derives less context |
| **Stage 7 governance / anti-leakage gate** | the native **`/security-review`** CLI utility | the highest-leverage gate for this PII- + secret-handling outbound-calling system |
| QA verification | **the PM, itself** (re-runs the referenced `QA_checklist.md` checks) | unchanged; PM never marks ✅ on the executer's word (§0.1, §11, §12) |

Rationale (token/loop optimization, decision 2026-06-23): native CLI review tools cost fewer
agent-loop round-trips than cold reviewer spawns, and `general-purpose` executers keep the
swe/reviewer/PM-QA separation intact. Reviewer ≠ executer ≠ PM-as-QA — the three stay distinct.

---

## 2. Source-of-truth files & repo layout

```text
alta-voice-agent/                       # repo root
├── app/
│   ├── config.py                       # §9 constants, lazy client getters, .env loading, literals — the ONLY place magic values live
│   ├── persona.py                      # system prompt + dialog policy (state machine) + guardrails + the two literals
│   ├── tools.py                        # the agent's callable functions (deterministic): check_availability, book_meeting, log_disposition, detect_voicemail, end_call
│   ├── vapi_client.py                  # VoiceProvider adapter (Vapi impl): assistant config + place_call + fetch_call_cost; Retell-swappable
│   ├── server.py                       # FastAPI: signature-verified tool/function + call-status webhooks; import-safe
│   ├── budget.py                       # spend ledger + per-call ceiling + hard-cap guard + receipts capture
│   ├── consent.py                      # consent allowlist gate — only allowlisted numbers are dialable
│   ├── calendar_client.py              # lazy booking backend behind a CalendarProvider interface (sandbox default)
│   ├── orchestrate.py                  # campaign runner over the synthetic lead list (retries, voicemail, daily cap, budget guard)
│   └── eval/
│       ├── harness.py                  # offline deterministic eval over labeled SIMULATED transcripts — the reproducible core
│       ├── rubric.py                   # scored rubric (disclosure-said, pitched, objection-handled, booked, compliant) — computed, never hardcoded
│       └── simulated_callee.py         # seeded persona simulator (no network) for offline conversation eval
├── data/                               # the bounded SYNTHETIC inputs — single source of truth, never inlined into code
│   ├── leads.synthetic.json            # who to call (synthetic prospects)
│   ├── icp.synthetic.json              # ICP / qualification criteria
│   └── value_prop.md                   # Alta value-prop facts the agent may cite (assumed/synthetic)
├── fixtures/transcripts/               # labeled SIMULATED transcripts for eval (no real PII; tracked)
├── tests/                              # offline deterministic suite (dev-only)
├── scripts/
│   ├── place_demo_call.py              # gated live-call launcher (consent + budget) — `make call`
│   └── capture_receipts.py             # pull per-call cost → receipts/  (proof for the $50 budget)
├── receipts/                           # cost evidence; raw (with account ids) gitignored, redacted copies tracked
├── requirements.txt                    # pinned deps
├── .env.example                        # placeholders only (no real secret, no card number)
├── .gitignore                          # covers .env, real recordings/transcripts, raw receipts, .venv
├── Makefile                            # one-command run/test/call
├── README.md                           # run-from-clean-checkout
└── (spine: CLAUDE.md, PLAN.md, QA_checklist.md, NOTES.md, PM_LOG.md, ORCHESTRATION.md, PM_Methodology_Prompt.md)
```

Source-of-truth rules:
- `data/*.synthetic.*` are the **three bounded inputs** and the single source of truth for prospects,
  ICP, and value-prop. **Their values are never hardcoded into a tool or prompt** (anti-leakage §5).
  Loaded by name, validated on load (`LEAD1`).
- Real recordings, real transcripts, and raw receipts are **generated, machine-local, and excluded**
  from any commit. Only labeled synthetic fixtures and redacted receipts are tracked.
- Do not duplicate decisions across files: rules here, status in `PLAN.md`, why in `NOTES.md`.

---

## 3. System objective & runtime contract

Aria runs an **autonomous outbound calling pipeline**: from the synthetic lead list it places a call,
**opens with the byte-exact disclosure**, pitches Alta's value proposition, qualifies the prospect,
handles objections, and **books a meeting** on the sales team's calendar — all under hard governance
(budget, consent, turn cap, recording disclosure).

### 3.1 Pipeline shape (the happy path)
```text
synthetic lead
  → consent gate (number on the allowlist?)          [app/consent.py — CON1]
  → budget guard (projected cost ≤ ceiling & under cap)   [app/budget.py — CALL4/SEC3]
  → place_call (Vapi + OpenAI Realtime)              [app/vapi_client.py — VOICE1]
     → DISCLOSURE_LINE spoken first                  [CON2 — byte-exact]
     → pitch → discovery → objection handling → propose slot   [app/persona.py — CONV1..4]
     → tool: check_availability → book_meeting       [app/tools.py — TOOL1/TOOL2, BOOK*]
     → end_call (or FAILSAFE_HANGUP_LINE on cap/error)   [CONV6]
  → log_disposition + capture receipt                [TOOL3 / SEC5]
```

### 3.2 Runtime I/O
1. Input is the **synthetic lead record** (name, company, phone, ICP fields) — not a free-text query.
2. Validate `data/*` on load; a malformed input is a clean startup error, not a mid-call crash.
3. Run the call under the **turn cap** (`MAX_AGENT_TURNS`) and the **wall-clock cap**
   (`MAX_CALL_DURATION_S`); on either, speak `FAILSAFE_HANGUP_LINE` and hang up safely.
4. Every booking and disposition is recorded; every live call captures a receipt (cost).
5. On any failure (no-answer, voicemail, declined, error), end in a **safe disposition** — never an
   uncaught exception, never a silent partial booking.

### 3.3 Governing policies (summary — full rules in §5)
| # | Name | One-line rule |
|---|---|---|
| 1 | Budget ceiling | Total spend ≤ `HARD_BUDGET_USD`; per-call ≤ `MAX_COST_PER_CALL_USD`; abort beyond |
| 2 | Consent / compliance | Dial only allowlisted, consented numbers; speak `DISCLOSURE_LINE` first; record only with disclosure |
| 3 | Turn / time caps | ≤ `MAX_AGENT_TURNS` turns and ≤ `MAX_CALL_DURATION_S` per call → failsafe hangup |
| 4 | Authoritative content bound | The agent cites only `data/value_prop.md` / lead facts — never invents Alta claims, pricing, or commitments |
| 5 | Booking integrity | A meeting is booked only via `book_meeting` against real availability; no double-book, no phantom booking |
| 6 | Safe terminal | Any failure path ends in a clean disposition; the generative path never improvises a non-compliant close |

### 3.4 Import-safety contract (restated — it is graded)
No module-level work beyond defining constants, functions, classes, and Pydantic models. Forbidden at
import: constructing the Vapi/OpenAI/calendar clients, loading `.env`, reading `data/*`, opening the
FastAPI lifespan resources, or **placing any call**. Use lazy singletons. Verified by `ENV4`.

---

## 4. The synthetic inputs — operational compliance (non-negotiable)

`data/leads.synthetic.json` records (validate on load — `LEAD1`):
```text
lead_id, first_name, last_name, company, phone_e164, role,
icp_tags[], timezone, do_not_call (bool), notes
required: lead_id, first_name, company, phone_e164
```
- `phone_e164` is dialable **only** if it is also on the consent allowlist (§5 Policy 2); `do_not_call
  == True` ⇒ suppressed regardless of fit (`CON5`).
- `data/icp.synthetic.json` holds qualification criteria; `data/value_prop.md` holds the **only** Alta
  facts the agent may assert (Policy 4). None of these values may be hardcoded into a tool or prompt
  (anti-leakage §5) — they are read at runtime and validated. A real prospect's data never enters a
  tracked file.

---

## 5. Governance policies & the task-specific anti-leakage rule — exact rules

Each policy has a dedicated QA section. **Policies are enforced at a single chokepoint, not hoped for.**

### Policy 1 — Budget ceiling  (QA: `SEC2`–`SEC4`, `CALL4`)
- A single ledger (`app/budget.py`) tracks cumulative spend; **no call is placed if** projected cost >
  `MAX_COST_PER_CALL_USD` **or** cumulative + projected > `HARD_BUDGET_USD`. The guard runs **before**
  `place_call`. Live calls additionally respect `LIVE_CALL_BUDGET_USD` and `MAX_LIVE_CALLS`.
- The cap is **hard**: there is no code path that dials around the budget guard.

### Policy 2 — Consent & compliance  (QA: `CON1`–`CON5`)
- Only numbers on the **consent allowlist** (an untracked file / env, not committed) may be dialed;
  every other number is refused with a structured result, never dialed. `do_not_call` is also honored.
- `DISCLOSURE_LINE` is spoken **first** on every call, **byte-exactly** (the one graded literal —
  analog to a strict-string contract). Recording is enabled only when the disclosure is delivered.
  **Enforcement (Red-Team 2026-06-23):** because the OpenAI Realtime model *generates* the audio, a
  prompt instruction to "say the disclosure first" could be paraphrased. The disclosure is therefore
  pinned to the voice platform's **static first-message** feature (spoken verbatim by the platform,
  not model-generated) — `VOICE1` asserts that field byte-exact, and `LIVE2` verifies it from the real
  transcript, never assumed. This makes "first, byte-exact" a configured chokepoint, not a hope.
- The allowlist gate is the **single chokepoint** in `app/consent.py`; no orchestration path reaches
  `place_call` around it.

### Policy 3 — Turn / time caps  (QA: `CONV5`, `CONV6`)
- The conversation is capped at `MAX_AGENT_TURNS` turns and `MAX_CALL_DURATION_S` wall-clock. On either
  ceiling, the agent speaks `FAILSAFE_HANGUP_LINE` and ends the call — it does **not** continue.

### Policy 4 — Authoritative content bound  (QA: `CONV4`, `LEAK3`)
- Any claim about Alta's product, pricing, or commitments derives **solely** from `data/value_prop.md`
  and the lead's own facts — never from the model's parametric knowledge. The system prompt forbids
  inventing claims; anti-leakage keeps real business data out of the code.

### Policy 5 — Booking integrity  (QA: `BOOK1`–`BOOK3`, `TOOL2`)
- A meeting is booked **only** through `book_meeting`, against availability returned by
  `check_availability`. `book_meeting` is **idempotent** (same lead + slot never double-books) and
  validates the slot is free; a conflict returns a structured "offer another slot," never a silent
  overwrite or a phantom confirmation the agent then voices.

### Policy 6 — Safe terminal  (QA: `CONV6`, `CALL1`)
- Every failure path (no-answer, voicemail, declined, tool error, cap hit) ends in a **clean
  disposition** and the failsafe close. The generative path is never asked to improvise a non-compliant
  promise; an uncaught exception anywhere is forbidden (§6).

### Anti-leakage — what "leakage" means *here*  (QA: `SEC1`, `LEAK1`–`LEAK5`, `CON4`)
Concretely, **none** of the following may occur — each is grep- or test-enforced:
1. **No secret in a tracked file** — the **assignment credit-card number**, `OPENAI_API_KEY`,
   `VAPI_API_KEY`, `VAPI_WEBHOOK_SECRET`, calendar tokens live only in env / untracked `.env`.
   `.env.example` holds placeholders. (`SEC1`, `LEAK1`) **Named files (Red-Team 2026-06-23):**
   `Home_Assignment_email.md` (carried the card; now redacted) and `REFERENCE/` (unaudited) are
   **gitignored** and must never be committed; the `LEAK1` grep targets the **16-digit PAN / its
   4-4-4-4 grouping**, not the bare 3-digit CVV (which false-positives on ports/line numbers).
2. **No real PII committed** — real phone numbers, real recordings, and live transcripts with real
   numbers are gitignored; only labeled synthetic fixtures are tracked. (`LEAK2`)
3. **No fabricated call outcomes** — tests/eval never hardcode `booked=True` or a canned transcript and
   score it as a real result; every reported metric is **computed** from a labeled simulated input, and
   no live call runs in the default suite. (`LEAK4`, `CON4`, `EVAL2`)
4. **No hardcoded real business/lead data** — prospects, ICP, and value-prop come from `data/*` at
   runtime, never inlined into code or a prompt. (`LEAK3`)
5. **No live outbound at import or in the default test suite** — calls are gated behind an explicit
   flag + the consent allowlist + the budget guard. (`ENV4`, `CON4`)
6. **Numbers are verified, never asserted** — any cost/booking/metric reported in the video or a
   handback is read from the source (the receipt, the calendar, the computed rubric), never copied from
   a stale draft. (mirrors the methodology's verify-every-number rule)

---

## 6. Resiliency boundaries  (QA: `CALL1`, `CONV6`, `VOICE2`)
- Every external failure (platform error, webhook timeout, calendar 5xx, OpenAI hiccup) becomes a
  **structured result**, surfaced and recovered — it never crashes the server or the campaign runner.
- Webhooks are **signature-verified** (`VAPI_WEBHOOK_SECRET`); an unverified webhook is rejected, not
  processed (`VOICE2`).
- An **uncaught Python exception anywhere is a defect.** `app/server.py` handlers and
  `app/orchestrate.py` are exception-safe end to end; component failures are data, not crashes.

---

## 7. Logging & literals
- **The two byte-exact, contractual strings** are `DISCLOSURE_LINE` and `FAILSAFE_HANGUP_LINE` (§9).
  They are module constants so they cannot drift; eval asserts them byte-for-byte (`CON2`, `CONV6`).
- Run logging is our own observability convention: a single structured logger writes call lifecycle
  events (placed / disclosed / pitched / objection / booked / disposition / cost) to stdout and a
  local log. **A log line never contains a secret, a full real phone number (mask all but last 2
  digits), or the card number.** (`SEC1`, `LEAK2`)

---

## 8. Service authoring & deterministic run workflow  *(the "notebook discipline", re-expressed for a service)*

> Asaf chose a service repo over a notebook (NOTES 2026-06-23). The *discipline* a clean notebook
> would have enforced is preserved here and is **non-negotiable**.

- **Strict module ordering, one responsibility per module.** `config.py` is the *only* home for
  constants/literals/lazy getters. No business logic in the logger; no policy logic buried inside a
  tool — governance lives in `budget.py`/`consent.py`/the gateway helpers. The layout in §2 is the order.
- **The offline `pytest` suite is the "Restart & Run All" equivalent:** `make test` must run **clean,
  top to bottom, from a fresh checkout, with no network and no secrets**, and is **fully deterministic**
  — `RANDOM_SEED` seeds every stochastic offline component (the simulated callee, any sampling). Same
  input ⇒ same eval numbers, every run. No hidden state between tests (fixtures reset lazy singletons).
- **No dead/scratch code in the shipped tree** — no commented-out experiments, no unused branches, no
  `TODO`-only modules. What ships is what runs.
- **Every step is documented** — `README.md` narrates the run-from-clean-checkout; each module carries a
  top docstring stating its single responsibility; `data/value_prop.md` documents the assumed pitch.
  (This replaces the notebook's markdown narrative cells.)
- **TDD first.** For each module/tool the matching `QA_checklist.md` check is written before the code
  and must pass before the module is "done."
- **No magic values inline** — every number/threshold/literal is a named constant in §9 / `config.py`.
- **Default authoring mode:** draft a non-trivial change as a labelled, copy-pasteable block for review
  before it lands; state clearly whether it is *drafted only* or *written and test-verified*.

---

## 9. Stable names & conventions

```python
# --- budget / spend governance ---
HARD_BUDGET_USD        = 50.00     # absolute ceiling (the provided card limit)
LIVE_CALL_BUDGET_USD   = 15.00     # soft reserve for live calls (lean posture)
MAX_COST_PER_CALL_USD  = 1.00      # per-call projected-cost ceiling
MAX_LIVE_CALLS         = 6         # lean live eval-set ceiling
BUDGET_ALARM_ROUNDING_MARGIN = Decimal("0.01")  # post-hoc over-cap alarm tolerance in record_cost (F1 2026-06-23; the pre-call gate budget_permits is exact and does NOT use this)

# --- call governance ---
MAX_CALL_DURATION_S    = 300       # hard per-call wall-clock
MAX_AGENT_TURNS        = 40        # anti-loop cap on conversation turns
DAILY_CALL_CAP         = 25        # outbound throttle / day
CALL_RETRY_MAX         = 2         # retries on no-answer
VOICEMAIL_MAX_S        = 30        # leave-voicemail cap
ANSWER_DETECTION_S     = 20        # ring/answer timeout

# --- booking ---
BOOKING_SLOT_MINUTES   = 30
BOOKING_LOOKAHEAD_DAYS = 10

# --- providers / models / determinism ---
REALTIME_MODEL         = "gpt-4o-realtime-preview"   # OQ-VOICE-1 LOCKED; still verified vs the real install at ENV2
VOICE_PROVIDER         = "vapi"                       # managed; Retell-swappable behind the adapter
RANDOM_SEED            = 42

# --- byte-exact graded literals ---
DISCLOSURE_LINE        = "Hi, this is Aria, an AI assistant calling on behalf of Alta. This call may be recorded for quality. Do you have a quick minute?"
FAILSAFE_HANGUP_LINE   = "Thanks for your time — I'll follow up by email. Goodbye."

# --- the agent's callable functions (name == schema name == dispatch key) ---
AGENT_TOOLS = ["check_availability", "book_meeting", "log_disposition", "detect_voicemail", "end_call"]
```

- The voice-provider interface (`VoiceProvider`: `configure_assistant`, `place_call`,
  `fetch_call_cost`) and the calendar interface (`CalendarProvider`: `list_slots`, `create_event`) are
  the **only** ways out to those services — guard the implementations behind them so the vendor is a swap.
- Tool function name == schema name == dispatch key; a mismatch breaks dispatch — guard with an
  import-time `assert` over `AGENT_TOOLS`.
- Avoid vague names (`tmp`, `do_thing`). Helpers say what they do (`consent_allows`, `budget_permits`,
  `mask_phone`, `score_transcript`).

---

## 10. Non-negotiable quality rules (the short list)
1. **Import-safe.** No side effects, no client, no `.env`, no call at import (§3.4, `ENV4`).
2. **No secrets in tracked files.** Card number + all keys via env only (§5 anti-leakage, `SEC1`/`LEAK1`).
3. **Consent before dialing.** Allowlist + `do_not_call` enforced at one chokepoint (`CON1`/`CON5`).
4. **Disclosure first, byte-exact.** `DISCLOSURE_LINE` opens every call (`CON2`).
5. **Budget is hard.** Per-call + cumulative caps enforced before `place_call` (`SEC3`/`CALL4`).
6. **Caps are hard.** Turn cap + wall-clock cap → failsafe hangup (`CONV5`/`CONV6`).
7. **Inputs by name, validated, never hardcoded.** Synthetic lead/ICP/value-prop from `data/*` (`LEAD1`/`LEAK3`).
8. **Fail loudly in components, never crash the server/runner.** Errors are data (§6).
9. **Deterministic offline suite.** `make test` is reproducible, seeded, network-free (`EVAL1`, §8).
10. **TDD.** A stage is done only when its referenced `QA_checklist.md` checks **pass — run, not inspected.**

---

## 11. Completion checklist (per stage — ticked before every handback)
- [ ] The module(s) for this stage run without errors.
- [ ] Every `QA_checklist.md` check referenced by this stage's DoD **passes** (run, not inspected).
- [ ] Import-safety holds (`ENV4` re-proven from an empty dir, all lazy singletons `None`).
- [ ] No secret / card number / real PII in any tracked file (grep clean — `SEC1`/`LEAK1`/`LEAK2`).
- [ ] Consent + disclosure + budget chokepoints enforced and tested where the stage touches them.
- [ ] No hardcoded synthetic/real input values in code or prompts (`LEAK3`).
- [ ] Caps/literals byte-exact; offline suite still deterministic and green.
- [ ] Any number reported is verified against its source (receipt / calendar / computed rubric).
- [ ] `NOTES.md` updated with decisions, verified facts, and a handback.
- [ ] `PLAN.md` status ready for PM review (PM marks ✅, not the executer).

---

## 12. Claude Code handback format
When a stage is complete, report back with (and append to `NOTES.md`):
1. **What changed** — modules/sections drafted vs written; new tests; files touched.
2. **DoD checklist** — each referenced QA ID ✅ / ⚠️; *drafted only* vs *written and test-verified* separated.
3. **QA results** — which check IDs were run and their pass/fail (paste the salient output).
4. **Decisions made** — anything not explicitly specified (record in `NOTES.md`).
5. **Deviations** — anything different from `PLAN.md`, with reason.
6. **Blockers / risks** — unpinned deps, missing keys/numbers, consent gaps, budget exposure, compliance doubt.
7. **Next recommended action** — one concrete next step only.

Do not silently advance to the next stage. Do not mark a stage ✅ on the executer's word — the PM
re-runs the checks itself.
