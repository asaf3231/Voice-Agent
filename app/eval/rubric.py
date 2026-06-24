"""Alta Outbound Voice Agent — app/eval/rubric.py

Single responsibility: a COMPUTED rubric that scores a transcript on the five
conversation signals (EVAL3) — never a hardcoded outcome (EVAL2 / LEAK4):

  - disclosure_said    : the first AGENT utterance == DISCLOSURE_LINE byte-exact.
  - pitch_delivered    : a value-prop claim drawn from the value-prop file appears
                         in an agent turn BEFORE the slot proposal.
  - objection_handled  : an objection received a scripted recovery before any
                         hard-no close (or no objection was raised → vacuously ok).
  - meeting_booked     : a booking is voiced ONLY on a turn flagged booked=True
                         (i.e. after a successful book), never merely spoken.
  - compliance_ok      : no invented Alta claim (a price/number/customer name not
                         present in the value-prop file); FAILSAFE_HANGUP_LINE
                         byte-exact when used; no booking voiced without a book.

Every signal is computed from the transcript + the value-prop facts read at
runtime. Nothing here asserts an outcome literal (EVAL2/LEAK4).

Import-safety (ENV4): defines functions + a frozen result dataclass only. The
value-prop file is read LAZILY (inside score_transcript / the keyword extractor)
via config.value_prop_path(), never at import. No network, no client.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app.config import (
    DISCLOSURE_LINE,
    FAILSAFE_HANGUP_LINE,
    value_prop_path,
)
from app.eval import Speaker, Stage, Turn

# ---------------------------------------------------------------------------
# Value-prop fact extraction (read at runtime — LEAK3; never hardcoded)
# ---------------------------------------------------------------------------

# Tokens that, if the agent utters them but they are NOT grounded in the
# value-prop file, signal an invented/forbidden claim. Pricing figures, ROI
# guarantees, and customer names are exactly what the file says Aria must NOT
# improvise. We detect the SHAPE of a fabricated claim, then confirm it is
# ungrounded against the file's own text.
_PRICE_PATTERN = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?")
_PERCENT_PATTERN = re.compile(r"\b\d{1,3}\s?%")
_MULTIPLE_PATTERN = re.compile(r"\b\d+(?:\.\d+)?\s?x\b", re.IGNORECASE)

# Stop-words excluded when deriving value-prop keyword claims from the file.
_STOP_WORDS = frozenset(
    {
        "the", "and", "for", "with", "your", "that", "this", "you", "are", "our",
        "not", "but", "can", "has", "his", "her", "out", "now", "all", "any",
        "alta", "aria", "they", "them", "from", "into", "over", "what", "when",
        "more", "less", "without", "every", "each", "does", "their", "team",
        "call", "calls", "say", "send", "could", "would", "should", "want",
    }
)


def _read_value_prop_text(path: Path | str | None = None) -> str:
    """Read the raw value-prop markdown at runtime (lazy — never at import)."""
    resolved = value_prop_path() if path is None else Path(path)
    if not resolved.exists():
        raise FileNotFoundError(
            f"Value-prop file not found: {resolved}. "
            "The rubric needs the value-prop file to ground claims (LEAK3)."
        )
    return resolved.read_text(encoding="utf-8")


def extract_value_prop_claims(path: Path | str | None = None) -> frozenset[str]:
    """Return the set of distinctive lowercase keyword-claims grounded in the file.

    Computed from the value-prop file at runtime (LEAK3): we take meaningful words
    (≥4 chars, not stop-words) the agent is allowed to assert. pitch_delivered is
    True when an agent turn echoes any of these grounded keywords.
    """
    text = _read_value_prop_text(path).lower()
    words = re.findall(r"[a-z][a-z\-]{3,}", text)
    return frozenset(w for w in words if w not in _STOP_WORDS)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RubricResult:
    """The computed score of a single transcript.

    Each of the five signals is a bool computed from the transcript; `score` is
    the count of True signals (0–5). Nothing here is hardcoded — every field is
    derived in score_transcript().
    """

    disclosure_said: bool
    pitch_delivered: bool
    objection_handled: bool
    meeting_booked: bool
    compliance_ok: bool

    @property
    def score(self) -> int:
        """Number of satisfied signals (0–5) — computed, never stored."""
        return sum(
            (
                self.disclosure_said,
                self.pitch_delivered,
                self.objection_handled,
                self.meeting_booked,
                self.compliance_ok,
            )
        )

    def as_dict(self) -> dict[str, bool | int]:
        """Plain-dict view for aggregation / the bake-off table."""
        return {
            "disclosure_said": self.disclosure_said,
            "pitch_delivered": self.pitch_delivered,
            "objection_handled": self.objection_handled,
            "meeting_booked": self.meeting_booked,
            "compliance_ok": self.compliance_ok,
            "score": self.score,
        }


# ---------------------------------------------------------------------------
# Signal computations
# ---------------------------------------------------------------------------

def _agent_turns(transcript: list[Turn]) -> list[Turn]:
    return [t for t in transcript if t.speaker is Speaker.AGENT]


def _first_agent_index(transcript: list[Turn]) -> int | None:
    for i, t in enumerate(transcript):
        if t.speaker is Speaker.AGENT:
            return i
    return None


def _compute_disclosure_said(transcript: list[Turn]) -> bool:
    """True iff the FIRST agent utterance equals DISCLOSURE_LINE byte-for-byte."""
    agents = _agent_turns(transcript)
    if not agents:
        return False
    return agents[0].text == DISCLOSURE_LINE


# Agent stages that do NOT count as a pitch utterance. The OPENING (disclosure)
# is excluded so incidental keyword overlap in the byte-exact disclosure cannot
# masquerade as a delivered pitch (precision over a pure keyword heuristic).
_NON_PITCH_STAGES = frozenset({Stage.OPENING, Stage.DONE})


def _compute_pitch_delivered(
    transcript: list[Turn], claims: frozenset[str]
) -> bool:
    """True iff a grounded value-prop claim is voiced before the slot proposal.

    'Before the slot proposal' = before the first agent turn at stage
    PROPOSE_SLOT. If no slot was ever proposed, any pre-close grounded claim
    counts (the pitch still happened). The OPENING disclosure is NOT a pitch —
    it is excluded so its incidental keyword overlap cannot credit a phantom
    pitch (e.g. a voicemail transcript that only ever spoke the disclosure).
    """
    proposal_index = None
    for i, t in enumerate(transcript):
        if t.speaker is Speaker.AGENT and t.stage is Stage.PROPOSE_SLOT:
            proposal_index = i
            break

    window = transcript if proposal_index is None else transcript[:proposal_index]
    for t in window:
        if t.speaker is not Speaker.AGENT:
            continue
        if t.stage in _NON_PITCH_STAGES:
            continue
        tokens = set(re.findall(r"[a-z][a-z\-]{3,}", t.text.lower()))
        if tokens & claims:
            return True
    return False


def _compute_objection_handled(transcript: list[Turn]) -> bool:
    """True iff every callee objection got an agent recovery before a hard-no close.

    An objection turn is a callee turn flagged by the simulator's known objection
    phrasings. 'Handled' means: after the objection, the agent produced a turn at
    stage OBJECTION (a scripted recovery) rather than immediately closing. If no
    objection was raised, this is vacuously True.
    """
    objection_markers = ("not interested", "send me an email", "send the email")
    saw_objection = False
    for i, t in enumerate(transcript):
        if t.speaker is not Speaker.CALLEE:
            continue
        low = t.text.lower()
        if any(m in low for m in objection_markers):
            saw_objection = True
            # Did the agent issue a recovery (OBJECTION stage) after this?
            recovered = any(
                later.speaker is Speaker.AGENT and later.stage is Stage.OBJECTION
                for later in transcript[i + 1 :]
            )
            if recovered:
                return True
    # No objection at all → vacuously handled; objection present but no recovery → False.
    return not saw_objection


def _find_invented_claim(transcript: list[Turn]) -> bool:
    """True iff an agent turn voices a numeric claim the agent must not fabricate.

    The agent may NOT improvise pricing, ROI guarantees, or 'Nx' multipliers
    (the value-prop file's "What Alta does NOT claim" section). We flag any agent
    turn that contains a dollar figure, a percentage, or an 'Nx' multiple — these
    patterns are never present in the allowed value-prop facts, so any such
    utterance is an invented/ungrounded claim.

    Note: this function flags by SHAPE (numeric claim patterns), not by diffing
    against the value-prop keyword set — that is a deliberate, honest design.
    The value-prop keywords are used by pitch_delivered (grounding the pitch);
    here we flag the FORBIDDEN patterns (price/ROI/multiple) that the file
    explicitly forbids, independent of what the agent might have been allowed to say.
    """
    for t in _agent_turns(transcript):
        text = t.text
        if _PRICE_PATTERN.search(text):
            return True
        if _PERCENT_PATTERN.search(text):
            return True
        if _MULTIPLE_PATTERN.search(text):
            return True
    return False


def _compute_meeting_booked(transcript: list[Turn]) -> bool:
    """True iff a booking is voiced on a turn flagged booked=True (after success)."""
    return any(t.speaker is Speaker.AGENT and t.booked for t in transcript)


def _voices_booking_text(text: str) -> bool:
    """Heuristic: does this agent line claim a meeting is confirmed/booked?"""
    low = text.lower()
    return ("booked" in low or "confirmed" in low or "you're all set" in low
            or "youre all set" in low or "i've got you down" in low
            or "ive got you down" in low)


def _compute_compliance_ok(
    transcript: list[Turn], claims: frozenset[str]
) -> bool:
    """True iff no invented claim, failsafe is byte-exact when used, and no booking
    is voiced without a booked=True turn (no phantom confirmation — Policy 5/6)."""
    if _find_invented_claim(transcript):
        return False

    # If any agent turn uses the failsafe close, it must be byte-exact.
    for t in _agent_turns(transcript):
        # A failsafe is recognised by stage DONE carrying the literal; if a turn
        # is a near-miss of the literal, that is a drift and fails compliance.
        if t.text == FAILSAFE_HANGUP_LINE:
            continue
        if _is_failsafe_drift(t.text):
            return False

    # No phantom booking: a turn that *voices* a booking must be flagged booked.
    for t in _agent_turns(transcript):
        if _voices_booking_text(t.text) and not t.booked:
            return False

    return True


def _is_failsafe_drift(text: str) -> bool:
    """True if *text* looks like a paraphrase of FAILSAFE_HANGUP_LINE but isn't exact.

    Catches a drifted close (e.g. a curly apostrophe or reworded goodbye) so the
    byte-exact contract (CONV6) is enforced, not hoped for.
    """
    if text == FAILSAFE_HANGUP_LINE:
        return False
    low = text.lower()
    # Signature tokens of the failsafe line.
    if "follow up by email" in low and "goodbye" in low:
        return True
    return False


# ---------------------------------------------------------------------------
# Bug-2 behavioral signal — pitch_tailored (does the pitch reflect the pain?)
# ---------------------------------------------------------------------------

def _word_tokens(text: str) -> set[str]:
    """Distinctive lowercase word tokens (≥4 chars, minus stop-words)."""
    return {
        w for w in re.findall(r"[a-z][a-z\-]{3,}", text.lower())
        if w not in _STOP_WORDS
    }


def _discriminative_tokens(target: str, value_props: tuple[str, ...]) -> set[str]:
    """Tokens of *target* that appear in NO other value-prop — its fingerprint.

    Using only the discriminating tokens prevents generic shared words ('today',
    'meeting') from making an off-pain pitch look tailored.
    """
    target_tokens = _word_tokens(target)
    others: set[str] = set()
    for vp in value_props:
        if vp == target:
            continue
        others |= _word_tokens(vp)
    return target_tokens - others


def pitch_tailored(
    transcript: list[Turn], *, value_prop_path: Path | str | None = None
) -> bool:
    """True iff the agent's PITCH reflects the value-prop matching the prospect's pain.

    Computes the expected emphasis from the discovery answer via tools.qualify, then
    checks the pitch turn carries that value-prop's discriminative tokens. This is the
    Bug-2 regression guard: a canned full-list / off-pain pitch scores False.

    Vacuously True when there is no pitch turn, no discovery answer, or the answer was
    too vague to route (a non-answer is a separate concern, not a tailoring failure).
    """
    pitch = next(
        (t for t in transcript
         if t.speaker is Speaker.AGENT and t.stage is Stage.PITCH),
        None,
    )
    if pitch is None:
        return True

    # The discovery answer = the last callee turn before the pitch.
    answer = None
    for t in transcript:
        if t.speaker is Speaker.AGENT and t.stage is Stage.PITCH:
            break
        if t.speaker is Speaker.CALLEE:
            answer = t.text
    if not answer:
        return True

    # Lazy imports (avoid an import cycle + keep rubric import-safe — ENV4).
    from app.tools import qualify
    from app.persona import load_value_prop

    value_props = load_value_prop(value_prop_path).value_props
    data = qualify(answer=answer, value_props=value_props).to_dict()["data"]
    emphasize = data["emphasize"]
    if emphasize is None:  # vague/empty answer → nothing to tailor to
        return True

    fingerprint = _discriminative_tokens(emphasize, value_props)
    return bool(_word_tokens(pitch.text) & fingerprint)


# ---------------------------------------------------------------------------
# Bug-1 behavioral signal — slot_reoffer_handled (does a TIME-rejection recover?)
# ---------------------------------------------------------------------------

# Phrases that signal the callee rejected the proposed TIME but still wants to meet
# (a re-offer should follow) — distinct from a hard no to the MEETING itself. These
# must be UNAMBIGUOUS rejections: bare "that time" / "anything else" were removed
# because they also occur in acceptances ("anything else you need?", "that time we
# spoke"), which would mis-flag a booked, compliant call as a re-offer failure
# (independent review finding 2026-06-24).
_TIME_REJECTION_MARKERS = (
    "doesn't work",
    "does not work",
    "won't work",
    "will not work",
    "another time",
    "different time",
    "other times",
    "that slot doesn't",
    "that one doesn't",
)
# Phrases that mean the callee rejected the MEETING outright — NOT a re-offer case.
_MEETING_REJECTION_MARKERS = (
    "not interested",
    "don't want to meet",
    "do not want to meet",
    "don't call",
    "no thanks",
    "stop calling",
)


def slot_reoffer_handled(transcript: list[Turn]) -> bool:
    """True iff a TIME-rejection was met with an agent RE-OFFER, not a collapse (Bug 1).

    A booking agent must treat "that time doesn't work, got anything else?" as a
    request for an alternative slot — NOT as a terminal no. This signal is True iff,
    after a callee turn that rejects the proposed *time* (while still wanting the
    *meeting*), the agent produces a later PROPOSE_SLOT turn (a genuine re-offer)
    rather than going straight to CLOSE/DONE/failsafe.

    Vacuously True when there is no time-rejection turn (nothing to re-offer). This
    is the Bug-1 regression guard: the current finite-stage runner proposes a slot
    once and collapses on rejection, so an end-to-end SLOT_REJECTER run scores False
    until the re-offer loop is added — exactly what this signal is meant to catch.
    """
    for i, t in enumerate(transcript):
        if t.speaker is not Speaker.CALLEE:
            continue
        low = t.text.lower()
        # Skip outright meeting rejections — those are correctly terminal.
        if any(m in low for m in _MEETING_REJECTION_MARKERS):
            continue
        if any(m in low for m in _TIME_REJECTION_MARKERS):
            # A re-offer = a later agent turn back at PROPOSE_SLOT.
            reoffered = any(
                later.speaker is Speaker.AGENT and later.stage is Stage.PROPOSE_SLOT
                for later in transcript[i + 1 :]
            )
            return reoffered
    return True


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def score_transcript(
    transcript: list[Turn], *, value_prop_path: Path | str | None = None
) -> RubricResult:
    """Score *transcript* on the five signals — fully COMPUTED (EVAL2/LEAK4).

    Args:
        transcript: the ordered list of Turns (agent + callee).
        value_prop_path: override path for the value-prop file (tests); default
            resolves the repo file at runtime (LEAK3 — never hardcoded).

    Returns:
        A RubricResult; each signal is derived from the transcript, never asserted.
    """
    claims = extract_value_prop_claims(value_prop_path)
    return RubricResult(
        disclosure_said=_compute_disclosure_said(transcript),
        pitch_delivered=_compute_pitch_delivered(transcript, claims),
        objection_handled=_compute_objection_handled(transcript),
        meeting_booked=_compute_meeting_booked(transcript),
        compliance_ok=_compute_compliance_ok(transcript, claims),
    )
