"""Alta Outbound Voice Agent — app/testing/mock_bridge.py

Single responsibility: the MOCK-BRIDGE — a local fault-injection driver over the
**webhook + transcript layer** for the stress suite (STR-T* / STR-P*).

Scoping truth (do not over-claim): our service does NOT own the media path — the
voice platform (Vapi) does. So raw SIP packet loss / SNR / codec faults cannot be
injected at our boundary; what reaches our code is **Vapi webhook envelopes** and
**transcripts**. This bridge exercises exactly those fault EFFECTS:
  - well-formed and MALFORMED Vapi tool-call envelopes (missing toolCallId, flat vs
    nested, stringified args, garbled-JSON args, empty / no-tool-call),
  - call-status / lifecycle webhooks (incl. mid-call drop signals),
  - webhook REDELIVERY (the same envelope posted N times),
  - garbled / lossy transcripts (the STT/SNR effect on a string),
  - a WRONG secret (fail-closed auth under load).
True RTP-level validation (real barge-in, disclosure-under-impairment) lives only on
the LIVE-GATED tier and is read back with scripts/inspect_call.py.

Import-safety (ENV4): importing this module builds NO client, reads NO .env, opens NO
network. The FastAPI TestClient is constructed LAZILY on first use inside the bridge.
"""

from __future__ import annotations

import json
import random
import time
from typing import Any

from app.config import RANDOM_SEED  # the single determinism seed (CLAUDE.md §8)

# A clearly-fake shared secret for the offline bridge. NOT a real credential — the
# server reads VAPI_WEBHOOK_SECRET from the env, which the test fixture sets to this.
DEFAULT_SECRET = "mock-bridge-fake-secret"

TOOL_PATH = "/webhook/tool"
STATUS_PATH = "/webhook/status"


# ===========================================================================
# Envelope builders — well-formed and adversarial Vapi webhook payloads
# ===========================================================================

def tool_call_envelope(
    name: str,
    arguments: dict[str, Any] | None = None,
    *,
    tool_call_id: str | None = "call_0001",
    arguments_as_string: bool = False,
    nested: bool = True,
) -> dict[str, Any]:
    """Build a Vapi tool-call webhook envelope.

    nested=True  → Vapi form: {"message": {"toolCalls": [{"id", "function": {...}}]}}
    nested=False → flat form:  {"name", "arguments", "toolCallId"}  (simple provider)
    arguments_as_string=True reproduces Vapi sometimes sending a JSON-encoded string.
    tool_call_id=None reproduces a provider that omits the id (STR-T9).
    """
    args = arguments or {}
    if not nested:
        env: dict[str, Any] = {"name": name, "arguments": args}
        if tool_call_id is not None:
            env["toolCallId"] = tool_call_id
        return env
    fn = {
        "name": name,
        "arguments": json.dumps(args) if arguments_as_string else args,
    }
    return {"message": {"toolCalls": [{"id": tool_call_id, "function": fn}]}}


def garbled_args_envelope(
    name: str, *, tool_call_id: str | None = "call_0001"
) -> dict[str, Any]:
    """A tool-call whose arguments are an INVALID JSON string (STR-T9)."""
    return {
        "message": {
            "toolCalls": [
                {"id": tool_call_id,
                 "function": {"name": name, "arguments": "{not valid json,,,"}}
            ]
        }
    }


def empty_envelope() -> dict[str, Any]:
    """A message with no tool call at all (STR-T5/T9)."""
    return {"message": {}}


def no_tool_call_envelope() -> dict[str, Any]:
    """A message carrying an empty toolCalls list (STR-T9)."""
    return {"message": {"toolCalls": []}}


def status_envelope(
    status: str, *, call_id: str = "call_xyz", number: str | None = None
) -> dict[str, Any]:
    """A call-status / lifecycle webhook (e.g. status='customer-ended-call' = drop)."""
    call: dict[str, Any] = {"id": call_id}
    if number:
        call["customer"] = {"number": number}
    return {"message": {"status": status, "call": call}}


# ===========================================================================
# Transcript faults — the STT/SNR EFFECT on a string (STR-T2/T3/P3)
# ===========================================================================

def garble(text: str, *, loss: float = 0.3, seed: int = RANDOM_SEED) -> str:
    """Drop a deterministic fraction of words (the packet-loss / low-SNR effect).

    Seeded off config.RANDOM_SEED (the single offline determinism knob, §8) so the
    stress suite stays reproducible. loss=1.0 → empty (total loss).
    """
    rng = random.Random(seed)
    return " ".join(w for w in text.split() if rng.random() > loss)


# ===========================================================================
# The bridge — posts envelopes to the real server via a lazy TestClient
# ===========================================================================

class MockVapiBridge:
    """Drives app.server's webhooks with synthetic Vapi envelopes (no network).

    The caller (a test) must set VAPI_WEBHOOK_SECRET in the env to `secret` so the
    server accepts the bridge's posts; pass a different `secret=` to a post() to
    exercise fail-closed auth. The TestClient is built lazily (ENV4).
    """

    def __init__(self, *, secret: str = DEFAULT_SECRET) -> None:
        self.secret = secret
        self._client = None

    def _get_client(self):
        if self._client is None:
            from fastapi.testclient import TestClient  # lazy — not at import
            from app.server import app

            self._client = TestClient(app)
        return self._client

    def post(
        self,
        path: str,
        envelope: dict[str, Any],
        *,
        secret: str | None = None,
        latency_s: float = 0.0,
    ):
        """POST *envelope* to *path* with the x-vapi-secret header.

        latency_s optionally delays the send (a coarse client-side delay knob); the
        latency suite normally measures the REAL handler time and does not inject.
        """
        if latency_s:
            time.sleep(latency_s)
        raw = json.dumps(envelope).encode("utf-8")
        return self._get_client().post(
            path,
            content=raw,
            headers={
                "x-vapi-secret": self.secret if secret is None else secret,
                "content-type": "application/json",
            },
        )

    def tool_call(self, name: str, arguments: dict[str, Any] | None = None, **kw):
        """Convenience: post a tool-call envelope and return the raw response."""
        return self.post(TOOL_PATH, tool_call_envelope(name, arguments, **kw))

    @staticmethod
    def result_of(resp) -> dict[str, Any]:
        """Unwrap Vapi's {"results":[{"toolCallId","result"}]} envelope to the payload."""
        body = resp.json()
        inner = body["results"][0]["result"]
        return json.loads(inner) if isinstance(inner, str) else inner
