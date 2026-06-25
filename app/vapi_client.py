"""Voice provider adapter — the only path out to the telephony platform.

Defines the VoiceProvider interface (configure_assistant / place_call /
fetch_call_cost) and its Vapi implementation, so the platform stays a config swap
rather than a rewrite. configure_assistant is a pure builder (offline-callable) that
wires the model, the tools, and — the key compliance detail — pins the AI disclosure
to the platform's static first message, so it is spoken verbatim rather than left to
the model to paraphrase. place_call and fetch_call_cost reach the live API through a
lazy HTTP client and surface any failure as structured data, never an exception.

Import-safe: no client, network, or .env access at import; the HTTP client is built
on first live use only.
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

# Turn-taking + pacing tuning (Vapi-specific knobs, not governance).
#  stopSpeakingPlan: brief backchannels ("okay", "mm-hm") / line noise must not cut
#    Aria off mid-sentence — `numWords=1` ⇒ a single word from the caller interrupts
#    her; `voiceSeconds=0.25` ⇒ ~250ms of voice to confirm it isn't noise;
#    `backoffSeconds=0.6` ⇒ pause before resuming after a real interruption
#    (tuned 2026-06-25 toward a snappier, more sensitive barge-in; numWords=1 makes
#    her yield fast — brief backchannels like "okay" may now cut her off until STT
#    backchannel filtering lands).
#  startSpeakingPlan.waitSeconds=0.2: floor silence wait after the caller stops.
#    Turn-taking is NOT the latency lever — live 2026-06-25 (call 019efe50) Vapi
#    performanceMetrics showed endpointingLatency=100ms; the ~5s reply gap was
#    modelLatency ~2.6s (gpt-4o) + voiceLatency ~2.1s (OpenAI TTS). Fix applied (§9):
#    LLM_MODEL→gpt-4o-mini + TTS→Deepgram Aura, both far lower latency. The Deepgram
#    voice reuses the key already connected for the transcriber (no extra provider key).
_STOP_SPEAKING_PLAN = {"numWords": 1, "voiceSeconds": 0.25, "backoffSeconds": 0.6}
_START_SPEAKING_PLAN = {"waitSeconds": 0.2}


# ===========================================================================
# Structured result types (no exceptions across the seam)
# ===========================================================================

@dataclass(frozen=True)
class CallResult:
    """The structured outcome of a place_call attempt (never an exception).

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
    """The structured outcome of a fetch_call_cost attempt.

    ok=True  → cost_usd is the provider-reported, FINAL cost for the call.
    ok=False → error/message explain why; cost_usd is None. error="cost_pending"
               specifically means the call has not ended yet, so its cost is not
               final — the caller should retry later or record a conservative
               projected estimate, NEVER the pre-final figure.
    """

    ok: bool
    cost_usd: float | None = None
    error: str | None = None
    message: str | None = None


# Vapi call statuses that mean the call has FINISHED and its `cost` field is final.
# CRITICAL (cost-0-vs-null bug, 2026-06-24): while a call is still queued/ringing/
# in-progress, Vapi reports `cost` as 0 — NOT null. The old guard only rejected a
# null cost, so a 0 from a not-yet-ended call sailed through as a "successful" $0.00
# and was recorded into the ledger (5 live calls → cumulative $0.00), silently
# under-counting spend and defeating the HARD_BUDGET_USD cap. Cost is trusted ONLY
# once the call has ended.
_TERMINAL_CALL_STATUSES = frozenset({"ended"})


def _cost_from_call(data: dict[str, Any]) -> CostResult:
    """Derive a CostResult from a Vapi call object, treating cost as final ONLY when ended.

    - Not yet ended  → ok=False, error="cost_pending" (the 0-vs-null fix): the `cost`
      field is 0/partial until the call ends, so it must not be recorded as actual spend.
    - Ended, no cost → ok=False, error="cost_unavailable": ended but Vapi hasn't attached
      a cost yet (brief end-of-call-report lag) — retry shortly.
    - Ended, cost set → ok=True with the final figure (a genuinely free call ⇒ 0.0 is fine
      precisely because the call has ended and that 0 is authoritative).
    """
    status = str(data.get("status") or "").lower()
    raw_cost = data.get("cost")
    if status not in _TERMINAL_CALL_STATUSES:
        shown = status or "unknown"
        return CostResult(
            ok=False, error="cost_pending",
            message=f"call status={shown!r}; cost is not final until the call ends",
        )
    if raw_cost is None:
        return CostResult(
            ok=False, error="cost_unavailable",
            message="call ended but Vapi has not reported a cost yet — retry shortly",
        )
    return CostResult(ok=True, cost_usd=float(raw_cost))


# ===========================================================================
# The VoiceProvider interface — the ONLY way out to the voice platform.
# These three method signatures are the contract: configure_assistant /
# place_call / fetch_call_cost. Do NOT change them.
# ===========================================================================

@runtime_checkable
class VoiceProvider(Protocol):
    """The voice-platform seam — the single egress to the voice platform.

    The single egress for outbound call control + assistant config. Swapping the
    implementation (Vapi ↔ Retell ↔ the test fake) must not touch
    orchestrate.py / server.py — they depend only on this interface.
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
# Tool/function JSON-schema definitions (names == AGENT_TOOLS)
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
    the webhook 401s and the tool result is "unauthorized").
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
    """The Vapi implementation of VoiceProvider — the only Vapi-specific code.

    `configure_assistant` is a pure builder (offline-safe, no network). `place_call`
    / `fetch_call_cost` reach the live REST API through the LAZY `_get_vapi()` client
    only — never at import, never in the offline suite.
    """

    BASE_URL = "https://api.vapi.ai"

    # -- assistant config (pure builder — no network, offline-callable) -------

    def configure_assistant(
        self,
        *,
        variant: str = "A",
        value_prop_path: str | None = None,
        lead: dict[str, Any] | None = None,
        available_slots: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Build the Vapi assistant payload.

        Wires LLM_MODEL, the runtime-assembled system prompt, the 5 tool
        definitions, and — the graded chokepoint — DISCLOSURE_LINE in the STATIC
        first-message field (`firstMessage`), byte-exact and consumed from config
        (NOT a prompt the model could paraphrase). Recording is enabled together
        with the disclosure. Pure: no network, callable offline.

        *available_slots* (optional): slots pre-fetched at call setup, injected into
        the system prompt so Aria proposes times instantly without a mid-call
        check_availability round-trip. Additive (like *lead*); the graded
        VoiceProvider signature is unchanged.
        """
        vp = load_value_prop(value_prop_path)
        system_prompt = build_system_prompt(
            variant, vp, available_slots=available_slots
        )

        # Authoritative lead context → assistant metadata. Sourced from the lead
        # record if supplied, else from the env-backed get_lead_context() so the
        # webhook can recover the same values (the model never supplies them).
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
            # Standard pipeline: a chat LLM, a
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
            "voice": {"provider": TTS_PROVIDER, "voiceId": TTS_VOICE_ID},
            "transcriber": {
                "provider": TRANSCRIBER_PROVIDER,
                "model": TRANSCRIBER_MODEL,
                "language": "en",
            },
            # CHOKEPOINT: the disclosure is the platform's
            # static first message — spoken VERBATIM by the platform, byte-exact,
            # never model-generated. Consumed from config (DISCLOSURE_LINE).
            "firstMessage": DISCLOSURE_LINE,
            "firstMessageMode": "assistant-speaks-first",
            # Recording stays ON and ships in the
            # same payload as the verbatim AI disclosure (firstMessage above). The
            # spoken *recording notice* was dropped from DISCLOSURE_LINE — recording
            # without a spoken notice is lawful only for the one-party-consent
            # consented test line; restore a notice before two-party-consent use.
            "recordingEnabled": True,
            # CLEAN HANGUP: pin termination to the PLATFORM.
            # endCallFunctionEnabled lets a decision-to-end ACTUALLY hang up (a custom
            # end_call tool returned JSON but never terminated → the agent rambled past
            # "goodbye"; that tool is retired). END_CALL_MESSAGE is the byte-exact close
            # spoken BY Vapi — neutral so it fits a booking and a decline, never drifts
            # or doubles, and there is no "after goodbye" to ramble into. (Exact Vapi
            # field semantics are a live-reconcile item — verified by the live test,
            # like x-vapi-secret / the model id / the tool-result envelope.)
            "endCallFunctionEnabled": True,
            "endCallMessage": END_CALL_MESSAGE,
            # Anti-loop / cost guard mirrors the wall-clock cap.
            "maxDurationSeconds": MAX_CALL_DURATION_S,
            # Turn-taking so brief backchannels don't fragment the agent's speech
            # (fixes the "fragmented voice" seen on live calls).
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

    # -- live outbound (lazy client only) ------------------------------------

    def place_call(
        self,
        *,
        to_number: str,
        assistant: dict[str, Any],
    ) -> CallResult:
        """Place an outbound call via Vapi (live). Any failure → structured data.

        Reads VAPI_PHONE_NUMBER_ID via config and dials through the lazy client.
        Never raises across this boundary — a misconfig or HTTP error is a
        CallResult(ok=False), so the campaign runner is never crashed by the
        provider.
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
        except Exception as exc:  # noqa: BLE001 — surface as data
            return CallResult(ok=False, error="vapi_error", message=str(exc))

    def fetch_call_cost(self, *, call_id: str) -> CostResult:
        """Return the Vapi-reported FINAL cost for *call_id* (live). Failure → data.

        Status-aware (cost-0-vs-null fix): a cost is returned ok=True ONLY once the
        call has ended; before that Vapi reports `cost` as 0 and we surface
        ok=False/error="cost_pending" so the caller never records a fake $0. See
        _cost_from_call. The 3 graded method signatures are unchanged.
        """
        try:
            client = _get_vapi()
            resp = client.get(f"/call/{call_id}")
            if resp.status_code >= 400:
                return CostResult(
                    ok=False, error="vapi_error",
                    message=f"HTTP {resp.status_code} from Vapi /call/{call_id}: {resp.text[:500]}",
                )
            return _cost_from_call(resp.json())
        except Exception as exc:  # noqa: BLE001 — surface as data
            return CostResult(ok=False, error="vapi_error", message=str(exc))

    def fetch_call_cost_settled(
        self,
        *,
        call_id: str,
        max_wait_s: int = 180,
        interval_s: int = 6,
        sleeper: Any | None = None,
    ) -> CostResult:
        """Poll fetch_call_cost until the call's cost is FINAL (ended) or a timeout.

        Returns the final CostResult on success, or the last non-ok result (typically
        error="cost_pending") on timeout — so the caller's projected-estimate fallback
        fires, NEVER a fake $0. A non-pending hard failure (e.g. vapi_error) returns
        immediately; only "cost_pending"/"cost_unavailable" are retried.

        Not part of the graded VoiceProvider interface (a concrete-adapter helper, like
        fetch_call) — so the 3 graded signatures stay frozen. *sleeper* is injectable so
        the offline suite drives the poll with zero real wall-clock.
        """
        import time as _time

        sleep = sleeper if sleeper is not None else _time.sleep
        attempts = max(1, int(max_wait_s // max(1, interval_s)) + 1)
        last = CostResult(ok=False, error="cost_pending", message="no fetch attempted")
        for i in range(attempts):
            last = self.fetch_call_cost(call_id=call_id)
            if last.ok:
                return last
            # Only a not-yet-final cost is worth waiting on; a real error is terminal.
            if last.error not in ("cost_pending", "cost_unavailable"):
                return last
            if i < attempts - 1:
                sleep(interval_s)
        return last

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
# Lazy singleton — the live httpx client is built on first call ONLY
# ===========================================================================

_vapi: Any | None = None


def _get_vapi() -> Any:
    """Return (constructing on first call) the LIVE Vapi httpx client.

    NOT constructed at import — the module-level `_vapi` is None until the first
    live caller (place_call / fetch_call_cost). The default offline suite uses
    FakeVoiceProvider and never reaches this function.
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
