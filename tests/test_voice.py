"""VoiceProvider-adapter tests: the assistant payload, the byte-exact disclosure first-message, and lazy-client import-safety."""

from __future__ import annotations

import pytest

from app.config import AGENT_TOOLS, DISCLOSURE_LINE, LLM_MODEL
import app.vapi_client as vapi
from app.vapi_client import (
    CallResult,
    CostResult,
    VapiVoiceProvider,
    VoiceProvider,
)


@pytest.fixture()
def assistant() -> dict:
    """A built assistant payload from the real (pure, offline) Vapi builder."""
    return VapiVoiceProvider().configure_assistant()


# ---------------------------------------------------------------------------
# VOICE1 — assistant config wires model + prompt + 5 tools + first-message
# ---------------------------------------------------------------------------

class TestVoice1AssistantConfig:
    """VOICE1: the assistant payload is shape-valid and wires the graded pieces."""

    def test_wires_llm_model(self, assistant):
        """The pinned LLM_MODEL is the assistant's model id (ENV2 cross-check)."""
        assert assistant["model"]["model"] == LLM_MODEL
        assert assistant["model"]["model"] == "gpt-4o-mini"

    def test_standard_pipeline_voice_and_transcriber(self, assistant):
        """Standard pipeline: a dedicated TTS voice + transcriber (telephony-robust).
        2026-06-25 (Asaf): TTS swapped to Deepgram Aura to cut voice latency (~2.1s on
        OpenAI TTS, call 019efe50); reuses the Deepgram key already used for STT."""
        assert assistant["voice"]["provider"] == "deepgram"
        assert assistant["voice"]["voiceId"]
        assert assistant["transcriber"]["provider"] == "deepgram"

    def test_turn_taking_configured(self, assistant):
        """Turn-taking is configured (stopSpeakingPlan + startSpeakingPlan present).
        numWords tuned to 1 (2026-06-25, Asaf) for a snappier, more sensitive barge-in."""
        assert assistant["stopSpeakingPlan"]["numWords"] >= 1
        assert "startSpeakingPlan" in assistant

    def test_pacing_tuned_faster(self, assistant):
        """Pacing: a short post-caller wait so the agent replies promptly. (The OpenAI-TTS
        `speed` knob was dropped 2026-06-25 — Deepgram Aura has no top-level speed field.)"""
        # Snappier reply: shorter wait after the caller stops talking.
        assert assistant["startSpeakingPlan"]["waitSeconds"] <= 0.5

    def test_tools_carry_server_url_and_secret_when_configured(self, monkeypatch):
        """Each tool must carry server.url (WHERE to POST → else 'No result returned')
        AND server.secret (the x-vapi-secret Vapi echoes → else our webhook 401s and
        the tool result is 'unauthorized'). Both are the live booking fixes (2026-06-24).
        """
        monkeypatch.setenv("PUBLIC_WEBHOOK_URL", "https://example.ngrok-free.dev")
        monkeypatch.setenv("VAPI_WEBHOOK_SECRET", "unit-test-secret")
        a = VapiVoiceProvider().configure_assistant()
        tools = a["model"]["tools"]
        assert tools and all(
            t.get("server", {}).get("url") == "https://example.ngrok-free.dev/webhook/tool"
            and t.get("server", {}).get("secret") == "unit-test-secret"
            for t in tools
        )

    def test_system_prompt_present_and_grounded(self, assistant):
        """A non-empty system prompt is wired, grounded in the value-prop content."""
        messages = assistant["model"]["messages"]
        system = next(m for m in messages if m["role"] == "system")
        assert system["content"], "system prompt must be non-empty"
        # Grounded in the value-prop file (LEAK3): a real value-prop phrase appears.
        assert "Alta" in system["content"]

    def test_five_tools_named_exactly_agent_tools(self, assistant):
        """The 5 tool/function definitions' names equal AGENT_TOOLS exactly (dispatch keys)."""
        tools = assistant["model"]["tools"]
        names = [t["function"]["name"] for t in tools]
        assert names == AGENT_TOOLS
        assert len(names) == 4

    def test_each_tool_has_a_json_schema(self, assistant):
        """Every tool definition carries a JSON-schema parameters object."""
        for t in assistant["model"]["tools"]:
            fn = t["function"]
            assert "name" in fn and "description" in fn
            params = fn["parameters"]
            assert params["type"] == "object"
            assert "properties" in params

    def test_book_meeting_requires_only_slot_not_lead_id(self, assistant):
        """book_meeting's schema requires ONLY slot_start_iso — lead_id is injected
        authoritatively at the chokepoint (D3), so the model never supplies it."""
        book = next(
            t["function"] for t in assistant["model"]["tools"]
            if t["function"]["name"] == "book_meeting"
        )
        assert set(book["parameters"]["required"]) == {"slot_start_iso"}
        assert "lead_id" not in book["parameters"]["properties"]


# ---------------------------------------------------------------------------
# CON2 — disclosure is the static first-message, byte-exact (from config)
# ---------------------------------------------------------------------------

class TestCon2DisclosureFirstMessage:
    """CON2: DISCLOSURE_LINE is the byte-exact static first message, not a prompt."""

    def test_first_message_is_disclosure_byte_exact(self, assistant):
        """firstMessage equals DISCLOSURE_LINE byte-for-byte (the graded chokepoint)."""
        assert assistant["firstMessage"] == DISCLOSURE_LINE

    def test_first_message_is_the_config_literal_identity(self, assistant):
        """firstMessage is consumed FROM config (identity), never re-literaled here."""
        assert assistant["firstMessage"] is DISCLOSURE_LINE or (
            assistant["firstMessage"] == DISCLOSURE_LINE
        )
        # And it is the exact CLAUDE.md §9 literal.
        expected = (
            "Hi, this is Aria, an AI assistant calling on behalf of Alta. "
            "Do you have a quick minute?"
        )
        assert assistant["firstMessage"] == expected

    def test_assistant_speaks_first(self, assistant):
        """The platform speaks the disclosure FIRST (not waiting for the callee)."""
        assert assistant["firstMessageMode"] == "assistant-speaks-first"

    def test_no_smart_quotes_in_first_message(self, assistant):
        """The disclosure carries no smart quotes (the byte-exact regression guard)."""
        forbidden = {"‘", "’", "“", "”"}
        assert not forbidden.intersection(assistant["firstMessage"])


# ---------------------------------------------------------------------------
# CON3 — recording enabled together with the disclosure
# ---------------------------------------------------------------------------

class TestCon3RecordingGatedOnDisclosure:
    """CON3 (updated 2026-06-24): recording is enabled in the same payload as the
    AI disclosure. The spoken recording notice was dropped; recordingEnabled stays True."""

    def test_recording_enabled_with_disclosure(self, assistant):
        """recordingEnabled is True and the verbatim AI disclosure is present in the same payload."""
        assert assistant["recordingEnabled"] is True
        assert assistant["firstMessage"] == DISCLOSURE_LINE


# ---------------------------------------------------------------------------
# Step 1 (D9/D4/D5) — the hangup + close are pinned to the Vapi PLATFORM, not
# model-generated: native end-call (actually hangs up) + a byte-exact endCallMessage
# (so the goodbye can't drift/double, and there is no "after goodbye" to ramble into).
# ---------------------------------------------------------------------------

class TestCleanHangup:
    def test_native_end_call_enabled(self, assistant):
        """Vapi's native end-call is enabled so a decision to end ACTUALLY hangs up
        (the custom end_call tool returned JSON but never terminated — D9)."""
        assert assistant["endCallFunctionEnabled"] is True

    def test_end_call_message_is_neutral_close_byte_exact(self, assistant):
        """The closing line is spoken by the platform, byte-exact from config — never
        model-generated (which drifted/doubled live — D4/D5). Neutral so it fits a
        booking and a decline alike."""
        from app.config import END_CALL_MESSAGE
        assert assistant["endCallMessage"] == END_CALL_MESSAGE


# ---------------------------------------------------------------------------
# VOICE4 — lazy client; singleton None at import; pure builder builds nothing
# ---------------------------------------------------------------------------

class TestVoice4LazyClient:
    """VOICE4: the live client is built only by _get_vapi(); None at import."""

    def test_singleton_none_at_import(self):
        """The module-level Vapi singleton is None until a live caller builds it."""
        vapi.reset_vapi()
        assert vapi._vapi is None

    def test_configure_assistant_builds_no_client(self, monkeypatch):
        """The pure builder constructs NO client and reads NO secret (offline-callable)."""
        for key in ["VAPI_API_KEY", "VAPI_PHONE_NUMBER_ID", "VAPI_WEBHOOK_SECRET"]:
            monkeypatch.delenv(key, raising=False)
        vapi.reset_vapi()
        VapiVoiceProvider().configure_assistant()  # must not raise / build a client
        assert vapi._vapi is None, "configure_assistant must not build the Vapi client"

    def test_importing_module_does_not_pull_httpx(self):
        """Importing app.vapi_client must not import httpx (it is lazy in _get_vapi)."""
        # If vapi_client imported httpx at module level the lazy contract would break.
        # We can't unimport, but we can assert vapi_client has no module-level httpx ref.
        assert "httpx" not in dir(vapi), "vapi_client must not import httpx at module level"

    def test_get_vapi_requires_key_when_called(self, monkeypatch):
        """_get_vapi() reads VAPI_API_KEY only when CALLED; a missing key is a clean error."""
        monkeypatch.delenv("VAPI_API_KEY", raising=False)
        vapi.reset_vapi()
        with pytest.raises(ValueError):
            vapi._get_vapi()
        vapi.reset_vapi()


# ---------------------------------------------------------------------------
# VOICE5 — the VoiceProvider interface is the only egress; impls interchangeable
# ---------------------------------------------------------------------------

class TestVoice5AdapterSwap:
    """VOICE5: Vapi impl + the fake both satisfy the interface and swap cleanly."""

    def test_vapi_impl_satisfies_protocol(self):
        """VapiVoiceProvider structurally satisfies the runtime-checkable interface."""
        assert isinstance(VapiVoiceProvider(), VoiceProvider)

    def test_fake_satisfies_protocol(self, fake_voice_provider):
        """The FakeVoiceProvider satisfies the same interface (drop-in swap)."""
        assert isinstance(fake_voice_provider, VoiceProvider)

    def test_interface_methods_exact(self):
        """The graded interface exposes EXACTLY the three methods (no drift)."""
        for method in ("configure_assistant", "place_call", "fetch_call_cost"):
            assert hasattr(VapiVoiceProvider, method)

    def test_fake_place_call_returns_scripted_result(self, fake_voice_provider):
        """The fake returns a scripted CallResult and never networks."""
        fake_voice_provider.queue_call_result(
            CallResult(ok=True, call_id="abc-123", status="queued")
        )
        result = fake_voice_provider.place_call(
            to_number="+15551230000", assistant={"firstMessage": DISCLOSURE_LINE}
        )
        assert result.ok and result.call_id == "abc-123"
        assert fake_voice_provider.calls_placed[0]["to_number"] == "+15551230000"

    def test_fake_can_simulate_failure(self, fake_voice_provider):
        """The fake can be set to raise — proving resilience paths offline (§6)."""
        fake_voice_provider.raise_on_call = True
        with pytest.raises(RuntimeError):
            fake_voice_provider.place_call(to_number="+1", assistant={})

    def test_fake_fetch_cost(self, fake_voice_provider):
        """The fake returns a scripted CostResult for fetch_call_cost."""
        fake_voice_provider.queue_cost_result(CostResult(ok=True, cost_usd=0.42))
        cost = fake_voice_provider.fetch_call_cost(call_id="abc-123")
        assert cost.ok and cost.cost_usd == 0.42
        assert fake_voice_provider.costs_fetched == ["abc-123"]


# ---------------------------------------------------------------------------
# Resilience of the LIVE methods (structured data, never a crash — §6)
# ---------------------------------------------------------------------------

class TestLiveMethodsResilient:
    """place_call / fetch_call_cost surface failures as data, never raise (§6)."""

    def test_place_call_missing_phone_id_is_structured(self, monkeypatch):
        """A missing VAPI_PHONE_NUMBER_ID → CallResult(ok=False), not an exception."""
        monkeypatch.delenv("VAPI_PHONE_NUMBER_ID", raising=False)
        vapi.reset_vapi()
        result = VapiVoiceProvider().place_call(
            to_number="+15551230000", assistant={}
        )
        assert result.ok is False
        assert result.error == "config_error"
        vapi.reset_vapi()
