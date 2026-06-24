"""Offline-eval package — the shared vocabulary for transcript scoring.

Defines the small types every eval module agrees on (the conversation Turn and the
Speaker/Stage/Persona/Disposition enums) in one place, so the simulator, the rubric,
and the dialog policy never re-declare the shape of a transcript.

Import-safe: defines only enums and dataclasses — no side effects.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Speaker(str, Enum):
    """Who produced a turn in the transcript."""

    AGENT = "agent"
    CALLEE = "callee"


class Stage(str, Enum):
    """The dialog state-machine stages (CONV1).

    Happy path (variant-dependent):
        OPENING → {A: DISCOVERY → PITCH | B: PITCH} → OBJECTION* → PROPOSE_SLOT → CLOSE → DONE.
    DONE is the terminal sink once the call has ended. OBJECTION* means zero or
    more objection-recovery exchanges can interleave before PROPOSE_SLOT.
    """

    OPENING = "opening"          # the disclosure utterance
    PITCH = "pitch"
    DISCOVERY = "discovery"
    OBJECTION = "objection"
    PROPOSE_SLOT = "propose_slot"
    CLOSE = "close"
    DONE = "done"


class Persona(str, Enum):
    """The offline simulated-callee personas.

    The first five are the graded EVAL4 matrix (fixed in bakeoff.PERSONA_MATRIX).
    The trailing two are ADVERSARIAL personas for the stress suite (STR-L*); they
    are deliberately NOT in PERSONA_MATRIX, so adding them does not change the
    graded bake-off / eval numbers. The simulated-callee reply tables fall back to
    a generic ack for any persona they don't script, so adding members is safe.
    """

    COOPERATIVE = "cooperative"
    OBJECTING = "objecting"
    NO_ANSWER = "no_answer"
    VOICEMAIL = "voicemail"
    PROBING = "probing"
    # --- adversarial / stress personas (STR-L*; not in the graded matrix) ---
    INJECTION = "injection"        # prompt-injection / secret-exfil / policy-break attempts
    SLOT_REJECTER = "slot_rejecter"  # wants the meeting, rejects the first offered TIME (Bug 1)


class Disposition(str, Enum):
    """The terminal outcome of a simulated call (TOOL3 vocabulary, used early here)."""

    BOOKED = "booked"
    DECLINED = "declined"
    NO_ANSWER = "no_answer"
    VOICEMAIL = "voicemail"
    FAILSAFE = "failsafe"        # turn/time cap or error → FAILSAFE_HANGUP_LINE
    ERROR = "error"


@dataclass(frozen=True)
class Turn:
    """A single utterance in a transcript.

    Attributes:
        speaker: who spoke (AGENT or CALLEE).
        text:    the spoken text (byte-exact for the graded literals).
        stage:   the dialog stage the AGENT was in when it produced the turn
                 (None for callee turns).
        booked:  True only on an agent turn that voices a confirmed booking AFTER
                 a successful book_meeting (compliance_ok / meeting_booked signal).
    """

    speaker: Speaker
    text: str
    stage: Stage | None = None
    booked: bool = False
