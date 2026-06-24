"""Pre-live readiness check (`make preflight`).

Verifies that every setting the live path needs is present and that the consent
allowlist loads with at least one number — without ever printing a secret value (it
shows each variable name with a PRESENT/MISSING marker only). Exit code 0 means ready
for a live test; 1 means something is missing or invalid.

Import-safe: all work is inside main(); importing reads no .env and places no call.
"""

from __future__ import annotations

import sys

# Settings the live path REQUIRES (read via require_setting in the live code).
# OPENAI_API_KEY is intentionally NOT here — the OpenAI Realtime model is
# configured inside the Vapi platform, not read by this service.
REQUIRED_SETTINGS = (
    "VAPI_API_KEY",            # Vapi private (server) API key — place_call / fetch_call_cost
    "VAPI_PHONE_NUMBER_ID",    # the imported outbound number's UUID
    "VAPI_WEBHOOK_SECRET",     # static x-vapi-secret the webhook server verifies
    "CALCOM_API_KEY",          # Cal.com booking
    "CALCOM_EVENT_TYPE_ID",    # Cal.com event type to book against
)
# Optional (a sensible default applies if unset).
OPTIONAL_SETTINGS = (
    "CONSENT_ALLOWLIST_PATH",  # defaults to consent_allowlist.json
)


def main(argv: list[str] | None = None) -> int:
    """Run the preflight checks. Returns 0 if ready, 1 otherwise."""
    # Ensure the repo root is importable when run directly (`python scripts/preflight.py`
    # / `make preflight`), not only under PYTHONPATH=. — OS-agnostic via pathlib.
    from pathlib import Path
    repo_root = str(Path(__file__).resolve().parent.parent)
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    from app.config import get_setting, load_env

    load_env()  # sanctioned runtime entry point (never at import)

    print("Alta preflight — live-readiness check")
    print("(names + PRESENT/MISSING only — no secret value is ever printed)\n")

    # --- required settings ---------------------------------------------------
    required_ok = True
    print("Required settings:")
    for name in REQUIRED_SETTINGS:
        value = get_setting(name)
        present = bool(value and value.strip())
        required_ok = required_ok and present
        print(f"  [{'OK     ' if present else 'MISSING'}] {name}")

    # --- optional settings ---------------------------------------------------
    print("\nOptional settings:")
    for name in OPTIONAL_SETTINGS:
        value = get_setting(name)
        present = bool(value and value.strip())
        print(f"  [{'set    ' if present else 'default'}] {name}")

    # --- consent allowlist ---------------------------------------------------
    allowlist_ok = False
    print("\nConsent allowlist:")
    try:
        from app.consent import load_allowlist

        numbers = load_allowlist()
        allowlist_ok = len(numbers) > 0
        marker = "OK     " if allowlist_ok else "EMPTY  "
        print(f"  [{marker}] {len(numbers)} consented number(s) loaded")
    except Exception as exc:  # noqa: BLE001 — surface as a readable line, never crash
        print(f"  [ERROR  ] could not load allowlist: {exc}")

    # --- budget headroom (spend numbers only — not a secret) -----------------
    print("\nBudget ledger:")
    try:
        from app.budget import get_ledger

        snap = get_ledger().snapshot()
        print(
            f"  cumulative ${snap['cumulative_usd']:.2f} / cap ${snap['hard_cap_usd']:.2f}"
            f"  (remaining ${snap['remaining_usd']:.2f})"
        )
        print(
            f"  live calls {snap['live_call_count']}/{snap['max_live_calls']}"
            f"  (live spend ${snap['live_cumulative_usd']:.2f})"
        )
    except Exception as exc:  # noqa: BLE001
        print(f"  [WARN   ] could not read ledger: {exc}")

    # --- verdict -------------------------------------------------------------
    ready = required_ok and allowlist_ok
    print()
    if ready:
        print("PREFLIGHT PASSED — ready for a live test.")
        return 0
    print("PREFLIGHT FAILED — fix the MISSING/EMPTY items above before any live call.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
