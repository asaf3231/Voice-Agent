"""Alta Outbound Voice Agent — scripts/place_demo_call.py

The GATED single-number demo-call launcher (`make call TO=<e164>`).

Usage:
  python scripts/place_demo_call.py <e164_number>
  # or via Makefile:
  make call TO=+15551234567

Governance (graded — same chokepoints as orchestrate.py):
  - consent_allows() MUST pass before place_call (CON1/SEC3).
  - budget_permits()  MUST pass before place_call (CALL4/SEC3).
  - The call is NEVER placed if either gate fails.
  This script is spy-proven to route through both gates (SEC3/CON1 second entry
  point — Red-Team 2026-06-23, Finding 8).

Import-safety (ENV4): no side effects at module level. All work is inside main(),
guarded by `if __name__ == "__main__"`.
"""

from __future__ import annotations

import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    """Entry point — gated live-call launcher.

    Returns 0 on success, 1 on any failure (consent refused, budget exceeded,
    provider error, missing arg). Never raises across this boundary (§6).
    """
    if argv is None:
        argv = sys.argv[1:]

    if not argv:
        print(
            "ERROR: no target number supplied.\n"
            "Usage: python scripts/place_demo_call.py <e164_number>\n"
            "       make call TO=<e164_number>",
            file=sys.stderr,
        )
        return 1

    to_number = argv[0].strip()

    # -- load .env (the gated live entry point; never at import -- ENV4) ------
    from app.config import load_env
    load_env()

    # -- imports (all after load_env so keys are available if needed) ---------
    from app.budget import BudgetLedger
    from app.consent import consent_allows, load_allowlist, mask_phone
    from app.vapi_client import VapiVoiceProvider
    from app.orchestrate import PROJECTED_COST_PER_CALL

    # -- load consent allowlist -----------------------------------------------
    try:
        allowlist = load_allowlist()
    except Exception as exc:
        print(f"ERROR: Cannot load consent allowlist: {exc}", file=sys.stderr)
        return 1

    masked = mask_phone(to_number)

    # -- GATE 1: consent (CON1) — SINGLE CHOKEPOINT ---------------------------
    if not consent_allows(to_number, do_not_call=False, allowlist=allowlist):
        print(
            f"REFUSED: {masked} is not on the consent allowlist. Call not placed.\n"
            "Add the number to consent_allowlist.json (with explicit consent) first.",
            file=sys.stderr,
        )
        return 1

    # -- GATE 2: budget guard (SEC3/CALL4) — MUST pass before place_call ------
    ledger = BudgetLedger()
    if not ledger.budget_permits(PROJECTED_COST_PER_CALL, is_live=True):
        snap = ledger.snapshot()
        print(
            f"REFUSED: Budget guard blocked the call for {masked}.\n"
            f"  Projected: ${PROJECTED_COST_PER_CALL:.2f}  "
            f"Cumulative: ${snap['cumulative_usd']:.4f}  "
            f"Remaining:  ${snap['remaining_usd']:.4f}",
            file=sys.stderr,
        )
        return 1

    # -- both gates passed: place the call ------------------------------------
    provider = VapiVoiceProvider()
    try:
        assistant = provider.configure_assistant()
    except Exception as exc:
        print(f"ERROR: Could not build assistant config: {exc}", file=sys.stderr)
        return 1

    print(f"Placing live call to {masked} …")
    try:
        result = provider.place_call(to_number=to_number, assistant=assistant)
    except Exception as exc:  # noqa: BLE001 — §6: surface as data
        print(f"ERROR: Provider raised during place_call: {exc}", file=sys.stderr)
        return 1

    if not result.ok:
        print(
            f"ERROR: place_call failed for {masked}: "
            f"{result.error} — {result.message}",
            file=sys.stderr,
        )
        return 1

    print(f"Call placed. call_id={result.call_id!r}  status={result.status!r}")

    # -- capture cost (best-effort; failure is non-fatal) ---------------------
    if result.call_id:
        try:
            cost_result = provider.fetch_call_cost(call_id=result.call_id)
            if cost_result.ok and cost_result.cost_usd is not None:
                print(f"Cost: ${cost_result.cost_usd:.4f}")
            else:
                print(
                    f"Cost not yet available: {cost_result.message or cost_result.error}"
                )
        except Exception as exc:  # noqa: BLE001
            print(f"Warning: cost fetch raised: {exc}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
