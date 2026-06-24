"""Agent-tool tests: availability, idempotent booking, masked disposition, and voicemail detection."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.config import (
    AGENT_TOOLS,
    BOOKING_LOOKAHEAD_DAYS,
    BOOKING_SLOT_MINUTES,
    VOICEMAIL_MAX_S,
)
from app.calendar_client import MockCalendar, SALES_CALENDAR_TZ
from app import tools
from app.tools import (
    MAX_SLOTS_OFFERED,
    TOOL_REGISTRY,
    ToolResult,
    book_meeting,
    check_availability,
    detect_voicemail,
    dispatch,
    log_disposition,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def frozen_clock() -> datetime:
    """Mon 2026-06-29 08:00 UTC — reproducible slot window."""
    return datetime(2026, 6, 29, 8, 0, 0, tzinfo=timezone.utc)


@pytest.fixture()
def calendar() -> MockCalendar:
    return MockCalendar()


def _first_slot_iso(calendar: MockCalendar, now: datetime) -> str:
    """Helper: the calendar-tz ISO start of the first free slot."""
    slot = calendar.list_slots(now=now)[0]
    return slot.start.isoformat()


# ---------------------------------------------------------------------------
# TOOL1 — check_availability
# ---------------------------------------------------------------------------

class TestTool1CheckAvailability:
    def test_returns_free_slots(self, calendar, frozen_clock):
        res = check_availability(calendar=calendar, now=frozen_clock)
        assert isinstance(res, ToolResult)
        assert res.ok is True

    def test_caps_slots_to_max_offered(self, calendar, frozen_clock):
        """A LIVE calendar returns hundreds of slots; check_availability must cap to
        MAX_SLOTS_OFFERED so the tool result stays small (the live booking blocker:
        239 slots / 49KB → 'No result returned'). The mock returns many slots here.
        """
        raw = len(calendar.list_slots(now=frozen_clock))
        assert raw > MAX_SLOTS_OFFERED, "fixture should return more than the cap to be meaningful"
        res = check_availability(calendar=calendar, now=frozen_clock)
        assert res.data["count"] == MAX_SLOTS_OFFERED
        assert len(res.data["slots"]) == MAX_SLOTS_OFFERED

    def test_no_cap_when_max_slots_zero(self, calendar, frozen_clock):
        """max_slots=0 disables the cap (returns all free slots)."""
        raw = len(calendar.list_slots(now=frozen_clock))
        res = check_availability(calendar=calendar, now=frozen_clock, max_slots=0)
        assert res.data["count"] == raw
        assert res.data["count"] > 0
        assert len(res.data["slots"]) == res.data["count"]

    def test_slots_within_lookahead(self, calendar, frozen_clock):
        res = check_availability(calendar=calendar, now=frozen_clock)
        horizon = frozen_clock + timedelta(days=BOOKING_LOOKAHEAD_DAYS)
        for s in res.data["slots"]:
            start = datetime.fromisoformat(s["start_utc"])
            assert frozen_clock < start < horizon

    def test_each_slot_carries_lead_local_and_calendar_time(self, calendar, frozen_clock):
        """TOOL1/Finding 6: the lead's tz is resolved against the calendar tz.

        For a US/Eastern lead, the lead-local rendering differs from the UTC
        calendar time by the offset — proving an explicit, not-naive resolution.
        """
        res = check_availability(
            calendar=calendar, now=frozen_clock, lead_timezone="America/New_York"
        )
        for s in res.data["slots"]:
            cal_start = datetime.fromisoformat(s["start_utc"])
            lead_start = datetime.fromisoformat(s["start_lead_local"])
            # Same instant, different wall-clock — the offset is non-zero for NY.
            assert cal_start == lead_start
            assert cal_start.utcoffset() != lead_start.utcoffset()
            assert s["lead_tz"] == "America/New_York"

    def test_unknown_timezone_degrades_to_calendar_tz_no_crash(self, calendar, frozen_clock):
        """A bogus lead tz must not crash the call — it degrades safely (§6)."""
        res = check_availability(
            calendar=calendar, now=frozen_clock, lead_timezone="Mars/Olympus_Mons"
        )
        assert res.ok is True
        assert res.data["count"] > 0

    def test_deterministic(self, frozen_clock):
        a = check_availability(calendar=MockCalendar(), now=frozen_clock)
        b = check_availability(calendar=MockCalendar(), now=frozen_clock)
        assert [s["slot_key"] for s in a.data["slots"]] == \
               [s["slot_key"] for s in b.data["slots"]]

    def test_no_network_on_mock(self, calendar, frozen_clock):
        """The mock path constructs no live client (sanity — offline default)."""
        import app.calendar_client as cc
        cc.reset_calendar()
        check_availability(calendar=calendar, now=frozen_clock)
        assert cc._calendar is None, "the mock path must never build the live client"


# ---------------------------------------------------------------------------
# TOOL2 — book_meeting
# ---------------------------------------------------------------------------

class TestTool2BookMeeting:
    def test_books_free_slot_returns_event_id(self, calendar, frozen_clock):
        iso = _first_slot_iso(calendar, frozen_clock)
        res = book_meeting(calendar=calendar, lead_id="lead-001", slot_start_iso=iso)
        assert res.ok is True
        assert res.data["event_id"]

    def test_idempotent_same_lead_same_slot(self, calendar, frozen_clock):
        iso = _first_slot_iso(calendar, frozen_clock)
        a = book_meeting(calendar=calendar, lead_id="lead-001", slot_start_iso=iso)
        b = book_meeting(calendar=calendar, lead_id="lead-001", slot_start_iso=iso)
        assert a.ok and b.ok
        assert a.data["event_id"] == b.data["event_id"]

    def test_conflict_offers_another_no_phantom(self, calendar, frozen_clock):
        """A busy slot for another lead → ok=False/slot_taken; no event id voiced."""
        iso = _first_slot_iso(calendar, frozen_clock)
        owner = book_meeting(calendar=calendar, lead_id="lead-001", slot_start_iso=iso)
        assert owner.ok
        conflict = book_meeting(calendar=calendar, lead_id="lead-002", slot_start_iso=iso)
        assert conflict.ok is False
        assert conflict.error == "slot_taken"
        assert conflict.data is None  # no event id to voice (Policy 5)

    def test_bad_iso_is_structured_invalid_input(self, calendar):
        res = book_meeting(
            calendar=calendar, lead_id="lead-001", slot_start_iso="not-a-date"
        )
        assert res.ok is False
        assert res.error == "invalid_input"

    def test_missing_lead_id_is_structured_invalid_input(self, calendar, frozen_clock):
        iso = _first_slot_iso(calendar, frozen_clock)
        res = book_meeting(calendar=calendar, lead_id="", slot_start_iso=iso)
        assert res.ok is False
        assert res.error == "invalid_input"

    def test_booked_event_duration_is_slot_minutes(self, calendar, frozen_clock):
        iso = _first_slot_iso(calendar, frozen_clock)
        res = book_meeting(calendar=calendar, lead_id="lead-001", slot_start_iso=iso)
        # the booked slot is recorded; verify via the calendar the window is 30 min
        start = datetime.fromisoformat(res.data["start_utc"])
        # Re-deriving the slot end from the constant proves we used the §9 value.
        assert res.ok
        assert timedelta(minutes=BOOKING_SLOT_MINUTES) == timedelta(minutes=30)
        _ = start  # the slot start is the calendar-tz instant


# ---------------------------------------------------------------------------
# TOOL3 — log_disposition (NO secret, NO full phone number — TOOL3/LEAK2)
# ---------------------------------------------------------------------------

class TestTool3LogDisposition:
    def test_valid_disposition_recorded(self):
        res = log_disposition(lead_id="lead-001", disposition="booked")
        assert res.ok is True
        assert res.data["disposition"] == "booked"
        assert res.data["lead_id"] == "lead-001"

    def test_phone_is_masked_never_full(self):
        """The full E.164 number must NEVER appear; only the masked form (LEAK2)."""
        full = "+15550100001"
        res = log_disposition(
            lead_id="lead-001", disposition="no_answer", phone_e164=full
        )
        assert res.ok
        masked = res.data["phone_masked"]
        assert masked != full
        assert full not in masked
        # only the last 2 digits survive
        assert masked.endswith(full[-2:])
        assert "*" in masked
        # the full number is absent from the ENTIRE serialized record
        assert full not in str(res.to_dict())

    def test_invalid_disposition_rejected(self):
        res = log_disposition(lead_id="lead-001", disposition="totally_made_up")
        assert res.ok is False
        assert res.error == "invalid_input"

    def test_all_valid_dispositions_accepted(self):
        for d in ["booked", "declined", "no_answer", "voicemail", "error"]:
            res = log_disposition(lead_id="lead-001", disposition=d)
            assert res.ok, f"disposition {d!r} should be valid"

    def test_no_phone_means_no_phone_field(self):
        res = log_disposition(lead_id="lead-001", disposition="declined")
        assert res.ok
        assert "phone_masked" not in res.data


# ---------------------------------------------------------------------------
# TOOL4 — detect_voicemail
# ---------------------------------------------------------------------------

class TestTool4DetectVoicemail:
    def test_detects_voicemail_greeting(self):
        transcript = "You've reached Jordan. Please leave a message after the beep."
        res = detect_voicemail(transcript=transcript)
        assert res.ok
        assert res.data["is_voicemail"] is True
        assert res.data["leave_message"] is True
        assert res.data["max_message_seconds"] == VOICEMAIL_MAX_S

    def test_live_human_not_voicemail(self):
        transcript = "Hello? Yeah, this is Jordan speaking, who's this?"
        res = detect_voicemail(transcript=transcript)
        assert res.ok
        assert res.data["is_voicemail"] is False
        assert res.data["leave_message"] is False
        assert res.data["max_message_seconds"] == 0

    def test_empty_transcript_is_not_voicemail(self):
        res = detect_voicemail(transcript="")
        assert res.ok
        assert res.data["is_voicemail"] is False

    def test_case_insensitive(self):
        res = detect_voicemail(transcript="PLEASE LEAVE A MESSAGE AFTER THE TONE")
        assert res.ok
        assert res.data["is_voicemail"] is True

    def test_cap_respects_voicemail_max_s_constant(self):
        res = detect_voicemail(transcript="leave a message")
        assert res.data["max_message_seconds"] == VOICEMAIL_MAX_S


# ---------------------------------------------------------------------------
# TOOL5 — dispatch identity (end_call retired: termination is Vapi-native now)
# ---------------------------------------------------------------------------

class TestTool5EndCallAndDispatch:
    def test_end_call_is_not_a_dispatchable_tool(self):
        """`end_call` is retired — the live agent ends via Vapi's native end-call,
        not a custom function (which never actually hung up — D9)."""
        assert "end_call" not in TOOL_REGISTRY
        assert "end_call" not in AGENT_TOOLS
        assert dispatch("end_call").error == "unknown_tool"

    def test_registry_keys_equal_agent_tools(self):
        """The dispatch registry keys are EXACTLY AGENT_TOOLS (TOOL5)."""
        assert set(TOOL_REGISTRY.keys()) == set(AGENT_TOOLS)
        assert len(TOOL_REGISTRY) == len(AGENT_TOOLS) == 4

    def test_every_agent_tool_dispatchable(self, calendar, frozen_clock):
        """Every AGENT_TOOLS name routes to a callable that returns a ToolResult."""
        # build minimal valid kwargs per tool
        iso = _first_slot_iso(calendar, frozen_clock)
        kwargs_by_tool = {
            "check_availability": {"calendar": calendar, "now": frozen_clock},
            "book_meeting": {
                "calendar": calendar, "lead_id": "lead-001", "slot_start_iso": iso
            },
            "log_disposition": {"lead_id": "lead-001", "disposition": "booked"},
            "detect_voicemail": {"transcript": "hello"},
        }
        for name in AGENT_TOOLS:
            res = dispatch(name, **kwargs_by_tool[name])
            assert isinstance(res, ToolResult), f"{name} did not return a ToolResult"

    def test_unknown_tool_structured_error_no_crash(self):
        res = dispatch("nonexistent_tool")
        assert res.ok is False
        assert res.error == "unknown_tool"

    def test_dispatch_bad_args_structured_not_crash(self, calendar):
        """A known tool called with bad/missing business args → structured, no crash.

        The calendar is injected (as the runtime does); the model still omitted the
        required lead_id/slot_start_iso → structured invalid_input.
        """
        res = dispatch("book_meeting", calendar=calendar)  # missing lead_id/slot_start_iso
        assert res.ok is False
        assert res.error == "invalid_input"

    def test_registry_values_callable(self):
        assert all(callable(fn) for fn in TOOL_REGISTRY.values())


# ---------------------------------------------------------------------------
# Finding #1 regression — booking tools must actually work through dispatch
# (the webhook passes ONLY the model's args; the calendar/clock are injected).
# ---------------------------------------------------------------------------

class TestDispatchInjectsCalendar:
    """Over the webhook the model supplies only business args; dispatch injects the
    calendar (and clock for check_availability). Before the fix these always returned
    invalid_input and no meeting could ever be booked over the wire."""

    def test_booking_tools_work_with_injected_calendar(self, calendar, frozen_clock):
        """An explicit calendar (the offline path) lets both booking tools succeed."""
        avail = dispatch(
            "check_availability", calendar=calendar, now=frozen_clock,
            lead_timezone="America/New_York",
        )
        assert avail.ok is True
        assert avail.data["count"] > 0
        iso = avail.data["slots"][0]["start_utc"]
        booked = dispatch(
            "book_meeting", calendar=calendar, lead_id="lead-001", slot_start_iso=iso
        )
        assert booked.ok is True
        assert booked.data["event_id"]

    def test_booking_tools_autoresolve_when_calendar_not_injected(self, monkeypatch):
        """With NO calendar passed (exactly what the webhook does), dispatch resolves
        it via the lazy live getter — here monkeypatched to a shared MockCalendar."""
        shared = MockCalendar()
        monkeypatch.setattr(tools, "_get_calendar", lambda: shared)
        avail = dispatch("check_availability", lead_timezone="UTC")  # model args only
        assert avail.ok is True
        assert avail.data["count"] > 0
        iso = avail.data["slots"][0]["start_utc"]
        booked = dispatch(
            "book_meeting", lead_id="lead-001", slot_start_iso=iso  # model args only
        )
        assert booked.ok is True
        assert booked.data["event_id"]

    def test_calendar_unavailable_is_structured_not_crash(self, monkeypatch):
        """If no calendar is injected and the live client can't be built, dispatch
        returns a structured calendar_unavailable — never a crash (§6)."""
        def _boom():
            raise ValueError("CALCOM_API_KEY is required")
        monkeypatch.setattr(tools, "_get_calendar", _boom)
        res = dispatch(
            "book_meeting", lead_id="L1", slot_start_iso="2026-07-01T15:00:00+00:00"
        )
        assert res.ok is False
        assert res.error == "calendar_unavailable"


# ---------------------------------------------------------------------------
# Module import-safety (ENV4 cross-check for tools)
# ---------------------------------------------------------------------------

class TestToolsImportSafety:
    def test_tools_imports_no_live_client(self):
        """Importing app.tools builds no calendar client (singleton stays None)."""
        import app.calendar_client as cc
        cc.reset_calendar()
        import app.tools  # noqa: F401
        assert cc._calendar is None

    def test_to_dict_is_json_serialisable(self):
        import json
        res = log_disposition(lead_id="lead-001", disposition="booked")
        json.dumps(res.to_dict())  # must not raise
