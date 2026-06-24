"""Budget governance — the spend ledger and the pre-call cost guard.

Tracks cumulative spend and enforces the hard ceilings before any call is placed: a
per-call cap and a total cap, with tighter sub-caps for live calls. Spend is
persisted to a local state file so the total cap holds across separate runs (and
across the two live entry points), not just within a single process.

Import-safe: no I/O at import — the ledger singleton is created on first use.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from app.config import (
    BUDGET_ALARM_ROUNDING_MARGIN,
    HARD_BUDGET_USD,
    LIVE_CALL_BUDGET_USD,
    MAX_COST_PER_CALL_USD,
    MAX_LIVE_CALLS,
    REPO_ROOT,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default persistent state file path (gitignored; live entry points use this).
# Must not be read at import — only touched inside get_ledger().
# ---------------------------------------------------------------------------
_LEDGER_STATE_PATH: Path = REPO_ROOT / "receipts" / ".budget_ledger.json"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _to_decimal(value: float | str | Decimal) -> Decimal:
    """Coerce to Decimal, always rounding to 6 dp for stable comparisons."""
    return Decimal(str(value)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# BudgetLedger
# ---------------------------------------------------------------------------

@dataclass
class BudgetLedger:
    """Spend ledger: tracks cumulative cost + enforces per-call and hard caps.

    Thread-safety: not thread-safe by design (single-threaded campaign runner).
    For concurrent use, wrap in a lock at the call site.

    Persistence (opt-in):
      Set persist_path to a writable file path to persist cumulative spend across
      process invocations — this is what makes the total cap real rather than
      per-process. The file holds only numeric spend state (no secrets, no phone
      numbers). A missing or corrupt file is treated as a fresh start (logged, never
      crashes). The default (persist_path=None) is fully in-memory.
    """

    _cumulative: Decimal = field(default_factory=lambda: Decimal("0"))
    _live_cumulative: Decimal = field(default_factory=lambda: Decimal("0"))
    _live_call_count: int = field(default=0)
    # hard caps (constants from config; stored for testability with injection)
    hard_budget: Decimal = field(
        default_factory=lambda: _to_decimal(HARD_BUDGET_USD)
    )
    per_call_ceiling: Decimal = field(
        default_factory=lambda: _to_decimal(MAX_COST_PER_CALL_USD)
    )
    live_budget: Decimal = field(
        default_factory=lambda: _to_decimal(LIVE_CALL_BUDGET_USD)
    )
    max_live_calls: int = field(default=MAX_LIVE_CALLS)
    # Post-hoc over-cap alarm tolerance — sourced from the shared constant, not inlined.
    alarm_margin: Decimal = field(
        default_factory=lambda: _to_decimal(BUDGET_ALARM_ROUNDING_MARGIN)
    )
    # Opt-in persistence: when set, state is loaded on construction + saved on record_cost.
    # None → in-memory only (the default; isolated tests stay unaffected).
    persist_path: Path | None = field(default=None)

    def __post_init__(self) -> None:
        """Load persisted state if persist_path is set (missing/corrupt → start at 0)."""
        if self.persist_path is not None:
            self._load_state()

    # ------------------------------------------------------------------
    # Persistence helpers (only used when persist_path is set)
    # ------------------------------------------------------------------

    def _load_state(self) -> None:
        """Load cumulative spend from the persist_path JSON file.

        A missing file → start at 0 (normal first run, no warning needed).
        A corrupt/unreadable file → start at 0 + log a warning (never crashes).
        The file must hold only numeric spend state — no secrets, no phone numbers.
        """
        path = Path(self.persist_path)  # type: ignore[arg-type]
        if not path.exists():
            # Normal first-run — no file yet; start at 0 silently.
            return
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
            cum = _to_decimal(data.get("cumulative", "0"))
            live_cum = _to_decimal(data.get("live_cumulative", "0"))
            live_count = int(data.get("live_call_count", 0))
        except Exception as exc:  # noqa: BLE001 — corrupt file → start at 0
            logger.warning(
                "budget: corrupt ledger state file %s (%s) — starting at $0. "
                "If this was unexpected, check the file manually.",
                path, exc,
            )
            return
        self._cumulative = cum
        self._live_cumulative = live_cum
        self._live_call_count = live_count
        logger.info(
            "budget: loaded persisted state from %s — cumulative=$%.4f",
            path, float(self._cumulative),
        )

    def _save_state(self) -> None:
        """Atomically write the current spend state to persist_path.

        Uses write-temp-then-rename so a crash mid-write cannot corrupt the
        existing ledger state. Only numeric spend is written — no secrets.
        """
        path = Path(self.persist_path)  # type: ignore[arg-type]
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "cumulative": str(self._cumulative),
            "live_cumulative": str(self._live_cumulative),
            "live_call_count": self._live_call_count,
        }
        # Atomic write: temp file in the same directory → os.replace (atomic on POSIX).
        try:
            fd, tmp_path = tempfile.mkstemp(
                dir=path.parent, prefix=".ledger_tmp_", suffix=".json"
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(data, f)
                os.replace(tmp_path, path)
            except Exception:
                # Clean up the temp file if the rename failed.
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        except Exception as exc:  # noqa: BLE001 — log + continue, never crash
            logger.error(
                "budget: failed to persist ledger state to %s: %s — "
                "cumulative spend may be lost across restarts.",
                path, exc,
            )

    # ------------------------------------------------------------------
    # Budget guard (the pre-call chokepoint)
    # ------------------------------------------------------------------

    def budget_permits(self, projected: float, *, is_live: bool = False) -> bool:
        """Return True only when the projected cost fits within all applicable caps.

        Checks (all must pass):
          1. projected <= per-call ceiling (MAX_COST_PER_CALL_USD)
          2. cumulative + projected <= hard cap (HARD_BUDGET_USD)
          3. If is_live: live_cumulative + projected <= live sub-cap (LIVE_CALL_BUDGET_USD)
          4. If is_live: live call count < MAX_LIVE_CALLS

        Returns False (never raises) — the caller decides how to surface the block.
        """
        p = _to_decimal(projected)

        # Per-call ceiling
        if p > self.per_call_ceiling:
            return False

        # Cumulative hard cap
        if self._cumulative + p > self.hard_budget:
            return False

        # Live-specific sub-caps
        if is_live:
            if self._live_cumulative + p > self.live_budget:
                return False
            if self._live_call_count >= self.max_live_calls:
                return False

        return True

    # ------------------------------------------------------------------
    # Ledger mutation (call AFTER a call completes, not before)
    # ------------------------------------------------------------------

    def record_cost(self, actual: float, *, is_live: bool = False) -> None:
        """Record the actual cost of a completed call into the ledger.

        Must be called AFTER the call ends (not projected — actual from receipt).
        Raises ValueError if recording would push cumulative past hard cap +
        a reasonable rounding margin (guards against a race or logic bug).
        """
        a = _to_decimal(actual)
        new_cum = self._cumulative + a

        if new_cum > self.hard_budget + self.alarm_margin:
            # The guard should have prevented this; raise so the bug is visible.
            raise ValueError(
                f"Recording ${actual:.6f} would push cumulative "
                f"${float(self._cumulative):.6f} past hard cap "
                f"${float(self.hard_budget):.2f}."
            )

        self._cumulative = new_cum
        if is_live:
            self._live_cumulative += a
            self._live_call_count += 1

        # Persist the updated state if a path was configured.
        if self.persist_path is not None:
            self._save_state()

    # ------------------------------------------------------------------
    # Read accessors
    # ------------------------------------------------------------------

    @property
    def cumulative(self) -> float:
        """Total spend recorded so far (float for external display)."""
        return float(self._cumulative)

    @property
    def live_cumulative(self) -> float:
        """Live-call spend so far."""
        return float(self._live_cumulative)

    @property
    def live_call_count(self) -> int:
        """Number of live calls recorded."""
        return self._live_call_count

    @property
    def remaining(self) -> float:
        """How much budget remains under the hard cap."""
        return float(self.hard_budget - self._cumulative)

    def snapshot(self) -> dict:
        """Return a loggable snapshot (no secrets; safe to log)."""
        return {
            "cumulative_usd": self.cumulative,
            "remaining_usd": self.remaining,
            "hard_cap_usd": float(self.hard_budget),
            "live_cumulative_usd": self.live_cumulative,
            "live_call_count": self._live_call_count,
            "max_live_calls": self.max_live_calls,
        }


# ---------------------------------------------------------------------------
# Module-level lazy singleton
# ---------------------------------------------------------------------------

_ledger: BudgetLedger | None = None


def get_ledger() -> BudgetLedger:
    """Return (creating on first call) the persistent module-level BudgetLedger singleton.

    The singleton persists to receipts/.budget_ledger.json (gitignored), so the
    cumulative cap holds across separate process invocations. Both live entry points
    (the campaign runner and the demo-call script) call this and so share one total.

    NOT constructed at import — call this inside a function/method only.
    Tests that need isolation must create their own BudgetLedger() instances directly
    (without persist_path) rather than calling this singleton.
    """
    global _ledger
    if _ledger is None:
        _ledger = BudgetLedger(persist_path=_LEDGER_STATE_PATH)
    return _ledger


def default_ledger_path() -> Path:
    """Return the default persistent ledger state file path (gitignored).

    A read-only accessor so a second live entry point (e.g. scripts/stress_live.py)
    can construct a ledger on the SAME persisted state — sharing one cumulative total
    under the $50 hard cap — without reaching into a module-private. No I/O here.
    """
    return _LEDGER_STATE_PATH


def reset_ledger(*, also_delete_state_file: bool = False) -> None:
    """Reset the singleton (test helper — do NOT call in production code).

    Args:
        also_delete_state_file: if True, also delete the persistent state file
            (_LEDGER_STATE_PATH) so the next get_ledger() starts at $0 even with
            persistence enabled. Use this when a test exercises the singleton and
            needs a clean persistent state.
    """
    global _ledger
    _ledger = None
    if also_delete_state_file:
        try:
            _LEDGER_STATE_PATH.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------------------
# Module-level convenience wrappers (delegate to the singleton)
# ---------------------------------------------------------------------------

def budget_permits(projected: float, *, is_live: bool = False) -> bool:
    """Module-level budget guard. Delegates to get_ledger().budget_permits().

    This is the function the orchestrator and demo-call script call before any call is
    placed. Tests that need isolation should instantiate BudgetLedger directly.
    """
    return get_ledger().budget_permits(projected, is_live=is_live)


def record_cost(actual: float, *, is_live: bool = False) -> None:
    """Module-level cost recorder. Delegates to get_ledger().record_cost()."""
    get_ledger().record_cost(actual, is_live=is_live)
