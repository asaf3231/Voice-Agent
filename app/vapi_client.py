"""Alta Outbound Voice Agent — app/vapi_client.py

Single responsibility: the `VoiceProvider` adapter — the ONLY egress to the
telephony/voice platform (CLAUDE.md §1.2 / OQ-VOICE-2: Vapi primary, adapter
mandatory so Retell is a config swap, never a rewrite). Two parts live here:

  - `VoiceProvider` — the graded interface (CLAUDE.md §9) with EXACTLY three
    methods: `configure_assistant(...)`, `place_call(...)`, `fetch_call_cost(...)`.
    These signatures are a graded contract — do not rename or change them.
  - `VapiVoiceProvider` — the Vapi implementation:
      * `configure_assistant(...)` is a PURE BUILDER (no network, offline-callable):
        it wires REALTIME_MODEL, the system prompt, the 5 tool/function definitions
        (names == AGENT_TOOLS), and DISCLOSURE_LINE pinned to Vapi's STATIC
        first-message field (`firstMessage`), byte-exact (VOICE1 / CON2 / Red-Team
        Finding 4 — NOT a prompt the model could paraphrase). Recording is enabled
        ONLY together with the disclosure (CON3).
      * `place_call(...)` / `fetch_call_cost(...)` are the LIVE outbound + cost-pull,
        over a LAZY httpx client built only by `_get_vapi()`. A live failure is
        structured data, never a crash (§6).

Import-safety (ENV4): importing this module defines only constants, dataclasses,
classes, and functions. No client, no network, no .env read, no call. The
module-level Vapi singleton (`_vapi`) is None at import; only the lazy
`_get_vapi()` constructs it, reading VAPI_API_KEY / VAPI_PHONE_NUMBER_ID via
config WHEN CALLED (never at import, never in the offline suite). The two graded
literals come from app.config so they cannot drift.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from app.config import (
    AGENT_TOOLS,
    DISCLOSURE_LINE,
    MAX_CALL_DURATION_S,
    REALTIME_MODEL,
    require_setting,
)
from app.persona import build_system_prompt, load_value_prop


# ===========================================================================
# Structured result types (no exceptions across the seam, §6)
# ===========================================================================

@dataclass(frozen=True)
class CallResult:
    """The structured outcome of a place_call attempt (never an exception, §6).

    ok=True  → call_id identifies the placed call; status carries the provider's
               call status if already known.
    ok=False → error is a short machine code (e.g. "vapi_error", "config_error");
               message is human-readable. call_id is None.
    """

    ok: bool
    call_id: str | None = None
    status: str | None = None
    error: str | None = None
    message: str | None = None


@dataclass(frozen=True)
class CostResult:
    """The structured outcome of a fetch_call_cost attempt (§6).

    ok=True  → cost_usd is the provider-reported cost for the call.
    ok=False → error/message explain why; cost_usd is None.
    """

    ok: bool
    cost_usd: float | None = None
    error: str | None = None
    message: str | None = None


# ===========================================================================
# The VoiceProvider interface — the ONLY way out to the voice platform.
# Graded signatures (CLAUDE.md §9): configure_assistant / place_call /
# fetch_call_cost. Do NOT change these.
# ===========================================================================

@runtime_checkable
class VoiceProvider(Protocol):
    """The voice-platform seam (CLAUDE.md §9 / OQ-VOICE-2 adapter mandate).

    The single egress for outbound call control + assistant config. Swapping the
    implementation (Vapi ↔ Retell ↔ the test fake) must not touch
    orchestrate.py / server.py — they depend only on this interface (VOICE5).
    """

    def configure_assistant(
        self,
        *,
        variant: str = "A",
        value_prop_path: str | None = None,
    ) -> dict[str, Any]:
        """Build the provider assistant payload (pure builder; no network)."""
        ...

    def place_call(
        self,
        *,
        to_number: str,
        assistant: dict[str, Any],
    ) -> CallResult:
        """Place an outbound call to *to_number* with the given assistant config."""
        ...

    def fetch_call_cost(self, *, call_id: str) -> CostResult:
        """Return the provider-reported cost for *call_id*."""
        ...


# ===========================================================================
# Tool/function JSON-schema definitions (names == AGENT_TOOLS — VOICE1)
# ===========================================================================

def _tool_schemas() -> list[dict[str, Any]]:
    """Return the 5 tool/function definitions for the assistant payload.

    Each function's `name` is exactly its AGENT_TOOLS entry (the dispatch key the
    webhook routes on — server.py → tools.dispatch). The argument schemas mirror
    the keyword params of the matching app.tools function. Built fresh each call
    (a pure value); a closing assert proves the names equal AGENT_TOOLS so a drift
    fails loudly, not silently at call time.
    """
    schemas: list[dict[str, Any]] = [
        {
            "type": "function",
            "function": {
                "name": "check_availability",
                "description": (
                    "Return free meeting slots in the lookahead window, resolved to "
                    "the lead's timezone. Call before proposing a slot."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "lead_timezone": {
                            "type": "string",
                            "description": "IANA tz of the lead, e.g. 'America/New_York'.",
                        },
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "book_meeting",
                "description": (
                    "Book a 30-minute meeting for the lead at a free slot. Only voice a "
                    "confirmation AFTER this returns ok. A taken slot → offer another."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "lead_id": {"type": "string", "description": "The lead's id."},
                        "slot_start_iso": {
                            "type": "string",
                            "description": "ISO-8601 start time of the chosen free slot.",
                        },
                        "summary": {
                            "type": "string",
                            "description": "Optional meeting title.",
                        },
                    },
                    "required": ["lead_id", "slot_start_iso"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "log_disposition",
                "description": (
                    "Record the structured call outcome (booked / declined / no_answer "
                    "/ voicemail / error). The phone number is masked automatically."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "lead_id": {"type": "string"},
                        "disposition": {
                            "type": "string",
                            "enum": [
                                "booked", "declined", "no_answer", "voicemail", "error",
                            ],
                        },
                        "phone_e164": {"type": "string"},
                        "event_id": {"type": "string"},
                        "notes": {"type": "string"},
                    },
                    "required": ["lead_id", "disposition"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "detect_voicemail",
                "description": (
                    "Classify whether a transcript is a voicemail greeting; on "
                    "detection, leave a short message then end."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "transcript": {
                            "type": "string",
                            "description": "The text heard on answer.",
                        },
                    },
                    "required": ["transcript"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "end_call",
                "description": "Hang up cleanly with a structured reason.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reason": {"type": "string"},
                    },
                    "required": [],
                },
            },
        },
    ]

    # Guard: the function names MUST equal AGENT_TOOLS exactly (the dispatch keys).
    names = [s["function"]["name"] for s in schemas]
    assert names == AGENT_TOOLS, (
        "tool schema names must equal AGENT_TOOLS exactly. "
        f"schemas={names} AGENT_TOOLS={AGENT_TOOLS}"
    )
    return schemas


# ===========================================================================
# VapiVoiceProvider — the Vapi implementation
# ===========================================================================

class VapiVoiceProvider:
    """The Vapi VoiceProvider (CLAUDE.md §1.2). The only Vapi-specific code.

    `configure_assistant` is a pure builder (offline-safe, no network). `place_call`
    / `fetch_call_cost` reach the live REST API through the LAZY `_get_vapi()` client
    only — never at import, never in the offline suite (ENV4 / VOICE4).
    """

    BASE_URL = "https://api.vapi.ai"

    # -- assistant config (pure builder — no network, offline-callable) -------

    def configure_assistant(
        self,
        *,
        variant: str = "A",
        value_prop_path: str | None = None,
    ) -> dict[str, Any]:
        """Build the Vapi assistant payload (VOICE1 / CON2 / CON3).

        Wires REALTIME_MODEL, the runtime-assembled system prompt, the 5 tool
        definitions, and — the graded chokepoint — DISCLOSURE_LINE in the STATIC
        first-message field (`firstMessage`), byte-exact and consumed from config
        (NOT a prompt the model could paraphrase). Recording is enabled together
        with the disclosure (CON3). Pure: no network, callable offline.
        """
        vp = load_value_prop(value_prop_path)
        system_prompt = build_system_prompt(variant, vp)

        return {
            # The OpenAI Realtime model is configured INSIDE the platform; we name
            # the exact pinned id so the assistant uses the locked engine (ENV2).
            "model": {
                "provider": "openai",
                "model": REALTIME_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                ],
                "tools": _tool_schemas(),
            },
            # CHOKEPOINT (VOICE1/CON2/Finding 4): the disclosure is the platform's
            # static first message — spoken VERBATIM by the platform, byte-exact,
            # never model-generated. Consumed from config (DISCLOSURE_LINE).
            "firstMessage": DISCLOSURE_LINE,
            "firstMessageMode": "assistant-speaks-first",
            # CON3: recording is enabled ONLY together with the disclosure. The
            # disclosure (above) is always present in this payload, so recording is
            # gated on the same payload that carries the verbatim recorded-disclosure.
            "recordingEnabled": True,
            # Anti-loop / cost guard mirrors the wall-clock cap (§9).
            "maxDurationSeconds": MAX_CALL_DURATION_S,
            "metadata": {"variant": variant},
        }

    # -- live outbound (lazy client only — ENV4) ------------------------------

    def place_call(
        self,
        *,
        to_number: str,
        assistant: dict[str, Any],
    ) -> CallResult:
        """Place an outbound call via Vapi (live). Any failure → structured data (§6).

        Reads VAPI_PHONE_NUMBER_ID via config and dials through the lazy client.
        Never raises across this boundary — a misconfig or HTTP error is a
        CallResult(ok=False), so the campaign runner is never crashed by the
        provider (CALL1).
        """
        try:
            phone_number_id = require_setting("VAPI_PHONE_NUMBER_ID")
        except ValueError as exc:
            return CallResult(ok=False, error="config_error", message=str(exc))

        try:
            client = _get_vapi()
            resp = client.post(
                "/call",
                json={
                    "phoneNumberId": phone_number_id,
                    "customer": {"number": to_number},
                    "assistant": assistant,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            call_id = str(data.get("id") or "")
            if not call_id:
                return CallResult(ok=False, error="vapi_error",
                                  message="Vapi returned no call id")
            return CallResult(ok=True, call_id=call_id, status=data.get("status"))
        except Exception as exc:  # noqa: BLE001 — surface as data (§6)
            return CallResult(ok=False, error="vapi_error", message=str(exc))

    def fetch_call_cost(self, *, call_id: str) -> CostResult:
        """Return the Vapi-reported cost for *call_id* (live). Failure → data (§6)."""
        try:
            client = _get_vapi()
            resp = client.get(f"/call/{call_id}")
            resp.raise_for_status()
            data = resp.json()
            raw_cost = data.get("cost")
            if raw_cost is None:
                return CostResult(ok=False, error="vapi_error",
                                  message="Vapi returned no cost for the call")
            return CostResult(ok=True, cost_usd=float(raw_cost))
        except Exception as exc:  # noqa: BLE001 — surface as data (§6)
            return CostResult(ok=False, error="vapi_error", message=str(exc))


# ===========================================================================
# Lazy singleton — the live httpx client is built on first call ONLY (ENV4)
# ===========================================================================

_vapi: Any | None = None


def _get_vapi() -> Any:
    """Return (constructing on first call) the LIVE Vapi httpx client.

    NOT constructed at import — the module-level `_vapi` is None until the first
    live caller (place_call / fetch_call_cost). The default offline suite uses
    FakeVoiceProvider and never reaches this function (ENV4 / VOICE4 / CON4).
    Reads VAPI_API_KEY via config only here; httpx is imported lazily so importing
    this module pulls no HTTP client into the import graph.
    """
    global _vapi
    if _vapi is None:
        import httpx  # lazy: importing this module must not pull httpx in

        api_key = require_setting("VAPI_API_KEY")
        _vapi = httpx.Client(
            base_url=VapiVoiceProvider.BASE_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=httpx.Timeout(20.0),
        )
    return _vapi


def reset_vapi() -> None:
    """Reset the live singleton (test helper — do NOT call in production code)."""
    global _vapi
    _vapi = None
