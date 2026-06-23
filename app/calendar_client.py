"""Alta Outbound Voice Agent — app/calendar_client.py

Single responsibility: the booking layer behind ONE seam — the `CalendarProvider`
interface (CLAUDE.md §9). Two implementations live here:

  - `MockCalendar`  — the deterministic, in-memory, OFFLINE test default. Controllable
    free/busy slots; `create_event` returns a real-looking event id; idempotent (the
    same lead + slot ⇒ the same event, never a double-book); a busy slot ⇒ a structured
    "slot taken", never a silent overwrite (BOOK1–BOOK3 / Policy 5).
  - `CalComCalendar` — the LIVE Cal.com HTTP client (httpx). Built ONLY via the lazy
    `_get_calendar()`; import-safe (no client/secret/network at import). It reads
    CALCOM_API_KEY / CALCOM_EVENT_TYPE_ID via config only when CALLED. It is NEVER
    constructed at import nor exercised in the default suite (ENV4 / CON4).

The graded interface signature methods are EXACTLY `list_slots(...)` and
`create_event(...)` — do not rename or change them (CLAUDE.md §9).

Import-safety (ENV4): importing this module defines only constants, dataclasses,
classes, and functions. No client, no network, no .env read, no data read. The
module-level Cal.com singleton (`_calendar`) is None at import and only the lazy
`_get_calendar()` constructs it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Protocol, runtime_checkable

from app.config import (
    BOOKING_LOOKAHEAD_DAYS,
    BOOKING_SLOT_MINUTES,
    require_setting,
)

# The sales calendar's authoritative timezone. Bookings are stored/compared in
# this zone; the lead's local tz is resolved against it (TOOL1/BOOK1, Finding 6).
# UTC is the only safe, OS-agnostic default that the offline suite can rely on
# without a tz database surprise; the live Cal.com event type carries its own tz.
SALES_CALENDAR_TZ = timezone.utc


# ===========================================================================
# Value types (structured data — never raw exceptions across the seam, §6)
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
    """The structured outcome of a create_event attempt (never an exception, §6).

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
    """The booking seam (CLAUDE.md §9). EXACTLY these two graded methods.

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
    # are mock-shaping knobs, NOT governance constants, so they don't belong in §9).
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
    other live paths and is never used in the default offline suite (CON4).
    """

    BASE_URL = "https://api.cal.com/v1"

    def __init__(self) -> None:
        # require_setting raises a clean ValueError if the secret is absent — a
        # live-path misconfiguration is a loud, structured failure, not a crash
        # mid-call. These are read at construction (live path only), never import.
        self._api_key = require_setting("CALCOM_API_KEY")
        self._event_type_id = require_setting("CALCOM_EVENT_TYPE_ID")
        self._client = None  # httpx client built lazily on first request

    def _get_client(self):
        """Build the httpx client on first use (kept off the import path)."""
        if self._client is None:
            import httpx  # lazy: importing this module must not pull httpx in

            self._client = httpx.Client(
                base_url=self.BASE_URL,
                timeout=httpx.Timeout(10.0),
            )
        return self._client

    def list_slots(
        self,
        *,
        now: datetime,
        lookahead_days: int = BOOKING_LOOKAHEAD_DAYS,
        slot_minutes: int = BOOKING_SLOT_MINUTES,
    ) -> list[Slot]:
        """Fetch free slots from Cal.com (live). Errors → empty list, never a crash."""
        try:
            client = self._get_client()
            start = now.astimezone(SALES_CALENDAR_TZ)
            end = start + timedelta(days=lookahead_days)
            resp = client.get(
                "/slots",
                params={
                    "apiKey": self._api_key,
                    "eventTypeId": self._event_type_id,
                    "startTime": start.isoformat(),
                    "endTime": end.isoformat(),
                },
            )
            resp.raise_for_status()
            payload = resp.json()
            return _parse_calcom_slots(payload, slot_minutes=slot_minutes)
        except Exception:  # noqa: BLE001 — a live failure is data, not a crash (§6)
            return []

    def create_event(
        self,
        *,
        lead_id: str,
        slot: Slot,
        summary: str,
    ) -> BookingResult:
        """Create a Cal.com booking (live). Any failure → structured BookingResult."""
        try:
            client = self._get_client()
            resp = client.post(
                "/bookings",
                params={"apiKey": self._api_key},
                json={
                    "eventTypeId": int(self._event_type_id),
                    "start": slot.start.astimezone(SALES_CALENDAR_TZ).isoformat(),
                    "end": slot.end.astimezone(SALES_CALENDAR_TZ).isoformat(),
                    "metadata": {"lead_id": lead_id},
                    "title": summary,
                },
            )
            if resp.status_code == 409:
                return BookingResult(ok=False, reason="slot_taken",
                                     detail="Cal.com reports the slot is no longer free")
            resp.raise_for_status()
            data = resp.json()
            event_id = str(data.get("id") or data.get("uid") or "")
            if not event_id:
                return BookingResult(ok=False, reason="calendar_error",
                                     detail="Cal.com returned no booking id")
            return BookingResult(ok=True, event_id=event_id)
        except Exception as exc:  # noqa: BLE001 — surface as data (§6)
            return BookingResult(ok=False, reason="calendar_error", detail=str(exc))


def _parse_calcom_slots(payload: dict, *, slot_minutes: int) -> list[Slot]:
    """Map a Cal.com /slots response into our Slot list (best-effort, total)."""
    slots: list[Slot] = []
    raw = payload.get("slots", {}) if isinstance(payload, dict) else {}
    step = timedelta(minutes=slot_minutes)
    for _day, items in (raw.items() if isinstance(raw, dict) else []):
        for item in items or []:
            time_str = item.get("time") if isinstance(item, dict) else None
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
# Lazy singleton — the live client is built on first call ONLY (ENV4)
# ===========================================================================

_calendar: CalendarProvider | None = None


def _get_calendar() -> CalendarProvider:
    """Return (constructing on first call) the LIVE Cal.com calendar client.

    NOT constructed at import — the module-level `_calendar` is None until the
    first live caller. The default offline suite uses MockCalendar directly and
    never reaches this function (CON4 / ENV4). Reads secrets via config only here.
    """
    global _calendar
    if _calendar is None:
        _calendar = CalComCalendar()
    return _calendar


def reset_calendar() -> None:
    """Reset the live singleton (test helper — do NOT call in production code)."""
    global _calendar
    _calendar = None
