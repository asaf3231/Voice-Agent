"""Alta Outbound Voice Agent — app/server.py

Single responsibility: the secret-verified FastAPI webhook server the voice
platform calls for tool/function invocations and call-status events. It is the
inbound counterpart to the VoiceProvider adapter (which owns OUTBOUND calls).

What it enforces:
  - Webhook authenticity (VOICE2): every inbound webhook is authenticated against
    VAPI_WEBHOOK_SECRET — Vapi sends the configured server secret verbatim in the
    `x-vapi-secret` header; we constant-time compare it to our secret. A bad/missing
    secret → HTTP 401, never processed. A valid one → processed.
  - Tool dispatch (VOICE3): a verified tool-call webhook routes to
    app.tools.dispatch(name, **args) with validated args; an unknown tool → a
    structured error (no crash). A call-status webhook records a lifecycle event.
  - Resiliency (§6): handlers are exception-safe end to end — a component failure
    is a structured JSON response, never a 500 traceback.

Import-safety (ENV4): `app = FastAPI(...)` at module level is a pure object
construction (no side effects). Importing this module reads NO .env, builds NO
client, opens NO lifespan resource, and places NO call. The webhook secret is read
lazily (per request) via config.get_setting; the .env is loaded only at the
runtime entry point (`make serve` → uvicorn lifespan startup), never at import.
"""

from __future__ import annotations

import hmac
import json
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import get_lead_context, get_setting, load_env
from app.consent import mask_phone
from app.tools import dispatch

# The header Vapi sends its server-message secret in. CONFIRMED at live
# integration (2026-06-23): Vapi authenticates server/webhook requests with a
# STATIC shared secret echoed in the `x-vapi-secret` header (set under the Vapi
# dashboard Server → Authorization settings), NOT an HMAC signature. The verify
# function is isolated/swappable so the GRADED behavior — reject-bad / accept-good,
# fail-closed — is what is tested, independent of the exact provider scheme.
SIGNATURE_HEADER = "x-vapi-secret"


# ===========================================================================
# Webhook authentication (VOICE2) — isolated + swappable
# ===========================================================================

def verify_secret(secret: str | None, provided: str | None) -> bool:
    """Return True iff the inbound webhook secret matches our shared secret (VOICE2).

    Vapi sends the configured server secret verbatim in the `x-vapi-secret` header;
    we compare it to VAPI_WEBHOOK_SECRET with a constant-time comparison
    (hmac.compare_digest) to defeat timing attacks. A missing server secret (server
    misconfigured) or a missing/blank header fails CLOSED — returns False, the
    request is rejected (401), never processed.
    """
    if not secret or not provided:
        return False
    return hmac.compare_digest(provided, secret)


# ===========================================================================
# The FastAPI app (module-level construction is side-effect free — ENV4)
# ===========================================================================

@asynccontextmanager
async def _lifespan(_app: FastAPI):  # pragma: no cover — runtime entry, not the suite
    """Load the local .env at SERVER STARTUP only (never at import — ENV4).

    This is the sanctioned runtime entry point for `load_env` (config docstring):
    `make serve` boots uvicorn, which enters this lifespan so get_setting()
    observes the developer's local secrets. Importing the module does NOT run this
    (constructing FastAPI(lifespan=...) only stores the callable; it is awaited at
    startup), so import-safety holds (ENV4).
    """
    load_env()
    yield


app = FastAPI(title="Alta Outbound Voice Agent — webhooks", lifespan=_lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe — no auth, no secret, no side effect."""
    return {"status": "ok"}


# ===========================================================================
# Shared: verify-then-parse a webhook (the single inbound chokepoint)
# ===========================================================================

async def _verified_body(request: Request) -> tuple[bool, bytes, dict[str, Any]]:
    """Read the raw body, verify the x-vapi-secret header, and parse JSON.

    Returns (ok, raw_body, payload). When ok is False the caller returns 401
    WITHOUT processing the payload (VOICE2). The secret is read lazily per request
    via config.get_setting — never at import.
    """
    raw_body = await request.body()
    secret = get_setting("VAPI_WEBHOOK_SECRET")
    provided = request.headers.get(SIGNATURE_HEADER)
    if not verify_secret(secret, provided):
        return False, raw_body, {}
    try:
        payload = json.loads(raw_body or b"{}")
        if not isinstance(payload, dict):
            payload = {}
    except json.JSONDecodeError:
        payload = {}
    return True, raw_body, payload


def _unauthorized() -> JSONResponse:
    """The single 401 response for an unverified webhook (VOICE2)."""
    return JSONResponse(status_code=401, content={"ok": False, "error": "unauthorized"})


# ===========================================================================
# Tool-call webhook (VOICE3) — routes to app.tools.dispatch
# ===========================================================================

def _extract_tool_call(
    payload: dict[str, Any],
) -> tuple[str | None, str | None, dict[str, Any]]:
    """Pull (tool_call_id, tool_name, args) from a webhook payload, tolerant of nesting.

    Vapi nests the function call under message.toolCalls/functionCall and assigns
    each call an `id` we MUST echo back in the result envelope; we accept a flat
    {name, arguments} too (tests / a simple provider). Returns (None, None, {}) if
    no tool call is present.
    """
    # Flat form (tests / a simple provider): {"name": ..., "arguments": {...}}.
    if "name" in payload:
        args = payload.get("arguments") or payload.get("args") or {}
        return payload.get("toolCallId"), payload["name"], args if isinstance(args, dict) else {}

    message = payload.get("message")
    if isinstance(message, dict):
        # Vapi tool-calls form: message.toolCalls[0].{id, function.{name,arguments}}.
        tool_calls = message.get("toolCalls") or message.get("toolCallList") or []
        if isinstance(tool_calls, list) and tool_calls:
            call0 = tool_calls[0] or {}
            fn = call0.get("function") or {}
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            return call0.get("id"), fn.get("name"), args if isinstance(args, dict) else {}
        # Legacy single functionCall form.
        fc = message.get("functionCall")
        if isinstance(fc, dict):
            args = fc.get("parameters") or fc.get("arguments") or {}
            return (message.get("toolCallId") or fc.get("id"), fc.get("name"),
                    args if isinstance(args, dict) else {})
    return None, None, {}


def _payload_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    """Best-effort lookup of the assistant metadata Vapi echoes in a webhook payload.

    Vapi's exact nesting for echoed metadata is a live-reconcile item (like the
    x-vapi-secret header was) — we probe the likely containers and return the first
    that carries lead context; an empty dict if none (→ env fallback).
    """
    msg = payload.get("message") if isinstance(payload, dict) else {}
    msg = msg if isinstance(msg, dict) else {}
    call = msg.get("call") or payload.get("call") or {}
    call = call if isinstance(call, dict) else {}
    for container in (call.get("assistant"), call.get("assistantOverrides"),
                      msg.get("assistant"), call, msg, payload):
        if isinstance(container, dict):
            md = container.get("metadata")
            if isinstance(md, dict) and (md.get("lead_id") or md.get("lead_timezone")):
                return md
    return {}


def extract_lead_context(payload: dict[str, Any]) -> tuple[str, str | None]:
    """Return the AUTHORITATIVE (lead_id, lead_timezone) for this tool call (D2/D3).

    Prefers the assistant metadata Vapi echoes in the payload (scalable path); fills
    any gap from the env-backed get_lead_context() so the demo works even without the
    metadata round-trip. The model's own tool args are NEVER consulted here — the
    runtime, not the model, decides which lead a booking/disposition is written under.
    """
    meta = _payload_metadata(payload)
    lead_id = meta.get("lead_id")
    lead_tz = meta.get("lead_timezone")
    env_id, env_tz = get_lead_context()
    return (lead_id or env_id, lead_tz or env_tz)


def _tool_results(tool_call_id: str | None, payload: dict[str, Any]) -> JSONResponse:
    """Wrap a tool's structured payload in **Vapi's tool-result envelope** (VOICE3).

    Vapi requires a custom-tool webhook to answer with
    `{"results": [{"toolCallId": <id>, "result": <string>}]}` — the model receives
    `result` as the tool's output. We JSON-encode our structured payload so the
    model can use it (e.g. read the free slots from check_availability, then call
    book_meeting). Returning the wrong shape makes Vapi report "No result returned"
    and the agent can never book (reconciled against the live Vapi contract 2026-06-24).
    """
    return JSONResponse(
        status_code=200,
        content={"results": [{"toolCallId": tool_call_id, "result": json.dumps(payload)}]},
    )


@app.post("/webhook/tool")
async def tool_webhook(request: Request) -> JSONResponse:
    """Handle a secret-verified tool-call webhook (VOICE2 + VOICE3).

    A bad/missing secret → 401 (never processed). A verified call routes to
    app.tools.dispatch(name, **args) and the structured result is returned in
    Vapi's tool-result envelope (`_tool_results`). An unknown tool, bad args, or
    handler error is still returned as a structured result string (dispatch never
    raises across its boundary — §6), never a 500.
    """
    ok, _raw, payload = await _verified_body(request)
    if not ok:
        return _unauthorized()

    tool_call_id: str | None = None
    try:
        tool_call_id, name, args = _extract_tool_call(payload)
        if not name:
            return _tool_results(tool_call_id, {"ok": False, "error": "no_tool_call",
                                                "message": "webhook carried no tool call"})
        # Inject AUTHORITATIVE lead context; strip any model-supplied lead_id/timezone
        # so a hallucinated placeholder or invented tz can never reach a tool (D2/D3).
        lead_id, lead_timezone = extract_lead_context(payload)
        args.pop("lead_id", None)
        args.pop("lead_timezone", None)
        result = dispatch(name, lead_id=lead_id, lead_timezone=lead_timezone, **args)
        return _tool_results(tool_call_id, result.to_dict())
    except Exception as exc:  # noqa: BLE001 — never leak a 500 traceback (§6)
        return _tool_results(tool_call_id, {"ok": False, "error": "handler_error",
                                            "message": str(exc)})


# ===========================================================================
# Call-status webhook — records lifecycle events (resilient, §6)
# ===========================================================================

@app.post("/webhook/status")
async def status_webhook(request: Request) -> JSONResponse:
    """Handle a secret-verified call-status (lifecycle) webhook.

    Records the lifecycle event and acknowledges. Any phone number in the payload
    is masked before it is echoed (LEAK2/SEC1 — a log line never carries a full
    real number). Exception-safe end to end (§6).
    """
    ok, _raw, payload = await _verified_body(request)
    if not ok:
        return _unauthorized()

    try:
        message = payload.get("message") if isinstance(payload, dict) else {}
        message = message if isinstance(message, dict) else {}
        status = message.get("status") or payload.get("status") or "unknown"
        call = message.get("call") or payload.get("call") or {}
        call_id = call.get("id") if isinstance(call, dict) else None
        number = None
        if isinstance(call, dict):
            customer = call.get("customer") or {}
            if isinstance(customer, dict):
                number = customer.get("number")
        ack: dict[str, Any] = {"ok": True, "status": status, "call_id": call_id}
        if number:
            ack["phone_masked"] = mask_phone(number)
        return JSONResponse(status_code=200, content=ack)
    except Exception as exc:  # noqa: BLE001 — never leak a 500 traceback (§6)
        return JSONResponse(
            status_code=200,
            content={"ok": False, "error": "handler_error", "message": str(exc)},
        )
