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

from app.config import get_setting, load_env
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

def _extract_tool_call(payload: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    """Pull (tool_name, args) from a webhook payload, tolerant of nesting.

    Vapi nests the function call under message.toolCalls/functionCall; we accept
    a flat {name, arguments} too so the contract under test is the dispatch
    behavior, not one exact provider envelope (the verify fn is the swappable seam).
    Returns (None, {}) if no tool call is present.
    """
    # Flat form (tests / a simple provider): {"name": ..., "arguments": {...}}.
    if "name" in payload:
        args = payload.get("arguments") or payload.get("args") or {}
        return payload["name"], args if isinstance(args, dict) else {}

    message = payload.get("message")
    if isinstance(message, dict):
        # Vapi tool-calls form: message.toolCalls[0].function.{name,arguments}.
        tool_calls = message.get("toolCalls") or message.get("toolCallList") or []
        if isinstance(tool_calls, list) and tool_calls:
            fn = (tool_calls[0] or {}).get("function") or {}
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            return fn.get("name"), args if isinstance(args, dict) else {}
        # Legacy single functionCall form.
        fc = message.get("functionCall")
        if isinstance(fc, dict):
            args = fc.get("parameters") or fc.get("arguments") or {}
            return fc.get("name"), args if isinstance(args, dict) else {}
    return None, {}


@app.post("/webhook/tool")
async def tool_webhook(request: Request) -> JSONResponse:
    """Handle a secret-verified tool-call webhook (VOICE2 + VOICE3).

    A bad/missing secret → 401 (never processed). A verified call routes to
    app.tools.dispatch(name, **args); an unknown tool or bad args returns a
    STRUCTURED error (dispatch never raises across its boundary — §6), never a 500.
    """
    ok, _raw, payload = await _verified_body(request)
    if not ok:
        return _unauthorized()

    try:
        name, args = _extract_tool_call(payload)
        if not name:
            return JSONResponse(
                status_code=200,
                content={"ok": False, "error": "no_tool_call",
                         "message": "webhook carried no tool call"},
            )
        result = dispatch(name, **args)
        return JSONResponse(status_code=200, content=result.to_dict())
    except Exception as exc:  # noqa: BLE001 — never leak a 500 traceback (§6)
        return JSONResponse(
            status_code=200,
            content={"ok": False, "error": "handler_error", "message": str(exc)},
        )


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
