"""Stress tests — latency boundaries and STT/TTS tolerance."""

from __future__ import annotations

import time
from datetime import datetime, timezone

import pytest

from app.testing import mock_bridge as mb
from app.testing.mock_bridge import MockVapiBridge
from app import tools
from app.calendar_client import BookingResult

# Proposed SLO for the compute-only webhook path (auth + dispatch + envelope).
# Deliberately generous (in-process TestClient calls are ~ms) so the suite is not
# flaky on a slow CI box while still catching a gross regression. STR-P1.
WEBHOOK_TTFB_SLO_S = 0.5


@pytest.fixture()
def bridge(monkeypatch) -> MockVapiBridge:
    monkeypatch.setenv("VAPI_WEBHOOK_SECRET", mb.DEFAULT_SECRET)
    return MockVapiBridge()


# ===========================================================================
# STR-P1 — tool-webhook TTFB under the SLO
# ===========================================================================

def test_str_p1_tool_webhook_ttfb_p95_under_slo(bridge):
    """A pure compute tool (detect_voicemail) over the webhook stays under the SLO."""
    env = mb.tool_call_envelope("detect_voicemail", {"transcript": "hello there"})
    samples: list[float] = []
    for _ in range(50):
        t0 = time.perf_counter()
        resp = bridge.post(mb.TOOL_PATH, env)
        samples.append(time.perf_counter() - t0)
        assert resp.status_code == 200
    samples.sort()
    p95 = samples[int(0.95 * len(samples)) - 1]
    assert p95 < WEBHOOK_TTFB_SLO_S, (
        f"webhook TTFB p95 {p95:.4f}s exceeded SLO {WEBHOOK_TTFB_SLO_S}s"
    )


# ===========================================================================
# STR-P3 — STT resilience: garbled human speech does not false-trigger voicemail
# ===========================================================================

def test_str_p3_garbled_human_speech_no_false_voicemail():
    human = "yeah hi this is jordan from acme who is this whats this regarding"
    noisy = mb.garble(human, loss=0.5)            # heavy loss, no voicemail cues
    r = tools.detect_voicemail(transcript=noisy)
    assert r.data["is_voicemail"] is False


# ===========================================================================
# STR-P5 — slow/timeout calendar backend → structured error, NO phantom booking
# ===========================================================================

class _FailingCalendar:
    """A backend that times out on reads and reports a structured error on writes.

    list_slots RAISES (check_availability catches all → calendar_error). create_event
    honors the CalendarProvider contract (never raise across the seam) and returns a
    structured failure, which book_meeting must surface as a re-offer (no phantom).
    """

    def list_slots(self, *, now, lookahead_days=10, slot_minutes=30):
        raise TimeoutError("calendar backend timed out")

    def create_event(self, *, lead_id, slot, summary):
        return BookingResult(ok=False, reason="calendar_error", detail="backend timeout")


def test_str_p5_check_availability_timeout_is_structured():
    now = datetime(2026, 6, 30, 10, 0, tzinfo=timezone.utc)
    r = tools.check_availability(calendar=_FailingCalendar(), now=now)
    assert r.ok is False and r.error == "calendar_error"


def test_str_p5_book_on_backend_error_has_no_phantom_confirmation():
    iso = datetime(2026, 6, 30, 15, 0, tzinfo=timezone.utc).isoformat()
    r = tools.book_meeting(calendar=_FailingCalendar(), lead_id="L", slot_start_iso=iso)
    assert r.ok is False                          # surfaced as re-offer
    assert (r.data or {}).get("event_id") is None  # NO event id, no phantom booking
