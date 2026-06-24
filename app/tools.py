"""Agent tools — the deterministic functions the model calls during a call.

Four callable tools, each returning structured data and never raising across its
boundary (a busy slot, a backend error, or bad input all come back as a structured
result):
  - check_availability : free slots in the lookahead window, each rendered in the
                         lead's local timezone.
  - book_meeting       : idempotent booking — a conflict offers another slot rather
                         than double-booking or confirming a phantom meeting.
  - log_disposition    : the structured outcome; the phone number is always masked.
  - detect_voicemail   : classify a greeting and decide whether to leave a message.

A dispatch registry routes a tool name to its function and injects the runtime
infrastructure the model must not supply itself — the calendar backend, the clock,
and the authoritative lead id/timezone. Also hosts `qualify`, an internal helper the
offline rubric uses to check the pitch was tailored to the prospect's stated need.

Import-safe: no client, .env, data, or network access at import; the calendar
backend is injected (a mock offline, the live client only on demand).
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
# Timezone resolution
# ===========================================================================

def _resolve_zone(tz_name: str | None) -> ZoneInfo | timezone:
    """Resolve an IANA tz name to a tzinfo; fall back to the calendar tz.

    A missing or unknown tz never crashes the call — it degrades to the sales-calendar
    tz (a safe, explicit default), so a bad lead record can't take the booking path down.
    """
    if not tz_name:
        return SALES_CALENDAR_TZ
    try:
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        return SALES_CALENDAR_TZ


def _format_say(lead_start: datetime) -> str:
    """A ready-to-speak slot label — the bare time in the lead's local timezone.

    The agent voices this string verbatim, so it never has to pick a UTC field or
    compute a time itself. Formatting avoids platform-specific directives so it works
    on any OS. Example: "Tuesday, June 30 at 4:45 PM".
    """
    hour12 = lead_start.hour % 12 or 12
    ampm = "AM" if lead_start.hour < 12 else "PM"
    return (
        f"{lead_start.strftime('%A')}, {lead_start.strftime('%B')} {lead_start.day} "
        f"at {hour12}:{lead_start.minute:02d} {ampm}"
    )


def _slot_to_payload(slot: Slot, lead_zone: ZoneInfo | timezone) -> dict[str, Any]:
    """Render a slot for the agent: the authoritative calendar-tz time, the lead's
    local time, and a ready-to-speak `say` string in the lead's local time.

    The `say` field is what the agent reads aloud; the calendar-tz value is the time
    the meeting is actually booked at — carrying both prevents "3pm in the wrong tz".
    """
    cal_start = slot.start.astimezone(SALES_CALENDAR_TZ)
    lead_start = slot.start.astimezone(lead_zone)
    return {
        "slot_key": slot.key(),
        "start_utc": cal_start.isoformat(),
        "end_utc": slot.end.astimezone(SALES_CALENDAR_TZ).isoformat(),
        "start_lead_local": lead_start.isoformat(),
        "lead_tz": str(getattr(lead_zone, "key", lead_zone)),
        "say": _format_say(lead_start),
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

    Deterministic under the mock (the clock is injected). Each slot is voiced in the
    lead's local time while booked at the authoritative calendar time. The result is
    capped to a small spread of options — a live calendar can return hundreds of slots,
    which both overflows the platform's tool-result and makes a poor "pick a time"
    experience. Any backend failure surfaces as a structured error, never a crash.
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

    A repeat call for the same lead and slot returns the same event id. A slot taken
    by another lead (or already busy) returns ok=False / "slot_taken" so the agent
    offers another time — never a silent overwrite, and never a spoken confirmation
    without a real event. A bad start string is a structured invalid_input, not a crash.
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
# Tool 3 — log_disposition  (the phone number is always masked)
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

    The record carries only: lead_id, a validated disposition, a masked phone (last
    two digits), an optional event_id, and short notes — never a full number or a
    secret. An unknown disposition is rejected as structured invalid_input.
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
# Tool 4 — detect_voicemail
# ===========================================================================

def detect_voicemail(
    *,
    transcript: str,
    voicemail_max_s: int = VOICEMAIL_MAX_S,
) -> ToolResult:
    """Classify whether *transcript* is a voicemail greeting (deterministic).

    On detection, the result tells the caller to leave a message no longer than
    VOICEMAIL_MAX_S, then end. Pure substring matching over generic carrier/greeting
    cues — no network, no model.
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


# NOTE: there is no `end_call` tool. Ending the call is pinned to Vapi's NATIVE
# end-call (endCallFunctionEnabled) + the byte-exact END_CALL_MESSAGE — a custom
# function returning JSON never actually terminated the call (D9, 2026-06-24).


# ===========================================================================
# Internal helper — qualify  (the offline tailoring oracle; not a live tool)
# ===========================================================================
# Routes a discovery answer to the grounded value-prop to emphasize. Kept as a pure,
# deterministic function so the rubric can use it as a tailoring oracle; the live agent
# does the same tailoring inline via the system prompt (a mid-call tool round-trip added
# noticeable latency, so it is not dispatched live).

# Pain-theme → trigger keywords found in a prospect's answer. This is classification
# logic, not Alta business content — the assertable value-prop text still comes only
# from the value-prop file. Each theme's anchor words also appear in the value-prop it
# routes to, so the selector picks the grounded match from the file.
_QUALIFY_THEMES: dict[str, tuple[str, ...]] = {
    "scale": (
        "scale", "scaling", "volume", "manual", "manually", "by hand", "hundreds",
        "headcount", "capacity", "bandwidth", "keep up", "more calls", "sdr",
        "sdrs", "reps", "hiring", "outreach", "throughput",
    ),
    "consistency": (
        "consistent", "consistency", "messaging", "off script", "off-script",
        "playbook", "script", "inconsistent", "varies",
    ),
    "quality": (
        "robotic", "robocall", "robo", "natural", "sound", "human", "conversation",
        "rapport", "tone",
    ),
    "compliance": (
        "compliance", "compliant", "dnc", "do not call", "do-not-call", "legal",
        "regulation", "regulatory", "tcpa", "consent",
    ),
    "integration": (
        "crm", "salesforce", "hubspot", "integrate", "integration", "set up",
        "setup", "onboarding", "implementation", "it team", "it lift",
    ),
}


def _qualify_match_themes(answer_low: str) -> list[str]:
    """Return the pain themes whose trigger keywords appear in *answer_low*."""
    return [
        theme for theme, kws in _QUALIFY_THEMES.items()
        if any(kw in answer_low for kw in kws)
    ]


def _qualify_theme_hits(theme: str, answer_low: str) -> int:
    return sum(1 for kw in _QUALIFY_THEMES[theme] if kw in answer_low)


def _qualify_select_value_prop(
    theme: str, value_props: tuple[str, ...]
) -> str | None:
    """Pick the value-prop whose text best matches *theme*'s keywords (grounded)."""
    best, best_score = None, 0
    for vp in value_props:
        low = vp.lower()
        score = sum(1 for kw in _QUALIFY_THEMES[theme] if kw in low)
        if score > best_score:
            best, best_score = vp, score
    return best


def _load_value_props_for_qualify() -> tuple[str, ...]:
    """Lazily parse the value-prop file's items (never read at import)."""
    from app.persona import load_value_prop  # lazy: no cycle, no import-time file read
    return load_value_prop().value_props


def qualify(
    *,
    answer: str,
    value_props: tuple[str, ...] | None = None,
) -> ToolResult:
    """Route a prospect's discovery answer to the grounded value-prop to emphasize.

    Turns "tailor the pitch to what they say" into an explicit, deterministic decision.
    Returns the matched pain theme(s), the single value-prop to lead with (always one of
    the value-prop file's items, never invented here), and whether the answer was too
    vague or empty to route — so the agent asks one clarifying question instead of
    pitching a canned script on a non-answer.

    Used by the offline rubric with the prospect's answer; the value-prop content is
    loaded from the file at runtime (or injected for tests). Never raises.
    """
    a = (answer or "").strip()
    if not a:
        return ToolResult(ok=True, data={
            "answer_quality": "empty",
            "matched_themes": [],
            "emphasize": None,
            "needs_clarification": True,
            "guidance": (
                "The prospect did not actually answer. Ask ONE short, friendly "
                "clarifying question about their current outbound — do NOT pitch yet."
            ),
        })

    low = a.lower()
    themes = _qualify_match_themes(low)

    if not themes:
        return ToolResult(ok=True, data={
            "answer_quality": "vague",
            "matched_themes": [],
            "emphasize": None,
            "needs_clarification": True,
            "guidance": (
                "The answer is vague or off-topic — it names no clear need. Ask ONE "
                "short clarifying question to surface their outbound pain before "
                "pitching. Do NOT launch the value-prop on a non-answer."
            ),
        })

    if value_props is None:
        value_props = _load_value_props_for_qualify()

    # Primary theme = the one with the most keyword hits (stable: dict order on ties).
    primary = max(themes, key=lambda t: _qualify_theme_hits(t, low))
    emphasize = _qualify_select_value_prop(primary, value_props)

    if emphasize is None:
        # A theme keyword matched the answer, but NO value-prop on file grounds it
        # (best_score == 0). Do NOT report a substantive route with a null emphasis:
        # that previously told the live agent to "lead with ONLY this value-prop: None"
        # and made rubric.pitch_tailored pass vacuously on a true routing miss
        # (independent review 2026-06-24). Ask to clarify instead of pitching nothing.
        return ToolResult(ok=True, data={
            "answer_quality": "unmapped",
            "matched_themes": themes,
            "emphasize": None,
            "needs_clarification": True,
            "guidance": (
                f"They hinted at a '{primary}' need, but no value-prop on file directly "
                "addresses it. Ask ONE short clarifying question to pin down their pain — "
                "do NOT pitch an ungrounded claim."
            ),
        })

    return ToolResult(ok=True, data={
        "answer_quality": "substantive",
        "matched_themes": themes,
        "emphasize": emphasize,
        "needs_clarification": False,
        "guidance": (
            f"They raised a '{primary}' need. Reflect their own words back, then lead "
            "with ONLY this value-prop (not the whole list), then make the meeting "
            f"ask: {emphasize}"
        ),
    })


# ===========================================================================
# Dispatch registry — keys MUST equal AGENT_TOOLS (import-time assert, TOOL5)
# ===========================================================================

TOOL_REGISTRY: dict[str, Callable[..., ToolResult]] = {
    "check_availability": check_availability,
    "book_meeting": book_meeting,
    "log_disposition": log_disposition,
    "detect_voicemail": detect_voicemail,
}
# Deliberately absent (retired): `end_call` (the platform's native end-call replaces
# the custom no-op) and `qualify` (the offline tailoring oracle, not a dispatched live
# tool — tailoring is done inline by the system prompt).

# Import-time identity guard: name == AGENT_TOOLS entry == dispatch key.
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
# webhook the model supplies only business arguments (lead_id, slot, timezone); the
# calendar and the clock are infrastructure the runtime must inject — the model
# neither can nor should. Without this injection every booking webhook failed with
# "missing keyword-only argument 'calendar'" and no meeting could be booked over the
# wire, defeating the core deliverable.
_CALENDAR_TOOLS = frozenset({"check_availability", "book_meeting"})
# Tools whose lead_id is INFRASTRUCTURE, injected authoritatively by the runtime —
# never trusted from the model (which once fabricated "lead_id_placeholder").
_LEAD_ID_TOOLS = frozenset({"book_meeting", "log_disposition"})


def dispatch(
    name: str,
    /,
    *,
    calendar: CalendarProvider | None = None,
    now: datetime | None = None,
    lead_id: str | None = None,
    lead_timezone: str | None = None,
    **kwargs: Any,
) -> ToolResult:
    """Route a tool-call by name to its function (the single dispatch point).

    This is the one runtime tool-invocation chokepoint the webhook (and the campaign
    runner) call. The model passes only business args; for the booking tools the
    calendar backend — and, for check_availability, the clock — are injected here:
    an explicit *calendar* (the offline suite injects a MockCalendar) or, when none is
    given, the lazy live Cal.com client. A missing live key or any build failure
    surfaces as a structured `calendar_unavailable`, never a crash. An unknown tool
    name or bad/missing args likewise return a structured error, never a crash.
    """
    fn = TOOL_REGISTRY.get(name)
    if fn is None:
        return ToolResult(
            ok=False,
            error="unknown_tool",
            message=f"no such tool {name!r}; known: {sorted(TOOL_REGISTRY)}",
        )

    # Self-defending chokepoint: lead_id / lead_timezone are infrastructure the model
    # never owns. Strip any that arrived in the model args so (a) they can't collide
    # with the authoritative explicit params below and (b) the override is enforced
    # HERE, not only in the webhook caller.
    kwargs.pop("lead_id", None)
    kwargs.pop("lead_timezone", None)

    # Inject runtime infrastructure the model cannot (and must not) supply.
    if name in _CALENDAR_TOOLS:
        if calendar is None:
            try:
                calendar = _get_calendar()  # lazy live client; never built at import
            except Exception as exc:  # noqa: BLE001 — missing key/build → data
                return ToolResult(ok=False, error="calendar_unavailable",
                                  message=str(exc))
        kwargs["calendar"] = calendar
        if name == "check_availability":
            kwargs["now"] = now if now is not None else datetime.now(SALES_CALENDAR_TZ)
            # Authoritative lead timezone overrides any model-supplied value.
            if lead_timezone is not None:
                kwargs["lead_timezone"] = lead_timezone

    # Authoritative lead_id overrides any model-supplied value — the model never
    # decides which lead a booking/disposition is written under.
    if name in _LEAD_ID_TOOLS and lead_id is not None:
        kwargs["lead_id"] = lead_id

    try:
        return fn(**kwargs)
    except TypeError as exc:
        # Bad/missing args for a known tool → structured invalid_input, not a crash.
        return ToolResult(ok=False, error="invalid_input", message=str(exc))
