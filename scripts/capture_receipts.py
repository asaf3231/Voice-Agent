"""Alta Outbound Voice Agent — scripts/capture_receipts.py

Capture a per-call cost receipt from the voice provider and write a REDACTED
record under receipts/. Satisfies SEC5 / LIVE4.

Usage:
  python scripts/capture_receipts.py <call_id> [<call_id> ...]
  # or via Makefile:
  make receipts CALL_IDS="call_abc123 call_def456"

What it writes (receipts/<call_id>.json):
  {
    "call_id": "<call_id>",          # the provider call identifier
    "cost_usd": 0.1234,              # reported by fetch_call_cost — verified, not asserted
    "timestamp": "2026-06-23T20:00:00Z"  # ISO-8601 UTC capture time
  }

Redaction contract (CLAUDE.md §5 anti-leakage / LEAK2):
  - NO full phone number (use mask_phone if any phone appears)
  - NO account id or API key
  - NO secret of any kind
  The file holds ONLY: call_id, cost_usd (float), and timestamp (ISO-8601 UTC).

Import-safety (ENV4): no side effects at module level.
All work is inside main(), guarded by `if __name__ == "__main__"`.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def _receipts_dir() -> Path:
    """Return the receipts directory, creating it if needed."""
    from app.config import REPO_ROOT
    d = REPO_ROOT / "receipts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def capture_receipt(
    call_id: str,
    provider,  # VoiceProvider — injected for testability
    *,
    receipts_dir: Path | None = None,
) -> dict:
    """Capture and write a redacted receipt for *call_id*.

    Returns the receipt dict (also written to disk).
    Raises nothing — errors are returned in the dict under "error" (§6).

    Args:
        call_id: the voice-platform call identifier.
        provider: a VoiceProvider instance (real or fake) used to fetch the cost.
        receipts_dir: directory to write to; defaults to REPO_ROOT/receipts/.
    """
    if receipts_dir is None:
        receipts_dir = _receipts_dir()

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        cost_result = provider.fetch_call_cost(call_id=call_id)
    except Exception as exc:  # noqa: BLE001 — §6: surface as data
        receipt: dict = {
            "call_id": call_id,
            "cost_usd": None,
            "timestamp": timestamp,
            "error": f"fetch_call_cost raised: {exc}",
        }
        _write_receipt(receipt, receipts_dir)
        return receipt

    if not cost_result.ok or cost_result.cost_usd is None:
        receipt = {
            "call_id": call_id,
            "cost_usd": None,
            "timestamp": timestamp,
            "error": cost_result.error or cost_result.message or "cost unavailable",
        }
        _write_receipt(receipt, receipts_dir)
        return receipt

    # SEC5: the figure equals the provider's reported fetch_call_cost — verified here,
    # not asserted from a stale copy.
    receipt = {
        "call_id": call_id,
        "cost_usd": float(cost_result.cost_usd),
        "timestamp": timestamp,
    }
    _write_receipt(receipt, receipts_dir)
    return receipt


def _write_receipt(receipt: dict, receipts_dir: Path) -> None:
    """Write *receipt* atomically to receipts_dir/<call_id>.json."""
    import os
    import tempfile

    call_id = receipt["call_id"]
    receipts_dir.mkdir(parents=True, exist_ok=True)
    target = receipts_dir / f"{call_id}.json"

    # Atomic write: temp then rename so a crash mid-write is safe.
    try:
        fd, tmp_path = tempfile.mkstemp(
            dir=receipts_dir, prefix=".receipt_tmp_", suffix=".json"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(receipt, f, indent=2)
            os.replace(tmp_path, target)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except Exception as exc:  # noqa: BLE001
        print(
            f"WARNING: could not write receipt for {call_id}: {exc}",
            file=sys.stderr,
        )


def main(argv: list[str] | None = None, *, provider=None) -> int:
    """Entry point for the receipt capture script.

    Args:
        argv: list of call_id strings (overrides sys.argv[1:]).
        provider: injected VoiceProvider for testing (uses VapiVoiceProvider if None).

    Returns 0 on success, 1 if no call ids supplied.
    """
    if argv is None:
        argv = sys.argv[1:]

    if not argv:
        print(
            "ERROR: no call_id(s) supplied.\n"
            "Usage: python scripts/capture_receipts.py <call_id> [<call_id> ...]\n"
            "       make receipts CALL_IDS='call_abc call_def'",
            file=sys.stderr,
        )
        return 1

    # Ensure the repo root is importable when run directly — OS-agnostic via pathlib.
    repo_root = str(Path(__file__).resolve().parent.parent)
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    # -- load .env (live entry point; never at import -- ENV4) ----------------
    from app.config import load_env
    load_env()

    # -- build the live provider if not injected (allows offline testing) -----
    if provider is None:
        from app.vapi_client import VapiVoiceProvider
        provider = VapiVoiceProvider()

    receipts_dir = _receipts_dir()
    any_error = False

    for call_id in argv:
        call_id = call_id.strip()
        if not call_id:
            continue
        receipt = capture_receipt(call_id, provider, receipts_dir=receipts_dir)
        if "error" in receipt:
            print(
                f"WARNING: {call_id} — cost unavailable: {receipt['error']}",
                file=sys.stderr,
            )
            any_error = True
        else:
            print(
                f"Receipt captured: {call_id}  cost=${receipt['cost_usd']:.4f}  "
                f"ts={receipt['timestamp']}  "
                f"path=receipts/{call_id}.json"
            )

    return 1 if any_error else 0


if __name__ == "__main__":
    sys.exit(main())
