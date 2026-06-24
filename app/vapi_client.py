"""Alta Outbound Voice Agent — app/vapi_client.py

Single responsibility: the `VoiceProvider` adapter — the ONLY egress to the
telephony/voice platform (CLAUDE.md §1.2 / OQ-VOICE-2: Vapi primary, adapter
mandatory so Retell is a config swap, never a rewrite). Two parts live here:

  - `VoiceProvider` — the graded interface (CLAUDE.md §9) with EXACTLY three
    methods: `configure_assistant(...)`, `place_call(...)`, `fetch_call_cost(...)`.
    These signatures are a graded contract — do not rename or change them.
  - `VapiVoiceProvider` — the Vapi implementation:
      * `configure_assistant(...)` is a PURE BUILDER (no network, offline-callable):
        it wires LLM_MODEL, the system prompt, the 5 tool/function definitions
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
    END_CALL_MESSAGE,
    LLM_MODEL,
    MAX_CALL_DURATION_S,
    TRANSCRIBER_MODEL,
    TRANSCRIBER_PROVIDER,
    TTS_PROVIDER,
    TTS_VOICE_ID,
    get_lead_context,
    get_setting,
    require_setting,
)
from app.persona import build_system_prompt, load_value_prop

# Turn-taking + pacing tuning (Vapi-specific knobs, NOT §9 governance).
#  stopSpeakingPlan: brief backchannels ("okay", "mm-hm") / line noise must not cut
#    Aria off mid-sentence — `numWords=3` ⇒ the caller must say 3+ words before she
#    stops; `backoffSeconds` ⇒ pause before resuming after a real interruption.
#  startSpeakingPlan.waitSeconds: how long to wait after the caller stops before Aria
#    replies — lowered 0.6→0.4→0.3 to cut the response lag (Asaf live reviews 2026-06-24).
#  _TTS_SPEED: OpenAI-TTS playback rate (1.0 = normal). 1.1 ⇒ slightly faster than
#    normal — 1.2 was a touch too fast on the live call (Asaf review 2026-06-24).
#    Tunable; Vapi range 0.25–4.0.
_STOP_SPEAKING_PLAN = {"numWords": 3, "voiceSeconds": 0.3, "backoffSeconds": 1.5}
_START_SPEAKING_PLAN = {"waitSeconds": 0.3}
_TTS_SPEED = 1.1


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

def _tool_schemas(
    server_url: str | None = None,
    server_secret: str | None = None,
) -> list[dict[str, Any]]:
    """Return the 5 tool/function definitions for the assistant payload.

    Each function's `name` is exactly its AGENT_TOOLS entry (the dispatch key the
    webhook routes on — server.py → tools.dispatch). The argument schemas mirror
    the keyword params of the matching app.tools function. Built fresh each call
    (a pure value); a closing assert proves the names equal AGENT_TOOLS so a drift
    fails loudly, not silently at call time.

    If *server_url* is given, each tool carries `server.url` = that URL so Vapi
    knows WHERE to POST the tool invocation (without it → "No result returned").
    If *server_secret* is given too, it is set as `server.secret`, which Vapi sends
    back as the `x-vapi-secret` header so our webhook auth passes (without it →
    the webhook 401s and the tool result is "unauthorized" — live fix 2026-06-24).
    """
    schemas: list[dict[str, Any]] = [
        {
            "type": "function",
            "function": {
                "name": "check_availability",
                "description": (
                    "Return free meeting slots in the lookahead window, in the lead's "
                    "timezone. Call this BEFORE proposing any time. Offer the returned "
                    "`say` strings to the prospect VERBATIM — never compute or reword "
                    "dates/times yourself."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
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
                        "slot_start_iso": {
                            "type": "string",
                            "description": "The chosen slot's slot_key/start_utc from check_availability.",
                        },
                        "summary": {
                            "type": "string",
                            "description": "Optional meeting title.",
                        },
                    },
                    "required": ["slot_start_iso"],
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
                        "disposition": {
                            "type": "string",
                            "enum": [
                                "booked", "declined", "no_answer", "voicemail", "error",
                            ],
                        },
                        "event_id": {"type": "string"},
                        "notes": {"type": "string"},
                    },
                    "required": ["disposition"],
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
    ]

    # Tell Vapi WHERE to send each tool invocation (else "No result returned"),
    # and WITH WHICH SECRET so our webhook auth passes (else "unauthorized").
    if server_url:
        for s in schemas:
            server: dict[str, Any] = {"url": server_url}
            if server_secret:
                server["secret"] = server_secret
            s["server"] = server

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
        lead: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build the Vapi assistant payload (VOICE1 / CON2 / CON3).

        Wires LLM_MODEL, the runtime-assembled system prompt, the 5 tool
        definitions, and — the graded chokepoint — DISCLOSURE_LINE in the STATIC
        first-message field (`firstMessage`), byte-exact and consumed from config
        (NOT a prompt the model could paraphrase). Recording is enabled together
        with the disclosure (CON3). Pure: no network, callable offline.
        """
        vp = load_value_prop(value_prop_path)
        system_prompt = build_system_prompt(variant, vp)

        # Authoritative lead context → assistant metadata. Sourced from the lead
        # record if supplied, else from the env-backed get_lead_context() so the
        # webhook can recover the same values (D2/D3 — the model never supplies them).
        if lead is not None:
            lead_id = lead.get("lead_id") or lead.get("id")
            lead_timezone = lead.get("timezone") or lead.get("lead_timezone")
        else:
            lead_id, lead_timezone = get_lead_context()

        # Tool server URL: Vapi POSTs each tool invocation here. Derived from
        # PUBLIC_WEBHOOK_URL (the public tunnel/host) + the /webhook/tool route.
        # Without it Vapi has no address → "No result returned" on every tool.
        public_base = (get_setting("PUBLIC_WEBHOOK_URL") or "").rstrip("/")
        tool_server_url = f"{public_base}/webhook/tool" if public_base else None
        # The shared secret Vapi must echo as x-vapi-secret so our webhook auth
        # passes; read at build time, sent only in the runtime payload to Vapi.
        tool_server_secret = get_setting("VAPI_WEBHOOK_SECRET")

        return {
            # Standard pipeline (OQ-VOICE-1 revised 2026-06-24): a chat LLM, a
            # dedicated TTS voice, and a transcriber — robust telephony audio,
            # unlike realtime speech-to-speech which fragmented/paused on the phone.
            "model": {
                "provider": "openai",
                "model": LLM_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                ],
                "tools": _tool_schemas(tool_server_url, tool_server_secret),
            },
            "voice": {"provider": TTS_PROVIDER, "voiceId": TTS_VOICE_ID, "speed": _TTS_SPEED},
            "transcriber": {
                "provider": TRANSCRIBER_PROVIDER,
                "model": TRANSCRIBER_MODEL,
                "language": "en",
            },
            # CHOKEPOINT (VOICE1/CON2/Finding 4): the disclosure is the platform's
            # static first message — spoken VERBATIM by the platform, byte-exact,
            # never model-generated. Consumed from config (DISCLOSURE_LINE).
            "firstMessage": DISCLOSURE_LINE,
            "firstMessageMode": "assistant-speaks-first",
            # CON3 (updated 2026-06-24, Asaf): recording stays ON and ships in the
            # same payload as the verbatim AI disclosure (firstMessage above). The
            # spoken *recording notice* was dropped from DISCLOSURE_LINE — recording
            # without a spoken notice is lawful only for the one-party-consent
            # consented test line; restore a notice before two-party-consent use.
            "recordingEnabled": True,
            # CLEAN HANGUP (D9/D4/D5, 2026-06-24): pin termination to the PLATFORM.
            # endCallFunctionEnabled lets a decision-to-end ACTUALLY hang up (a custom
            # end_call tool returned JSON but never terminated → the agent rambled past
            # "goodbye"; that tool is retired). END_CALL_MESSAGE is the byte-exact close
            # spoken BY Vapi — neutral so it fits a booking and a decline, never drifts
            # or doubles, and there is no "after goodbye" to ramble into. (Exact Vapi
            # field semantics are a live-reconcile item — verified by the live test,
            # like x-vapi-secret / the model id / the tool-result envelope.)
            "endCallFunctionEnabled": True,
            "endCallMessage": END_CALL_MESSAGE,
            # Anti-loop / cost guard mirrors the wall-clock cap (§9).
            "maxDurationSeconds": MAX_CALL_DURATION_S,
            # Turn-taking so brief backchannels don't fragment the agent's speech
            # (live "fragmented voice" fix 2026-06-24).
            "stopSpeakingPlan": _STOP_SPEAKING_PLAN,
            "startSpeakingPlan": _START_SPEAKING_PLAN,
            # Only include lead keys when set — a None would serialize as JSON null,
            # which Vapi may reject (metadata values are expected to be strings) and
            # the webhook recovers either value from the env anyway (extract_lead_context).
            "metadata": {
                "variant": variant,
                **({"lead_id": lead_id} if lead_id else {}),
                **({"lead_timezone": lead_timezone} if lead_timezone else {}),
            },
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
            if resp.status_code >= 400:
                # Surface Vapi's error BODY (the actionable reason — e.g. an
                # invalid assistant-payload field), not just the status line.
                return CallResult(
                    ok=False, error="vapi_error",
                    message=f"HTTP {resp.status_code} from Vapi /call: {resp.text[:2000]}",
                )
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
            if resp.status_code >= 400:
                return CostResult(
                    ok=False, error="vapi_error",
                    message=f"HTTP {resp.status_code} from Vapi /call/{call_id}: {resp.text[:500]}",
                )
            data = resp.json()
            raw_cost = data.get("cost")
            if raw_cost is None:
                return CostResult(ok=False, error="vapi_error",
                                  message="Vapi returned no cost for the call")
            return CostResult(ok=True, cost_usd=float(raw_cost))
        except Exception as exc:  # noqa: BLE001 — surface as data (§6)
            return CostResult(ok=False, error="vapi_error", message=str(exc))

    def fetch_call(self, *, call_id: str) -> dict[str, Any]:
        """Return the full Vapi call object for *call_id* (live, read-only).

        Used by diagnostic tooling (scripts/inspect_call.py) to render the
        timestamped transcript + interruption flags when debugging the live
        call experience. This is a read-only helper on the concrete Vapi
        adapter ONLY — it is NOT part of the graded VoiceProvider interface
        (the 3 graded methods configure_assistant/place_call/fetch_call_cost
        are unchanged), so it does not widen the provider seam.

        Raises RuntimeError with the response body on a non-2xx so the caller
        sees the actionable reason; the diagnostic script catches + prints it.
        """
        client = _get_vapi()
        resp = client.get(f"/call/{call_id}")
        if resp.status_code >= 400:
            raise RuntimeError(
                f"HTTP {resp.status_code} from Vapi /call/{call_id}: {resp.text[:2000]}"
            )
        return resp.json()


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
