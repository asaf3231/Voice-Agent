# QA_checklist.md — Test-Driven-Development Blueprint

Project: **Alta Outbound Voice Agent ("Aria")**
Maintained by: Asaf

> This file is the verification contract. `CLAUDE.md` defines the rules, `PLAN.md` tracks the stages,
> `NOTES.md` records decisions. **Every stage in `PLAN.md` lists the check IDs below as its Definition
> of Done.** A stage is not "done" until its referenced checks pass — *run, not inspected*. Checks are
> written **before** the matching code (test-first). Each has a stable ID (e.g. `CON2`, `EVAL3`,
> `SEC1`) so `PLAN.md` can reference it without ambiguity.
>
> **Live vs offline:** the default suite (`make test`) is **offline, deterministic, network-free, and
> places no call**. Checks marked **(live, gated)** require keys + budget + a consented number; they are
> `@pytest.mark.skipif`-gated and **SKIPPED (not failed)** when prerequisites are absent — mirroring the
> reference project's gated live smokes.

---

## §0. Harness, environment & fixtures

| ID | Check | Method | Pass condition |
|---|---|---|---|
| `ENV1` | Fresh-venv install | `python -m venv .venv && pip install -r requirements.txt` | Exit 0; all pins resolve |
| `ENV2` | Every import is pinned | grep each non-stdlib import against `requirements.txt`; assert each has `==` | No imported module unpinned |
| `ENV3` | One-command clean run | `make test` then `make serve` from a fresh checkout (no `.env`/keys) | Suite green; server boots; **no call placed, no cost** |
| `ENV4` | **Import-safety** | `python -c "import app.config, app.server, app.tools, app.orchestrate, app.budget, app.consent"` from an empty dir, no `.env`, no network | Exit 0; **zero** side effects (no client built, no `.env` read, no `data/*` read, no call); all lazy singletons `None`. The single most important environment check |

**Shared fixtures**
- `tmp_leads_json` — a small schema-valid `leads.synthetic.json` (≥1 normal lead, ≥1 `do_not_call=True`).
- `tmp_icp_json`, `tmp_value_prop` — minimal valid ICP + value-prop.
- `tmp_allowlist` — a consent allowlist with one allowed number and one number deliberately absent.
- `FakeVoiceProvider` — a `VoiceProvider` stand-in: `place_call(...)` returns a scripted call result
  (transcript, duration, cost) from a queue; can be set to raise / return an error; **never networks**.
- `FakeCalendar` — a `CalendarProvider` stand-in with controllable free/busy slots; idempotent.
- `SimulatedCallee` — the seeded (`RANDOM_SEED`) persona simulator: cooperative / objecting / no-answer
  / voicemail personas for offline conversation eval.
- `frozen_clock` — deterministic time so durations/booking windows are reproducible.

---

## §1. Secrets & budget governance (`SEC*`)

| ID | Check | Pass condition |
|---|---|---|
| `SEC1` | No secret in any tracked file | grep for key patterns, the Vapi/OpenAI tokens, **and the assignment card number (16-digit PAN / its 4-4-4-4 grouping — *not* the bare 3-digit CVV, which false-positives on ports/line numbers)** across all tracked files → zero hits; `.env` gitignored; `.env.example` placeholders only; **`Home_Assignment_email.md` (redacted) and `REFERENCE/` are gitignored and never tracked** |
| `SEC2` | Budget ledger correctness | `app/budget.py` tracks cumulative spend deterministically; recording a cost updates the ledger; unit-tested at boundaries |
| `SEC3` | Hard cap enforced before dialing | `budget_permits(projected)` returns False when `projected > MAX_COST_PER_CALL_USD` **or** `cumulative + projected > HARD_BUDGET_USD`; `place_call` is unreachable when it returns False (spy: provider never called) — proven for **both** entry points (`orchestrate.py` *and* `scripts/place_demo_call.py`) |
| `SEC4` | Live sub-caps | live runs respect `LIVE_CALL_BUDGET_USD` and `MAX_LIVE_CALLS`; the (N+1)th live call is refused |
| `SEC5` | Receipts captured | `scripts/capture_receipts.py` writes a per-call cost record (redacted) under `receipts/`; the figure equals the provider's reported `fetch_call_cost` (verified, not asserted) |

---

## §2. Consent & compliance (`CON*`)

| ID | Check | Pass condition |
|---|---|---|
| `CON1` | Allowlist gate | `consent_allows(number)` True only for allowlisted numbers; a non-allowlisted number is refused with a structured result and **never** reaches `place_call` (spy). **Allowlist source validates on load** (analogous to `LEAD1`): a malformed/empty allowlist is a clean explicit error, not silent allow-none. **Both entry points gated** — `orchestrate.py` *and* `scripts/place_demo_call.py` are spy-proven to pass through `consent_allows` before `place_call` |
| `CON2` | **Disclosure first, byte-exact** | the first utterance on every call equals `DISCLOSURE_LINE` byte-for-byte; pinned to the platform's **static first-message** feature (spoken verbatim, **not** a prompt instruction the Realtime model could paraphrase); asserted byte-exact in the assistant config (`VOICE1`) + the offline conversation eval, and verified from the real transcript live (`LIVE2`) |
| `CON3` | Recording enabled with the disclosure payload | `recordingEnabled: True` ships in the **same static-first-message payload** as `DISCLOSURE_LINE` (the AI disclosure). **Decision 2026-06-24 (Asaf):** the spoken *recording notice* was dropped from `DISCLOSURE_LINE` (AI self-id retained); recording stays **on**. Lawful for the **one-party-consent** consented test line; a recording notice **must be restored before any two-party-consent / real-prospect use** |
| `CON4` | No live call at import / in default suite | `ENV4` cross-check + a grep/spy: the default `pytest` run places zero live calls (provider is always the fake) |
| `CON5` | `do_not_call` honored | a `do_not_call=True` lead is suppressed from the campaign regardless of fit |

---

## §3. Synthetic inputs (`LEAD*`)

| ID | Check | Pass condition |
|---|---|---|
| `LEAD1` | Validate on load | `data/leads.synthetic.json` parsed by name; required fields present; a missing/renamed field → clean explicit startup error, not a later `KeyError` |
| `LEAD2` | ICP + value-prop load | `data/icp.synthetic.json` + `data/value_prop.md` load and validate; the agent's assertable facts come only from these |
| `LEAD3` | No hardcoded input values | grep: no lead name/company/phone/ICP/value-prop literal appears in `app/` code or any prompt (`LEAK3` cross-check) |

---

## §4. Conversation / dialog policy (`CONV*`)

Driven by `SimulatedCallee` + `FakeVoiceProvider`, fully offline.

| ID | Check | Pass condition |
|---|---|---|
| `CONV1` | State machine stages | the policy advances through pitch → discovery → objection-handling → propose-slot → close; each stage is reachable and deterministic under a fixed persona |
| `CONV2` | Value-prop pitch present | against a cooperative persona, the agent delivers a value-prop drawn from `data/value_prop.md` before proposing a slot |
| `CONV3` | Objection handling | against an objecting persona (e.g. "not interested" / "send an email"), the agent responds with a scripted recovery, not a hang-up, before respecting a hard no |
| `CONV4` | Authoritative content bound | the agent asserts no Alta fact absent from `data/value_prop.md` (Policy 4); a probing persona cannot elicit an invented price/claim (`LEAK3` cross-check) |
| `CONV5` | Turn cap | a never-ending persona triggers the failsafe at `MAX_AGENT_TURNS`; no (N+1)th turn |
| `CONV6` | **Failsafe terminal, byte-exact** | on turn-cap / time-cap / error, the agent speaks `FAILSAFE_HANGUP_LINE` byte-for-byte and ends; clean disposition recorded |

---

## §5. Agent callable functions (`TOOL*`) & booking (`BOOK*`)

| ID | Check | Pass condition |
|---|---|---|
| `TOOL1` | `check_availability` | returns free slots within `BOOKING_LOOKAHEAD_DAYS` of `BOOKING_SLOT_MINUTES` each; **resolves the lead's `timezone` against the sales-calendar tz** (no "3pm in the wrong tz" booking); deterministic under `FakeCalendar`; no network |
| `TOOL2` | `book_meeting` idempotent | books a free slot; a repeat call for the same lead+slot does **not** double-book; a busy slot returns "offer another", never a silent overwrite |
| `TOOL3` | `log_disposition` | records a structured disposition (booked / declined / no-answer / voicemail / error); no secret or full phone number in the record |
| `TOOL4` | `detect_voicemail` | classifies a voicemail-greeting transcript; on detection, leave ≤ `VOICEMAIL_MAX_S` then end |
| `TOOL5` | `end_call` + dispatch identity | clean hangup; `AGENT_TOOLS` names == schema names == dispatch keys (import-time assert) |
| `BOOK1` | Slot listing | `CalendarProvider.list_slots` returns only genuinely free slots **with explicit timezone resolution** (lead tz ↔ calendar tz); sandbox backend by default |
| `BOOK2` | Event creation | `create_event` creates a `BOOKING_SLOT_MINUTES` event; returns a confirmation id the agent voices only after success |
| `BOOK3` | Conflict / no phantom booking | a race/conflict yields a structured "slot taken" → the agent re-offers; no confirmation is voiced without a created event (Policy 5) |

---

## §6. Voice-platform integration (`VOICE*`)

| ID | Check | Pass condition |
|---|---|---|
| `VOICE1` | Assistant config | `configure_assistant` builds a valid Vapi assistant payload wiring `REALTIME_MODEL`, the persona prompt, the 5 tool definitions, and `DISCLOSURE_LINE` **as the static first-message field (verbatim), asserted byte-exact** — not a prompt the model may reword; shape-validated offline. **A public HTTPS webhook tunnel + one signed end-to-end webhook smoke test over the public URL is a Stage-4 deliverable** (`make serve` localhost is unreachable by Vapi) |
| `VOICE2` | Webhook signature verify | an inbound webhook with a bad/missing `VAPI_WEBHOOK_SECRET` signature is rejected (401), never processed; a valid one is processed |
| `VOICE3` | Tool webhook dispatch | a tool-call webhook routes to the right `AGENT_TOOLS` function with validated args; an unknown tool → structured error, no crash |
| `VOICE4` | Import-safe lazy client | `_get_vapi()` builds the client on first use only; `ENV4` holds with `vapi_client` imported (singleton `None` at import) |
| `VOICE5` | Provider adapter swap | the `VoiceProvider` interface is the only egress; swapping the impl (Vapi↔fake/Retell) needs no change in `orchestrate.py`/`server.py` (design + test) |

---

## §7. Outbound orchestration (`CALL*`)

| ID | Check | Pass condition |
|---|---|---|
| `CALL1` | Resilient runner | a provider error / no-answer becomes a structured disposition; the campaign continues; no uncaught exception |
| `CALL2` | Retry on no-answer | a no-answer retries up to `CALL_RETRY_MAX`, then dispositions; not infinite |
| `CALL3` | Daily cap | the runner places ≤ `DAILY_CALL_CAP` calls/day; the (N+1)th is deferred, not dropped silently |
| `CALL4` | Budget guard pre-call | every call passes `budget_permits` **before** dialing (`SEC3` cross-check); over-budget ⇒ campaign halts cleanly with a recorded reason |

---

## §8. Offline evaluation harness (`EVAL*`) — the reproducible core

| ID | Check | Pass condition |
|---|---|---|
| `EVAL1` | Deterministic & offline | `make test` runs the eval network-free; `RANDOM_SEED` makes it reproducible — same input ⇒ same scores across runs (`ENV3` cross-check) |
| `EVAL2` | **Scores computed, not hardcoded** | the rubric is computed from each labeled transcript; no test asserts a metric by copying a literal outcome (`LEAK4` cross-check) |
| `EVAL3` | Rubric coverage | `rubric.py` scores: disclosure-said, pitch-delivered, objection-handled, meeting-booked, compliance-ok — each a checkable signal over a transcript |
| `EVAL4` | Persona matrix | the harness runs cooperative / objecting / no-answer / voicemail / probing personas; each yields the expected disposition |
| `EVAL5` | Aggregate metrics | the harness emits a deterministic summary (book-rate, disclosure-compliance, avg turns) over the persona set; figures reproducible for the video |
| `EVAL6` | Regression guard | a change that breaks disclosure-first or books-without-availability is caught by the eval (negative fixtures included) |

---

## §9. Live calling (`LIVE*`) — **(live, gated; SKIPPED without keys/budget/consented number)**

| ID | Check | Pass condition |
|---|---|---|
| `LIVE0` | **Provisioning readiness** (day-1, parallel) | Vapi account + outbound number provisioned (A2P/identity verification allowed for); Cal.com account + API key + event type configured; OpenAI Realtime access verified on the key; a public HTTPS webhook tunnel reachable. The #1 schedule risk — must be green before Stage 8 is attempted (Red-Team 2026-06-23) |
| `LIVE1` | One real booked call | a real outbound call to a consented test number opens with the disclosure, pitches, and books a real calendar event |
| `LIVE2` | Disclosure audible | the recording/transcript shows `DISCLOSURE_LINE` as the **verbatim** first utterance — verified from the real transcript, not assumed (`CON2`/`VOICE1` static-first-message live cross-check) |
| `LIVE3` | Cost within ceiling | the call's `fetch_call_cost` ≤ `MAX_COST_PER_CALL_USD`; cumulative ≤ `LIVE_CALL_BUDGET_USD` ≤ `HARD_BUDGET_USD` (verified from the receipt) |
| `LIVE4` | Receipt captured | a redacted receipt for the call lands under `receipts/` (`SEC5` live cross-check) |

---

## §10. Anti-leakage audit (`LEAK*`) — highest-leverage correctness gate

| ID | Check | Method | Pass condition |
|---|---|---|---|
| `LEAK1` | No secrets / no card number | grep keys/tokens + the card **16-digit PAN / its 4-4-4-4 grouping** (not the bare 3-digit CVV) over all tracked files; confirm `Home_Assignment_email.md` + `REFERENCE/` are gitignored | Zero hits; all via `os.environ` (`SEC1`); the two named files untracked |
| `LEAK2` | No real PII / recordings | grep for real E.164 numbers; check `.gitignore` covers recordings/transcripts/raw receipts | No real number/recording tracked; logs mask phones |
| `LEAK3` | No hardcoded business/lead data | grep lead/company/ICP/value-prop literals in `app/` + prompts | None; all read from `data/*` at runtime (`LEAD3`) |
| `LEAK4` | No fabricated outcomes | inspect tests/eval for hardcoded `booked=True`/canned scored transcripts | None; metrics computed (`EVAL2`) |
| `LEAK5` | OS-agnostic paths | grep absolute paths / `C:\\` / leading `/Users`; check `pathlib` use | No hardcoded absolute paths |

---

## §11. Packaging & video (`PKG*`, `VID*`)

| ID | Check | Pass condition |
|---|---|---|
| `PKG1` | Requirements pinned | every non-stdlib import in `requirements.txt` with `==` (`ENV2`) |
| `PKG2` | Clean-checkout run | fresh venv → `pip install` → `make test` green → `make serve` boots, no traceback (`ENV1`/`ENV3`) |
| `PKG3` | Allowlist packaging | ship from an explicit allowlist; exclude `.venv/`, real recordings/transcripts, raw `receipts/`, `.env`, `tests/` if required by submission rules |
| `PKG4` | `.gitignore` correctness | `.env`, recordings, raw receipts, `.venv` ignored; `.env.example` + synthetic fixtures tracked |
| `VID1` | Video covers the system | the explanation walks architecture → governance (budget/consent/disclosure) → a **live demo call booking a meeting** |
| `VID2` | Evidence shown | the video shows the **offline eval summary** and the **receipts** proving spend ≤ $50 |
| `VID3` | Length / clarity | within the expected length; reproducible claims (numbers shown match the receipts/eval output) |

---

## §12. Adversarial / load stress suite (`STR-*`) — Stage 8.5

The 100+-parallel tester-fleet blueprint. Full definitions + the exact mock
scenario/persona per case live in `docs/STRESS_TEST_ARCHITECTURE.md`. Each row is
tagged by execution tier: **OFFLINE** (deterministic harness, $0, where the fleet
fans out), **MOCK** (the local fault-injection bridge over the webhook+transcript
layer — `app/testing/mock_bridge.py`), **LIVE** (the bounded, sequential, gated
stress lane — `scripts/stress_live.py`). Implemented rows are runnable in `make test`.

| ID | Tier | Check | Pass condition |
|---|---|---|---|
| `STR-L1` | OFFLINE | Turn-cap hardness | every persona under a tight cap ends with `FAILSAFE_HANGUP_LINE` byte-exact; no turn past the cap |
| `STR-L2` | OFFLINE | Context overflow | a 200KB value-prop loads, disclosure stays first, no crash, compliance holds |
| `STR-L4/5` | OFFLINE | Prompt-injection / exfil | an INJECTION callee never makes the agent leak a secret/system-prompt or invent a claim |
| `STR-L7` | OFFLINE | Booking integrity | a voiced booking without a `booked=True` turn fails compliance (no phantom) |
| `STR-L9` | OFFLINE | Adversarial tool args | `tools.dispatch` returns structured errors for unknown tool / bad slot / missing lead_id / bad tz / extra kwargs — never a crash |
| `STR-L11` | OFFLINE | Slot re-offer (Bug 1) | `slot_reoffer_handled` is True on a re-offer, False on a collapse; the end-to-end runner guard is `xfail` until the re-offer loop lands |
| `STR-L14` | OFFLINE | Unicode / smart quotes | a unicode value-prop never drifts the graded literals; no failsafe drift |
| `STR-T2/T3` | MOCK | Lossy / noisy transcript | total loss → no false voicemail; a cue in noise still classifies |
| `STR-T5` | MOCK | Drop mid-call / empty envelope | structured `no_tool_call` / masked status ack, never a 500 |
| `STR-T6` | MOCK | Voicemail detect | greeting → leave ≤ `VOICEMAIL_MAX_S` then end; a human is not flagged |
| `STR-T8` | MOCK | Redelivery storm | the same tool webhook posted N× books exactly once (idempotent) |
| `STR-T9` | MOCK | Malformed envelopes | missing toolCallId / garbled args / flat form → structured result, no crash |
| `STR-T10` | MOCK | Disclosure pinned first | the assistant payload's static first-message == `DISCLOSURE_LINE` (offline proxy for `LIVE2`) |
| `STR-T1` | LIVE | Real barge-in | (gated) `interrupted` count from `scripts/inspect_call.py` on a live call |
| `STR-P1` | MOCK | Webhook TTFB | p95 of the compute-path tool webhook < the SLO (proposed 500ms) |
| `STR-P3` | MOCK | STT resilience | garbled human speech does not false-trigger voicemail |
| `STR-P5` | OFFLINE | Slow/failing backend | a timing-out calendar → structured `calendar_error`; a backend error → no phantom booking |
| `STR-C1` | OFFLINE | Sequential budget guard | recording to the hard cap makes the next dial refused (the guard is sound when used sequentially) |
| `STR-C2` | OFFLINE | Consent under concurrency | the stateless gate is consistent across 100 concurrent checks |
| `STR-C3` | OFFLINE | Booking idempotency | sequential repeats converge to one id; concurrent never crashes (Cal.com 409 is the cross-process guard) |
| `STR-C6` | OFFLINE | Session isolation | distinct leads do not bleed slot ownership / dispatch lead_id |
| `STR-C7` | OFFLINE | Cross-process budget TOCTOU | two ledgers on one state file under-count cumulative — the documented limitation that makes the live lane SEQUENTIAL |
| `STR-LIVE` | LIVE | Stress-lane gating | (offline-proven) the lane halts at `MAX_LIVE_STRESS_CALLS` and the $15 reserve, and refuses non-consented numbers — spy-proven no dial past a gate |

---

## Check-to-stage map (sanity)

| Stage | Checks |
|---|---|
| 0 setup | meta (this file set) |
| 1 env + secrets + budget + synthetic inputs | `ENV1`–`ENV4`, `SEC1`–`SEC4`, `LEAD1`–`LEAD3`, `CON1` (allowlist load), `LIVE0` (provisioning kickoff, day-1 parallel) |
| 2 conversation design | `CONV1`–`CONV6` |
| 3 agent functions + booking | `TOOL1`–`TOOL5`, `BOOK1`–`BOOK3` |
| 4 voice-platform integration | `VOICE1`–`VOICE5`, `CON2`–`CON3` |
| 5 orchestration + consent + budget guard | `CALL1`–`CALL4`, `CON1`, `CON4`, `CON5`, `SEC3` |
| 6 offline eval harness | `EVAL1`–`EVAL6` |
| 7 anti-leakage + packaging | `LEAK1`–`LEAK5`, `PKG1`–`PKG4` |
| 8 live calling (lean) | `LIVE0` (readiness gate), `LIVE1`–`LIVE4`, `SEC5` |
| 8.5 adversarial / load hardening | `STR-L*`, `STR-T*`, `STR-P*`, `STR-C*`, `STR-LIVE` (§12) |
| 9 video + demo | `VID1`–`VID3` |
