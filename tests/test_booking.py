"""Stage 3 — booking layer tests (BOOK1–BOOK3) + calendar import-safety.

Backend under test: app.calendar_client.MockCalendar (the offline default).
The live Cal.com client is NEVER constructed here (gated/lazy — ENV4/CON4).
A frozen clock makes the slot window reproducible.

  BOOK1 — list_slots returns only genuinely free slots, with explicit tz handling.
  BOOK2 — create_event creates a BOOKING_SLOT_MINUTES event, returns a real id.
  BOOK3 — a conflict yields structured "slot_taken"; no phantom/overwrite booking.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.config import BOOKING_LOOKAHEAD_DAYS, BOOKING_SLOT_MINUTES
from app.calendar_client import (
    BookingResult,
    CalComCalendar,
    CalendarProvider,
    MockCalendar,
    SALES_CALENDAR_TZ,
    Slot,
    _get_calendar,
    reset_calendar,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def frozen_clock() -> datetime:
    """A fixed 'now' (Mon 2026-06-29 08:00 UTC) so slot windows are reproducible."""
    return datetime(2026, 6, 29, 8, 0, 0, tzinfo=timezone.utc)


@pytest.fixture()
def calendar() -> MockCalendar:
    """A fresh deterministic MockCalendar (FakeCalendar) per test."""
    return MockCalendar()


# ---------------------------------------------------------------------------
# Interface conformance
# ---------------------------------------------------------------------------

class TestInterfaceConformance:
    def test_mock_is_calendar_provider(self, calendar):
        """MockCalendar satisfies the runtime-checkable CalendarProvider Protocol."""
        assert isinstance(calendar, CalendarProvider)

    def test_calcom_class_has_graded_method_names(self):
        """The graded method names list_slots / create_event exist on the live class."""
        assert hasattr(CalComCalendar, "list_slots")
        assert hasattr(CalComCalendar, "create_event")


# ---------------------------------------------------------------------------
# BOOK1 — slot listing
# ---------------------------------------------------------------------------

class TestBook1ListSlots:
    def test_returns_only_free_slots(self, calendar, frozen_clock):
        slots = calendar.list_slots(now=frozen_clock)
        assert len(slots) > 0, "expected free slots in the lookahead window"

    def test_all_slots_within_lookahead_window(self, calendar, frozen_clock):
        slots = calendar.list_slots(now=frozen_clock)
        horizon = frozen_clock + timedelta(days=BOOKING_LOOKAHEAD_DAYS)
        for s in slots:
            assert frozen_clock < s.start < horizon

    def test_each_slot_is_booking_slot_minutes(self, calendar, frozen_clock):
        slots = calendar.list_slots(now=frozen_clock)
        for s in slots:
            assert s.end - s.start == timedelta(minutes=BOOKING_SLOT_MINUTES)

    def test_slots_are_in_calendar_tz(self, calendar, frozen_clock):
        slots = calendar.list_slots(now=frozen_clock)
        for s in slots:
            assert s.start.tzinfo is not None
            assert s.start.utcoffset() == SALES_CALENDAR_TZ.utcoffset(None)

    def test_deterministic_across_calls(self, frozen_clock):
        """Same now + same busy set ⇒ identical slot list (determinism)."""
        a = MockCalendar().list_slots(now=frozen_clock)
        b = MockCalendar().list_slots(now=frozen_clock)
        assert [s.key() for s in a] == [s.key() for s in b]

    def test_busy_slot_is_excluded(self, calendar, frozen_clock):
        """A pre-occupied slot key never appears in the free list."""
        free = calendar.list_slots(now=frozen_clock)
        taken_key = free[0].key()
        cal2 = MockCalendar(busy_keys={taken_key})
        free2 = cal2.list_slots(now=frozen_clock)
        assert taken_key not in {s.key() for s in free2}

    def test_booked_slot_excluded_from_subsequent_listing(self, calendar, frozen_clock):
        """After a successful booking, that slot drops out of list_slots (no double-offer)."""
        free = calendar.list_slots(now=frozen_clock)
        target = free[0]
        res = calendar.create_event(lead_id="lead-001", slot=target, summary="x")
        assert res.ok
        free_after = calendar.list_slots(now=frozen_clock)
        assert target.key() not in {s.key() for s in free_after}


# ---------------------------------------------------------------------------
# BOOK2 — event creation
# ---------------------------------------------------------------------------

class TestBook2CreateEvent:
    def test_creates_event_returns_real_id(self, calendar, frozen_clock):
        slot = calendar.list_slots(now=frozen_clock)[0]
        res = calendar.create_event(lead_id="lead-001", slot=slot, summary="Alta intro")
        assert isinstance(res, BookingResult)
        assert res.ok is True
        assert res.event_id and res.event_id.startswith("mock-evt-")
        assert res.reason is None

    def test_event_is_booking_slot_minutes(self, calendar, frozen_clock):
        slot = calendar.list_slots(now=frozen_clock)[0]
        assert slot.end - slot.start == timedelta(minutes=BOOKING_SLOT_MINUTES)
        res = calendar.create_event(lead_id="lead-001", slot=slot, summary="x")
        assert res.ok

    def test_invalid_slot_rejected_structured(self, calendar):
        """A degenerate slot (end <= start) → structured invalid_slot, never a crash."""
        bad = Slot(
            start=datetime(2026, 6, 29, 10, 0, tzinfo=timezone.utc),
            end=datetime(2026, 6, 29, 10, 0, tzinfo=timezone.utc),
        )
        res = calendar.create_event(lead_id="lead-001", slot=bad, summary="x")
        assert res.ok is False
        assert res.reason == "invalid_slot"


# ---------------------------------------------------------------------------
# BOOK3 — conflict / no phantom booking / idempotency
# ---------------------------------------------------------------------------

class TestBook3ConflictAndIdempotency:
    def test_same_lead_same_slot_is_idempotent(self, calendar, frozen_clock):
        """Repeat booking for the SAME lead+slot returns the SAME id (no double-book)."""
        slot = calendar.list_slots(now=frozen_clock)[0]
        first = calendar.create_event(lead_id="lead-001", slot=slot, summary="x")
        second = calendar.create_event(lead_id="lead-001", slot=slot, summary="x")
        assert first.ok and second.ok
        assert first.event_id == second.event_id

    def test_other_lead_same_slot_is_slot_taken(self, calendar, frozen_clock):
        """A DIFFERENT lead booking an occupied slot → slot_taken, no overwrite."""
        slot = calendar.list_slots(now=frozen_clock)[0]
        owner = calendar.create_event(lead_id="lead-001", slot=slot, summary="x")
        assert owner.ok
        conflict = calendar.create_event(lead_id="lead-002", slot=slot, summary="x")
        assert conflict.ok is False
        assert conflict.reason == "slot_taken"
        assert conflict.event_id is None
        # The original owner's event id is unchanged (no silent overwrite).
        again = calendar.create_event(lead_id="lead-001", slot=slot, summary="x")
        assert again.event_id == owner.event_id

    def test_prebusy_slot_is_slot_taken(self, frozen_clock):
        """A slot in the busy set returns slot_taken — never a phantom confirmation."""
        cal = MockCalendar()
        slot = cal.list_slots(now=frozen_clock)[0]
        cal_busy = MockCalendar(busy_keys={slot.key()})
        res = cal_busy.create_event(lead_id="lead-001", slot=slot, summary="x")
        assert res.ok is False
        assert res.reason == "slot_taken"
        assert res.event_id is None

    def test_no_event_count_increase_on_conflict(self, calendar, frozen_clock):
        """A conflict must not create any event (no phantom booking, Policy 5)."""
        slot = calendar.list_slots(now=frozen_clock)[0]
        calendar.create_event(lead_id="lead-001", slot=slot, summary="x")
        before = len(calendar._events)
        calendar.create_event(lead_id="lead-002", slot=slot, summary="x")  # conflict
        assert len(calendar._events) == before


# ---------------------------------------------------------------------------
# Finding #2 — CalComCalendar.create_event idempotency (contract / Policy 5)
# ---------------------------------------------------------------------------

class TestCalComIdempotency:
    """The live client must honor the CalendarProvider idempotency contract: a repeat
    create_event for the same lead+slot returns the SAME id and does NOT POST again,
    so a retry / webhook redelivery cannot double-book (the live API POSTs blindly)."""

    class _FakeResp:
        status_code = 200

        def raise_for_status(self):  # no-op (200)
            pass

        def json(self):
            return {"id": "calcom-evt-1"}

    def _calcom(self, monkeypatch):
        monkeypatch.setenv("CALCOM_API_KEY", "test-key")
        monkeypatch.setenv("CALCOM_EVENT_TYPE_ID", "123")
        return CalComCalendar()

    def test_repeat_same_lead_slot_returns_same_id_without_reposting(
        self, monkeypatch, frozen_clock
    ):
        cal = self._calcom(monkeypatch)
        posts: list = []

        class _FakeClient:
            def post(_self, *a, **k):
                posts.append((a, k))
                return TestCalComIdempotency._FakeResp()

        monkeypatch.setattr(cal, "_get_client", lambda: _FakeClient())
        slot = Slot(
            start=frozen_clock,
            end=frozen_clock + timedelta(minutes=BOOKING_SLOT_MINUTES),
        )
        r1 = cal.create_event(lead_id="lead-001", slot=slot, summary="x")
        r2 = cal.create_event(lead_id="lead-001", slot=slot, summary="x")
        assert r1.ok and r2.ok
        assert r1.event_id == r2.event_id == "calcom-evt-1"
        assert len(posts) == 1, "a repeat booking must NOT POST again (no double-book)"


# ---------------------------------------------------------------------------
# Import-safety / live-client gating (ENV4 / CON4)
# ---------------------------------------------------------------------------

class TestCalendarImportSafety:
    def test_live_singleton_none_at_import(self):
        """The live Cal.com singleton is None at import (never built eagerly)."""
        import app.calendar_client as cc
        reset_calendar()
        assert cc._calendar is None

    def test_get_calendar_requires_secret(self, monkeypatch):
        """_get_calendar() (live path) raises a clean error when the secret is absent.

        Proves the live client is gated on CALCOM_API_KEY and is never silently
        constructed without it — and that this path is only reached on explicit call.
        """
        reset_calendar()
        monkeypatch.delenv("CALCOM_API_KEY", raising=False)
        monkeypatch.delenv("CALCOM_EVENT_TYPE_ID", raising=False)
        with pytest.raises(ValueError):
            _get_calendar()
        reset_calendar()

    def test_importing_module_builds_no_httpx_client(self):
        """Importing calendar_client must not pull httpx in at module level (ENV4)."""
        import app.calendar_client as cc
        assert "httpx" not in dir(cc), "httpx must be imported lazily, not at module level"
