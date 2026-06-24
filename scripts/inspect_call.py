"""Inspect a live call's transcript with timestamps and interruption markers.

Renders each utterance as `[mm:ss.s] ROLE: text`, flagging any agent line the caller
cut off, plus a summary of how many of Aria's turns were interrupted — the direct
signal when debugging "the agent isn't finishing its sentences."

Usage: python scripts/inspect_call.py <call_id> ...   (or `make inspect`).

Import-safe: live work is inside main(); the renderer is a pure function, so it is
offline-testable with a sample call dict.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Vapi role → display label
_ROLE_LABELS = {
    "bot": "ARIA",
    "user": "CALLEE",
    "tool_calls": "ARIA→tool",
    "tool_call_result": "tool→ARIA",
}


def _messages(call: dict) -> list[dict]:
    """Extract the timed message list from a Vapi call object (defensive).

    Vapi puts the richest (timed) transcript under call.artifact.messages;
    fall back to call.messages if that is absent.
    """
    artifact = call.get("artifact") or {}
    msgs = artifact.get("messages")
    if not msgs:
        msgs = call.get("messages")
    return msgs or []


def _fmt_ts(seconds: float | None) -> str:
    """Format a seconds-from-start offset as mm:ss.s (or --:-- if unknown)."""
    if seconds is None:
        return "--:--.-"
    minutes, secs = divmod(float(seconds), 60)
    return f"{int(minutes):02d}:{secs:04.1f}"


def _seconds_from_start(msg: dict, base_time_ms: float | None) -> float | None:
    """Best-effort seconds-from-call-start for a message.

    Prefers Vapi's explicit `secondsFromStart`; falls back to epoch `time`
    (ms) minus the first message's epoch time.
    """
    secs = msg.get("secondsFromStart")
    if secs is not None:
        return float(secs)
    t = msg.get("time")
    if t is not None and base_time_ms is not None:
        return (float(t) - base_time_ms) / 1000.0
    return None


def render_transcript(call: dict) -> str:
    """Render a Vapi call object as a timestamped, interruption-marked transcript.

    Pure function (no network) — offline-testable. Skips the system-prompt
    message (noise). Returns a single printable string.
    """
    lines: list[str] = []
    cid = call.get("id", "?")
    status = call.get("status", "?")
    ended = call.get("endedReason", "?")
    cost = call.get("cost")
    cost_str = f"${cost:.4f}" if isinstance(cost, (int, float)) else str(cost)
    duration = (
        call.get("durationSeconds")
        or call.get("duration")
        or "?"
    )

    msgs = _messages(call)

    # Base epoch for the time fallback (first message that carries `time`).
    base_time_ms: float | None = None
    for m in msgs:
        if m.get("time") is not None:
            base_time_ms = float(m["time"])
            break

    lines.append(f"Call {cid}")
    lines.append(
        f"  status={status}  endedReason={ended}  "
        f"cost={cost_str}  duration={duration}s  messages={len(msgs)}"
    )
    lines.append("")

    aria_turns = 0
    interrupted_turns = 0

    for m in msgs:
        role = m.get("role", "?")
        if role == "system":
            continue  # skip the system-prompt dump
        text = (m.get("message") or m.get("content") or "").strip()
        ts = _fmt_ts(_seconds_from_start(m, base_time_ms))
        label = _ROLE_LABELS.get(role, role.upper())
        interrupted = bool(m.get("interrupted"))
        if role == "bot":
            aria_turns += 1
            if interrupted:
                interrupted_turns += 1
        mark = " (INTERRUPTED)" if interrupted else ""
        lines.append(f"[{ts}] {label}{mark}: {text}")

    lines.append("")
    lines.append(
        f"  Aria turns: {aria_turns}  |  interrupted (cut off mid-sentence): "
        f"{interrupted_turns}"
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None, *, provider=None) -> int:
    """Entry point. Fetches each call and prints its timestamped transcript.

    Args:
        argv: list of Vapi call_id strings (overrides sys.argv[1:]).
        provider: injected VoiceProvider for testing (uses VapiVoiceProvider if None).

    Returns 0 on success, 1 if no call ids supplied or a fetch failed.
    """
    if argv is None:
        argv = sys.argv[1:]

    if not argv:
        print(
            "ERROR: no call_id(s) supplied.\n"
            "Usage: python scripts/inspect_call.py <call_id> [<call_id> ...]\n"
            "       make inspect CALL_IDS='019ef883 019ef86c'",
            file=sys.stderr,
        )
        return 1

    # Ensure the repo root is importable when run directly — OS-agnostic.
    repo_root = str(Path(__file__).resolve().parent.parent)
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    # -- load .env (live entry point; never at import -- ENV4) ----------------
    from app.config import load_env
    load_env()

    # -- build the live provider if not injected (allows offline testing) -----
    if provider is None:
        from app.vapi_client import VapiVoiceProvider
        provider = VapiVoiceProvider()

    rc = 0
    for call_id in argv:
        call_id = call_id.strip()
        if not call_id:
            continue
        try:
            call = provider.fetch_call(call_id=call_id)
        except Exception as exc:  # noqa: BLE001 — diagnostic: print + continue
            print(f"ERROR fetching {call_id}: {exc}", file=sys.stderr)
            rc = 1
            continue
        print(render_transcript(call))
        print()

    return rc


if __name__ == "__main__":
    sys.exit(main())
