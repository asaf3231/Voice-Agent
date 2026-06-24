"""Alta Outbound Voice Agent — scripts/stress_live.py

The GATED, SEQUENTIAL live STRESS-lane runner (`make stress-live`).

Authorized 2026-06-24 (Asaf — graded change): place up to MAX_LIVE_STRESS_CALLS
real calls SEQUENTIALLY to the consented numbers for telephony/latency sign-off,
spend bounded by LIVE_CALL_BUDGET_USD=$15 (the real limiter), the unchanged $50
HARD_BUDGET_USD, and the $1 per-call ceiling. SEQUENTIAL only: the persistent
budget ledger has a documented cross-process TOCTOU (STR-C7) — never run this
concurrently with `make call`/orchestrate against the live budget.

Governance (graded — same chokepoints as place_demo_call.py / orchestrate.py):
  - consent_allows() MUST pass before place_call (CON1/SEC3).
  - budget_permits(is_live=True) MUST pass before place_call (CALL4/SEC3) — this
    enforces the per-call $1, the $50 hard cap, the $15 live reserve, AND the live
    count ceiling (MAX_LIVE_STRESS_CALLS via the ledger's max_live_calls).
  - actual cost is recorded AFTER each call so the cumulative cap stays real.

The PM does NOT run this autonomously — it places real calls (real money). It is a
human-coordinated step (see docs/LIVE_RUNBOOK.md) and requires the recording-notice
compliance gate to be cleared for any number outside one-party-consent scope.

Import-safety (ENV4): no side effects at module level. The runnable core
`run_stress_lane(...)` takes injectables so the gating is OFFLINE-testable with a
fake provider; main() wires the real provider/ledger/allowlist inside the guard.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class StressCallOutcome:
    """One sequential stress-call outcome (structured; never an exception, §6)."""

    number_masked: str
    status: str                 # placed | consent_refused | budget_halted | place_failed
    call_id: str | None = None
    cost_usd: float | None = None


def run_stress_lane(
    numbers,
    *,
    provider,
    ledger,
    allowlist,
    projected_cost: float,
    max_calls: int,
    variant: str = "A",
):
    """Place up to *max_calls* gated, SEQUENTIAL live calls; return per-call outcomes.

    The chokepoint order per call is identical to place_demo_call.py:
      consent_allows → budget_permits(is_live=True) → place_call → record_cost.
    A consent failure skips that number; a budget/count failure HALTS the lane
    (the cap is reached). Never raises across this boundary (§6).

    Injectable (provider/ledger/allowlist) so the gating is offline-testable with a
    FakeVoiceProvider + an in-memory ledger — no real call, no network.
    """
    from app.consent import consent_allows, mask_phone

    outcomes: list[StressCallOutcome] = []
    placed = 0
    for number in numbers:
        if placed >= max_calls:
            break
        masked = mask_phone(number)

        # GATE 1 — consent (CON1): a non-consented number is skipped, never dialed.
        if not consent_allows(number, allowlist=allowlist):
            outcomes.append(StressCallOutcome(masked, "consent_refused"))
            continue

        # GATE 2 — budget/count (SEC3/CALL4): enforces $1 per-call, $50 hard, $15
        # live reserve, AND the live count ceiling. A block HALTS the lane.
        if not ledger.budget_permits(projected_cost, is_live=True):
            outcomes.append(StressCallOutcome(masked, "budget_halted"))
            break

        assistant = provider.configure_assistant(variant=variant)
        result = provider.place_call(to_number=number, assistant=assistant)
        if not result.ok:
            outcomes.append(StressCallOutcome(masked, "place_failed",
                                              call_id=result.call_id))
            continue

        # Record ACTUAL cost (fall back to the projected estimate) so the cumulative
        # cap can never slip past on a cost-fetch failure.
        cost = float(projected_cost)
        if result.call_id:
            cr = provider.fetch_call_cost(call_id=result.call_id)
            if cr.ok and cr.cost_usd is not None:
                cost = cr.cost_usd
        ledger.record_cost(cost, is_live=True)
        placed += 1
        outcomes.append(StressCallOutcome(masked, "placed",
                                          call_id=result.call_id, cost_usd=cost))
    return outcomes


def main(argv: list[str] | None = None) -> int:
    """Entry point — gated SEQUENTIAL live stress lane. Returns 0 on success."""
    if argv is None:
        argv = sys.argv[1:]

    # Ensure the repo root is importable when run directly (OS-agnostic).
    repo_root = str(Path(__file__).resolve().parent.parent)
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    from app.config import (
        load_env, MAX_LIVE_STRESS_CALLS, MAX_COST_PER_CALL_USD,
    )
    load_env()

    from app.budget import BudgetLedger, default_ledger_path
    from app.consent import load_allowlist
    from app.vapi_client import VapiVoiceProvider

    try:
        allowlist = load_allowlist()
    except Exception as exc:
        print(f"ERROR: cannot load consent allowlist: {exc}", file=sys.stderr)
        return 1

    # The number of calls to attempt this run (default = the full ceiling); the
    # ledger's caps are the real limiter.
    try:
        max_calls = int(argv[0]) if argv else MAX_LIVE_STRESS_CALLS
    except ValueError:
        print("Usage: python scripts/stress_live.py [max_calls]", file=sys.stderr)
        return 1
    max_calls = min(max_calls, MAX_LIVE_STRESS_CALLS)

    # Share the persistent ledger state (one cumulative under $50) but raise the live
    # COUNT ceiling to the stress cap. Spend is still bounded by the $15 live reserve.
    ledger = BudgetLedger(
        persist_path=default_ledger_path(),
        max_live_calls=MAX_LIVE_STRESS_CALLS,
    )

    # Sequential round-robin over the consented numbers.
    numbers = sorted(allowlist)
    sequence = [numbers[i % len(numbers)] for i in range(max_calls)] if numbers else []

    outcomes = run_stress_lane(
        sequence,
        provider=VapiVoiceProvider(),
        ledger=ledger,
        allowlist=allowlist,
        projected_cost=float(MAX_COST_PER_CALL_USD),
        max_calls=max_calls,
    )

    placed = sum(1 for o in outcomes if o.status == "placed")
    print(f"Stress lane complete: {placed} placed of {len(outcomes)} attempted.")
    for o in outcomes:
        cost = f" cost=${o.cost_usd:.4f}" if o.cost_usd is not None else ""
        print(f"  {o.number_masked}: {o.status}{cost}")
    snap = ledger.snapshot()
    print(f"Ledger: cumulative ${snap['cumulative_usd']:.4f} / ${snap['hard_cap_usd']:.2f}"
          f"  live={snap['live_call_count']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
