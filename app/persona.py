"""Conversation design — Aria's dialog policy and live system prompt.

Owns the conversation state machine (open → discovery/pitch → objection handling →
propose a slot → close), the two A/B style variants, and the assembly of the live
model's system prompt. The variants differ only in ordering, never in content:

    A "Consultative" : open → ask a discovery question → pitch to the surfaced pain.
    B "Direct"       : open → lead with the value-prop and ask for the meeting early.

Every Alta claim the agent may state is loaded from the value-prop file at runtime —
nothing is hardcoded — and the two spoken literals (the disclosure and the failsafe
close) come from config so they cannot drift. On the turn cap or an error the agent
speaks the failsafe line and ends.

This module drives the agent side of the offline simulator; the callee and the
scoring rubric live alongside it in app/eval.

Import-safe: the value-prop file is read lazily at run time, never at import.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from app.config import (
    BOOKING_SLOT_MINUTES,
    DISCLOSURE_LINE,
    FAILSAFE_HANGUP_LINE,
    MAX_AGENT_TURNS,
    value_prop_path,
)
from app.eval import Disposition, Persona, Speaker, Stage, Turn
from app.eval.simulated_callee import SimulatedCallee


# ===========================================================================
# Value-prop content, parsed from the value-prop file at runtime
# ===========================================================================

@dataclass(frozen=True)
class ValueProp:
    """The agent's assertable content, parsed from the value-prop file.

    Nothing here is hardcoded: every field is extracted from the file the caller
    passes (or the repo default) at runtime. The agent may assert ONLY this
    content.
    """

    value_props: tuple[str, ...]            # the numbered core value propositions
    objection_responses: dict[str, str]     # objection keyword → approved reply
    meeting_pitch: str                       # the 30-min meeting ask


def _read_text(path: Path | str | None) -> str:
    resolved = value_prop_path() if path is None else Path(path)
    if not resolved.exists():
        raise FileNotFoundError(
            f"Value-prop file not found: {resolved}. "
            "The agent grounds every claim in the value-prop file."
        )
    return resolved.read_text(encoding="utf-8")


def _extract_section(text: str, heading: str) -> str:
    """Return the body of a section whose '## ' heading STARTS WITH *heading*.

    Prefix-matched (not full-line) so a heading with a trailing qualifier — e.g.
    '## Objection responses (approved talking points)' — still resolves from
    'Objection responses'. Body runs up to the next '## ' heading or EOF.
    """
    pattern = re.compile(
        rf"^##\s+{re.escape(heading)}.*?$(.*?)(?=^##\s+|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    m = pattern.search(text)
    return m.group(1) if m else ""


def load_value_prop(path: Path | str | None = None) -> ValueProp:
    """Parse the value-prop file into structured, assertable content (runtime).

    Extracts:
      - the numbered '## Core value propositions' items → value_props
      - the '## Objection responses' bullets → objection_responses (keyword→reply)
      - the '## Meeting pitch' quoted block → meeting_pitch

    A missing file is a clean explicit error, not a mid-call crash.
    """
    text = _read_text(path)

    # --- core value propositions: numbered "N. **Title** — body" items ---
    vp_section = _extract_section(text, "Core value propositions")
    raw_items = re.split(r"^\s*\d+\.\s+", vp_section, flags=re.MULTILINE)
    value_props = tuple(
        _flatten(item) for item in raw_items if item.strip()
    )

    # --- objection responses: bullets of form: - **"trigger"** → "reply" ---
    obj_section = _extract_section(text, "Objection responses")
    objection_responses: dict[str, str] = {}
    for trigger, reply in re.findall(
        r"\*\*\"([^\"]+)\"\*\*[^\n]*?→\s*\"([^\"]+)\"",
        obj_section,
    ):
        objection_responses[trigger.strip().lower()] = _flatten(reply)

    # --- meeting pitch: the quoted block under '## Meeting pitch' ---
    pitch_section = _extract_section(text, "Meeting pitch")
    pitch_match = re.search(r"\"(.+?)\"", pitch_section, re.DOTALL)
    meeting_pitch = _flatten(pitch_match.group(1)) if pitch_match else ""

    if not value_props:
        raise ValueError(
            "The value-prop file parsed no '## Core value propositions' — the "
            "format changed; the agent cannot pitch ungrounded content."
        )

    return ValueProp(
        value_props=value_props,
        objection_responses=objection_responses,
        meeting_pitch=meeting_pitch,
    )


def _flatten(s: str) -> str:
    """Collapse whitespace/markdown emphasis into a single clean utterance line."""
    s = s.replace("*", "").replace("\n", " ")
    return re.sub(r"\s+", " ", s).strip()


# ===========================================================================
# The dialog policy (the two variants differ only by ordering)
# ===========================================================================

@dataclass(frozen=True)
class DialogPolicy:
    """An immutable description of one A/B variant's ordering rules.

    The two variants share ALL content (drawn from ValueProp) and differ only in
    `stage_order` — the sequence of agent stages between the disclosure and the
    close. This is the entire A/B contrast: policy, not content.
    """

    variant: str
    name: str
    stage_order: tuple[Stage, ...]


# Variant A — Consultative / discovery-led: ask first, then pitch to the pain.
_VARIANT_A = DialogPolicy(
    variant="A",
    name="Consultative / discovery-led",
    stage_order=(Stage.DISCOVERY, Stage.PITCH, Stage.PROPOSE_SLOT),
)

# Variant B — Direct / value-first: lead with the value-prop + early ask.
_VARIANT_B = DialogPolicy(
    variant="B",
    name="Direct / value-first",
    stage_order=(Stage.PITCH, Stage.PROPOSE_SLOT),
)

_VARIANTS = {"A": _VARIANT_A, "B": _VARIANT_B}


def build_policy(variant: str = "A") -> DialogPolicy:
    """Return the DialogPolicy for *variant* ('A' or 'B').

    This is the parameter-selected variant constructor mandated by the brief —
    NOT two copy-pasted modules. An unknown variant is a clean error.
    """
    key = variant.upper()
    if key not in _VARIANTS:
        raise ValueError(f"Unknown variant {variant!r}; expected 'A' or 'B'.")
    return _VARIANTS[key]


# ===========================================================================
# The conversation runner — drives one offline call to a transcript
# ===========================================================================

@dataclass
class ConversationResult:
    """The outcome of one simulated conversation."""

    transcript: list[Turn] = field(default_factory=list)
    disposition: Disposition = Disposition.ERROR
    agent_turns: int = 0


class DialogRunner:
    """Drives a deterministic offline conversation for one variant + persona.

    The runner produces the AGENT turns from the policy + ValueProp; the
    SimulatedCallee produces the callee turns. It enforces the turn cap
    (MAX_AGENT_TURNS → FAILSAFE_HANGUP_LINE) and never raises mid-call (a component
    failure becomes a FAILSAFE disposition).
    """

    def __init__(
        self,
        policy: DialogPolicy,
        value_prop: ValueProp,
        *,
        max_turns: int = MAX_AGENT_TURNS,
    ) -> None:
        self.policy = policy
        self.vp = value_prop
        self.max_turns = max_turns

    # -- agent utterance builders (all content from self.vp) ---------------

    def _disclosure_turn(self) -> Turn:
        # Byte-exact, from config — the FIRST utterance.
        return Turn(speaker=Speaker.AGENT, text=DISCLOSURE_LINE, stage=Stage.OPENING)

    def _discovery_turn(self) -> Turn:
        text = (
            "Before I dive in — how are you handling outbound prospecting today? "
            "I want to make sure this is even relevant to you."
        )
        return Turn(speaker=Speaker.AGENT, text=text, stage=Stage.DISCOVERY)

    def _pitch_turn(self) -> Turn:
        # Pitch is the joined grounded value-props from the file (never invented).
        body = " ".join(self.vp.value_props[:2]) if self.vp.value_props else ""
        return Turn(speaker=Speaker.AGENT, text=body, stage=Stage.PITCH)

    def _objection_turn(self, callee_text: str) -> Turn:
        """Return the approved scripted recovery for *callee_text* (from the file)."""
        reply = self._lookup_objection(callee_text)
        return Turn(speaker=Speaker.AGENT, text=reply, stage=Stage.OBJECTION)

    def _lookup_objection(self, callee_text: str) -> str:
        low = callee_text.lower()
        for trigger, reply in self.vp.objection_responses.items():
            if trigger in low:
                return reply
        # Fallback to the generic "not interested" recovery if present, else a
        # safe, content-grounded acknowledgement (never an invented claim).
        for key in ("not interested", "send me an email"):
            if key in self.vp.objection_responses:
                return self.vp.objection_responses[key]
        return "I understand — may I ask what you're using for outbound today?"

    def _propose_slot_turn(self) -> Turn:
        return Turn(
            speaker=Speaker.AGENT,
            text=self.vp.meeting_pitch,
            stage=Stage.PROPOSE_SLOT,
        )

    def _booking_confirm_turn(self) -> Turn:
        # booked=True flags a genuine booking (the rubric's no-phantom check).
        return Turn(
            speaker=Speaker.AGENT,
            text="You're all set — I've got you down for that slot. Looking forward to it.",
            stage=Stage.CLOSE,
            booked=True,
        )

    def _failsafe_turn(self) -> Turn:
        # Byte-exact, from config.
        return Turn(speaker=Speaker.AGENT, text=FAILSAFE_HANGUP_LINE, stage=Stage.DONE)

    # -- the main loop ------------------------------------------------------

    def run(self, callee: SimulatedCallee) -> ConversationResult:
        """Run one conversation against *callee*; return the transcript + outcome."""
        result = ConversationResult()
        transcript = result.transcript

        # Non-answering / voicemail personas short-circuit cleanly (no booking).
        if not callee.answers():
            result.disposition = Disposition.NO_ANSWER
            return result
        if callee.is_voicemail():
            transcript.append(self._disclosure_turn())
            result.agent_turns = 1
            transcript.append(callee.voicemail_greeting())
            result.disposition = Disposition.VOICEMAIL
            return result

        # 1. Disclosure first.
        self._emit(transcript, self._disclosure_turn(), result)
        if self._cap_hit(result):
            return self._failsafe(transcript, result)
        transcript.append(callee.respond(transcript[-1]))

        # 2. Walk the variant's stage order, handling objections inline.
        for stage in self.policy.stage_order:
            agent_turn = self._turn_for_stage(stage)
            self._emit(transcript, agent_turn, result)
            if self._cap_hit(result):
                return self._failsafe(transcript, result)

            callee_turn = callee.respond(agent_turn)
            transcript.append(callee_turn)

            # Inline objection handling: recover, then re-check for a hard no.
            handled = self._handle_objections(transcript, callee, result)
            if handled is _HARD_NO:
                result.disposition = Disposition.DECLINED
                return result
            if self._cap_hit(result):
                return self._failsafe(transcript, result)

        # 3. Close: if the callee accepted a slot, voice a real booking.
        if self._callee_accepted(transcript):
            self._emit(transcript, self._booking_confirm_turn(), result)
            result.disposition = Disposition.BOOKED
        else:
            result.disposition = Disposition.DECLINED
        return result

    # -- helpers ------------------------------------------------------------

    def _turn_for_stage(self, stage: Stage) -> Turn:
        if stage is Stage.DISCOVERY:
            return self._discovery_turn()
        if stage is Stage.PITCH:
            return self._pitch_turn()
        if stage is Stage.PROPOSE_SLOT:
            return self._propose_slot_turn()
        # Defensive: an unexpected stage falls back to the pitch (never raises).
        return self._pitch_turn()

    def _handle_objections(
        self,
        transcript: list[Turn],
        callee: SimulatedCallee,
        result: ConversationResult,
    ) -> object | None:
        """Recover from any objection in the callee's last turn.

        Returns _HARD_NO if the callee has issued its final hard no (the agent
        must respect it); None otherwise. Each recovery is a scripted reply from
        the value-prop file, never a hang-up on the first objection.
        """
        last = transcript[-1]
        if last.speaker is not Speaker.CALLEE:
            return None

        # A hard no is honored — respect the hang-up.
        if callee.hard_no_reached():
            return _HARD_NO

        low = last.text.lower()
        if self._is_objection(low):
            self._emit(transcript, self._objection_turn(last.text), result)
            if self._cap_hit(result):
                return None
            # Let the callee respond to the recovery, then re-check for a hard no.
            transcript.append(callee.respond(transcript[-1]))
            if callee.hard_no_reached():
                return _HARD_NO
        return None

    @staticmethod
    def _is_objection(low_text: str) -> bool:
        return any(
            m in low_text
            for m in ("not interested", "send me an email", "send the email", "busy")
        )

    @staticmethod
    def _callee_accepted(transcript: list[Turn]) -> bool:
        """True if the callee's last substantive turn accepted a proposed slot."""
        for t in reversed(transcript):
            if t.speaker is Speaker.CALLEE:
                low = t.text.lower()
                return any(
                    k in low for k in ("works for me", "works", "tuesday", "wednesday")
                )
        return False

    def _emit(
        self, transcript: list[Turn], turn: Turn, result: ConversationResult
    ) -> None:
        transcript.append(turn)
        result.agent_turns += 1

    def _cap_hit(self, result: ConversationResult) -> bool:
        return result.agent_turns >= self.max_turns

    def _failsafe(
        self, transcript: list[Turn], result: ConversationResult
    ) -> ConversationResult:
        """Speak FAILSAFE_HANGUP_LINE byte-exact and end."""
        transcript.append(self._failsafe_turn())
        result.disposition = Disposition.FAILSAFE
        return result


# Sentinel signalling the objecting callee has issued a final hard no.
_HARD_NO = object()


# ===========================================================================
# Convenience: run one variant against one persona to a transcript
# ===========================================================================

def run_conversation(
    variant: str,
    persona: Persona,
    *,
    value_prop_path: Path | str | None = None,
    max_turns: int = MAX_AGENT_TURNS,
) -> ConversationResult:
    """Run a single deterministic offline conversation; return its result.

    All content is loaded from the value-prop file at runtime; determinism
    comes from the seeded SimulatedCallee (config.RANDOM_SEED).
    """
    policy = build_policy(variant)
    vp = load_value_prop(value_prop_path)
    runner = DialogRunner(policy, vp, max_turns=max_turns)
    callee = SimulatedCallee(persona)
    return runner.run(callee)


# ===========================================================================
# Live system prompt — assembled at runtime from the value-prop
# ===========================================================================

# Variant-specific ordering guidance for the live model. These are POLICY hints
# (the same A/B contrast as build_policy — ordering, not content); the assertable
# facts are injected from the value-prop file, never from here.
_VARIANT_PROMPT_GUIDANCE: dict[str, str] = {
    "A": (
        "Style: consultative / discovery-led. After the opening, ask ONE short "
        "discovery question to surface the prospect's current outbound pain, then "
        "tailor the pitch to what they say before proposing the meeting."
    ),
    "B": (
        "Style: direct / value-first. After the opening, lead with the crispest "
        "value propositions and ask for the meeting early; handle objections after."
    ),
}


def build_system_prompt(
    variant: str = "A",
    value_prop: ValueProp | None = None,
    *,
    value_prop_path: Path | str | None = None,
    available_slots: list[dict] | None = None,
) -> str:
    """Assemble the LIVE model's system prompt from the chosen variant + value-prop.

    Every assertable Alta fact is injected from the value-prop content at runtime
    (no Alta claim is hardcoded here); the two graded literals are consumed
    from config (DISCLOSURE_LINE / FAILSAFE_HANGUP_LINE), never re-literaled. The
    prompt instructs: disclosure-first, pitch ONLY from the value-props, handle
    objections with the approved talking points, propose the 30-min meeting, book
    ONLY via the tools, and speak FAILSAFE_HANGUP_LINE on a cap or error.

    The disclosure is ALSO pinned to the platform static first-message (the
    chokepoint — see app/vapi_client.py); restating it here is belt-and-suspenders,
    not the enforcement point.

    Default variant is the LOCKED winner "A" (Consultative / discovery-led) —
    in the A/B bake-off, variant A booked at twice the rate of B while tying on
    disclosure/objection/compliance. It stays a parameter.

    Args:
        variant:           "A" or "B" — selects the ordering guidance.
        value_prop:        a pre-loaded ValueProp; if None it is loaded at runtime.
        value_prop_path:   override path used only when *value_prop* is None.

    Returns:
        The assembled system-prompt string.
    """
    policy = build_policy(variant)
    vp = value_prop if value_prop is not None else load_value_prop(value_prop_path)

    value_props_block = "\n".join(
        f"  - {claim}" for claim in vp.value_props
    )
    objections_block = "\n".join(
        f'  - When the prospect says "{trigger}", respond: {reply}'
        for trigger, reply in vp.objection_responses.items()
    ) or "  - (no scripted objection responses provided)"

    guidance = _VARIANT_PROMPT_GUIDANCE.get(
        variant.upper(), _VARIANT_PROMPT_GUIDANCE["A"]
    )

    # Pre-fetched availability (optional): when the caller pulled slots BEFORE the
    # call, inject them so Aria offers times INSTANTLY — no mid-call
    # check_availability round-trip (the "give me a moment" at proposal time). She
    # still calls check_availability only to RE-OFFER if the prospect rejects all.
    slots_block = ""
    if available_slots:
        slot_lines = "\n".join(
            f'  - "{s.get("say", "")}"  (book this one with slot_start_iso='
            f'"{s.get("slot_start_iso") or s.get("start_utc") or s.get("slot_key", "")}")'
            for s in available_slots
        )
        slots_block = (
            "PRE-FETCHED MEETING TIMES (already pulled for THIS call — offer these "
            "directly; do NOT call check_availability before your first proposal):\n"
            f"{slot_lines}\n"
            "Read two or three of the say-strings to the prospect VERBATIM, let them "
            "pick, then call book_meeting with that slot's slot_start_iso. Call "
            "check_availability ONLY if they reject all of these and want other "
            "times.\n\n"
        )

    return (
        "You are Aria, an assistant placing an outbound sales call on behalf of "
        "Alta. You are professional, warm, and concise.\n\n"
        f"OPENING (mandatory, verbatim, FIRST): \"{DISCLOSURE_LINE}\" "
        "This exact line is delivered by the platform as the first message; do not "
        "paraphrase it or speak before it.\n\n"
        f"DIALOG POLICY ({policy.variant} — {policy.name}):\n{guidance}\n\n"
        "DISCOVERY → TAILOR (do this BEFORE pitching): after the prospect answers "
        "your discovery question, reflect their specific pain back in your own words, "
        "then lead with ONLY the ONE value-prop that addresses it — never the whole "
        "list. If their answer is vague, empty, or off-topic, ask ONE short clarifying "
        "question first and do NOT pitch on a non-answer.\n\n"
        "WHAT YOU MAY ASSERT (the ONLY Alta facts you may state — never invent a "
        "claim, price, ROI number, or customer name outside this list):\n"
        f"{value_props_block}\n\n"
        f"THE MEETING ASK: {vp.meeting_pitch}\n\n"
        f"{slots_block}"
        f"MEETING LENGTH: always propose a single {BOOKING_SLOT_MINUTES}-minute meeting. "
        "Never offer a different duration (do not say 15 or 20 minutes).\n\n"
        "OBJECTION HANDLING — DON'T accept the first \"no\". A quick brush-off "
        "(\"not interested\", \"we're good\", \"we already do this\", \"we're doing "
        "fine\", \"now's not a good time\", \"just email me\") is a reflex, not a real "
        "decision — it usually means the value isn't clear yet. When the prospect pushes "
        "back, or sounds like they're already managing fine:\n"
        "  1) Acknowledge warmly in a few words (\"Totally fair\", \"I hear you\") — "
        "never argue or get defensive.\n"
        "  2) Then GENTLY keep going: give the ONE value-prop most relevant to what they "
        "said (from the approved list below) as a concrete reason this is worth 30 "
        "seconds — even if they think they're already covered, show them what they'd "
        "gain.\n"
        "  3) Softly re-ask for the meeting (\"Worst case, you walk away with 30 minutes "
        "of ideas — fair enough?\").\n"
        "Make up to TWO gentle attempts like this before you let the meeting go. Stay "
        "relaxed, warm, and easy to say yes to — curious, never pushy or a pest.\n"
        "HONOR A REAL NO: once they give a FIRM or repeated no (a second clear no, "
        "\"please take me off your list\", \"stop calling\", or clear annoyance), respect "
        "it immediately — thank them and end. Never make a third push, never badger.\n"
        f"Approved responses to draw from:\n{objections_block}\n\n"
        "TOOLS (you MUST use these — never claim a booking that a tool did not "
        "confirm): check_availability to find free slots, book_meeting to book one "
        "(only voice a confirmation AFTER it succeeds), log_disposition to record the "
        "outcome, and detect_voicemail on a greeting. To hang up, END THE CALL (see "
        "ENDING) — the platform speaks the closing line for you.\n\n"
        "WHILE check_availability OR book_meeting RUNS: say ONE short, WARM line — NEVER "
        "a flat robotic filler like \"give me a moment\", \"one moment\", \"hold on a "
        "sec\", or \"just a sec\". Make it warm and human, e.g. \"Ooh, love that — let me "
        "grab a couple of times that work for you.\" / \"Amazing, let me lock that in for "
        "you right now!\" / \"Wonderful — getting that booked for you.\" Then WAIT for "
        "the result; "
        "do not repeat yourself or narrate every step. When slots come back, read two "
        "or three of their `say` strings to the prospect VERBATIM and let them pick — "
        "never compute, convert, or reword a date/time yourself. "
        "log_disposition runs SILENTLY — say NOTHING before, during, or after it "
        "(no \"give me a moment\", no \"just a sec\"); it must NEVER produce a spoken "
        "line.\n\n"
        "PACING: speak in short, complete sentences — one point at a time, then pause "
        "for the prospect; do not deliver the whole pitch in a single breath.\n\n"
        "BOOKING CONFIRMATION (after book_meeting SUCCEEDS): confirm by reading back the "
        "SPECIFIC day and time you just booked (e.g. \"You're booked for Monday, June 29 "
        "at 3:30 PM\"), and tell them they'll get a calendar invite by email. If they ask "
        "a final question (e.g. \"so now what?\"), ANSWER it briefly first — never ignore "
        "it and hang up.\n\n"
        "ENDING THE CALL: do NOT hang up abruptly — give the prospect room to respond. "
        "After the booking is confirmed (or the prospect clearly wants to wrap up), give "
        "ONE warm, human sign-off that invites a reply — e.g. \"You're all set! Anything "
        "else I can help with before you go?\" or \"Loved chatting with you — have a "
        "great rest of your day!\" — and briefly WAIT so they can answer or say goodbye. "
        "If they reply, answer any quick question, then warmly acknowledge (e.g. \"Of "
        "course — take care!\"). THEN end the call (the platform speaks the final closing "
        "line and hangs up for you). End also on a FIRM or repeated no after your gentle "
        "attempts (see OBJECTION HANDLING), on voicemail, or on a limit/error. Never keep "
        "talking once you've wrapped, and never improvise a non-compliant promise."
    )
