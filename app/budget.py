"""Alta Outbound Voice Agent — app/budget.py

Single responsibility: spend ledger + per-call and cumulative budget guards.

Enforces CLAUDE.md §5 Policy 1:
  - budget_permits(projected) → False when projected > MAX_COST_PER_CALL_USD
    OR cumulative + projected > HARD_BUDGET_USD
  - Live calls also respect LIVE_CALL_BUDGET_USD and MAX_LIVE_CALLS.
  - The guard MUST run before place_call (enforced in orchestrate.py + scripts/).

Import-safety (ENV4): no I/O, no network, no .env read at import.
All state lives in BudgetLedger instances; the module-level singleton is
never initialised at import — call get_ledger() to access it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP

from app.config import (
    BUDGET_ALARM_ROUNDING_MARGIN,
    HARD_BUDGET_USD,
    LIVE_CALL_BUDGET_USD,
    MAX_COST_PER_CALL_USD,
    MAX_LIVE_CALLS,
)


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
    """Immutable-accumulator spend ledger for one campaign session.

    Thread-safety: not thread-safe by design (single-threaded campaign runner).
    For concurrent use, wrap in a lock at the call site.
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
    # Post-hoc over-cap alarm tolerance — sourced from the §9 constant, not inlined (F1).
    alarm_margin: Decimal = field(
        default_factory=lambda: _to_decimal(BUDGET_ALARM_ROUNDING_MARGIN)
    )

    # ------------------------------------------------------------------
    # Budget guard (the pre-call chokepoint — SEC3/CALL4)
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
    """Return (creating on first call) the module-level BudgetLedger singleton.

    NOT constructed at import — call this inside a function/method only.
    Tests should create their own BudgetLedger instances directly for isolation.
    """
    global _ledger
    if _ledger is None:
        _ledger = BudgetLedger()
    return _ledger


def reset_ledger() -> None:
    """Reset the singleton (test helper — do NOT call in production code)."""
    global _ledger
    _ledger = None


# ---------------------------------------------------------------------------
# Module-level convenience wrappers (delegate to the singleton)
# ---------------------------------------------------------------------------

def budget_permits(projected: float, *, is_live: bool = False) -> bool:
    """Module-level budget guard. Delegates to get_ledger().budget_permits().

    This is the function the orchestrator and demo-call script call before
    any place_call invocation (SEC3/CALL4). Tests that need isolation should
    instantiate BudgetLedger directly.
    """
    return get_ledger().budget_permits(projected, is_live=is_live)


def record_cost(actual: float, *, is_live: bool = False) -> None:
    """Module-level cost recorder. Delegates to get_ledger().record_cost()."""
    get_ledger().record_cost(actual, is_live=is_live)
