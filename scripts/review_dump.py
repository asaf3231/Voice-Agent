"""Dump the last N Vapi calls for a deep review — transcript + tool args + score.

Reuses the already-tested inspect_call.render_transcript + score_call.evaluate_call
so the output is consistent with `make inspect` / `make score`. Read-only.

Uses a dedicated long-timeout client + retry because the Vapi /call list endpoint
is intermittently slow (the default 20s client times out).

Usage:
  python scripts/review_dump.py [N]      # default N=4
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _get(client, path, **kw):
    """GET with up to 3 attempts on a read timeout (Vapi /call is intermittently slow)."""
    import httpx
    last = None
    for attempt in range(3):
        try:
            return client.get(path, **kw)
        except httpx.TimeoutException as exc:  # noqa: PERF203
            last = exc
    raise last


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    n = int(argv[0]) if argv else 4

    import httpx
    from app.config import load_env, require_setting
    load_env()
    from app.vapi_client import VapiVoiceProvider
    import scripts.inspect_call as ic
    import scripts.score_call as sc

    key = require_setting("VAPI_API_KEY")
    with httpx.Client(
        base_url=VapiVoiceProvider.BASE_URL,
        headers={"Authorization": f"Bearer {key}"},
        timeout=httpx.Timeout(60.0),
    ) as client:
        listing = _get(client, "/call", params={"limit": n}).json()
        for summary in listing:
            call = _get(client, f"/call/{summary['id']}").json()
            a = call.get("assistant") or {}
            model = a.get("model") or {}
            voice = a.get("voice") or {}
            meta = a.get("metadata") or {}
            print("=" * 92)
            print(f"CALL {call.get('id')}  created={call.get('createdAt')} "
                  f"ended={call.get('endedReason')} cost=${call.get('cost')}")
            print(f"  pipeline: {model.get('provider')}/{model.get('model')} "
                  f"voice={voice.get('voiceId')}@{voice.get('speed')} | metadata={meta}")
            msgs = (call.get("artifact") or {}).get("messages") or call.get("messages") or []
            print("  --- TOOL CALLS / RESULTS ---")
            for x in msgs:
                for tc in (x.get("toolCalls") or []):
                    fn = tc.get("function") or {}
                    print(f"    CALL {fn.get('name')}: {json.dumps(fn.get('arguments'))[:220]}")
                if x.get("role") == "tool_call_result":
                    print(f"    RSLT {x.get('name')}: {str(x.get('result'))[:300]}")
            print("  --- TRANSCRIPT ---")
            print(ic.render_transcript(call))
            print("  --- SCORE ---")
            sc._print_report(sc.evaluate_call(call))
            print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
