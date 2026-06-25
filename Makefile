# Alta Outbound Voice Agent — Makefile
# One-command paths from a clean checkout (CLAUDE.md §1).
# Python: 3.11+ (uses python3.13 if available, else python3.11, else python3)

PYTHON := $(shell command -v python3.13 2>/dev/null || command -v python3.11 2>/dev/null || command -v python3)
VENV   := .venv
PIP    := $(VENV)/bin/pip
PYTEST := $(VENV)/bin/pytest
UVICORN := $(VENV)/bin/uvicorn

.PHONY: install test serve call preflight inspect score eval receipts

## install — create .venv and install all pinned deps
install:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip --quiet
	$(PIP) install -r requirements.txt --quiet
	@echo "Install complete. Activate: source .venv/bin/activate"

## test — offline deterministic suite (no .env, no network, no live call)
## The "Restart & Run All" equivalent (CLAUDE.md §8).
test:
	$(PYTEST) tests/ -v

## preflight — pre-live readiness check (no secret VALUE is ever printed)
## Confirms required settings are present + the consent allowlist loads, then
## prints a PASS/FAIL verdict. Run this before `make call`. Exit 0 = ready.
preflight:
	$(VENV)/bin/python scripts/preflight.py

## serve — start the FastAPI webhook server (no call placed, no live cost)
## Exercised from Stage 4 when app.server lands. Safe to run now: just boots.
serve:
	$(UVICORN) app.server:app --reload --host 0.0.0.0 --port 8000

## call — GATED live-call launcher (Stage 5 wired; Stage 8 provisioning required)
## Routes through consent_allows + budget_permits before place_call (CON1/SEC3).
## Requires: a real consented number on the allowlist + a filled .env.
## Usage: make call TO=+15551234567
call:
ifndef TO
	@echo "ERROR: 'make call' requires a target number."
	@echo "Usage: make call TO=<e164_number>"
	@echo "Example: make call TO=+15551234567"
	@echo ""
	@echo "No call was placed. No cost incurred."
	@exit 1
else
	$(VENV)/bin/python scripts/place_demo_call.py $(TO)
endif

## inspect — print a live call's timestamped transcript + interruption markers
## Read-only diagnostic for the live call experience (e.g. "not finishing sentences":
## look for ARIA lines flagged (INTERRUPTED)). Needs VAPI_API_KEY in .env.
## Usage: make inspect CALL_IDS="019ef883 019ef86c"
inspect:
ifndef CALL_IDS
	@echo "ERROR: 'make inspect' requires one or more Vapi call ids."
	@echo "Usage: make inspect CALL_IDS=\"019ef883 019ef86c\""
	@exit 1
else
	$(VENV)/bin/python scripts/inspect_call.py $(CALL_IDS)
endif

## score — Bug-2 live proof: did the agent CALL qualify + tailor the pitch?
## Scores a real call with rubric.pitch_tailored + reports the qualify round-trip
## latency. Newest call if CALL_ID is omitted. Needs VAPI_API_KEY in .env.
## Usage: make score CALL_ID=019ef90c-...   (or just: make score)
score:
	$(VENV)/bin/python scripts/score_call.py $(CALL_ID)

## eval — print the offline eval summary + A/B bake-off (the numbers shown in the video)
## Deterministic, seeded, network-free; no .env, no call. The VID2 evidence command.
eval:
	$(VENV)/bin/python -m app.eval

## receipts — capture redacted per-call cost receipts → receipts/<call_id>.json
## Read-only GET against the voice platform; needs VAPI_API_KEY in .env. The $50 proof.
## Usage: make receipts CALL_IDS="019ef8f2-... 019ef883-..."
receipts:
ifndef CALL_IDS
	@echo "ERROR: 'make receipts' requires one or more Vapi call ids."
	@echo "Usage: make receipts CALL_IDS=\"019ef8f2-... 019ef883-...\""
	@exit 1
else
	$(VENV)/bin/python scripts/capture_receipts.py $(CALL_IDS)
endif
