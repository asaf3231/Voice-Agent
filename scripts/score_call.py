"""Alta Outbound Voice Agent — scripts/score_call.py

Live proof for Bug 2: score a REAL Vapi call on whether the agent actually used
the `qualify` tool and tailored its pitch to the surfaced pain — the only thing
that proves the unenforced qualify fix works (the model isn't forced to call it).

What it reports for a call:
  - qualify_fired      : did gpt-4o actually CALL the qualify tool?
  - qualify_answer     : the discovery answer it passed
  - qualify_emphasize  : the value-prop qualify told it to lead with
  - qualify_latency_s  : the mid-call round-trip the tool cost (the speed tradeoff)
  - pitch_tailored     : rubric.pitch_tailored over the (answer → pitch) pair

Usage:
  python scripts/score_call.py <call_id>          # newest if omitted
  make score CALL_ID=019ef90c-...

evaluate_call() is a pure function over a Vapi call dict (no network) so the
scoring logic is deterministic and inspectable; main() does the live fetch.
Import-safety (ENV4): no work at module level.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def _messages(call: dict) -> list[dict]:
    artifact = call.get("artifact") or {}
    return artifact.get("messages") or call.get("messages") or []


def _find_qualify(msgs: list[dict]) -> tuple[dict | None, dict | None]:
    """Return (the qualify tool-call message, the qualify result message) or (None, None)."""
    call_msg = result_msg = None
    for m in msgs:
        for tc in (m.get("toolCalls") or []):
            if (tc.get("function") or {}).get("name") == "qualify":
                call_msg = m
        if m.get("role") == "tool_call_result" and m.get("name") == "qualify":
            result_msg = m
    return call_msg, result_msg


def _arg(call_msg: dict | None, key: str) -> str | None:
    """Pull a function-argument value from a Vapi tool-call message."""
    if not call_msg:
        return None
    for tc in (call_msg.get("toolCalls") or []):
        fn = tc.get("function") or {}
        if fn.get("name") == "qualify":
            args = fn.get("arguments")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:  # noqa: BLE001
                    return None
            if isinstance(args, dict):
                return args.get(key)
    return None


def _secs(m: dict | None) -> float | None:
    return None if m is None else m.get("secondsFromStart")


# Short acknowledgements the prospect emits that are NOT the discovery answer.
_BACKCHANNELS = frozenset({
    "yes", "yeah", "yep", "sure", "ok", "okay", "right", "uh huh", "uh-huh",
    "mm-hm", "mhm", "go ahead", "got it", "fine", "no", "nope",
})


def _is_backchannel(text: str) -> bool:
    """True if *text* is a one-word/filler acknowledgement, not a substantive answer."""
    t = text.strip().lower().rstrip(".!?")
    return t in _BACKCHANNELS or len(t.split()) < 2


def _find_pitch(
    msgs: list[dict], claims: frozenset[str], *,
    start_index: int = 0, after_secs: float | None = None,
) -> tuple[str | None, float | None]:
    """The first agent (bot) turn AT/AFTER *start_index* that carries value-prop
    content — i.e. shares a grounded claim keyword. Located by POSITION so it is
    robust when a turn lacks `secondsFromStart` (Vapi sometimes timestamps only bot
    turns); *after_secs* is also honored as a guard when both timestamps exist."""
    for m in msgs[start_index:]:
        if m.get("role") != "bot":
            continue
        s = m.get("secondsFromStart")
        if after_secs is not None and s is not None and s <= after_secs:
            continue
        text = (m.get("message") or "").strip()
        if set(re.findall(r"[a-z][a-z\-]{3,}", text.lower())) & claims:
            return text, s
    return None, None


def evaluate_call(call: dict) -> dict:
    """Score a Vapi call dict on the qualify-fired + pitch-tailored signals (pure)."""
    from app.eval import Speaker, Stage, Turn
    from app.eval import rubric

    msgs = _messages(call)
    claims = rubric.extract_value_prop_claims()
    call_msg, result_msg = _find_qualify(msgs)
    qualify_fired = call_msg is not None  # informational (False in prompt-only mode)

    # Locate the discovery answer + the pitch by POSITION (works whether or not a
    # qualify tool fired): the discovery question is the 2nd agent turn (after the
    # disclosure); the answer is the next callee turn; the pitch is the first agent
    # turn after that answer carrying value-prop content.
    bot_idx = [i for i, m in enumerate(msgs) if m.get("role") == "bot"]
    answer = answer_secs = pitch = emphasize = latency = tailored = None
    answer_idx: int | None = None
    if len(bot_idx) >= 2:
        for j in range(bot_idx[1] + 1, len(msgs)):
            m = msgs[j]
            if m.get("role") == "user":
                text = (m.get("message") or "").strip()
                if _is_backchannel(text):
                    continue  # skip "yes"/"mm-hm" — not the real discovery answer
                answer = text
                answer_secs = m.get("secondsFromStart")
                answer_idx = j
                break
        if answer and answer_idx is not None:
            # Search for the pitch strictly AFTER the answer turn (positional), so a
            # missing secondsFromStart can't land it on an earlier bot turn.
            pitch, _ = _find_pitch(
                msgs, claims, start_index=answer_idx + 1, after_secs=answer_secs
            )

    # If a qualify tool actually fired (tool mode), prefer its own arg + latency.
    if qualify_fired:
        answer = _arg(call_msg, "answer") or answer
        cs, rs = _secs(call_msg), _secs(result_msg)
        if cs is not None and rs is not None:
            latency = round(rs - cs, 2)  # the mid-call round-trip the tool cost

    # Expected emphasis from the oracle (what the pitch SHOULD lead with).
    if answer:
        from app.tools import qualify
        emphasize = qualify(answer=answer).to_dict()["data"]["emphasize"]

    if answer and pitch:
        tailored = rubric.pitch_tailored([
            Turn(speaker=Speaker.CALLEE, text=answer),
            Turn(speaker=Speaker.AGENT, text=pitch, stage=Stage.PITCH),
        ])

    return {
        "call_id": call.get("id"),
        "qualify_fired": qualify_fired,
        "qualify_answer": answer,
        "qualify_emphasize": emphasize,
        "qualify_latency_s": latency,
        "pitch": pitch,
        "pitch_tailored": tailored,
    }


def _print_report(r: dict) -> None:
    print(f"Call {r['call_id']}")
    mode = "tool mode" if r["qualify_fired"] else "prompt-only (tailoring inline, no tool hop)"
    print(f"  mode              : {mode}")
    print(f"  discovery answer  : {r['qualify_answer']!r}")
    print(f"  should emphasize  : {(r['qualify_emphasize'] or '')[:70]}")
    lat = r["qualify_latency_s"]
    print(f"  qualify latency   : {str(lat) + 's  (mid-call round-trip)' if lat is not None else 'n/a (no qualify hop)'}")
    print(f"  pitch (truncated) : {(r['pitch'] or '')[:90]}")
    verdict = {True: "TAILORED ✓", False: "NOT tailored ✗", None: "n/a"}[r["pitch_tailored"]]
    print(f"  pitch_tailored    : {verdict}")


def main(argv: list[str] | None = None, *, provider=None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    repo_root = str(Path(__file__).resolve().parent.parent)
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    from app.config import load_env
    load_env()
    if provider is None:
        from app.vapi_client import VapiVoiceProvider, _get_vapi
        provider = VapiVoiceProvider()
        if not argv:  # default to newest call
            argv = [_get_vapi().get("/call", params={"limit": 1}).json()[0]["id"]]

    rc = 0
    for call_id in argv:
        try:
            call = provider.fetch_call(call_id=call_id.strip())
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR fetching {call_id}: {exc}", file=sys.stderr)
            rc = 1
            continue
        _print_report(evaluate_call(call))
        print()
    return rc


if __name__ == "__main__":
    sys.exit(main())
