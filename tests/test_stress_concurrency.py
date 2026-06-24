"""Stress tests — concurrency and infrastructure load."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from app.budget import BudgetLedger
from app.consent import consent_allows
from app import tools
from app.calendar_client import MockCalendar


def _iso(hour: int) -> str:
    return datetime(2026, 6, 30, hour, 0, tzinfo=timezone.utc).isoformat()


# ===========================================================================
# STR-C1 — the budget guard is sound when used sequentially
# ===========================================================================

def test_str_c1_sequential_budget_guard_is_sound():
    """Recording up to the hard cap sequentially makes the guard refuse the next dial."""
    led = BudgetLedger()  # in-memory; default $50 hard cap, $1/call ceiling
    for _ in range(50):
        assert led.budget_permits(1.0) is True
        led.record_cost(1.0)
    assert led.cumulative == 50.0
    # Cumulative is at the hard cap — any further projected spend is refused.
    assert led.budget_permits(0.01) is False
    assert led.budget_permits(1.0) is False


# ===========================================================================
# STR-C2 — the consent gate is a pure stateless read (safe under concurrency)
# ===========================================================================

def test_str_c2_consent_gate_concurrent_is_consistent():
    allow = frozenset({"+15550000001"})

    def check(number: str) -> bool:
        return consent_allows(number, allowlist=allow)

    with ThreadPoolExecutor(max_workers=16) as ex:
        allowed = list(ex.map(check, ["+15550000001"] * 100))
        denied = list(ex.map(check, ["+15559999999"] * 100))

    assert all(allowed)
    assert not any(denied)


# ===========================================================================
# STR-C3 — booking idempotency: sequential convergence + concurrent no-crash
# ===========================================================================

def test_str_c3_book_idempotent_sequential():
    cal = MockCalendar()
    iso = _iso(15)
    r1 = tools.book_meeting(calendar=cal, lead_id="L", slot_start_iso=iso)
    r2 = tools.book_meeting(calendar=cal, lead_id="L", slot_start_iso=iso)
    assert r1.ok and r2.ok
    assert r1.data["event_id"] == r2.data["event_id"]   # same id, no double-book


def test_str_c3_book_concurrent_does_not_crash_and_converges():
    """Concurrent identical bookings never raise; a later sequential call converges.

    Exactly-once across threads is NOT guaranteed (MockCalendar is not thread-safe
    by design; Cal.com's 409 is the real cross-process guard). The honest invariant
    is: no crash, all structured-ok, and post-hoc idempotent convergence.
    """
    cal = MockCalendar()
    iso = _iso(15)

    def book(_):
        return tools.book_meeting(calendar=cal, lead_id="L", slot_start_iso=iso)

    with ThreadPoolExecutor(max_workers=16) as ex:
        results = list(ex.map(book, range(50)))

    assert all(r.ok for r in results)
    final = tools.book_meeting(calendar=cal, lead_id="L", slot_start_iso=iso)
    assert final.ok and final.data["event_id"]


# ===========================================================================
# STR-C6 — distinct leads do not bleed state
# ===========================================================================

def test_str_c6_distinct_leads_no_state_bleed():
    cal = MockCalendar()
    rA = tools.book_meeting(calendar=cal, lead_id="leadA", slot_start_iso=_iso(15))
    rB = tools.book_meeting(calendar=cal, lead_id="leadB", slot_start_iso=_iso(16))
    assert rA.ok and rB.ok
    assert rA.data["event_id"] != rB.data["event_id"]

    # leadB cannot grab leadA's slot — no overwrite, structured slot_taken.
    conflict = tools.book_meeting(calendar=cal, lead_id="leadB", slot_start_iso=_iso(15))
    assert conflict.ok is False and conflict.error == "slot_taken"

    # A disposition is keyed to exactly the lead it was logged for (no bleed).
    dA = tools.dispatch("log_disposition", lead_id="leadA", disposition="booked")
    assert dA.ok and dA.data["lead_id"] == "leadA"


# ===========================================================================
# STR-C7 — cross-process budget TOCTOU demonstrated DETERMINISTICALLY
# ===========================================================================

def test_str_c7_cross_process_toctou_two_ledgers_same_path(tmp_path):
    """Two ledgers on one persist file model two processes: the cap under-counts.

    This is the documented, ACCEPTED Stage-8 limitation (no cross-process lock; a
    portable lock conflicts with the graded OS-agnostic rule). The mitigation is the
    operating constraint: run live calls SEQUENTIALLY. This test pins the behavior so
    nobody assumes a cap that isn't there.
    """
    path = tmp_path / "ledger.json"
    a = BudgetLedger(persist_path=path)  # "process A" — loads $0
    b = BudgetLedger(persist_path=path)  # "process B" — also loads $0

    amount = 0.90
    # Both pass the guard independently (neither has recorded yet).
    assert a.budget_permits(amount, is_live=True) is True
    assert b.budget_permits(amount, is_live=True) is True

    # Both record; B's save overwrites A's — the persisted total under-counts.
    a.record_cost(amount, is_live=True)
    b.record_cost(amount, is_live=True)

    persisted = json.loads(path.read_text(encoding="utf-8"))
    # Real spend was 2*amount = $1.80, but the file reflects only one view.
    assert float(persisted["cumulative"]) < 2 * amount
