"""Conversation-design tests: the dialog state machine, the byte-exact literals, and disclosure-first."""

from __future__ import annotations

import pytest

from app.config import (
    DISCLOSURE_LINE,
    FAILSAFE_HANGUP_LINE,
    MAX_AGENT_TURNS,
)
from app.eval import Disposition, Persona, Speaker, Stage
from app.eval.bakeoff import PERSONA_MATRIX, VARIANTS, run_bakeoff, run_cells
from app.eval.rubric import (
    RubricResult,
    extract_value_prop_claims,
    score_transcript,
)
from app.eval.simulated_callee import SimulatedCallee
from app.persona import (
    DialogRunner,
    ValueProp,
    build_policy,
    load_value_prop,
    run_conversation,
)

ALL_VARIANTS = ("A", "B")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _agent_turns(transcript):
    return [t for t in transcript if t.speaker is Speaker.AGENT]


def _stages_seen(transcript):
    return [t.stage for t in transcript if t.speaker is Speaker.AGENT]


# ===========================================================================
# CONV1 — state machine advances through all stages
# ===========================================================================

@pytest.mark.parametrize("variant", ALL_VARIANTS)
def test_conv1_state_machine_advances_cooperative(variant):
    """A cooperative persona walks the policy's full happy path to a booking."""
    result = run_conversation(variant, Persona.COOPERATIVE)
    stages = _stages_seen(result.transcript)

    # The opening (disclosure) is always first.
    assert stages[0] is Stage.OPENING
    # The pitch, slot proposal, and close all appear, in order.
    assert Stage.PITCH in stages
    assert Stage.PROPOSE_SLOT in stages
    assert Stage.CLOSE in stages
    assert stages.index(Stage.PITCH) < stages.index(Stage.PROPOSE_SLOT)
    assert stages.index(Stage.PROPOSE_SLOT) < stages.index(Stage.CLOSE)
    assert result.disposition is Disposition.BOOKED


def test_conv1_variant_a_is_discovery_led():
    """Variant A asks a discovery question BEFORE pitching (its distinguishing order)."""
    result = run_conversation("A", Persona.COOPERATIVE)
    stages = _stages_seen(result.transcript)
    assert Stage.DISCOVERY in stages
    assert stages.index(Stage.DISCOVERY) < stages.index(Stage.PITCH)


def test_conv1_variant_b_is_value_first():
    """Variant B leads with the pitch (no discovery stage before it)."""
    result = run_conversation("B", Persona.COOPERATIVE)
    stages = _stages_seen(result.transcript)
    assert Stage.DISCOVERY not in stages
    assert stages.index(Stage.OPENING) < stages.index(Stage.PITCH)


# ===========================================================================
# CONV2 — value-prop pitched (from the file) before the slot proposal
# ===========================================================================

@pytest.mark.parametrize("variant", ALL_VARIANTS)
def test_conv2_pitch_before_proposal_is_grounded(variant):
    """The pitch echoes a grounded value-prop claim before the slot is proposed."""
    result = run_conversation(variant, Persona.COOPERATIVE)
    rubric = score_transcript(result.transcript)
    assert rubric.pitch_delivered is True


def test_conv2_pitch_text_comes_from_value_prop_file():
    """The agent's pitch text is grounded in data/value_prop.md (LEAK3)."""
    vp = load_value_prop()
    result = run_conversation("B", Persona.COOPERATIVE)
    pitch_turns = [
        t for t in result.transcript
        if t.speaker is Speaker.AGENT and t.stage is Stage.PITCH
    ]
    assert pitch_turns, "no pitch turn produced"
    # Every word of the pitch is drawn from a value-prop item (not invented).
    joined_props = " ".join(vp.value_props)
    assert pitch_turns[0].text and pitch_turns[0].text in joined_props


# ===========================================================================
# CONV3 — objection handled before honoring a hard no
# ===========================================================================

@pytest.mark.parametrize("variant", ALL_VARIANTS)
def test_conv3_objection_recovered_not_hung_up(variant):
    """Against an objecting persona the agent issues a scripted recovery first."""
    result = run_conversation(variant, Persona.OBJECTING)
    agent_objection_turns = [
        t for t in result.transcript
        if t.speaker is Speaker.AGENT and t.stage is Stage.OBJECTION
    ]
    # At least one scripted recovery happened — the agent did not hang up on the
    # first objection.
    assert agent_objection_turns, "agent did not produce any objection recovery"
    rubric = score_transcript(result.transcript)
    assert rubric.objection_handled is True


@pytest.mark.parametrize("variant", ALL_VARIANTS)
def test_conv3_hard_no_is_honored(variant):
    """After recovery, a final hard no ends the call in a clean DECLINED disposition."""
    result = run_conversation(variant, Persona.OBJECTING)
    assert result.disposition is Disposition.DECLINED
    # No booking is voiced when the prospect declines.
    assert not any(t.booked for t in result.transcript)


def test_conv3_recovery_text_is_grounded_in_value_prop():
    """The objection recovery is an approved talking point from the file (CONV4)."""
    vp = load_value_prop()
    result = run_conversation("A", Persona.OBJECTING)
    recoveries = [
        t.text for t in result.transcript
        if t.speaker is Speaker.AGENT and t.stage is Stage.OBJECTION
    ]
    approved = set(vp.objection_responses.values())
    for r in recoveries:
        assert r in approved, f"ungrounded objection recovery: {r!r}"


# ===========================================================================
# CONV4 — authoritative-content bound (no invented price/claim)
# ===========================================================================

@pytest.mark.parametrize("variant", ALL_VARIANTS)
def test_conv4_probing_persona_elicits_no_invented_claim(variant):
    """A probing persona cannot make the agent assert a fabricated price/ROI/customer."""
    result = run_conversation(variant, Persona.PROBING)
    rubric = score_transcript(result.transcript)
    # compliance_ok is False if any invented numeric claim was voiced.
    assert rubric.compliance_ok is True


@pytest.mark.parametrize("variant", ALL_VARIANTS)
def test_conv4_no_agent_turn_contains_a_dollar_or_percent_or_multiple(variant):
    """No agent utterance carries a $price, a %figure, or an Nx claim (ungrounded)."""
    import re

    money = re.compile(r"\$\s?\d")
    percent = re.compile(r"\d\s?%")
    multiple = re.compile(r"\d+\s?x\b", re.IGNORECASE)
    for persona in PERSONA_MATRIX:
        result = run_conversation(variant, persona)
        for t in _agent_turns(result.transcript):
            assert not money.search(t.text), f"invented price: {t.text!r}"
            assert not percent.search(t.text), f"invented percent: {t.text!r}"
            assert not multiple.search(t.text), f"invented multiple: {t.text!r}"


# ===========================================================================
# CONV5 — turn cap fires; no (N+1)th turn
# ===========================================================================

def test_conv5_turn_cap_fires_at_max_agent_turns():
    """A low cap forces the failsafe; the agent never exceeds the cap (+1 failsafe)."""
    vp = load_value_prop()
    policy = build_policy("A")
    # A tiny cap of 2 guarantees the happy path cannot complete before the cap.
    runner = DialogRunner(policy, vp, max_turns=2)
    callee = SimulatedCallee(Persona.COOPERATIVE)
    result = runner.run(callee)
    assert result.disposition is Disposition.FAILSAFE
    # agent_turns counts the substantive turns BEFORE the failsafe; it never
    # exceeds the cap. (The failsafe line itself is the terminal close.)
    assert result.agent_turns <= 2


def test_conv5_uses_the_real_constant_not_a_magic_number():
    """The default cap is config.MAX_AGENT_TURNS (no inline magic value, §8)."""
    vp = load_value_prop()
    runner = DialogRunner(build_policy("A"), vp)
    assert runner.max_turns == MAX_AGENT_TURNS


# ===========================================================================
# CONV6 — FAILSAFE_HANGUP_LINE byte-exact on cap; clean disposition
# ===========================================================================

def test_conv6_failsafe_line_is_byte_exact():
    """On the turn cap the agent's terminal line equals FAILSAFE_HANGUP_LINE exactly."""
    vp = load_value_prop()
    runner = DialogRunner(build_policy("B"), vp, max_turns=1)
    result = runner.run(SimulatedCallee(Persona.COOPERATIVE))
    assert result.disposition is Disposition.FAILSAFE
    last = result.transcript[-1]
    assert last.speaker is Speaker.AGENT
    assert last.stage is Stage.DONE
    # Byte-for-byte — the graded literal, consumed from config (never redefined).
    assert last.text == FAILSAFE_HANGUP_LINE


def test_conv6_failsafe_disposition_is_clean_not_an_exception():
    """The cap path produces a structured FAILSAFE disposition, never a crash (§6)."""
    vp = load_value_prop()
    runner = DialogRunner(build_policy("A"), vp, max_turns=1)
    # Must not raise.
    result = runner.run(SimulatedCallee(Persona.COOPERATIVE))
    assert isinstance(result.disposition, Disposition)


# ===========================================================================
# CON2 (offline) — disclosure first, byte-exact
# ===========================================================================

@pytest.mark.parametrize("variant", ALL_VARIANTS)
@pytest.mark.parametrize(
    "persona",
    [Persona.COOPERATIVE, Persona.OBJECTING, Persona.VOICEMAIL, Persona.PROBING],
)
def test_con2_disclosure_is_first_agent_utterance_byte_exact(variant, persona):
    """For every answered persona the first agent utterance is DISCLOSURE_LINE exactly."""
    result = run_conversation(variant, persona)
    agents = _agent_turns(result.transcript)
    assert agents, "no agent turn produced for an answered persona"
    assert agents[0].text == DISCLOSURE_LINE
    assert agents[0].stage is Stage.OPENING
    # The rubric agrees (computed signal).
    assert score_transcript(result.transcript).disclosure_said is True


def test_con2_no_answer_persona_produces_no_disclosure():
    """A line that never answers yields no agent utterance (no disclosure spoken)."""
    result = run_conversation("A", Persona.NO_ANSWER)
    assert _agent_turns(result.transcript) == []
    assert result.disposition is Disposition.NO_ANSWER


def test_con2_disclosure_literal_is_not_redefined_in_persona_module():
    """app.persona consumes DISCLOSURE_LINE from config — it does not redefine it."""
    import app.persona as persona_mod

    # The module must NOT bind its own string literal for the disclosure.
    assert persona_mod.DISCLOSURE_LINE is DISCLOSURE_LINE
    assert persona_mod.FAILSAFE_HANGUP_LINE is FAILSAFE_HANGUP_LINE


# ===========================================================================
# EVAL2 — scores are COMPUTED, never hardcoded; bake-off reproducible
# ===========================================================================

def test_eval2_rubric_is_computed_from_transcript():
    """Mutating the transcript changes the computed score — proving it isn't canned."""
    result = run_conversation("A", Persona.COOPERATIVE)
    full = score_transcript(result.transcript)
    # Remove the disclosure (first turn) → disclosure_said must flip to False.
    without_disclosure = result.transcript[1:]
    degraded = score_transcript(without_disclosure)
    assert full.disclosure_said is True
    assert degraded.disclosure_said is False
    assert degraded.score < full.score


def test_eval2_invented_claim_breaks_compliance():
    """An injected fabricated price makes compliance_ok compute False (negative guard)."""
    from app.eval import Turn

    result = run_conversation("A", Persona.COOPERATIVE)
    tampered = list(result.transcript)
    tampered.append(
        Turn(speaker=Speaker.AGENT, text="It's only $499 per month.", stage=Stage.PITCH)
    )
    assert score_transcript(tampered).compliance_ok is False


def test_eval2_phantom_booking_breaks_compliance():
    """Voicing a booking without a booked=True turn computes compliance_ok False."""
    from app.eval import Turn

    transcript = [
        Turn(speaker=Speaker.AGENT, text=DISCLOSURE_LINE, stage=Stage.OPENING),
        # Claims a booking but the turn is NOT flagged booked → phantom.
        Turn(speaker=Speaker.AGENT, text="Great, you're all set!", stage=Stage.CLOSE),
    ]
    assert score_transcript(transcript).meeting_booked is False
    assert score_transcript(transcript).compliance_ok is False


def test_eval2_failsafe_drift_breaks_compliance():
    """A paraphrased (non-byte-exact) failsafe close computes compliance_ok False."""
    from app.eval import Turn

    transcript = [
        Turn(speaker=Speaker.AGENT, text=DISCLOSURE_LINE, stage=Stage.OPENING),
        # Near-miss of FAILSAFE_HANGUP_LINE (curly apostrophe drift).
        Turn(
            speaker=Speaker.AGENT,
            text="Thanks for your time — I’ll follow up by email. Goodbye.",
            stage=Stage.DONE,
        ),
    ]
    assert score_transcript(transcript).compliance_ok is False


def test_eval2_claims_extracted_from_file_not_hardcoded():
    """extract_value_prop_claims derives keywords from the file at runtime (LEAK3)."""
    claims = extract_value_prop_claims()
    # A distinctive value-prop word is present; a random non-word is not.
    assert "compliance" in claims or "outbound" in claims
    assert "zzzznotaword" not in claims


# ===========================================================================
# Bake-off — computed, deterministic, NO winner declared
# ===========================================================================

def test_bakeoff_runs_both_variants_over_full_persona_matrix():
    """run_cells covers every (variant × persona) cell — 2 × the matrix."""
    cells = run_cells()
    assert len(cells) == len(VARIANTS) * len(PERSONA_MATRIX)
    covered = {(c.variant, c.persona) for c in cells}
    expected = {(v, p) for v in VARIANTS for p in PERSONA_MATRIX}
    assert covered == expected


def test_bakeoff_table_has_a_row_per_variant_and_no_winner_field():
    """The table is one computed row per variant; it declares NO winner (brief)."""
    rows = run_bakeoff()
    assert len(rows) == len(VARIANTS)
    for row in rows:
        assert "winner" not in row
        # Every metric is a computed number, not a hardcoded literal label.
        assert isinstance(row["book_rate"], (int, float))
        assert 0.0 <= row["book_rate"] <= 1.0
        assert 0.0 <= row["disclosure_rate"] <= 1.0
        assert 0.0 <= row["compliance_rate"] <= 1.0


def test_bakeoff_is_deterministic_across_runs():
    """Same inputs ⇒ same table every run (config.RANDOM_SEED) — EVAL1/EVAL2."""
    assert run_bakeoff() == run_bakeoff()


def test_rubric_result_score_is_sum_of_signals():
    """RubricResult.score is the computed count of satisfied signals (0–5)."""
    r = RubricResult(True, True, True, True, True)
    assert r.score == 5
    r2 = RubricResult(False, False, False, False, False)
    assert r2.score == 0


# ===========================================================================
# Determinism + import-safety smoke (cross-checks for ENV4/EVAL1)
# ===========================================================================

def test_simulated_callee_is_seeded_and_deterministic():
    """Two callees built the same way produce identical sequences (RANDOM_SEED)."""
    a = SimulatedCallee(Persona.OBJECTING)
    b = SimulatedCallee(Persona.OBJECTING)
    from app.eval import Turn

    probe = Turn(speaker=Speaker.AGENT, text="x", stage=Stage.OBJECTION)
    seq_a = [a.respond(probe).text for _ in range(3)]
    seq_b = [b.respond(probe).text for _ in range(3)]
    assert seq_a == seq_b


def test_value_prop_loader_rejects_missing_file(tmp_path):
    """A missing value-prop file is a clean explicit error, not a KeyError (LEAD1-style)."""
    missing = tmp_path / "nope.md"
    with pytest.raises(FileNotFoundError):
        load_value_prop(missing)


def test_build_policy_rejects_unknown_variant():
    """An unknown variant is a clean ValueError, not a silent default."""
    with pytest.raises(ValueError):
        build_policy("Z")


def test_value_prop_dataclass_shape():
    """load_value_prop returns the structured, file-derived content (no hardcoding)."""
    vp = load_value_prop()
    assert isinstance(vp, ValueProp)
    assert len(vp.value_props) >= 3
    assert vp.meeting_pitch
    assert vp.objection_responses  # at least one approved talking point parsed
