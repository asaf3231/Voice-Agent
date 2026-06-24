"""Calendar backend — booking behind one swappable interface.

Defines the CalendarProvider interface (list_slots / create_event) with two
implementations: an in-memory MockCalendar (the deterministic offline default) and
CalComCalendar (the live Cal.com client). Both are idempotent — booking the same
lead and slot twice returns the same event and never double-books — and both return
structured results instead of raising, so a busy slot or a backend error is data,
not a crash.

Import-safe: the live client is built lazily on first use; the offline suite uses
the mock directly and never touches the network.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Protocol, runtime_checkable

from app.config import (
    BOOKING_LOOKAHEAD_DAYS,
    BOOKING_SLOT_MINUTES,
    get_setting,
    require_setting,
)

logger = logging.getLogger(__name__)

# The sales calendar's authoritative timezone. Bookings are stored/compared in
# this zone; the lead's local tz is resolved against it.
# UTC is the only safe, OS-agnostic default that the offline suite can rely on
# without a tz database surprise; the live Cal.com event type carries its own tz.
SALES_CALENDAR_TZ = timezone.utc


# ===========================================================================
# Value types (structured data — never raw exceptions across the seam)
# ===========================================================================

@dataclass(frozen=True)
class Slot:
    """A bookable time window in the sales calendar.

    `start` / `end` are timezone-aware UTC datetimes (the calendar's tz). The
    duration is always BOOKING_SLOT_MINUTES — the slot grid is fixed.
    """

    start: datetime
    end: datetime

    def key(self) -> str:
        """A stable, comparable identity for this slot (idempotency key part)."""
        return self.start.astimezone(timezone.utc).isoformat()


@dataclass(frozen=True)
class BookingResult:
    """The structured outcome of a create_event attempt (never an exception).

    ok=True  → event_id is the created/idempotent event's id.
    ok=False → reason is one of: "slot_taken", "calendar_error", "invalid_slot".
               event_id is None. The agent must NOT voice a confirmation.
    """

    ok: bool
    event_id: str | None = None
    reason: str | None = None
    detail: str | None = None


# ===========================================================================
# The CalendarProvider interface — the ONLY way out to a booking backend.
# ===========================================================================

@runtime_checkable
class CalendarProvider(Protocol):
    """The booking seam. Exactly these two methods.

    An implementation must be deterministic given its own inputs and must never
    raise across this boundary for an expected failure (a busy slot, a backend
    5xx) — it returns structured data instead (BookingResult / a slot list).
    """

    def list_slots(
        self,
        *,
        now: datetime,
        lookahead_days: int = BOOKING_LOOKAHEAD_DAYS,
        slot_minutes: int = BOOKING_SLOT_MINUTES,
    ) -> list[Slot]:
        """Return only genuinely free slots within the lookahead window.

        All slots are in the calendar's tz (SALES_CALENDAR_TZ). `now` is injected
        for determinism (the frozen clock in tests).
        """
        ...

    def create_event(
        self,
        *,
        lead_id: str,
        slot: Slot,
        summary: str,
    ) -> BookingResult:
        """Create a BOOKING_SLOT_MINUTES event for *lead_id* at *slot*.

        Idempotent: a repeat call for the same lead_id + slot returns the SAME
        event id and does NOT double-book. A slot already taken by ANOTHER lead
        returns ok=False / reason="slot_taken" — never a silent overwrite.
        """
        ...


# ===========================================================================
# MockCalendar — deterministic offline default (the test/suite backend)
# ===========================================================================

@dataclass
class MockCalendar:
    """An in-memory deterministic CalendarProvider for the offline suite.

    Free/busy is fully controllable: `busy_keys` holds slot keys that are
    pre-occupied; `_events` records bookings keyed by slot. Determinism: given
    the same `now`, the same lookahead/slot args, and the same busy set, it
    always returns the same slots in the same order.

    Slot grid: starting from the next whole hour at/after `now`, one slot every
    `slot_minutes`, business hours only (BUSINESS_START_HOUR..BUSINESS_END_HOUR
    in the calendar tz), across the lookahead window. This keeps the offline
    window small and reproducible without depending on a real backend.
    """

    # Business-hours bounds in the calendar tz (kept local to the mock — these
    # are mock-shaping knobs, not governance constants, so they live here, not in config.
    BUSINESS_START_HOUR: int = 9
    BUSINESS_END_HOUR: int = 17  # exclusive (last slot starts before this hour)

    # Slot keys that are pre-occupied (test-controllable busy set).
    busy_keys: set[str] = field(default_factory=set)
    # lead_id+slotkey -> event_id  (records bookings; powers idempotency)
    _events: dict[str, str] = field(default_factory=dict)
    # slotkey -> lead_id  (which lead holds a slot; powers no-double-book)
    _slot_owner: dict[str, str] = field(default_factory=dict)
    _seq: int = 0

    # ------------------------------------------------------------------
    # list_slots
    # ------------------------------------------------------------------

    def list_slots(
        self,
        *,
        now: datetime,
        lookahead_days: int = BOOKING_LOOKAHEAD_DAYS,
        slot_minutes: int = BOOKING_SLOT_MINUTES,
    ) -> list[Slot]:
        """Return free business-hours slots in the calendar tz, deterministically."""
        cal_now = now.astimezone(SALES_CALENDAR_TZ)
        # Start grid at the next whole hour strictly after `now` (no partial slot).
        cursor = cal_now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        horizon = cal_now + timedelta(days=lookahead_days)
        step = timedelta(minutes=slot_minutes)

        slots: list[Slot] = []
        while cursor < horizon:
            in_hours = self.BUSINESS_START_HOUR <= cursor.hour < self.BUSINESS_END_HOUR
            if in_hours:
                end = cursor + step
                # Only emit if the whole slot fits inside business hours.
                if end.hour <= self.BUSINESS_END_HOUR and end.date() == cursor.date():
                    slot = Slot(start=cursor, end=end)
                    if slot.key() not in self.busy_keys and slot.key() not in self._slot_owner:
                        slots.append(slot)
            cursor += step
        return slots

    # ------------------------------------------------------------------
    # create_event
    # ------------------------------------------------------------------

    def create_event(
        self,
        *,
        lead_id: str,
        slot: Slot,
        summary: str,
    ) -> BookingResult:
        """Idempotent booking; conflict → structured 'slot_taken' (no overwrite)."""
        # Validate the slot is a real BOOKING_SLOT_MINUTES window.
        if slot.end <= slot.start:
            return BookingResult(ok=False, reason="invalid_slot",
                                 detail="slot end is not after slot start")

        slot_key = slot.key()
        event_key = f"{lead_id}|{slot_key}"

        # Idempotency: same lead + same slot → return the SAME event id.
        existing = self._events.get(event_key)
        if existing is not None:
            return BookingResult(ok=True, event_id=existing)

        # Pre-occupied (test busy set) or owned by ANOTHER lead → slot_taken.
        owner = self._slot_owner.get(slot_key)
        if slot_key in self.busy_keys or (owner is not None and owner != lead_id):
            return BookingResult(ok=False, reason="slot_taken",
                                 detail="that time was just taken")

        # Create.
        self._seq += 1
        event_id = f"mock-evt-{self._seq:04d}"
        self._events[event_key] = event_id
        self._slot_owner[slot_key] = lead_id
        return BookingResult(ok=True, event_id=event_id)


# ===========================================================================
# CalComCalendar — the LIVE Cal.com client (lazy, gated, never in the suite)
# ===========================================================================

class CalComCalendar:
    """The live Cal.com CalendarProvider over httpx.

    Constructed ONLY by the lazy `_get_calendar()` (never at import). It reads
    CALCOM_API_KEY / CALCOM_EVENT_TYPE_ID via config when instantiated, and
    builds the httpx client lazily on first request. It is gated exactly like the
    other live paths and is never used in the default offline suite.
    """

    BASE_URL = "https://api.cal.com/v2"
    # Cal.com v2 pins a date-versioned contract PER endpoint (verified live
    # 2026-06-24): /slots needs 2024-09-04; /bookings needs 2026-02-25. v1 is
    # decommissioned (HTTP 410).
    SLOTS_API_VERSION = "2024-09-04"
    BOOKINGS_API_VERSION = "2026-02-25"

    def __init__(self) -> None:
        # require_setting raises a clean ValueError if the secret is absent — a
        # live-path misconfiguration is a loud, structured failure, not a crash
        # mid-call. These are read at construction (live path only), never import.
        self._api_key = require_setting("CALCOM_API_KEY")
        self._event_type_id = require_setting("CALCOM_EVENT_TYPE_ID")
        self._client = None  # httpx client built lazily on first request
        # Idempotency guard (the CalendarProvider contract): lead_id|slot_key
        # -> event_id for bookings already created by THIS client. A retry / webhook
        # redelivery for the same lead+slot returns the same id without POSTing again
        # (the live API POSTs unconditionally, so without this a double-call would
        # double-book).
        self._booked: dict[str, str] = {}

    def _get_client(self):
        """Build the httpx client on first use (kept off the import path).

        v2 authenticates with a Bearer token header (v1 used an apiKey query param).
        """
        if self._client is None:
            import httpx  # lazy: importing this module must not pull httpx in

            self._client = httpx.Client(
                base_url=self.BASE_URL,
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=httpx.Timeout(15.0),
            )
        return self._client

    def list_slots(
        self,
        *,
        now: datetime,
        lookahead_days: int = BOOKING_LOOKAHEAD_DAYS,
        slot_minutes: int = BOOKING_SLOT_MINUTES,
    ) -> list[Slot]:
        """Fetch free slots from Cal.com v2 (live). Errors → empty list (logged), never a crash."""
        try:
            client = self._get_client()
            start = now.astimezone(SALES_CALENDAR_TZ)
            end = start + timedelta(days=lookahead_days)
            resp = client.get(
                "/slots",
                headers={"cal-api-version": self.SLOTS_API_VERSION},
                params={
                    "eventTypeId": self._event_type_id,
                    "start": start.strftime("%Y-%m-%d"),
                    "end": end.strftime("%Y-%m-%d"),
                    "timeZone": "UTC",
                },
            )
            if resp.status_code >= 400:
                # Surface (don't silently swallow) — masked the v1-decommission 410.
                logger.warning("Cal.com /slots %s: %s", resp.status_code, resp.text[:300])
                return []
            return _parse_calcom_slots(resp.json(), slot_minutes=slot_minutes)
        except Exception as exc:  # noqa: BLE001 — a live failure is data, not a crash
            logger.warning("Cal.com /slots request failed: %s", exc)
            return []

    def create_event(
        self,
        *,
        lead_id: str,
        slot: Slot,
        summary: str,
    ) -> BookingResult:
        """Create a Cal.com v2 booking (live), idempotently. Any failure → structured.

        Idempotency: a repeat call for the same
        lead_id + slot returns the SAME event id and does NOT POST again, so a retry
        or webhook redelivery cannot double-book.

        v2 requires an `attendee` (name/email/timeZone). The lead's contact email is
        not in the synthetic data, so it defaults to a synthetic per-lead address;
        set CALCOM_ATTENDEE_EMAIL / CALCOM_ATTENDEE_NAME / CALCOM_ATTENDEE_TIMEZONE
        in the env to book against a real inbox (e.g. for the live demo).
        """
        # Idempotency guard: same lead + slot already booked by this client → reuse.
        event_key = f"{lead_id}|{slot.key()}"
        cached = self._booked.get(event_key)
        if cached is not None:
            return BookingResult(ok=True, event_id=cached)

        attendee = {
            "name": get_setting("CALCOM_ATTENDEE_NAME") or f"Alta Prospect {lead_id}",
            "email": get_setting("CALCOM_ATTENDEE_EMAIL") or f"aria-demo+{lead_id}@example.com",
            "timeZone": get_setting("CALCOM_ATTENDEE_TIMEZONE") or "UTC",
        }
        try:
            client = self._get_client()
            resp = client.post(
                "/bookings",
                headers={"cal-api-version": self.BOOKINGS_API_VERSION},
                json={
                    "eventTypeId": int(self._event_type_id),
                    "start": slot.start.astimezone(timezone.utc).isoformat(),
                    "attendee": attendee,
                    "metadata": {"lead_id": lead_id},
                },
            )
            if resp.status_code == 409:
                return BookingResult(ok=False, reason="slot_taken",
                                     detail="Cal.com reports the slot is no longer free")
            if resp.status_code >= 400:
                return BookingResult(ok=False, reason="calendar_error",
                                     detail=f"Cal.com /bookings {resp.status_code}: {resp.text[:300]}")
            data = resp.json().get("data") or {}
            event_id = str(data.get("uid") or data.get("id") or "")
            if not event_id:
                return BookingResult(ok=False, reason="calendar_error",
                                     detail="Cal.com returned no booking id")
            self._booked[event_key] = event_id  # remember for idempotency
            return BookingResult(ok=True, event_id=event_id)
        except Exception as exc:  # noqa: BLE001 — surface as data
            return BookingResult(ok=False, reason="calendar_error", detail=str(exc))


def _parse_calcom_slots(payload: dict, *, slot_minutes: int) -> list[Slot]:
    """Map a Cal.com **v2** /slots response into our Slot list (best-effort, total).

    v2 shape: {"data": {"YYYY-MM-DD": [{"start": "ISO±offset"}, ...], ...}}.
    """
    slots: list[Slot] = []
    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    step = timedelta(minutes=slot_minutes)
    for _day, items in (data.items() if isinstance(data, dict) else []):
        for item in items or []:
            time_str = item.get("start") if isinstance(item, dict) else None
            if not time_str:
                continue
            try:
                start = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
            except ValueError:
                continue
            start = start.astimezone(SALES_CALENDAR_TZ)
            slots.append(Slot(start=start, end=start + step))
    return slots


# ===========================================================================
# Lazy singleton — the live client is built on first call ONLY
# ===========================================================================

_calendar: CalendarProvider | None = None


def _get_calendar() -> CalendarProvider:
    """Return (constructing on first call) the LIVE Cal.com calendar client.

    NOT constructed at import — the module-level `_calendar` is None until the
    first live caller. The default offline suite uses MockCalendar directly and
    never reaches this function. Reads secrets via config only here.
    """
    global _calendar
    if _calendar is None:
        _calendar = CalComCalendar()
    return _calendar


def reset_calendar() -> None:
    """Reset the live singleton (test helper — do NOT call in production code)."""
    global _calendar
    _calendar = None
