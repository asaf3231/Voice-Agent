"""Budget-ledger tests: the per-call and cumulative caps, and the over-cap alarm."""

from __future__ import annotations

import json
import pytest

from app.budget import BudgetLedger
from app.config import (
    HARD_BUDGET_USD,
    LIVE_CALL_BUDGET_USD,
    MAX_COST_PER_CALL_USD,
    MAX_LIVE_CALLS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def ledger(
    *,
    hard: float = HARD_BUDGET_USD,
    per_call: float = MAX_COST_PER_CALL_USD,
    live_bud: float = LIVE_CALL_BUDGET_USD,
    max_live: int = MAX_LIVE_CALLS,
) -> BudgetLedger:
    """Return a fresh BudgetLedger with optional overrides for boundary tests."""
    return BudgetLedger(
        hard_budget=_d(hard),
        per_call_ceiling=_d(per_call),
        live_budget=_d(live_bud),
        max_live_calls=max_live,
    )


def _d(v: float):
    from decimal import Decimal, ROUND_HALF_UP
    return Decimal(str(v)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# SEC2 — budget ledger correctness
# ---------------------------------------------------------------------------

class TestBudgetLedgerCorrectness:
    """SEC2: the ledger tracks spend deterministically and correctly."""

    def test_initial_state(self):
        b = ledger()
        assert b.cumulative == 0.0
        assert b.live_cumulative == 0.0
        assert b.live_call_count == 0

    def test_record_cost_updates_cumulative(self):
        b = ledger()
        b.record_cost(0.50)
        assert abs(b.cumulative - 0.50) < 1e-9

    def test_record_cost_multiple(self):
        b = ledger()
        b.record_cost(0.30)
        b.record_cost(0.45)
        assert abs(b.cumulative - 0.75) < 1e-9

    def test_record_cost_live_updates_live_counters(self):
        b = ledger()
        b.record_cost(0.40, is_live=True)
        assert abs(b.live_cumulative - 0.40) < 1e-9
        assert b.live_call_count == 1

    def test_record_cost_non_live_does_not_touch_live_counters(self):
        b = ledger()
        b.record_cost(0.40, is_live=False)
        assert b.live_cumulative == 0.0
        assert b.live_call_count == 0

    def test_remaining_decreases_with_spend(self):
        b = ledger(hard=10.0)
        b.record_cost(3.00)
        assert abs(b.remaining - 7.00) < 1e-9

    def test_record_cost_exactly_at_cap_allowed(self):
        """Recording exactly at the hard cap is allowed (within rounding margin)."""
        b = ledger(hard=1.00)
        b.record_cost(1.00)
        assert abs(b.cumulative - 1.00) < 1e-9

    def test_record_cost_over_cap_raises(self):
        """Recording a cost that pushes past hard cap + margin raises ValueError."""
        b = ledger(hard=1.00)
        b.record_cost(1.00)
        with pytest.raises(ValueError, match="past hard cap"):
            b.record_cost(0.02)  # 1.00 + 0.02 > 1.00 + 0.01 margin

    def test_snapshot_has_expected_keys(self):
        b = ledger()
        snap = b.snapshot()
        for key in ["cumulative_usd", "remaining_usd", "hard_cap_usd",
                    "live_cumulative_usd", "live_call_count", "max_live_calls"]:
            assert key in snap, f"snapshot() missing key '{key}'"

    def test_snapshot_no_secrets(self):
        """Snapshot values are all numeric — no string secrets."""
        b = ledger()
        snap = b.snapshot()
        for key, val in snap.items():
            assert isinstance(val, (int, float)), (
                f"snapshot()[{key!r}] = {val!r} — must be numeric (safe to log)"
            )

    def test_alarm_margin_sourced_from_config_constant(self):
        """F1: the over-cap alarm margin is the §9 config constant, not an inline literal."""
        from decimal import Decimal
        from app.config import BUDGET_ALARM_ROUNDING_MARGIN
        assert BUDGET_ALARM_ROUNDING_MARGIN == Decimal("0.01")
        # A default ledger sources its alarm_margin from that constant.
        assert ledger().alarm_margin == Decimal("0.01")

    def test_over_cap_alarm_uses_the_margin_constant(self):
        """The record_cost alarm fires exactly at hard_cap + BUDGET_ALARM_ROUNDING_MARGIN."""
        b = ledger(hard=1.00)
        b.record_cost(1.00)
        b.record_cost(0.01)  # 1.01 == 1.00 + margin → allowed (boundary)
        with pytest.raises(ValueError, match="past hard cap"):
            b.record_cost(0.005)  # 1.015 > 1.01 → alarm


# ---------------------------------------------------------------------------
# SEC3 — hard cap enforced before dialing
# ---------------------------------------------------------------------------

class TestBudgetPermits:
    """SEC3: budget_permits() returns False for all over-budget scenarios."""

    # --- per-call ceiling ---

    def test_permits_below_per_call_ceiling(self):
        b = ledger(per_call=1.00, hard=50.00)
        assert b.budget_permits(0.99) is True

    def test_permits_exactly_at_per_call_ceiling(self):
        b = ledger(per_call=1.00, hard=50.00)
        assert b.budget_permits(1.00) is True

    def test_refuses_above_per_call_ceiling(self):
        b = ledger(per_call=1.00, hard=50.00)
        assert b.budget_permits(1.01) is False

    # --- hard cap ---

    def test_permits_cumulative_plus_projected_at_cap(self):
        b = ledger(hard=10.00, per_call=5.00)
        b.record_cost(5.00)
        assert b.budget_permits(5.00) is True  # 5 + 5 == 10 ✓

    def test_refuses_cumulative_plus_projected_over_cap(self):
        b = ledger(hard=10.00, per_call=5.00)
        b.record_cost(5.00)
        assert b.budget_permits(5.01) is False  # 5 + 5.01 > 10 ✗

    def test_refuses_when_already_at_cap(self):
        b = ledger(hard=1.00, per_call=2.00)
        b.record_cost(1.00)
        assert b.budget_permits(0.01) is False  # 1.00 + 0.01 > 1.00

    def test_fresh_ledger_permits_small_amount(self):
        b = ledger()
        assert b.budget_permits(0.10) is True

    def test_boundary_zero_projected(self):
        """Projecting $0 is always permitted (no cost)."""
        b = ledger(hard=0.00, per_call=1.00)
        # Hard cap is 0, cumulative is 0 → 0 + 0 == 0 ≤ 0 → True
        # BUT per-call ceiling is 1.00, so 0 ≤ 1.00 → passes
        # cumulative + 0 = 0 ≤ 0 → True
        assert b.budget_permits(0.00) is True

    # --- both checks together ---

    def test_refuses_when_both_per_call_and_cum_exceeded(self):
        b = ledger(hard=2.00, per_call=1.00)
        b.record_cost(2.00)
        # projected 1.50 > per_call ceiling 1.00 → False
        assert b.budget_permits(1.50) is False


# ---------------------------------------------------------------------------
# SEC4 — live sub-caps
# ---------------------------------------------------------------------------

class TestLiveSubCaps:
    """SEC4: live calls respect LIVE_CALL_BUDGET_USD and MAX_LIVE_CALLS."""

    def test_live_permits_within_sub_cap(self):
        b = ledger(live_bud=5.00, max_live=3)
        assert b.budget_permits(1.00, is_live=True) is True

    def test_live_refuses_over_live_budget(self):
        b = ledger(live_bud=5.00, max_live=3, per_call=10.0, hard=50.0)
        b.record_cost(4.00, is_live=True)
        # 4.00 + 2.00 > 5.00 → False
        assert b.budget_permits(2.00, is_live=True) is False

    def test_live_refuses_at_max_live_calls(self):
        b = ledger(max_live=2, live_bud=50.00)
        b.record_cost(0.10, is_live=True)
        b.record_cost(0.10, is_live=True)
        # live_call_count == 2 == max_live → refuse
        assert b.budget_permits(0.10, is_live=True) is False

    def test_live_refuses_n_plus_1_th_call(self):
        """The (N+1)th live call is refused."""
        b = ledger(max_live=1, live_bud=50.00)
        b.record_cost(0.50, is_live=True)
        assert b.budget_permits(0.50, is_live=True) is False

    def test_non_live_ignores_live_sub_caps(self):
        """Non-live calls ignore live sub-caps."""
        b = ledger(max_live=0, live_bud=0.00)
        # max_live=0 and live_bud=0 would block live calls, but not non-live
        assert b.budget_permits(0.50, is_live=False) is True

    def test_live_cumulative_tracked_separately(self):
        b = ledger(max_live=6, live_bud=15.00)
        b.record_cost(2.00, is_live=True)
        b.record_cost(1.50, is_live=False)
        assert abs(b.live_cumulative - 2.00) < 1e-9
        assert abs(b.cumulative - 3.50) < 1e-9

    def test_live_call_count_only_increments_for_live(self):
        b = ledger(max_live=6)
        b.record_cost(1.00, is_live=True)
        b.record_cost(1.00, is_live=False)
        b.record_cost(1.00, is_live=True)
        assert b.live_call_count == 2

    # --- cross-check: live still subject to hard cap ---

    def test_live_refused_when_hard_cap_exceeded(self):
        b = ledger(hard=2.00, per_call=5.00, live_bud=10.00, max_live=10)
        b.record_cost(1.50)
        # 1.50 + 1.00 > 2.00 → hard cap blocks even though live sub-cap ok
        assert b.budget_permits(1.00, is_live=True) is False


# ---------------------------------------------------------------------------
# Module-level convenience wrappers
# ---------------------------------------------------------------------------

class TestModuleLevelConvenience:
    """The module-level budget_permits / record_cost delegates to the singleton."""

    def test_module_level_budget_permits(self, monkeypatch, tmp_path):
        """budget_permits() at module level works (doesn't crash without .env).

        Point the singleton's state file at tmp_path so this test NEVER touches the
        real receipts/.budget_ledger.json (test-hygiene: a failure here must not
        pollute a live operator's persistent ledger — Stage-8 review Finding 3).
        """
        import app.budget as bud
        monkeypatch.setattr(bud, "_LEDGER_STATE_PATH", tmp_path / "ledger.json")
        bud.reset_ledger()
        try:
            assert bud.budget_permits(0.10) is True  # fresh singleton permits a small cost
        finally:
            bud.reset_ledger()

    def test_module_level_record_cost(self, monkeypatch, tmp_path):
        """record_cost() at module level updates the singleton (tmp state file)."""
        import app.budget as bud
        monkeypatch.setattr(bud, "_LEDGER_STATE_PATH", tmp_path / "ledger.json")
        bud.reset_ledger()
        try:
            bud.record_cost(0.25)
            assert abs(bud.get_ledger().cumulative - 0.25) < 1e-9
        finally:
            bud.reset_ledger()


# ---------------------------------------------------------------------------
# Stage 8 — Persistence tests (the HIGH fix: cumulative cap real across instances)
# ---------------------------------------------------------------------------

class TestBudgetLedgerPersistence:
    """Persistence: opt-in persist_path makes the cumulative cap real across instances.

    These tests use tmp_path (pytest fixture) for isolation — they do NOT touch
    the real _LEDGER_STATE_PATH or the module-level singleton.
    """

    def test_persist_path_none_is_in_memory_only(self):
        """Default (persist_path=None) never touches the filesystem."""
        b = BudgetLedger()  # no persist_path
        b.record_cost(0.50)
        assert b.persist_path is None
        assert abs(b.cumulative - 0.50) < 1e-9

    def test_persistent_ledger_writes_state_on_record_cost(self, tmp_path):
        """record_cost with persist_path writes the state file."""
        state_file = tmp_path / "ledger.json"
        b = BudgetLedger(persist_path=state_file)
        b.record_cost(0.75)
        assert state_file.exists(), "state file must be written after record_cost"
        data = json.loads(state_file.read_text())
        from decimal import Decimal
        assert abs(float(Decimal(data["cumulative"])) - 0.75) < 1e-9

    def test_second_instance_loads_prior_state(self, tmp_path):
        """A second BudgetLedger on the same path loads the cumulative from the first.

        This is the core HIGH fix: separate process invocations (each building a
        BudgetLedger from the same file) share the cumulative total.
        """
        state_file = tmp_path / "ledger.json"

        # First instance — spends $0.60
        b1 = BudgetLedger(persist_path=state_file)
        b1.record_cost(0.60)
        assert abs(b1.cumulative - 0.60) < 1e-9

        # Second instance — loads state; must see $0.60 already spent
        b2 = BudgetLedger(persist_path=state_file)
        assert abs(b2.cumulative - 0.60) < 1e-9, (
            f"Second instance should load prior cumulative $0.60, got ${b2.cumulative}"
        )

    def test_cumulative_cap_enforced_across_instances(self, tmp_path):
        """The cumulative hard cap blocks once the total across two instances hits it.

        This is the exact security-HIGH scenario: without persistence the second
        process saw $0 and permitted the call; with persistence it sees the real
        cumulative and must refuse.
        """
        state_file = tmp_path / "ledger.json"
        cap = 1.00  # small cap for the test

        # First instance — spends most of the cap
        b1 = BudgetLedger(persist_path=state_file, hard_budget=_d(cap), per_call_ceiling=_d(0.80))
        b1.record_cost(0.80)

        # Second instance on the same file — should see $0.80 already spent
        b2 = BudgetLedger(persist_path=state_file, hard_budget=_d(cap), per_call_ceiling=_d(0.80))
        assert abs(b2.cumulative - 0.80) < 1e-9

        # $0.80 cumulative + $0.30 projected = $1.10 > cap $1.00 → must refuse
        assert b2.budget_permits(0.30) is False, (
            "budget_permits must be False when cumulative from prior invocation + "
            "projected exceeds the hard cap (the HIGH fix)"
        )

    def test_two_instances_accumulate_together(self, tmp_path):
        """Each record_cost from any instance updates the shared persistent state."""
        state_file = tmp_path / "ledger.json"

        b1 = BudgetLedger(persist_path=state_file, hard_budget=_d(10.0), per_call_ceiling=_d(5.0))
        b1.record_cost(1.00)

        b2 = BudgetLedger(persist_path=state_file, hard_budget=_d(10.0), per_call_ceiling=_d(5.0))
        b2.record_cost(2.00)

        # Fresh third instance sees the total: $1.00 + $2.00 = $3.00
        b3 = BudgetLedger(persist_path=state_file, hard_budget=_d(10.0), per_call_ceiling=_d(5.0))
        assert abs(b3.cumulative - 3.00) < 1e-9

    def test_missing_state_file_starts_at_zero(self, tmp_path):
        """A missing state file → start at $0 (normal first run); no crash."""
        state_file = tmp_path / "nonexistent.json"
        assert not state_file.exists()
        b = BudgetLedger(persist_path=state_file)
        assert b.cumulative == 0.0
        assert b.live_cumulative == 0.0
        assert b.live_call_count == 0

    def test_corrupt_state_file_degrades_gracefully(self, tmp_path):
        """A corrupt state file → start at $0 with a log warning; never crash (§6)."""
        state_file = tmp_path / "corrupt.json"
        state_file.write_text("{not valid json{{{{")
        # Must not raise
        b = BudgetLedger(persist_path=state_file)
        assert b.cumulative == 0.0, (
            "corrupt state file must degrade to $0, never crash"
        )

    def test_partial_state_file_uses_defaults_for_missing_keys(self, tmp_path):
        """Partial state (missing live fields) starts those at 0."""
        state_file = tmp_path / "partial.json"
        state_file.write_text(json.dumps({"cumulative": "0.500000"}))
        b = BudgetLedger(persist_path=state_file)
        assert abs(b.cumulative - 0.50) < 1e-9
        assert b.live_cumulative == 0.0
        assert b.live_call_count == 0

    def test_atomic_write_idempotent_on_same_path(self, tmp_path):
        """Multiple record_cost calls on the same path each update the file correctly."""
        state_file = tmp_path / "ledger.json"
        b = BudgetLedger(persist_path=state_file, hard_budget=_d(10.0), per_call_ceiling=_d(5.0))
        b.record_cost(1.00)
        b.record_cost(0.50)
        data = json.loads(state_file.read_text())
        from decimal import Decimal
        assert abs(float(Decimal(data["cumulative"])) - 1.50) < 1e-9

    def test_persist_path_string_is_accepted(self, tmp_path):
        """persist_path can be a str, not just a Path."""
        state_file = str(tmp_path / "ledger_str.json")
        b = BudgetLedger(persist_path=state_file)  # type: ignore[arg-type]
        b.record_cost(0.20)
        import os
        assert os.path.exists(state_file), "state file must exist after record_cost"

    def test_state_file_contains_no_secrets(self, tmp_path):
        """The state file must contain ONLY numeric spend fields — no phone/key/secret."""
        state_file = tmp_path / "ledger.json"
        b = BudgetLedger(persist_path=state_file)
        b.record_cost(0.33, is_live=True)
        data = json.loads(state_file.read_text())
        # Only these three keys are permitted
        assert set(data.keys()) == {"cumulative", "live_cumulative", "live_call_count"}, (
            f"state file must contain only spend fields; got {set(data.keys())}"
        )
        # All values must be numeric strings or ints — no free-text
        assert isinstance(data["live_call_count"], int)
        assert isinstance(data["cumulative"], str)
        assert isinstance(data["live_cumulative"], str)
