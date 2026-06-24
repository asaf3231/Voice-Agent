"""Stage 4 — FastAPI webhook server tests (VOICE2, VOICE3, import-safety).

VOICE2 — an inbound webhook with a bad/missing VAPI_WEBHOOK_SECRET signature is
         rejected (401), never processed; a valid one is processed.
VOICE3 — a verified tool-call webhook routes to the right AGENT_TOOLS function with
         validated args; an unknown tool → a structured error, no crash.
Import-safety — importing app.server has zero side effects (no .env read, no client).

Fully OFFLINE — TestClient + a locally-computed valid/invalid signature. No network,
no real Vapi/OpenAI client, no call.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import app.server as server
from app.server import app, verify_secret

WEBHOOK_SECRET = "test-webhook-secret-abc123"


@pytest.fixture()
def client(monkeypatch) -> TestClient:
    """A TestClient with VAPI_WEBHOOK_SECRET set in the environment."""
    monkeypatch.setenv("VAPI_WEBHOOK_SECRET", WEBHOOK_SECRET)
    return TestClient(app)


def _post_signed(client: TestClient, path: str, payload: dict, *, secret: str):
    """POST *payload* to *path* with the x-vapi-secret header set to *secret*."""
    raw = json.dumps(payload).encode("utf-8")
    return client.post(
        path,
        content=raw,
        headers={"x-vapi-secret": secret, "content-type": "application/json"},
    )


# ---------------------------------------------------------------------------
# verify_secret unit (the isolated, swappable webhook-auth fn)
# ---------------------------------------------------------------------------

class TestVerifySecretUnit:
    """The webhook-secret verifier: reject-bad / accept-good, fails closed."""

    def test_matching_secret_accepts(self):
        assert verify_secret(WEBHOOK_SECRET, WEBHOOK_SECRET) is True

    def test_wrong_secret_rejects(self):
        assert verify_secret(WEBHOOK_SECRET, "the-wrong-secret") is False

    def test_missing_header_rejects(self):
        assert verify_secret(WEBHOOK_SECRET, None) is False

    def test_blank_header_rejects(self):
        assert verify_secret(WEBHOOK_SECRET, "") is False

    def test_missing_server_secret_fails_closed(self):
        """A missing server secret fails CLOSED (never silently accepts)."""
        assert verify_secret(None, WEBHOOK_SECRET) is False

    def test_near_miss_secret_rejected(self):
        """A near-miss secret (differs by one char) is rejected (constant-time compare)."""
        assert verify_secret(WEBHOOK_SECRET, WEBHOOK_SECRET[:-1] + "X") is False


# ---------------------------------------------------------------------------
# VOICE2 — webhook signature verification end-to-end
# ---------------------------------------------------------------------------

class TestVoice2WebhookSecret:
    """VOICE2: bad/missing x-vapi-secret → 401; correct → processed."""

    def test_missing_secret_header_401(self, client):
        """No x-vapi-secret header → 401, never processed."""
        resp = client.post("/webhook/tool", json={"name": "end_call"})
        assert resp.status_code == 401

    def test_wrong_secret_header_401(self, client):
        """A wrong x-vapi-secret value → 401, never processed."""
        raw = json.dumps({"name": "end_call"}).encode("utf-8")
        resp = client.post(
            "/webhook/tool",
            content=raw,
            headers={"x-vapi-secret": "not-the-real-secret"},
        )
        assert resp.status_code == 401

    def test_correct_secret_processed(self, client):
        """A correctly authenticated tool webhook is processed (200, structured result)."""
        resp = _post_signed(
            client, "/webhook/tool", {"name": "end_call", "arguments": {}},
            secret=WEBHOOK_SECRET,
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_wrong_secret_value_401(self, client):
        """A request carrying the WRONG secret → 401."""
        resp = _post_signed(
            client, "/webhook/tool", {"name": "end_call"},
            secret="the-wrong-secret",
        )
        assert resp.status_code == 401

    def test_no_secret_configured_rejects(self, monkeypatch):
        """With no VAPI_WEBHOOK_SECRET set, even a 'correct' header is rejected (fails closed)."""
        monkeypatch.delenv("VAPI_WEBHOOK_SECRET", raising=False)
        local = TestClient(app)
        resp = _post_signed(
            local, "/webhook/tool", {"name": "end_call"}, secret=WEBHOOK_SECRET
        )
        assert resp.status_code == 401

    def test_status_webhook_also_verifies(self, client):
        """The status webhook enforces the same secret gate (401 on missing)."""
        resp = client.post("/webhook/status", json={"status": "ended"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# VOICE3 — tool dispatch
# ---------------------------------------------------------------------------

class TestVoice3ToolDispatch:
    """VOICE3: a verified tool webhook routes to the right tool; unknown → structured error."""

    def test_end_call_dispatches(self, client):
        """end_call routes to app.tools.end_call and returns its structured result."""
        resp = _post_signed(
            client, "/webhook/tool",
            {"name": "end_call", "arguments": {"reason": "completed"}},
            secret=WEBHOOK_SECRET,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["data"]["ended"] is True
        assert body["data"]["reason"] == "completed"

    def test_detect_voicemail_dispatches_with_args(self, client):
        """detect_voicemail routes with validated args and classifies the transcript."""
        resp = _post_signed(
            client, "/webhook/tool",
            {"name": "detect_voicemail",
             "arguments": {"transcript": "Please leave a message after the tone."}},
            secret=WEBHOOK_SECRET,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["data"]["is_voicemail"] is True

    def test_log_disposition_masks_phone(self, client):
        """log_disposition via the webhook masks the phone number (LEAK2 cross-check)."""
        resp = _post_signed(
            client, "/webhook/tool",
            {"name": "log_disposition",
             "arguments": {"lead_id": "lead-1", "disposition": "booked",
                           "phone_e164": "+15551234567"}},
            secret=WEBHOOK_SECRET,
        )
        body = resp.json()
        assert body["ok"] is True
        # The full number must NOT appear; only the masked form.
        assert "+15551234567" not in json.dumps(body)
        assert body["data"]["phone_masked"].endswith("67")

    def test_unknown_tool_structured_error_no_crash(self, client):
        """An unknown tool → a structured error, HTTP 200, no crash/traceback."""
        resp = _post_signed(
            client, "/webhook/tool", {"name": "definitely_not_a_tool"},
            secret=WEBHOOK_SECRET,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert body["error"] == "unknown_tool"

    def test_bad_args_for_known_tool_structured_error(self, client):
        """Bad/extra args for a known tool → structured invalid_input, not a 500."""
        resp = _post_signed(
            client, "/webhook/tool",
            {"name": "end_call", "arguments": {"bogus_param": True}},
            secret=WEBHOOK_SECRET,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert body["error"] == "invalid_input"

    def test_vapi_nested_tool_call_form(self, client):
        """The Vapi message.toolCalls[].function form routes the same as the flat form."""
        payload = {
            "message": {
                "toolCalls": [
                    {"function": {"name": "end_call",
                                  "arguments": {"reason": "vapi-nested"}}}
                ]
            }
        }
        resp = _post_signed(client, "/webhook/tool", payload, secret=WEBHOOK_SECRET)
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["data"]["reason"] == "vapi-nested"

    def test_no_tool_call_in_payload_structured(self, client):
        """A verified payload with no tool call → a structured 'no_tool_call', no crash."""
        resp = _post_signed(client, "/webhook/tool", {"message": {}},
                            secret=WEBHOOK_SECRET)
        assert resp.status_code == 200
        assert resp.json()["error"] == "no_tool_call"


# ---------------------------------------------------------------------------
# Finding #1 regression — the booking tools must actually book over the webhook
# (the core deliverable). The webhook passes ONLY the model's args; dispatch
# injects the calendar via _get_calendar(), here monkeypatched to a MockCalendar
# so the full HTTP → verify → dispatch → tool path runs offline. Before the fix
# these returned invalid_input and no meeting could ever be booked over the wire.
# ---------------------------------------------------------------------------

class TestVoice3BookingOverWebhook:
    """check_availability + book_meeting work end-to-end over the signed webhook."""

    def test_check_availability_over_webhook(self, client, monkeypatch):
        import app.tools as tools
        from app.calendar_client import MockCalendar

        monkeypatch.setattr(tools, "_get_calendar", lambda: MockCalendar())
        resp = _post_signed(
            client, "/webhook/tool",
            {"name": "check_availability",
             "arguments": {"lead_timezone": "America/New_York"}},
            secret=WEBHOOK_SECRET,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["data"]["count"] > 0

    def test_book_meeting_over_webhook_books_a_real_event(self, client, monkeypatch):
        import app.tools as tools
        from app.calendar_client import MockCalendar

        shared = MockCalendar()  # one calendar for both the lookup and the booking
        monkeypatch.setattr(tools, "_get_calendar", lambda: shared)

        avail = _post_signed(
            client, "/webhook/tool",
            {"name": "check_availability", "arguments": {}},
            secret=WEBHOOK_SECRET,
        ).json()
        iso = avail["data"]["slots"][0]["start_utc"]

        resp = _post_signed(
            client, "/webhook/tool",
            {"name": "book_meeting",
             "arguments": {"lead_id": "lead-001", "slot_start_iso": iso}},
            secret=WEBHOOK_SECRET,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True, f"booking failed over the webhook: {body}"
        assert body["data"]["event_id"]


# ---------------------------------------------------------------------------
# Call-status webhook — resilient + masks phones
# ---------------------------------------------------------------------------

class TestStatusWebhook:
    """The status webhook records lifecycle events resiliently and masks phones."""

    def test_status_recorded(self, client):
        resp = _post_signed(
            client, "/webhook/status",
            {"message": {"status": "ended",
                         "call": {"id": "call-9", "customer": {"number": "+15551234567"}}}},
            secret=WEBHOOK_SECRET,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["status"] == "ended"
        assert body["call_id"] == "call-9"
        # Phone masked — the full number never echoed (LEAK2).
        assert "+15551234567" not in json.dumps(body)
        assert body["phone_masked"].endswith("67")


# ---------------------------------------------------------------------------
# Health + import-safety
# ---------------------------------------------------------------------------

class TestHealthAndImportSafety:
    """Health probe works; importing app.server has zero side effects."""

    def test_health_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_server_module_no_httpx_at_module_level(self):
        """Importing app.server must not import httpx at module level (lazy egress)."""
        assert "httpx" not in dir(server)
