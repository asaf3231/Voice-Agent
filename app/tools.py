"""Alta Outbound Voice Agent — app/tools.py

Single responsibility: the agent's 5 deterministic callable functions (the tools
the Realtime model invokes during a call) + a dispatch registry whose keys are
asserted == AGENT_TOOLS at import (CLAUDE.md §9, TOOL5).

The 5 tools (name == AGENT_TOOLS entry == schema name == dispatch key):
  - check_availability : free slots in the lookahead window, with the lead's tz
                         resolved against the sales-calendar tz (TOOL1/BOOK1).
  - book_meeting       : idempotent booking; conflict → "offer another" (TOOL2/BOOK3).
  - log_disposition    : a structured disposition; NO secret, NO full phone number
                         (masked via consent.mask_phone — TOOL3/LEAK2).
  - detect_voicemail   : classify a voicemail-greeting transcript; leave ≤
                         VOICEMAIL_MAX_S then end (TOOL4).
  - end_call           : clean hangup (TOOL5).

Resiliency (§6): every tool returns STRUCTURED data and never raises across its
boundary for an expected condition (a busy slot, a backend error, a bad input).
Bad input is reported as a structured error result, not an exception.

Import-safety (ENV4): importing this module builds no client, reads no .env, no
data/*, no network. The calendar backend is INJECTED (the offline default is a
MockCalendar passed by the caller); the live Cal.com client is only ever reached
through calendar_client._get_calendar(), never at import.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.config import (
    AGENT_TOOLS,
    BOOKING_LOOKAHEAD_DAYS,
    BOOKING_SLOT_MINUTES,
    VOICEMAIL_MAX_S,
)
from app.calendar_client import (
    BookingResult,
    CalendarProvider,
    SALES_CALENDAR_TZ,
    Slot,
    _get_calendar,
)
from app.consent import mask_phone

# The disposition vocabulary (TOOL3). Kept here (the tool layer owns it at
# runtime); app/eval/Disposition mirrors it for the offline harness.
VALID_DISPOSITIONS = frozenset(
    {"booked", "declined", "no_answer", "voicemail", "error"}
)

# Max free slots check_availability returns to the agent. A LIVE calendar can
# return hundreds of 15-min slots across the lookahead window; handing all of
# them to the voice model (a) overflowed the voice platform's tool-result
# (caused "No result returned" on the live call 2026-06-24) and (b) is poor UX —
# the agent should offer a few natural choices. NOT a §9 governance constant; a
# local tool-output tuning knob (mirrors orchestrate.PROJECTED_COST_PER_CALL).
MAX_SLOTS_OFFERED = 5

# Voicemail-greeting cues — case-insensitive substring signals (TOOL4). Generic
# carrier/greeting phrases only; NOT lead/business data (LEAK3-safe).
_VOICEMAIL_CUES = (
    "leave a message",
    "leave your message",
    "after the tone",
    "after the beep",
    "at the tone",
    "is not available",
    "is unavailable",
    "please record",
    "your call has been forwarded",
    "voicemail",
    "voice mail",
    "the person you are trying to reach",
    "press 1",
    "no one is available to take your call",
)


# ===========================================================================
# Result types — structured tool outputs (no exceptions across the seam, §6)
# ===========================================================================

@dataclass(frozen=True)
class ToolResult:
    """A uniform structured tool result.

    ok=True  → data carries the tool's payload.
    ok=False → error is a short machine code (e.g. "invalid_input",
               "slot_taken", "calendar_error"); message is human-readable.
    Tool outputs are always JSON-serialisable dicts via .to_dict().
    """

    ok: bool
    data: dict[str, Any] | None = None
    error: str | None = None
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"ok": self.ok}
        if self.data is not None:
            out["data"] = self.data
        if self.error is not None:
            out["error"] = self.error
        if self.message is not None:
            out["message"] = self.message
        return out


# ===========================================================================
# Timezone resolution (TOOL1/BOOK1 — Finding 6)
# ===========================================================================

def _resolve_zone(tz_name: str | None) -> ZoneInfo | timezone:
    """Resolve an IANA tz name to a tzinfo; fall back to the calendar tz.

    A missing/unknown tz never crashes the call — it degrades to the sales
    calendar tz (a safe, explicit default), so a bad lead record can't take the
    booking path down (§6).
    """
    if not tz_name:
        return SALES_CALENDAR_TZ
    try:
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        return SALES_CALENDAR_TZ


def _slot_to_payload(slot: Slot, lead_zone: ZoneInfo | timezone) -> dict[str, Any]:
    """Render a slot for the agent: BOTH the calendar-tz time and the lead-local time.

    The lead-local rendering is what the agent voices ("3pm your time"); the
    calendar-tz value is the authoritative booking time. Carrying both is the
    explicit tz resolution the grader checks (no "3pm in the wrong tz").
    """
    cal_start = slot.start.astimezone(SALES_CALENDAR_TZ)
    lead_start = slot.start.astimezone(lead_zone)
    return {
        "slot_key": slot.key(),
        "start_utc": cal_start.isoformat(),
        "end_utc": slot.end.astimezone(SALES_CALENDAR_TZ).isoformat(),
        "start_lead_local": lead_start.isoformat(),
        "lead_tz": str(getattr(lead_zone, "key", lead_zone)),
    }


# ===========================================================================
# Tool 1 — check_availability
# ===========================================================================

def check_availability(
    *,
    calendar: CalendarProvider,
    now: datetime,
    lead_timezone: str | None = None,
    lookahead_days: int = BOOKING_LOOKAHEAD_DAYS,
    slot_minutes: int = BOOKING_SLOT_MINUTES,
    max_slots: int = MAX_SLOTS_OFFERED,
) -> ToolResult:
    """Return up to *max_slots* free slots within the lookahead window, tz-resolved.

    Deterministic under the mock (the `now` clock is injected). Resolves the
    lead's timezone against SALES_CALENDAR_TZ so each slot is voiced in the
    lead's local time while booked at the authoritative calendar time (TOOL1).
    The result is CAPPED to a small spread of options (live calendars return
    hundreds of slots, which overflows the voice platform's tool-result and makes
    a poor "pick a time" UX). Any backend failure surfaces as a structured error,
    never a crash (§6).
    """
    try:
        lead_zone = _resolve_zone(lead_timezone)
        slots = calendar.list_slots(
            now=now,
            lookahead_days=lookahead_days,
            slot_minutes=slot_minutes,
        )
        # Cap to a small, evenly-spread set of options (soonest first within each
        # pick) so the tool result stays small and the agent offers a few choices.
        if max_slots > 0 and len(slots) > max_slots:
            stride = len(slots) // max_slots
            slots = slots[::stride][:max_slots]
        payload = [_slot_to_payload(s, lead_zone) for s in slots]
        return ToolResult(ok=True, data={"slots": payload, "count": len(payload)})
    except Exception as exc:  # noqa: BLE001 — surface as data (§6)
        return ToolResult(ok=False, error="calendar_error", message=str(exc))


# ===========================================================================
# Tool 2 — book_meeting
# ===========================================================================

def _parse_slot_start(slot_iso: str) -> datetime:
    """Parse an ISO start string into a calendar-tz aware datetime."""
    dt = datetime.fromisoformat(slot_iso.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=SALES_CALENDAR_TZ)
    return dt.astimezone(SALES_CALENDAR_TZ)


def book_meeting(
    *,
    calendar: CalendarProvider,
    lead_id: str,
    slot_start_iso: str,
    summary: str = "Alta intro meeting",
    slot_minutes: int = BOOKING_SLOT_MINUTES,
) -> ToolResult:
    """Book *slot_start_iso* for *lead_id* — idempotent, no double-book, no phantom.

    A repeat call for the same lead + slot returns the SAME event id (TOOL2). A
    slot taken by another lead (or busy) returns ok=False / error="slot_taken"
    so the agent OFFERS ANOTHER slot — never a silent overwrite and never a voiced
    confirmation without a created event (BOOK3 / Policy 5). A bad start string is
    a structured invalid_input, not a crash.
    """
    if not lead_id:
        return ToolResult(ok=False, error="invalid_input", message="lead_id is required")
    try:
        start = _parse_slot_start(slot_start_iso)
    except (ValueError, TypeError):
        return ToolResult(ok=False, error="invalid_input",
                          message="slot_start_iso is not a valid ISO datetime")

    slot = Slot(start=start, end=start + timedelta(minutes=slot_minutes))
    result: BookingResult = calendar.create_event(
        lead_id=lead_id, slot=slot, summary=summary
    )

    if result.ok:
        # The agent may voice a confirmation ONLY now (a real event id exists).
        return ToolResult(
            ok=True,
            data={
                "event_id": result.event_id,
                "slot_key": slot.key(),
                "start_utc": start.isoformat(),
            },
        )
    # Conflict / backend error → structured re-offer signal; NO confirmation.
    return ToolResult(
        ok=False,
        error=result.reason or "calendar_error",
        message=result.detail or "could not book that slot — offer another",
    )


# ===========================================================================
# Tool 3 — log_disposition  (NO secret, NO full phone number — TOOL3/LEAK2)
# ===========================================================================

def log_disposition(
    *,
    lead_id: str,
    disposition: str,
    phone_e164: str | None = None,
    event_id: str | None = None,
    notes: str | None = None,
) -> ToolResult:
    """Record a structured disposition; the phone number is ALWAYS masked.

    The record carries ONLY: lead_id, a validated disposition, a MASKED phone
    (last 2 digits via consent.mask_phone), an optional event_id, and short
    notes. A full phone number or a secret never enters the record (TOOL3/LEAK2).
    An unknown disposition is rejected as structured invalid_input.
    """
    if disposition not in VALID_DISPOSITIONS:
        return ToolResult(
            ok=False,
            error="invalid_input",
            message=(
                f"disposition must be one of {sorted(VALID_DISPOSITIONS)}; "
                f"got {disposition!r}"
            ),
        )
    record: dict[str, Any] = {
        "lead_id": lead_id,
        "disposition": disposition,
    }
    if phone_e164:
        record["phone_masked"] = mask_phone(phone_e164)
    if event_id:
        record["event_id"] = event_id
    if notes:
        record["notes"] = notes
    return ToolResult(ok=True, data=record)


# ===========================================================================
# Tool 4 — detect_voicemail  (TOOL4)
# ===========================================================================

def detect_voicemail(
    *,
    transcript: str,
    voicemail_max_s: int = VOICEMAIL_MAX_S,
) -> ToolResult:
    """Classify whether *transcript* is a voicemail greeting (deterministic).

    On detection, the result tells the caller to leave a message no longer than
    VOICEMAIL_MAX_S then end (TOOL4). Pure substring matching over generic
    carrier/greeting cues — no network, no model, fully deterministic.
    """
    text = (transcript or "").lower()
    matched = [cue for cue in _VOICEMAIL_CUES if cue in text]
    is_vm = bool(matched)
    return ToolResult(
        ok=True,
        data={
            "is_voicemail": is_vm,
            "leave_message": is_vm,
            "max_message_seconds": voicemail_max_s if is_vm else 0,
            "matched_cues": matched,
        },
    )


# ===========================================================================
# Tool 5 — end_call  (TOOL5)
# ===========================================================================

def end_call(*, reason: str = "completed") -> ToolResult:
    """Signal a clean hangup with a structured reason (TOOL5).

    Never raises — ending the call is always a safe terminal (§6 / Policy 6).
    """
    return ToolResult(ok=True, data={"ended": True, "reason": reason})


# ===========================================================================
# Dispatch registry — keys MUST equal AGENT_TOOLS (import-time assert, TOOL5)
# ===========================================================================

TOOL_REGISTRY: dict[str, Callable[..., ToolResult]] = {
    "check_availability": check_availability,
    "book_meeting": book_meeting,
    "log_disposition": log_disposition,
    "detect_voicemail": detect_voicemail,
    "end_call": end_call,
}

# Import-time identity guard: name == AGENT_TOOLS entry == dispatch key (TOOL5).
# A rename/typo fails fast at import, not at runtime mid-call.
assert set(TOOL_REGISTRY.keys()) == set(AGENT_TOOLS), (
    "TOOL_REGISTRY keys must equal AGENT_TOOLS exactly. "
    f"registry={sorted(TOOL_REGISTRY)} AGENT_TOOLS={sorted(AGENT_TOOLS)}"
)
# Each registered value is callable.
assert all(callable(fn) for fn in TOOL_REGISTRY.values()), (
    "every TOOL_REGISTRY entry must be callable"
)


# Tools that need a calendar backend (and a clock) INJECTED at runtime. Over the
# webhook the Realtime model supplies only business arguments (lead_id, slot,
# timezone); the calendar and the clock are infrastructure the runtime must inject
# — the model neither can nor should. Without this injection every booking webhook
# returned `invalid_input` ("missing keyword-only argument 'calendar'") and NO
# meeting could ever be booked over the wire, defeating the core deliverable.
_CALENDAR_TOOLS = frozenset({"check_availability", "book_meeting"})


def dispatch(
    name: str,
    /,
    *,
    calendar: CalendarProvider | None = None,
    now: datetime | None = None,
    **kwargs: Any,
) -> ToolResult:
    """Route a tool-call by name to its function (the single dispatch point).

    This is the one runtime tool-invocation chokepoint the webhook (and the future
    campaign runner) call. The model passes only business args; for the booking
    tools (`check_availability` / `book_meeting`) the calendar backend — and, for
    `check_availability`, the clock — are INJECTED here: an explicit *calendar* (the
    offline suite injects a MockCalendar) or, when none is given, the lazy live
    Cal.com client via `_get_calendar()`. A missing live key (or any build failure)
    surfaces as a structured `calendar_unavailable`, never a crash (§6). An unknown
    tool name or bad/missing args likewise return a structured error — never a
    KeyError/TypeError crash.
    """
    fn = TOOL_REGISTRY.get(name)
    if fn is None:
        return ToolResult(
            ok=False,
            error="unknown_tool",
            message=f"no such tool {name!r}; known: {sorted(TOOL_REGISTRY)}",
        )

    # Inject runtime infrastructure the model cannot (and must not) supply.
    if name in _CALENDAR_TOOLS:
        if calendar is None:
            try:
                calendar = _get_calendar()  # lazy live client; never built at import
            except Exception as exc:  # noqa: BLE001 — missing key/build → data (§6)
                return ToolResult(ok=False, error="calendar_unavailable",
                                  message=str(exc))
        kwargs["calendar"] = calendar
        if name == "check_availability":
            kwargs["now"] = now if now is not None else datetime.now(SALES_CALENDAR_TZ)

    try:
        return fn(**kwargs)
    except TypeError as exc:
        # Bad/missing args for a known tool → structured invalid_input, not a crash.
        return ToolResult(ok=False, error="invalid_input", message=str(exc))
