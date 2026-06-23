"""Alta Outbound Voice Agent — app/orchestrate.py

Single responsibility: the campaign runner — iterates the synthetic lead list
and, for every lead, in this exact order:
  1. Suppress do_not_call=True leads (CON5).
  2. Consent gate (CON1) — consent_allows(phone_e164, do_not_call=...) must pass;
     a non-allowlisted number is refused with a structured disposition and NEVER
     reaches place_call.
  3. Budget guard (CALL4/SEC3) — budget_permits(projected_cost, is_live=...) must
     pass BEFORE dialing; over-budget ⇒ the campaign halts cleanly.
  4. Only then call the injected VoiceProvider.place_call(...).

Governance:
  - CALL1: any provider error / CallResult(ok=False) → structured disposition;
    campaign continues; no uncaught exception.
  - CALL2: a no-answer retries up to CALL_RETRY_MAX times, then dispositions.
  - CALL3: ≤ DAILY_CALL_CAP calls/day; the (N+1)th is DEFERRED (recorded), not
    silently dropped.
  - CALL4: budget guard runs BEFORE every dial (SEC3 cross-check).

Leads loader (LEAD1):
  load_leads() and load_icp() are the validated, runtime app loaders. They are
  promoted from tests/test_leads.py so the same logic runs in production and in
  tests (no duplicated logic). Tests import them from here.

Import-safety (ENV4):
  Importing this module defines ONLY constants, dataclasses, and functions.
  No VoiceProvider client is constructed, no .env is read, no data/* is read,
  no network call, no place_call at import. Clients are injected or resolved
  lazily when run() is called.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from app.config import (
    CALL_RETRY_MAX,
    DAILY_CALL_CAP,
    MAX_COST_PER_CALL_USD,
    RANDOM_SEED,
    REPO_ROOT,
)
from app.budget import BudgetLedger
from app.consent import consent_allows, mask_phone

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module constant: projected cost estimate used for the pre-dial budget guard.
# This is a per-call cost ESTIMATE (the actual cost is recorded after the call
# completes). Set conservatively at MAX_COST_PER_CALL_USD so we never permit a
# call whose worst-case cost would exceed the per-call ceiling.
# NOT a §9 constant — it is a local orchestration heuristic (the spec allows a
# "named module constant in orchestrate.py, NOT a §9 change").
# ---------------------------------------------------------------------------
PROJECTED_COST_PER_CALL: float = MAX_COST_PER_CALL_USD

# Required fields for a lead record (mirrors CLAUDE.md §4 / LEAD1)
_REQUIRED_LEAD_FIELDS = frozenset({"lead_id", "first_name", "company", "phone_e164"})


# ---------------------------------------------------------------------------
# Leads / ICP loaders — promoted from tests/test_leads.py (Stage 5, brief §)
# The test module now imports these to avoid duplicated logic (§8 / LEAD1).
# ---------------------------------------------------------------------------

def load_leads(path: Path | str) -> list[dict]:
    """Load and validate leads from *path*. Raises ValueError on schema error.

    LEAD1: every required field present → ValueError (not KeyError) on violation.
    No hardcoded lead/company/phone values in this code (LEAK3).
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Leads file not found: {p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Leads file is not valid JSON: {exc}") from exc

    if not isinstance(data, dict) or "leads" not in data:
        raise ValueError("Leads file must be a JSON object with a 'leads' key.")

    leads = data["leads"]
    if not isinstance(leads, list):
        raise ValueError("'leads' must be a JSON array.")

    for i, lead in enumerate(leads):
        missing = _REQUIRED_LEAD_FIELDS - set(lead.keys())
        if missing:
            raise ValueError(
                f"Lead at index {i} is missing required fields: {missing}. "
                "Required: lead_id, first_name, company, phone_e164."
            )

    return leads


def load_icp(path: Path | str) -> dict:
    """Load and validate ICP from *path*. Raises ValueError on schema error."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"ICP file not found: {p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"ICP file is not valid JSON: {exc}") from exc

    if not isinstance(data, dict) or "icp" not in data:
        raise ValueError("ICP file must be a JSON object with an 'icp' key.")
    return data["icp"]


# ---------------------------------------------------------------------------
# Structured disposition (the output of every call attempt, success or not)
# ---------------------------------------------------------------------------

@dataclass
class CallDisposition:
    """Structured outcome of one call attempt (CALL1 — never an exception).

    Fields:
      lead_id:    the lead's id.
      phone:      the masked phone (LEAK2: last 2 digits only).
      status:     one of: 'booked', 'declined', 'no_answer', 'voicemail',
                  'error', 'suppressed', 'consent_refused', 'budget_halted',
                  'daily_cap_deferred'.
      call_id:    the provider call_id (if a call was placed).
      cost_usd:   actual cost of the call (None if not placed/recorded).
      attempts:   how many dial attempts were made.
      notes:      free-text reason.
    """
    lead_id: str
    phone: str          # masked
    status: str
    call_id: str | None = None
    cost_usd: float | None = None
    attempts: int = 0
    notes: str = ""


# ---------------------------------------------------------------------------
# CampaignResult — the output of a full run() call
# ---------------------------------------------------------------------------

@dataclass
class CampaignResult:
    """Aggregate result of a campaign run.

    Attributes:
      dispositions:   one CallDisposition per lead processed.
      halted:         True if the campaign halted early (over-budget).
      halt_reason:    human-readable reason for a halt (or '').
      calls_placed:   total dials attempted (provider reached).
      daily_cap_hit:  True if the daily cap was reached.
    """
    dispositions: list[CallDisposition] = field(default_factory=list)
    halted: bool = False
    halt_reason: str = ""
    calls_placed: int = 0
    daily_cap_hit: bool = False


# ---------------------------------------------------------------------------
# _dial_one — the single-lead dial loop (retry on no_answer)
# ---------------------------------------------------------------------------

def _dial_one(
    lead: dict,
    *,
    provider: Any,
    assistant: dict,
    ledger: BudgetLedger,
    allowlist: frozenset[str] | None,
    is_live: bool,
) -> tuple[CallDisposition, bool]:
    """Place a call for *lead* with retries; return (disposition, budget_ok).

    budget_ok=False means the budget was exhausted mid-retry; the caller must
    halt the campaign after recording the disposition.

    The consent gate and budget guard are the ONLY code paths to place_call.
    This function is the single chokepoint — no path bypasses them (CON1/CALL4).
    """
    lead_id = lead["lead_id"]
    phone = lead["phone_e164"]
    masked = mask_phone(phone)

    for attempt in range(1, CALL_RETRY_MAX + 2):  # 1, 2, 3 (max_retries+1 = 3 attempts)
        # -- budget guard (SEC3/CALL4): MUST run before EVERY dial attempt --
        if not ledger.budget_permits(PROJECTED_COST_PER_CALL, is_live=is_live):
            logger.warning(
                "Budget exhausted before dial attempt %d for lead %s (%s)",
                attempt, lead_id, masked,
            )
            return (
                CallDisposition(
                    lead_id=lead_id,
                    phone=masked,
                    status="budget_halted",
                    attempts=attempt - 1,
                    notes="Campaign budget exhausted; call not placed.",
                ),
                False,  # signal: halt the campaign
            )

        logger.info(
            "Dialing lead %s (%s), attempt %d/%d",
            lead_id, masked, attempt, CALL_RETRY_MAX + 1,
        )

        try:
            result = provider.place_call(to_number=phone, assistant=assistant)
        except Exception as exc:  # noqa: BLE001 — §6: component failures are data
            logger.error("Provider raised on dial %s attempt %d: %s", lead_id, attempt, exc)
            if attempt > CALL_RETRY_MAX:
                return (
                    CallDisposition(
                        lead_id=lead_id,
                        phone=masked,
                        status="error",
                        attempts=attempt,
                        notes=f"Provider exception: {exc}",
                    ),
                    True,
                )
            continue  # retry

        if not result.ok:
            error_msg = result.message or result.error or "unknown error"
            logger.warning("Call failed for %s attempt %d: %s", lead_id, attempt, error_msg)
            if attempt > CALL_RETRY_MAX:
                return (
                    CallDisposition(
                        lead_id=lead_id,
                        phone=masked,
                        status="error",
                        attempts=attempt,
                        call_id=result.call_id,
                        notes=error_msg,
                    ),
                    True,
                )
            continue  # retry

        # -- call placed successfully; record cost --
        call_id = result.call_id
        actual_cost = 0.0
        try:
            cost_result = provider.fetch_call_cost(call_id=call_id)
            if cost_result.ok and cost_result.cost_usd is not None:
                actual_cost = cost_result.cost_usd
                ledger.record_cost(actual_cost, is_live=is_live)
            else:
                logger.warning(
                    "Could not fetch cost for call %s (%s): %s",
                    call_id, lead_id, cost_result.message,
                )
        except Exception as exc:  # noqa: BLE001 — cost fetch failure is not fatal
            logger.warning("Cost fetch raised for call %s: %s", call_id, exc)

        # Determine disposition from the call status.
        # "no_answer" is the only provider status that triggers a retry (CALL2).
        # All other statuses (queued, ringing, in-progress, ended, booked, etc.)
        # mean the call was accepted / connected — no retry needed.
        raw_status = result.status or ""

        # Map provider statuses to canonical dispositions
        if raw_status == "no_answer":
            disp_status = "no_answer"
        elif raw_status in {"booked"}:
            disp_status = "booked"
        elif raw_status in {"declined"}:
            disp_status = "declined"
        elif raw_status in {"voicemail"}:
            disp_status = "voicemail"
        else:
            # queued / ringing / in-progress / ended / unknown → call placed;
            # final outcome delivered via webhook; record as the raw status.
            disp_status = raw_status or "placed"

        if disp_status == "no_answer" and attempt <= CALL_RETRY_MAX:
            logger.info("No answer on lead %s attempt %d; will retry", lead_id, attempt)
            continue  # retry

        return (
            CallDisposition(
                lead_id=lead_id,
                phone=masked,
                status=disp_status,
                call_id=call_id,
                cost_usd=actual_cost,
                attempts=attempt,
            ),
            True,
        )

    # Exhausted all retries with no_answer
    return (
        CallDisposition(
            lead_id=lead_id,
            phone=masked,
            status="no_answer",
            attempts=CALL_RETRY_MAX + 1,
            notes="Exhausted retries with no answer.",
        ),
        True,
    )


# ---------------------------------------------------------------------------
# run() — the public campaign runner
# ---------------------------------------------------------------------------

def run(
    leads: list[dict],
    *,
    provider: Any,
    assistant: dict | None = None,
    ledger: BudgetLedger | None = None,
    allowlist: frozenset[str] | None = None,
    is_live: bool = False,
    today: date | None = None,
) -> CampaignResult:
    """Run the outbound campaign over *leads*.

    For each lead, in exact order:
      1. Suppress do_not_call=True (CON5).
      2. Consent gate — consent_allows() before place_call (CON1).
      3. Budget guard — budget_permits() before place_call (CALL4/SEC3).
      4. Dial via provider.place_call() (CALL1/CALL2).
      5. Enforce daily cap (CALL3).

    Args:
      leads:     a list of validated lead dicts (from load_leads()).
      provider:  a VoiceProvider instance (use FakeVoiceProvider in tests).
      assistant: the pre-built assistant config dict (if None, built from provider).
      ledger:    a BudgetLedger instance (if None, the module-level singleton is used).
      allowlist: explicit allowlist frozenset for tests (if None, loads from env).
      is_live:   True for live calls (applies live sub-caps in the ledger).
      today:     the reference date for the daily cap (if None, uses UTC today).

    Returns:
      CampaignResult with one CallDisposition per lead.
    """
    result = CampaignResult()
    effective_ledger = ledger if ledger is not None else _get_default_ledger()
    if today is None:
        today = datetime.now(timezone.utc).date()

    if assistant is None:
        assistant = provider.configure_assistant()

    calls_today = 0

    for lead in leads:
        lead_id = lead.get("lead_id", "<unknown>")
        phone = lead.get("phone_e164", "")
        masked = mask_phone(phone) if phone else "<no-phone>"
        do_not_call = bool(lead.get("do_not_call", False))

        # -- STEP 1: suppress do_not_call leads (CON5) -----------------------
        if do_not_call:
            logger.info("Suppressing DNC lead %s (%s)", lead_id, masked)
            result.dispositions.append(CallDisposition(
                lead_id=lead_id,
                phone=masked,
                status="suppressed",
                notes="do_not_call=True; suppressed before consent check.",
            ))
            continue

        # -- STEP 2: consent gate (CON1) — SINGLE CHOKEPOINT -----------------
        if not consent_allows(phone, do_not_call=do_not_call, allowlist=allowlist):
            logger.info("Consent refused for lead %s (%s)", lead_id, masked)
            result.dispositions.append(CallDisposition(
                lead_id=lead_id,
                phone=masked,
                status="consent_refused",
                notes="Number not on the consent allowlist; call not placed.",
            ))
            continue

        # -- STEP 3: daily cap (CALL3) — deferred, not dropped ---------------
        if calls_today >= DAILY_CALL_CAP:
            logger.warning(
                "Daily cap (%d) reached; deferring lead %s (%s)",
                DAILY_CALL_CAP, lead_id, masked,
            )
            result.dispositions.append(CallDisposition(
                lead_id=lead_id,
                phone=masked,
                status="daily_cap_deferred",
                notes=f"Daily cap of {DAILY_CALL_CAP} reached; deferred.",
            ))
            result.daily_cap_hit = True
            continue

        # -- STEP 4: budget guard (CALL4/SEC3) + dial (CALL1/CALL2) ----------
        disposition, budget_ok = _dial_one(
            lead,
            provider=provider,
            assistant=assistant,
            ledger=effective_ledger,
            allowlist=allowlist,
            is_live=is_live,
        )

        result.dispositions.append(disposition)

        if disposition.status not in ("suppressed", "consent_refused",
                                      "daily_cap_deferred", "budget_halted"):
            calls_today += 1
            result.calls_placed += 1

        logger.info(
            "Lead %s (%s) disposition: %s (attempts=%d, cost=$%.4f)",
            lead_id, masked, disposition.status,
            disposition.attempts, disposition.cost_usd or 0.0,
        )

        # -- STEP 5: halt on over-budget (CALL4) -----------------------------
        if not budget_ok:
            result.halted = True
            result.halt_reason = (
                f"Budget exhausted after {result.calls_placed} call(s); "
                "remaining leads not dialed."
            )
            logger.warning("Campaign halted: %s", result.halt_reason)
            break

    return result


# ---------------------------------------------------------------------------
# Lazy default ledger helper (avoids module-level side effects — ENV4)
# ---------------------------------------------------------------------------

def _get_default_ledger() -> BudgetLedger:
    """Return the module-level BudgetLedger singleton (never constructed at import)."""
    from app.budget import get_ledger
    return get_ledger()
