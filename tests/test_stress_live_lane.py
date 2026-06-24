"""Stress tests — the live stress-lane gating, exercised entirely offline."""

from __future__ import annotations

from decimal import Decimal

import scripts.stress_live as sl
from app.budget import BudgetLedger

CONSENTED = "+15550000001"
NOT_CONSENTED = "+15559999999"
ALLOW = frozenset({CONSENTED})


def test_stress_lane_halts_at_live_count_ceiling(fake_voice_provider):
    ledger = BudgetLedger(max_live_calls=3)        # small stress ceiling for the test
    outcomes = sl.run_stress_lane(
        [CONSENTED] * 10,
        provider=fake_voice_provider,
        ledger=ledger,
        allowlist=ALLOW,
        projected_cost=0.10,
        max_calls=10,
    )
    placed = [o for o in outcomes if o.status == "placed"]
    assert len(placed) == 3                         # stopped exactly at the count cap
    assert outcomes[-1].status == "budget_halted"
    # Spy: the provider was NEVER dialed past the gate.
    assert len(fake_voice_provider.calls_placed) == 3
    assert ledger.live_call_count == 3


def test_stress_lane_halts_at_dollar_reserve(fake_voice_provider):
    ledger = BudgetLedger(live_budget=Decimal("0.25"), max_live_calls=100)
    outcomes = sl.run_stress_lane(
        [CONSENTED] * 10,
        provider=fake_voice_provider,
        ledger=ledger,
        allowlist=ALLOW,
        projected_cost=0.10,
        max_calls=10,
    )
    placed = [o for o in outcomes if o.status == "placed"]
    # FakeVoiceProvider reports $0.12/call → 2 calls = $0.24; a 3rd would exceed $0.25.
    assert len(placed) == 2
    assert outcomes[-1].status == "budget_halted"
    assert ledger.live_cumulative <= 0.25


def test_stress_lane_refuses_non_consented_number(fake_voice_provider):
    ledger = BudgetLedger(max_live_calls=10)
    outcomes = sl.run_stress_lane(
        [NOT_CONSENTED],
        provider=fake_voice_provider,
        ledger=ledger,
        allowlist=ALLOW,
        projected_cost=0.10,
        max_calls=10,
    )
    assert [o.status for o in outcomes] == ["consent_refused"]
    # The consent chokepoint held — the provider was never dialed.
    assert fake_voice_provider.calls_placed == []
