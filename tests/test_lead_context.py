"""Tests that the authoritative lead_id and timezone are injected at the dispatch chokepoint — never trusted from the model."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

import app.tools as tools
import app.server as server
from app.calendar_client import MockCalendar
from app.vapi_client import VapiVoiceProvider


@pytest.fixture()
def frozen_clock() -> datetime:
    """Mon 2026-06-29 08:00 UTC — reproducible slot window."""
    return datetime(2026, 6, 29, 8, 0, 0, tzinfo=timezone.utc)


@pytest.fixture()
def calendar() -> MockCalendar:
    return MockCalendar()


def _first_slot(calendar, frozen_clock, tz="Asia/Jerusalem"):
    res = tools.check_availability(calendar=calendar, now=frozen_clock, lead_timezone=tz)
    return res.to_dict()["data"]["slots"][0]


# ---------------------------------------------------------------------------
# D2 — check_availability emits a pre-formatted 'say' string in the LEAD tz
# ---------------------------------------------------------------------------

class TestSayString:
    def test_slot_carries_a_say_string(self, calendar, frozen_clock):
        slot = _first_slot(calendar, frozen_clock)
        assert slot.get("say")
        # Note #3 (Asaf 2026-06-24): the verbose "your time" suffix is dropped — the
        # time is stated plainly (still computed in the lead's tz). Guard against re-add.
        assert "your time" not in slot["say"].lower()

    def test_say_uses_lead_local_time_not_utc(self, calendar, frozen_clock):
        slot = _first_slot(calendar, frozen_clock, tz="Asia/Jerusalem")
        local = datetime.fromisoformat(slot["start_lead_local"])
        hour12 = local.hour % 12 or 12
        # The lead-local 12h clock time must be the one voiced — never the UTC hour.
        assert f"{hour12}:{local.minute:02d}" in slot["say"]

    def test_say_does_not_claim_your_time_on_tz_fallback(self, calendar, frozen_clock):
        # No lead tz → degrades to the sales-calendar tz; must NOT falsely claim
        # "your time" (the D2 class of mislabel, just relocated to the calendar tz).
        res = tools.check_availability(calendar=calendar, now=frozen_clock, lead_timezone=None)
        assert "your time" not in res.to_dict()["data"]["slots"][0]["say"].lower()


# ---------------------------------------------------------------------------
# D2 — dispatch injects the authoritative lead_timezone (overrides any model value)
# ---------------------------------------------------------------------------

class TestTimezoneInjection:
    def test_dispatch_injects_authoritative_timezone(self, calendar, frozen_clock):
        slot = tools.dispatch(
            "check_availability", calendar=calendar, now=frozen_clock,
            lead_timezone="Asia/Jerusalem",
        ).to_dict()["data"]["slots"][0]
        assert slot["lead_tz"] == "Asia/Jerusalem"


# ---------------------------------------------------------------------------
# D3 — dispatch injects the authoritative lead_id (no fabricated placeholder)
# ---------------------------------------------------------------------------

class TestLeadIdInjection:
    def test_dispatch_injects_lead_id_into_book_meeting(self, calendar, frozen_clock):
        iso = _first_slot(calendar, frozen_clock)["start_utc"]
        res = tools.dispatch(
            "book_meeting", calendar=calendar, lead_id="real-007", slot_start_iso=iso
        )
        assert res.ok is True  # injected lead_id → booking proceeds

    def test_dispatch_injects_lead_id_into_log_disposition(self):
        res = tools.dispatch("log_disposition", lead_id="real-007", disposition="booked")
        assert res.to_dict()["data"]["lead_id"] == "real-007"

    def test_book_meeting_fails_loud_without_an_injected_lead_id(self, calendar, frozen_clock):
        # No authoritative lead_id (and the model no longer supplies one) → fail loudly,
        # NEVER silently book under a placeholder default.
        iso = _first_slot(calendar, frozen_clock)["start_utc"]
        res = tools.dispatch("book_meeting", calendar=calendar, slot_start_iso=iso)
        assert res.ok is False and res.error == "invalid_input"


# ---------------------------------------------------------------------------
# Assistant wiring — metadata carries lead context; schemas drop the lead fields
# ---------------------------------------------------------------------------

class TestAssistantWiring:
    def test_metadata_carries_lead_context(self):
        a = VapiVoiceProvider().configure_assistant(
            variant="A", lead={"lead_id": "L1", "timezone": "Asia/Jerusalem"}
        )
        assert a["metadata"]["lead_id"] == "L1"
        assert a["metadata"]["lead_timezone"] == "Asia/Jerusalem"

    def test_schema_drops_model_supplied_lead_fields(self):
        a = VapiVoiceProvider().configure_assistant(variant="A")
        fns = {t["function"]["name"]: t["function"] for t in a["model"]["tools"]}
        assert "lead_id" not in fns["book_meeting"]["parameters"]["properties"]
        assert "lead_timezone" not in fns["check_availability"]["parameters"]["properties"]


# ---------------------------------------------------------------------------
# Server chokepoint — lead context from payload metadata, env fallback
# ---------------------------------------------------------------------------

class TestServerLeadContext:
    def test_extract_from_payload_metadata(self):
        payload = {"message": {"call": {"assistant": {"metadata": {
            "lead_id": "meta-007", "lead_timezone": "Asia/Jerusalem"}}}}}
        lead_id, tz = server.extract_lead_context(payload)
        assert lead_id == "meta-007"
        assert tz == "Asia/Jerusalem"

    def test_extract_falls_back_to_env(self, monkeypatch):
        monkeypatch.setenv("LEAD_ID", "env-007")
        monkeypatch.setenv("LEAD_TIMEZONE", "Asia/Jerusalem")
        lead_id, tz = server.extract_lead_context({})
        assert lead_id == "env-007"
        assert tz == "Asia/Jerusalem"


# ---------------------------------------------------------------------------
# Webhook integration — a model-supplied placeholder is stripped + overridden
# ---------------------------------------------------------------------------

class TestWebhookInjection:
    def test_model_lead_id_overridden_by_authoritative(self, monkeypatch):
        from fastapi.testclient import TestClient
        monkeypatch.setenv("VAPI_WEBHOOK_SECRET", "s3cr3t")
        monkeypatch.setenv("LEAD_ID", "real-007")
        monkeypatch.delenv("LEAD_TIMEZONE", raising=False)
        client = TestClient(server.app)
        payload = {
            "name": "log_disposition",
            "arguments": {"lead_id": "lead_id_placeholder", "disposition": "booked"},
        }
        resp = client.post(
            "/webhook/tool", json=payload, headers={"x-vapi-secret": "s3cr3t"}
        )
        result = json.loads(resp.json()["results"][0]["result"])
        assert result["data"]["lead_id"] == "real-007"  # placeholder ignored
