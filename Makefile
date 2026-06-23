# Alta Outbound Voice Agent — Makefile
# One-command paths from a clean checkout (CLAUDE.md §1).
# Python: 3.11+ (uses python3.13 if available, else python3.11, else python3)

PYTHON := $(shell command -v python3.13 2>/dev/null || command -v python3.11 2>/dev/null || command -v python3)
VENV   := .venv
PIP    := $(VENV)/bin/pip
PYTEST := $(VENV)/bin/pytest
UVICORN := $(VENV)/bin/uvicorn

.PHONY: install test serve call

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

## serve — start the FastAPI webhook server (no call placed, no live cost)
## Exercised from Stage 4 when app.server lands. Safe to run now: just boots.
serve:
	$(UVICORN) app.server:app --reload --host 0.0.0.0 --port 8000

## call — GATED live-call launcher (Stages 5/8 required)
## Refuses until consent + budget logic is wired in Stage 5/8.
call:
	@echo "ERROR: 'make call' is not yet enabled."
	@echo "The live call launcher (scripts/place_demo_call.py) requires:"
	@echo "  - Stage 5 consent + budget guard to be wired (CALL4/CON1)"
	@echo "  - Stage 8 live provisioning to be complete (LIVE0)"
	@echo "  - A real consented number: make call TO=<e164_number>"
	@echo ""
	@echo "No call was placed. No cost incurred."
	@exit 1
