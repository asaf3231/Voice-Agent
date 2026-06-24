"""Stress suite — Scope 2: Telephony & E2E Audio Protocols — STR-T*.

See docs/STRESS_TEST_ARCHITECTURE.md. Driven by the MOCK-BRIDGE (app.testing.
mock_bridge) over the webhook + transcript layer. Honest scoping: the media path is
Vapi's, so raw SIP/RTP faults are not injectable here — we exercise the EFFECTS that
reach our service (malformed/redelivered webhooks, lifecycle drops, lossy
transcripts). Genuinely media-level cases (real barge-in) are LIVE-GATED.

Coverage:
  STR-T2/T3 — lossy / noisy transcript → no false voicemail trigger, no crash.
  STR-T5    — drop mid-call / empty envelope → structured, never a 500.
  STR-T6    — voicemail greeting detected; leave ≤ VOICEMAIL_MAX_S then end (TOOL4).
  STR-T8    — webhook redelivery storm → idempotent booking (no double-book).
  STR-T9    — malformed envelopes (no toolCallId, garbled args, flat form) → no crash.
  STR-T10   — disclosure pinned to the static first-message (offline proxy for LIVE2).
  STR-T1    — real barge-in: LIVE-GATED (skipped here, measured via inspect_call).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.config import DISCLOSURE_LINE, VOICEMAIL_MAX_S
from app.testing import mock_bridge as mb
from app.testing.mock_bridge import MockVapiBridge
from app import tools
from app.calendar_client import MockCalendar


@pytest.fixture()
def bridge(monkeypatch) -> MockVapiBridge:
    """A MockVapiBridge whose secret matches the server's env secret."""
    monkeypatch.setenv("VAPI_WEBHOOK_SECRET", mb.DEFAULT_SECRET)
    return MockVapiBridge()


def _iso(hour: int) -> str:
    return datetime(2026, 6, 30, hour, 0, tzinfo=timezone.utc).isoformat()


# ===========================================================================
# STR-T2 / STR-T3 — lossy / noisy transcript (the STT/SNR effect)
# ===========================================================================

def test_str_t2_total_loss_transcript_no_false_voicemail():
    """Total packet loss → empty transcript → NOT classified as voicemail."""
    lost = mb.garble("after the tone please leave a message", loss=1.0)
    assert lost == ""
    r = tools.detect_voicemail(transcript=lost)
    assert r.ok is True and r.data["is_voicemail"] is False


def test_str_t3_voicemail_cue_survives_surrounding_noise():
    """A strong cue embedded in background noise still classifies (SNR robustness)."""
    noisy = "kshhh static garble leave a message after the beep crackle pop zzz"
    r = tools.detect_voicemail(transcript=noisy)
    assert r.data["is_voicemail"] is True


# ===========================================================================
# STR-T5 — drop mid-call / empty envelope → structured, never a 500
# ===========================================================================

def test_str_t5_empty_envelope_is_structured_no_tool_call(bridge):
    resp = bridge.post(mb.TOOL_PATH, mb.empty_envelope())
    assert resp.status_code == 200
    payload = bridge.result_of(resp)
    assert payload["ok"] is False and payload["error"] == "no_tool_call"


def test_str_t5_status_drop_mid_call_is_handled_and_masks_phone(bridge):
    resp = bridge.post(
        mb.STATUS_PATH,
        mb.status_envelope("customer-ended-call", number="+15551234567"),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body.get("phone_masked", "").endswith("67")
    assert "+15551234567" not in str(body)        # full number never echoed


# ===========================================================================
# STR-T6 — voicemail detection (TOOL4)
# ===========================================================================

def test_str_t6_voicemail_greeting_detected():
    greeting = ("You've reached the voicemail of this number. "
                "Please leave a message after the tone.")
    r = tools.detect_voicemail(transcript=greeting)
    assert r.ok and r.data["is_voicemail"] is True
    assert r.data["leave_message"] is True
    assert r.data["max_message_seconds"] == VOICEMAIL_MAX_S


def test_str_t6_live_human_not_flagged_voicemail():
    r = tools.detect_voicemail(transcript="Hi, this is Jordan — who's calling?")
    assert r.data["is_voicemail"] is False
    assert r.data["max_message_seconds"] == 0


# ===========================================================================
# STR-T8 — webhook redelivery storm → idempotent booking (no double-book)
# ===========================================================================

def test_str_t8_redelivery_storm_is_idempotent(bridge, monkeypatch):
    shared = MockCalendar()
    monkeypatch.setattr("app.tools._get_calendar", lambda: shared)
    env = mb.tool_call_envelope(
        "book_meeting", {"slot_start_iso": _iso(15)}, tool_call_id="cId-7"
    )

    event_ids = []
    for _ in range(8):                       # the platform redelivers the same call
        resp = bridge.post(mb.TOOL_PATH, env)
        assert resp.status_code == 200
        assert resp.json()["results"][0]["toolCallId"] == "cId-7"   # id echoed back
        payload = bridge.result_of(resp)
        assert payload["ok"] is True
        event_ids.append(payload["data"]["event_id"])

    assert len(set(event_ids)) == 1          # redelivery NEVER double-books


# ===========================================================================
# STR-T9 — malformed envelopes → structured result, never a 500
# ===========================================================================

def test_str_t9_missing_tool_call_id_still_processes(bridge):
    resp = bridge.post(
        mb.TOOL_PATH,
        mb.tool_call_envelope("detect_voicemail",
                              {"transcript": "leave a message after the tone"},
                              tool_call_id=None),
    )
    assert resp.status_code == 200
    assert resp.json()["results"][0]["toolCallId"] is None          # null, no crash
    assert bridge.result_of(resp)["data"]["is_voicemail"] is True


def test_str_t9_garbled_args_no_crash(bridge):
    resp = bridge.post(mb.TOOL_PATH, mb.garbled_args_envelope("detect_voicemail"))
    assert resp.status_code == 200
    payload = bridge.result_of(resp)
    # garbled JSON args → empty args → missing required transcript → structured error.
    assert payload["ok"] is False and payload["error"] == "invalid_input"


def test_str_t9_flat_form_envelope_processes(bridge):
    resp = bridge.post(
        mb.TOOL_PATH,
        mb.tool_call_envelope("detect_voicemail",
                              {"transcript": "please leave a message"},
                              nested=False, tool_call_id="flat-1"),
    )
    assert resp.status_code == 200
    assert bridge.result_of(resp)["data"]["is_voicemail"] is True


# ===========================================================================
# STR-T10 — disclosure pinned to the static first-message (offline proxy / LIVE2)
# ===========================================================================

def test_str_t10_disclosure_is_the_static_first_message():
    """The platform speaks DISCLOSURE_LINE verbatim first — not a model-paraphrasable
    prompt. Offline proxy for the live LIVE2 transcript check (under impairment)."""
    from app.vapi_client import VapiVoiceProvider

    assistant = VapiVoiceProvider().configure_assistant()
    assert assistant["firstMessage"] == DISCLOSURE_LINE


# ===========================================================================
# STR-T1 — real barge-in / overlap: LIVE-GATED (media-path, not at our boundary)
# ===========================================================================

@pytest.mark.skip(
    reason="LIVE-GATED: real barge-in / overlapping speech is a media-path fault "
           "owned by Vapi — not reproducible at our webhook boundary. Measured on a "
           "live call via scripts/inspect_call.py (the per-utterance `interrupted` "
           "count). See docs/STRESS_TEST_ARCHITECTURE.md STR-T1."
)
def test_str_t1_barge_in_overlap_live_only():
    raise AssertionError("live-only placeholder — see skip reason")
