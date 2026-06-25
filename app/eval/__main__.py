"""Run the offline eval and print its results — the command shown in the demo video.

`python -m app.eval` (or `make eval`) runs the deterministic, network-free eval and
prints two computed tables to stdout:

  1. the A/B bake-off (one row per persona variant), and
  2. the full persona-matrix summary (aggregate metrics + per-cell breakdown).

Every number is computed from the rubric over seeded simulated transcripts — nothing
is hardcoded, and the same seed yields the same numbers every run. No network, no
voice-platform client, no `.env`, and no call: safe to run from a clean checkout.
"""

from __future__ import annotations

import sys

from app.eval import bakeoff, harness


def main(argv: list[str] | None = None) -> int:
    """Print the bake-off table and the eval summary; return a process exit code."""
    print("########## A/B BAKE-OFF (computed, seeded, offline) ##########")
    rows = bakeoff.run_bakeoff()
    print(bakeoff.format_table(rows))

    print()
    print("########## OFFLINE EVAL SUMMARY ##########")
    summary = harness.run_eval()
    print(harness.format_summary(summary))
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised via `make eval`
    sys.exit(main())
