"""Bug-2 fix — TDD for the `qualify` tool + the `pitch_tailored` rubric signal.

`qualify` turns "tailor the pitch to what they say" from an unobservable prompt
hope into an explicit, deterministic, logged, unit-testable routing decision
(CTO review 2026-06-24): given the prospect's discovery answer it returns which
grounded value-prop to emphasize, and flags vague/junk/empty answers so the agent
asks a clarifying question instead of plowing through the canned funnel.

These tests are written FIRST and fail on the current codebase (Red): `qualify`
and `pitch_tailored` do not yet exist, `"qualify"` is not in AGENT_TOOLS / the
tool schemas, and the system prompt never mentions it.

All `qualify` content stays grounded in value_prop.md (LEAK3): the emphasized
text is always one of the file's value-props, never invented here.
"""

from __future__ import annotations

import app.config as config
import app.tools as tools
import app.eval.rubric as rubric
from app.eval import Speaker, Stage, Turn
from app.persona import build_system_prompt
from app.vapi_client import VapiVoiceProvider


# Injected value-props (simplified copies of value_prop.md's items) so the pure
# qualify unit tests are deterministic and file-independent. They carry the same
# distinctive anchor words the real file uses, so routing resolves identically.
VALUE_PROPS = (
    "Instant scale - Alta can make hundreds of personalised outbound calls per day, "
    "running 24/7 without ramp time or sick days.",
    "Consistent messaging - every call follows your exact pitch and handles objections "
    "to your playbook.",
    "Human-quality conversations - agents sound natural, respond in real time, and adapt "
    "to the prospect's tone.",
    "Full compliance built in - every call opens with a clear AI disclosure and honours "
    "do-not-call lists.",
    "Easy integration - connects to your CRM and calendar in under a day, no IT lift.",
)


def _q(answer: str):
    """Call qualify with the injected value-props and return its data dict."""
    result = tools.qualify(answer=answer, value_props=VALUE_PROPS)
    assert result.ok is True
    return result.to_dict()["data"]


# ---------------------------------------------------------------------------
# A. Routing — a real answer selects the matching grounded value-prop
# ---------------------------------------------------------------------------

class TestQualifyRouting:
    def test_scale_pain_routes_to_instant_scale(self):
        d = _q("we do everything manually and can't keep up with the volume")
        assert d["answer_quality"] == "substantive"
        assert "scale" in d["matched_themes"]
        assert d["needs_clarification"] is False
        assert "scale" in d["emphasize"].lower()

    def test_bare_manually_is_substantive_scale(self):
        # The exact word that got the canned pitch on the live call — now it routes.
        d = _q("Manually")
        assert d["answer_quality"] == "substantive"
        assert "scale" in d["matched_themes"]
        assert d["emphasize"] is not None

    def test_consistency_pain_routes_to_messaging(self):
        d = _q("our messaging is all over the place, reps go off script")
        assert "consistency" in d["matched_themes"]
        assert "messaging" in d["emphasize"].lower() or "consistent" in d["emphasize"].lower()

    def test_quality_pain_routes_to_human_quality(self):
        d = _q("the other tools just sound like a robocall, not natural")
        assert "quality" in d["matched_themes"]
        assert "natural" in d["emphasize"].lower()

    def test_compliance_pain_routes_to_compliance(self):
        d = _q("we're really worried about DNC and compliance")
        assert "compliance" in d["matched_themes"]
        assert "compliance" in d["emphasize"].lower()

    def test_integration_pain_routes_to_integration(self):
        d = _q("everything has to work with our Salesforce CRM integration")
        assert "integration" in d["matched_themes"]
        assert "integration" in d["emphasize"].lower() or "crm" in d["emphasize"].lower()

    def test_multiple_themes_picks_a_primary(self):
        d = _q("we can't scale our manual outreach and it must fit our CRM integration")
        assert {"scale", "integration"} <= set(d["matched_themes"])
        # Exactly one value-prop is emphasized (the primary), and it's grounded.
        assert d["emphasize"] in VALUE_PROPS


# ---------------------------------------------------------------------------
# B. Edge cases — vague / junk / empty answers must trigger a clarifying step
# ---------------------------------------------------------------------------

class TestQualifyNonAnswers:
    def test_vague_answer_needs_clarification(self):
        d = _q("I don't know, not sure really")
        assert d["answer_quality"] == "vague"
        assert d["needs_clarification"] is True
        assert d["emphasize"] is None

    def test_junk_answer_needs_clarification(self):
        d = _q("purple monkey dishwasher")
        assert d["answer_quality"] == "vague"
        assert d["needs_clarification"] is True
        assert d["emphasize"] is None

    def test_gibberish_answer_needs_clarification(self):
        d = _q("asdfgh qwerty")
        assert d["needs_clarification"] is True
        assert d["emphasize"] is None

    def test_empty_answer_is_empty_quality(self):
        for blank in ("", "   ", "\n\t"):
            d = _q(blank)
            assert d["answer_quality"] == "empty"
            assert d["needs_clarification"] is True
            assert d["emphasize"] is None

    def test_clarifying_guidance_is_present_for_non_answers(self):
        d = _q("not sure")
        assert d["guidance"] and len(d["guidance"]) > 0


# ---------------------------------------------------------------------------
# C. Robustness + grounding
# ---------------------------------------------------------------------------

class TestQualifyRobustness:
    def test_case_insensitive(self):
        assert _q("MANUALLY, WE CAN'T SCALE")["answer_quality"] == "substantive"

    def test_emphasis_is_always_grounded_never_invented(self):
        d = _q("we can't scale the manual volume")
        assert d["emphasize"] in VALUE_PROPS

    def test_loads_value_props_lazily_when_not_injected(self):
        # No value_props passed → qualify reads the real value_prop.md at runtime.
        result = tools.qualify(answer="we do it all manually")
        assert result.ok is True
        data = result.to_dict()["data"]
        assert data["answer_quality"] == "substantive"
        assert data["emphasize"] is not None

    def test_returns_serializable_toolresult(self):
        result = tools.qualify(answer="manually", value_props=VALUE_PROPS)
        d = result.to_dict()
        assert d["ok"] is True
        assert set(d["data"]) >= {
            "answer_quality", "matched_themes", "emphasize",
            "needs_clarification", "guidance",
        }


# ---------------------------------------------------------------------------
# D. qualify is an INTERNAL oracle, NOT a live tool (dropped 2026-06-24 — latency)
# ---------------------------------------------------------------------------

class TestQualifyIsInternalOracle:
    def test_qualify_not_in_agent_tools(self):
        assert "qualify" not in config.AGENT_TOOLS

    def test_qualify_not_in_dispatch_registry(self):
        assert "qualify" not in tools.TOOL_REGISTRY

    def test_qualify_not_dispatchable_as_a_live_tool(self):
        result = tools.dispatch("qualify", answer="we do it manually")
        assert result.ok is False
        assert result.error == "unknown_tool"

    def test_qualify_not_in_live_tool_schema(self):
        assistant = VapiVoiceProvider().configure_assistant(variant="A")
        names = [t["function"]["name"] for t in assistant["model"]["tools"]]
        assert "qualify" not in names

    def test_qualify_function_still_callable_directly(self):
        # It survives as the tailoring oracle for rubric.pitch_tailored.
        assert tools.qualify(answer="manually").ok is True


# ---------------------------------------------------------------------------
# E. System prompt does the tailoring INLINE (no qualify tool call)
# ---------------------------------------------------------------------------

class TestPromptTailorsInline:
    def test_prompt_does_not_expose_qualify_as_a_tool(self):
        assert "qualify" not in build_system_prompt(variant="A").lower()

    def test_prompt_instructs_leading_with_one_value_prop(self):
        prompt = build_system_prompt(variant="A").lower()
        assert "one value-prop" in prompt or "only the one value-prop" in prompt

    def test_prompt_forbids_pitching_on_a_non_answer(self):
        prompt = build_system_prompt(variant="A").lower()
        assert ("clarif" in prompt) or ("non-answer" in prompt) or ("do not pitch" in prompt)


# ---------------------------------------------------------------------------
# F. Rubric signal — pitch_tailored catches a pitch that ignores the pain
# ---------------------------------------------------------------------------

def _t(speaker: Speaker, text: str, stage: Stage | None = None) -> Turn:
    return Turn(speaker=speaker, text=text, stage=stage)


def _transcript_with_pitch(pitch_text: str) -> list[Turn]:
    """A minimal transcript where the prospect names a SCALE pain, then the agent
    delivers *pitch_text* as its PITCH turn."""
    return [
        _t(Speaker.AGENT, config.DISCLOSURE_LINE, Stage.OPENING),
        _t(Speaker.CALLEE, "yes"),
        _t(Speaker.AGENT, "How are you handling outbound today?", Stage.DISCOVERY),
        _t(Speaker.CALLEE, "we do it all manually and can't keep up with the volume"),
        _t(Speaker.AGENT, pitch_text, Stage.PITCH),
    ]


class TestPitchTailoredSignal:
    def test_tailored_pitch_scores_true(self):
        # Pitch addresses the SCALE pain the prospect raised.
        transcript = _transcript_with_pitch(
            "We give you instant scale — hundreds of calls a day without ramp time."
        )
        assert rubric.pitch_tailored(transcript) is True

    def test_untailored_pitch_scores_false(self):
        # Prospect raised a SCALE pain; agent pitches integration instead → not tailored.
        transcript = _transcript_with_pitch(
            "We connect to your CRM and calendar in under a day with no IT lift."
        )
        assert rubric.pitch_tailored(transcript) is False

    def test_no_pitch_is_vacuously_true(self):
        transcript = [
            _t(Speaker.AGENT, config.DISCLOSURE_LINE, Stage.OPENING),
            _t(Speaker.CALLEE, "yes"),
        ]
        assert rubric.pitch_tailored(transcript) is True
