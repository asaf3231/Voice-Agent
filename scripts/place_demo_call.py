"""Gated single-number demo-call launcher (`make call TO=<e164>`).

Places one outbound call, but only after both governance gates pass: the number must
be on the consent allowlist and the budget guard must approve the projected cost. If
either fails, no call is placed. After the call it polls for the final cost and
records it — falling back to a conservative estimate if the cost isn't final yet, so
the budget total is never under-counted.

Usage: python scripts/place_demo_call.py <e164_number>   (or `make call TO=...`).

Import-safe: all work is inside main(); importing reads no .env and places no call.
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

    # Ensure the repo root is importable when run directly (`python scripts/...` /
    # `make call`), not only under PYTHONPATH=. — OS-agnostic via pathlib.
    repo_root = str(Path(__file__).resolve().parent.parent)
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    # -- load .env (the gated live entry point; never at import -- ENV4) ------
    from app.config import load_env
    load_env()

    # -- imports (all after load_env so keys are available if needed) ---------
    from app.budget import get_ledger
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
    # Use the persistent singleton so cumulative spend persists across invocations
    # (Stage-8 security-HIGH fix: the HARD_BUDGET_USD=$50 cap is now real, not illusory).
    ledger = get_ledger()
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

    # -- pre-fetch availability so Aria offers times INSTANTLY (no mid-call hop) --
    # Pull the slots up front and inject them into the assistant prompt; on any
    # failure pass None so Aria falls back to fetching live via the tool.
    from app import tools
    from app.config import get_lead_context

    _lead_id, lead_tz = get_lead_context()
    available_slots = None
    try:
        avail = tools.dispatch("check_availability", lead_timezone=lead_tz)
        if avail.ok and avail.data:
            available_slots = avail.data.get("slots") or None
    except Exception:  # noqa: BLE001 — degrade gracefully to the live-fetch path
        available_slots = None

    # -- both gates passed: place the call ------------------------------------
    provider = VapiVoiceProvider()
    try:
        assistant = provider.configure_assistant(available_slots=available_slots)
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

    # -- capture cost AND record it into the persistent ledger ----------------
    # The call was placed → real spend occurred, so it MUST be recorded into the
    # persistent singleton ledger or the cumulative HARD_BUDGET_USD cap stays
    # illusory for this entry point (Stage-8 security review, Critical). Record the
    # ACTUAL cost when available, else the conservative projected estimate so a
    # cost-fetch failure can never let spend slip past the cumulative cap.
    recorded_cost = float(PROJECTED_COST_PER_CALL)
    if result.call_id:
        try:
            # Poll until Vapi finalizes the cost (it reports 0 until the call ENDS —
            # the cost-0-vs-null bug). On timeout we fall back to the conservative
            # projected estimate so the ledger can never under-count real spend.
            print("Waiting for Vapi to finalize the call cost …")
            cost_result = provider.fetch_call_cost_settled(call_id=result.call_id)
            if cost_result.ok and cost_result.cost_usd is not None:
                recorded_cost = cost_result.cost_usd
                print(f"Final cost: ${cost_result.cost_usd:.4f}")
            else:
                print(
                    f"Cost not final in time: {cost_result.message or cost_result.error}; "
                    f"recording projected estimate ${recorded_cost:.4f}. "
                    f"Run `make receipts CALL_IDS={result.call_id}` later for the exact figure."
                )
        except Exception as exc:  # noqa: BLE001
            print(f"Warning: cost fetch raised: {exc}; "
                  f"recording projected estimate ${recorded_cost:.4f}")

    try:
        ledger.record_cost(recorded_cost, is_live=True)
    except ValueError as exc:  # over-cap alarm — surface loudly, never silently
        print(f"BUDGET ALARM after a placed call: {exc}", file=sys.stderr)
        return 1
    snap = ledger.snapshot()
    print(
        f"Ledger updated: cumulative ${snap['cumulative_usd']:.4f} / "
        f"${snap['hard_cap_usd']:.2f}  (live calls: {snap['live_call_count']})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
