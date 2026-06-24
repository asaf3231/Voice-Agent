"""Offline tests for scripts/inspect_call.py — the timestamped-transcript renderer.

render_transcript() is a pure function over a Vapi call dict (no network), so the
diagnostic is exercised deterministically with a sample call object. Covers the
key signal for "not finishing sentences": the (INTERRUPTED) marker + timestamps.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make scripts/ importable (mirrors how the script bootstraps itself).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import inspect_call  # noqa: E402


_SAMPLE_CALL = {
    "id": "019ef883-test",
    "status": "ended",
    "endedReason": "customer-ended-call",
    "cost": 0.5667,
    "durationSeconds": 124,
    "artifact": {
        "messages": [
            {"role": "system", "message": "You are Aria...", "secondsFromStart": 0.0},
            {
                "role": "bot",
                "message": "Hi, this is Aria, an AI assistant calling on behalf of Alta.",
                "secondsFromStart": 0.5,
            },
            {"role": "user", "message": "uh huh", "secondsFromStart": 5.2},
            {
                "role": "bot",
                "message": "So Alta helps revenue teams automate—",
                "secondsFromStart": 6.0,
                "interrupted": True,
            },
        ]
    },
}


def test_render_includes_call_summary():
    out = inspect_call.render_transcript(_SAMPLE_CALL)
    assert "019ef883-test" in out
    assert "customer-ended-call" in out
    assert "$0.5667" in out


def test_render_includes_timestamps():
    out = inspect_call.render_transcript(_SAMPLE_CALL)
    # mm:ss.s formatting for the first Aria utterance at 0.5s and the 6.0s one.
    assert "[00:00.5]" in out
    assert "[00:06.0]" in out


def test_render_flags_interrupted_aria_turn():
    out = inspect_call.render_transcript(_SAMPLE_CALL)
    assert "(INTERRUPTED)" in out
    # The summary footer counts cut-off Aria turns — the "not finishing" metric.
    assert "interrupted (cut off mid-sentence): 1" in out


def test_render_skips_system_prompt():
    out = inspect_call.render_transcript(_SAMPLE_CALL)
    assert "You are Aria" not in out


def test_render_falls_back_to_epoch_time_when_no_secondsfromstart():
    call = {
        "id": "x",
        "messages": [
            {"role": "bot", "message": "first", "time": 1_000_000},
            {"role": "user", "message": "second", "time": 1_002_500},
        ],
    }
    out = inspect_call.render_transcript(call)
    assert "[00:00.0] ARIA: first" in out
    assert "[00:02.5] CALLEE: second" in out


def test_main_returns_1_with_no_args(capsys):
    rc = inspect_call.main(argv=[])
    assert rc == 1


def test_main_renders_via_injected_provider(capsys):
    class _FakeProvider:
        def fetch_call(self, *, call_id):
            return _SAMPLE_CALL

    rc = inspect_call.main(argv=["019ef883-test"], provider=_FakeProvider())
    out = capsys.readouterr().out
    assert rc == 0
    assert "(INTERRUPTED)" in out
    assert "[00:06.0]" in out
