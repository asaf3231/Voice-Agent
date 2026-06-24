"""Alta test suite — shared fixtures (QA_checklist.md §0).

Fixtures defined here:
  - tmp_leads_json     : a small schema-valid leads.synthetic.json path
  - tmp_icp_json       : a minimal valid icp.synthetic.json path
  - tmp_value_prop     : a minimal value_prop.md path
  - tmp_allowlist      : a consent allowlist with one allowed + one absent number
  - allowed_number     : the E.164 number that IS on tmp_allowlist
  - absent_number      : an E.164 number deliberately NOT on tmp_allowlist
  - FakeVoiceProvider  : a VoiceProvider stand-in (scripted, never networks)

These fixtures create real temporary files in tmp_path so the modules under
test can read them as they would in production. No network, no .env.
"""

from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Synthetic leads fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_leads_json(tmp_path: Path) -> Path:
    """Write a minimal valid leads.synthetic.json and return its path.

    Includes:
      - lead-001: normal lead (do_not_call=false, required fields present)
      - lead-002: do_not_call=true lead (must be suppressed)
    """
    data = {
        "leads": [
            {
                "lead_id": "lead-001",
                "first_name": "Jordan",
                "company": "Momentum SaaS",
                "phone_e164": "+15550100001",
                "last_name": "Rivera",
                "role": "VP of Sales",
                "icp_tags": ["b2b-saas"],
                "timezone": "America/New_York",
                "do_not_call": False,
                "notes": "Fixture lead — normal",
            },
            {
                "lead_id": "lead-002",
                "first_name": "Taylor",
                "company": "Optimus Tech",
                "phone_e164": "+15550100004",
                "last_name": "Nguyen",
                "role": "Director of Sales",
                "icp_tags": ["b2b-saas"],
                "timezone": "America/Denver",
                "do_not_call": True,
                "notes": "Fixture lead — do_not_call",
            },
        ]
    }
    p = tmp_path / "leads.synthetic.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


@pytest.fixture()
def tmp_icp_json(tmp_path: Path) -> Path:
    """Write a minimal valid icp.synthetic.json and return its path."""
    data = {
        "icp": {
            "name": "Test ICP",
            "required_tags": ["b2b-saas"],
            "target_roles": ["VP of Sales"],
        }
    }
    p = tmp_path / "icp.synthetic.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


@pytest.fixture()
def tmp_value_prop(tmp_path: Path) -> Path:
    """Write a minimal value_prop.md and return its path."""
    content = "# Alta Value Prop\n\nAlta helps B2B SaaS teams book more meetings.\n"
    p = tmp_path / "value_prop.md"
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Allowlist fixtures
# ---------------------------------------------------------------------------

ALLOWED_NUMBER = "+15559990001"
ABSENT_NUMBER = "+15559990099"


@pytest.fixture()
def allowed_number() -> str:
    return ALLOWED_NUMBER


@pytest.fixture()
def absent_number() -> str:
    return ABSENT_NUMBER


@pytest.fixture()
def tmp_allowlist(tmp_path: Path) -> Path:
    """Write a consent allowlist with exactly one allowed number and return its path.

    The ABSENT_NUMBER is deliberately not on this list.
    """
    data = {"allowed_numbers": [ALLOWED_NUMBER]}
    p = tmp_path / "consent_allowlist.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# FakeVoiceProvider — a VoiceProvider stand-in (QA_checklist.md §0)
# ---------------------------------------------------------------------------

class FakeVoiceProvider:
    """A scripted VoiceProvider for the offline suite — NEVER networks.

    Implements the graded VoiceProvider interface (configure_assistant /
    place_call / fetch_call_cost). `configure_assistant` delegates to the real
    Vapi builder (a pure, offline function) so the assistant payload under test is
    the genuine one; `place_call` / `fetch_call_cost` return scripted results from
    queues. Set `raise_on_call=True` to simulate a hard provider failure, or push
    error CallResults to test resilience. This proves the adapter seam (VOICE5):
    server.py / orchestrate.py depend only on the interface, so this fake drops in.
    """

    def __init__(self) -> None:
        # Scripted outputs (FIFO). Tests push expected results; the fake pops them.
        self._call_results: deque[Any] = deque()
        self._cost_results: deque[Any] = deque()
        self.raise_on_call = False
        # Spy state: what the fake was asked to do (assertion targets).
        self.calls_placed: list[dict[str, Any]] = []
        self.costs_fetched: list[str] = []

    # -- scripting helpers (test-only; not part of the interface) -----------

    def queue_call_result(self, result: Any) -> None:
        self._call_results.append(result)

    def queue_cost_result(self, result: Any) -> None:
        self._cost_results.append(result)

    # -- VoiceProvider interface --------------------------------------------

    def configure_assistant(
        self,
        *,
        variant: str = "A",
        value_prop_path: str | None = None,
        lead: dict[str, Any] | None = None,
        available_slots: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Build the assistant payload via the real (offline, pure) Vapi builder."""
        from app.vapi_client import VapiVoiceProvider

        return VapiVoiceProvider().configure_assistant(
            variant=variant,
            value_prop_path=value_prop_path,
            lead=lead,
            available_slots=available_slots,
        )

    def place_call(
        self,
        *,
        to_number: str,
        assistant: dict[str, Any],
    ) -> Any:
        """Return the next scripted CallResult — never networks."""
        from app.vapi_client import CallResult

        self.calls_placed.append({"to_number": to_number, "assistant": assistant})
        if self.raise_on_call:
            raise RuntimeError("FakeVoiceProvider scripted failure")
        if self._call_results:
            return self._call_results.popleft()
        return CallResult(ok=True, call_id="fake-call-0001", status="queued")

    def fetch_call_cost(self, *, call_id: str) -> Any:
        """Return the next scripted CostResult — never networks."""
        from app.vapi_client import CostResult

        self.costs_fetched.append(call_id)
        if self._cost_results:
            return self._cost_results.popleft()
        return CostResult(ok=True, cost_usd=0.12)


@pytest.fixture()
def fake_voice_provider() -> FakeVoiceProvider:
    """A fresh scripted FakeVoiceProvider per test (never networks)."""
    return FakeVoiceProvider()
