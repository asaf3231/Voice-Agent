"""Pre-fetched-slot injection + booking-confirmation prompt tightening.

Covers the two fixes from the live-call analysis (call 019efaf6-06da):
  1. Pre-fetch + inject availability so Aria proposes times INSTANTLY (no mid-call
     check_availability "give me a moment").
  2. log_disposition must be SILENT + a booking read-back / next-steps on success.

All OFFLINE: build_system_prompt + configure_assistant are pure builders. The live
behavior (does gpt-4o actually use the pre-loaded slots?) is verified on a real call.
"""

from __future__ import annotations

from app.persona import build_system_prompt

_SLOTS = [
    {"say": "Thursday, June 25 at 9:00 AM", "start_utc": "2026-06-25T06:00:00+00:00",
     "slot_key": "2026-06-25T06:00:00+00:00"},
    {"say": "Friday, June 26 at 12:00 PM", "start_utc": "2026-06-26T09:00:00+00:00",
     "slot_key": "2026-06-26T09:00:00+00:00"},
    {"say": "Monday, June 29 at 3:30 PM", "start_utc": "2026-06-29T12:30:00+00:00",
     "slot_key": "2026-06-29T12:30:00+00:00"},
]


# ===========================================================================
# (1) Pre-fetch + inject slots
# ===========================================================================

def test_prompt_injects_prefetched_slots_with_iso():
    prompt = build_system_prompt("A", available_slots=_SLOTS)
    # Each say-string AND its bookable ISO are present so the model can book directly.
    for s in _SLOTS:
        assert s["say"] in prompt
        assert s["start_utc"] in prompt
    # The instruction tells it NOT to fetch before the first proposal.
    assert "do NOT call check_availability before your first proposal" in prompt
    # …but to re-fetch only on a reject-all (re-offer).
    assert "check_availability ONLY if they reject all" in prompt


def test_prompt_without_slots_is_unchanged_backwards_compatible():
    prompt = build_system_prompt("A")
    assert "PRE-FETCHED MEETING TIMES" not in prompt
    # The live tool path is still described (no slots pre-loaded → fetch live).
    assert "check_availability" in prompt


def test_configure_assistant_threads_slots_into_system_prompt():
    from app.vapi_client import VapiVoiceProvider

    assistant = VapiVoiceProvider().configure_assistant(available_slots=_SLOTS)
    system = assistant["model"]["messages"][0]["content"]
    assert "PRE-FETCHED MEETING TIMES" in system
    assert "Monday, June 29 at 3:30 PM" in system
    # The graded chokepoint is untouched by the new param.
    from app.config import DISCLOSURE_LINE
    assert assistant["firstMessage"] == DISCLOSURE_LINE


# ===========================================================================
# (2) Booking read-back / next-steps + silent log_disposition
# ===========================================================================

def test_prompt_requires_booking_readback_and_next_steps():
    prompt = build_system_prompt("A")
    assert "BOOKING CONFIRMATION" in prompt
    assert "reading back" in prompt and "calendar invite" in prompt
    # The "so now what?" failure mode from the live call is addressed explicitly.
    assert "so now what" in prompt.lower()


def test_prompt_strengthens_silent_log_disposition():
    prompt = build_system_prompt("A")
    assert "log_disposition runs SILENTLY" in prompt
    assert "say NOTHING before, during, or after it" in prompt
