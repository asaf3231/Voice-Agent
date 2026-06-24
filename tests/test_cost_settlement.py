"""Regression tests for the cost-0-vs-null bug (2026-06-24).

THE BUG: while a Vapi call is still queued/ringing/in-progress, Vapi reports its
`cost` field as 0 (NOT null). The old fetch_call_cost only rejected a *null* cost,
so a 0 from a not-yet-ended call returned ok=True/cost_usd=0.0 and was recorded as
real spend — 5 live calls produced a cumulative of $0.00 in the ledger, silently
under-counting spend and defeating the HARD_BUDGET_USD cap.

THE FIX (app/vapi_client.py):
  - fetch_call_cost is status-aware: a cost is ok=True only once status == "ended".
    A not-yet-ended call → ok=False / error="cost_pending"; an ended call without a
    cost yet → ok=False / error="cost_unavailable".
  - fetch_call_cost_settled polls until the cost is final or a timeout, then returns
    the last (pending) result so the caller's projected-estimate fallback fires.
  - The recording entry points (place_demo_call / orchestrate / stress_live) record
    the conservative PROJECTED_COST_PER_CALL on a non-final cost — never a fake $0.

These tests exercise the REAL VapiVoiceProvider.fetch_call_cost over a mocked HTTP
client (the path that had no coverage before), plus the orchestrate recording path.
No network. Import-safe (ENV4): the live client is monkeypatched, never built.
"""

from __future__ import annotations

import json

import pytest

import app.vapi_client as vapi
from app.vapi_client import CostResult, VapiVoiceProvider


# ---------------------------------------------------------------------------
# Minimal HTTP fakes (never network) for the lazy Vapi client
# ---------------------------------------------------------------------------

class _FakeResp:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    """A stand-in httpx client whose .get() returns scripted call objects in order.

    The last scripted payload repeats once the queue is drained (so a poll that
    keeps fetching a 'ringing' call keeps seeing 'ringing').
    """

    def __init__(self, payloads: list[dict]) -> None:
        self._payloads = list(payloads)
        self.get_calls: list[str] = []

    def get(self, path: str) -> _FakeResp:
        self.get_calls.append(path)
        if len(self._payloads) > 1:
            return _FakeResp(self._payloads.pop(0))
        return _FakeResp(self._payloads[0])


@pytest.fixture()
def patch_client(monkeypatch):
    """Return a factory that installs a _FakeClient with the given payload sequence."""
    def _install(payloads: list[dict]) -> _FakeClient:
        client = _FakeClient(payloads)
        monkeypatch.setattr(vapi, "_get_vapi", lambda: client)
        return client
    return _install


# ===========================================================================
# fetch_call_cost — status awareness (the bug + the fix)
# ===========================================================================

class TestFetchCallCostStatusAware:
    @pytest.mark.parametrize("status", ["queued", "ringing", "in-progress", "forwarding"])
    def test_non_ended_call_with_cost_zero_is_pending_not_a_real_zero(self, patch_client, status):
        """THE BUG: a not-yet-ended call reports cost:0 — must NOT be a successful $0."""
        patch_client([{"status": status, "cost": 0}])
        res = VapiVoiceProvider().fetch_call_cost(call_id="call_x")
        assert res.ok is False, "a pre-final cost must never be reported ok=True"
        assert res.error == "cost_pending"
        assert res.cost_usd is None

    def test_non_ended_call_with_nonzero_cost_is_still_pending(self, patch_client):
        """Even a partial nonzero cost mid-call is not final — wait for 'ended'."""
        patch_client([{"status": "in-progress", "cost": 0.0123}])
        res = VapiVoiceProvider().fetch_call_cost(call_id="call_x")
        assert res.ok is False and res.error == "cost_pending"

    def test_ended_call_returns_the_final_cost(self, patch_client):
        """The fix still returns a real, final cost once the call has ended."""
        patch_client([{"status": "ended", "cost": 0.0734}])
        res = VapiVoiceProvider().fetch_call_cost(call_id="call_x")
        assert res.ok is True
        assert res.cost_usd == pytest.approx(0.0734)

    def test_ended_call_with_genuine_zero_is_trusted(self, patch_client):
        """A call that ended at $0 (e.g. never connected) is authoritative — ok=True/0.0."""
        patch_client([{"status": "ended", "cost": 0}])
        res = VapiVoiceProvider().fetch_call_cost(call_id="call_x")
        assert res.ok is True
        assert res.cost_usd == pytest.approx(0.0)

    def test_ended_call_without_cost_yet_is_unavailable(self, patch_client):
        """Ended but cost not attached yet (report lag) → retryable, not a $0."""
        patch_client([{"status": "ended", "cost": None}])
        res = VapiVoiceProvider().fetch_call_cost(call_id="call_x")
        assert res.ok is False and res.error == "cost_unavailable"

    def test_http_error_is_structured_not_a_crash(self, monkeypatch):
        client = _FakeClient([{}])
        monkeypatch.setattr(vapi, "_get_vapi", lambda: _ErrClient())
        res = VapiVoiceProvider().fetch_call_cost(call_id="call_x")
        assert res.ok is False and res.error == "vapi_error"


class _ErrClient:
    def get(self, path: str) -> _FakeResp:
        return _FakeResp({"error": "boom"}, status_code=500)


# ===========================================================================
# fetch_call_cost_settled — the poll
# ===========================================================================

class TestFetchCallCostSettled:
    def test_polls_until_ended_then_returns_final_cost(self, patch_client):
        slept: list[int] = []
        client = patch_client([
            {"status": "ringing", "cost": 0},
            {"status": "in-progress", "cost": 0},
            {"status": "ended", "cost": 0.21},
        ])
        res = VapiVoiceProvider().fetch_call_cost_settled(
            call_id="call_x", max_wait_s=60, interval_s=6, sleeper=slept.append
        )
        assert res.ok is True and res.cost_usd == pytest.approx(0.21)
        assert len(client.get_calls) == 3, "should poll until the call ends"
        assert slept == [6, 6], "should sleep between polls, not after the final one"

    def test_timeout_returns_pending_so_caller_falls_back(self, patch_client):
        """A call that never ends in the window → ok=False/cost_pending (NOT a fake $0)."""
        patch_client([{"status": "ringing", "cost": 0}])
        res = VapiVoiceProvider().fetch_call_cost_settled(
            call_id="call_x", max_wait_s=12, interval_s=6, sleeper=lambda _s: None
        )
        assert res.ok is False and res.error == "cost_pending"
        assert res.cost_usd is None

    def test_hard_error_short_circuits_without_polling(self, monkeypatch):
        monkeypatch.setattr(vapi, "_get_vapi", lambda: _ErrClient())
        calls = {"n": 0}
        VapiVoiceProvider().fetch_call_cost_settled(
            call_id="call_x", max_wait_s=60, interval_s=6,
            sleeper=lambda _s: calls.__setitem__("n", calls["n"] + 1),
        )
        assert calls["n"] == 0, "a real vapi_error must not be retried"


# ===========================================================================
# Recording path: a pending cost is recorded as the estimate, NEVER $0
# ===========================================================================

class TestRecordingNeverBooksFakeZero:
    def test_orchestrate_records_projected_estimate_on_pending_cost(
        self, fake_voice_provider, allowed_number
    ):
        """The exact failure mode: cost fetch is not final → ledger must book the
        conservative estimate, not $0 (which is what populated count=5 / cumulative=0)."""
        from app.budget import BudgetLedger
        from app.orchestrate import run, PROJECTED_COST_PER_CALL
        from app.vapi_client import CallResult

        allowlist = frozenset({allowed_number})
        leads = [{"lead_id": "L1", "first_name": "A", "company": "C",
                  "phone_e164": allowed_number}]

        fake_voice_provider.queue_call_result(CallResult(ok=True, call_id="c1", status="queued"))
        fake_voice_provider.queue_cost_result(CostResult(ok=False, error="cost_pending",
                                                         message="not final"))
        ledger = BudgetLedger()
        run(leads, provider=fake_voice_provider, ledger=ledger, allowlist=allowlist)

        assert ledger.cumulative == pytest.approx(PROJECTED_COST_PER_CALL), (
            "a non-final cost must record the projected estimate, never $0"
        )
        assert ledger.cumulative > 0.0, "the cumulative cap can never see a placed call as free"
