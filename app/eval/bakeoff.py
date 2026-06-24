"""A/B bake-off — compares the two dialog variants on the persona matrix.

Runs both variants across the fixed persona set, scores each transcript through the
computed rubric, and returns a deterministic table of aggregate metrics. It declares
no winner by design: the figures are computed from transcripts (never hardcoded) and
the decision is made on the numbers.

Import-safe: defines functions/dataclasses only; the value-prop file is read at run
time, never at import.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.eval import Persona
from app.eval.rubric import RubricResult, score_transcript
from app.persona import ConversationResult, build_policy, run_conversation

# The fixed Stage-2 persona matrix (EVAL4) — small + deterministic by design.
PERSONA_MATRIX: tuple[Persona, ...] = (
    Persona.COOPERATIVE,
    Persona.OBJECTING,
    Persona.NO_ANSWER,
    Persona.VOICEMAIL,
    Persona.PROBING,
)

VARIANTS: tuple[str, ...] = ("A", "B")


@dataclass(frozen=True)
class CellResult:
    """One (variant, persona) cell: the conversation + its computed rubric score."""

    variant: str
    persona: Persona
    conversation: ConversationResult
    rubric: RubricResult


@dataclass(frozen=True)
class VariantSummary:
    """Aggregate metrics for one variant across the persona matrix (all computed)."""

    variant: str
    name: str
    book_rate: float            # fraction of personas that ended booked
    disclosure_rate: float      # fraction with disclosure_said True
    objection_handled_rate: float
    compliance_rate: float      # fraction with compliance_ok True
    avg_agent_turns: float

    def as_row(self) -> dict[str, object]:
        """Plain-dict row for the bake-off table (no winner field — by design)."""
        return {
            "variant": self.variant,
            "name": self.name,
            "book_rate": round(self.book_rate, 4),
            "disclosure_rate": round(self.disclosure_rate, 4),
            "objection_handled_rate": round(self.objection_handled_rate, 4),
            "compliance_rate": round(self.compliance_rate, 4),
            "avg_agent_turns": round(self.avg_agent_turns, 4),
        }


def run_cells(
    *, value_prop_path: Path | str | None = None
) -> list[CellResult]:
    """Run every (variant × persona) cell and score each transcript (computed)."""
    cells: list[CellResult] = []
    for variant in VARIANTS:
        for persona in PERSONA_MATRIX:
            conv = run_conversation(
                variant, persona, value_prop_path=value_prop_path
            )
            rubric = score_transcript(
                conv.transcript, value_prop_path=value_prop_path
            )
            cells.append(
                CellResult(
                    variant=variant,
                    persona=persona,
                    conversation=conv,
                    rubric=rubric,
                )
            )
    return cells


def _summarize(variant: str, cells: list[CellResult]) -> VariantSummary:
    """Aggregate one variant's cells into computed rates (never hardcoded)."""
    rows = [c for c in cells if c.variant == variant]
    n = len(rows)
    name = build_policy(variant).name

    def frac(pred) -> float:
        return sum(1 for c in rows if pred(c)) / n if n else 0.0

    book_rate = frac(lambda c: c.rubric.meeting_booked)
    disclosure_rate = frac(lambda c: c.rubric.disclosure_said)
    objection_rate = frac(lambda c: c.rubric.objection_handled)
    compliance_rate = frac(lambda c: c.rubric.compliance_ok)
    avg_turns = (
        sum(c.conversation.agent_turns for c in rows) / n if n else 0.0
    )

    return VariantSummary(
        variant=variant,
        name=name,
        book_rate=book_rate,
        disclosure_rate=disclosure_rate,
        objection_handled_rate=objection_rate,
        compliance_rate=compliance_rate,
        avg_agent_turns=avg_turns,
    )


def run_bakeoff(
    *, value_prop_path: Path | str | None = None
) -> list[dict[str, object]]:
    """Run the full A/B bake-off; return a COMPUTED table (one row per variant).

    No winner is declared (brief). The PM re-runs this and decides on the numbers.
    Deterministic: same inputs ⇒ same table every run (config.RANDOM_SEED).
    """
    cells = run_cells(value_prop_path=value_prop_path)
    return [_summarize(v, cells).as_row() for v in VARIANTS]


def format_table(rows: list[dict[str, object]]) -> str:
    """Render the bake-off table as plain text (for the handback / logs)."""
    if not rows:
        return "(no rows)"
    headers = list(rows[0].keys())
    widths = {
        h: max(len(h), *(len(str(r[h])) for r in rows)) for h in headers
    }
    line = " | ".join(h.ljust(widths[h]) for h in headers)
    sep = "-+-".join("-" * widths[h] for h in headers)
    body = "\n".join(
        " | ".join(str(r[h]).ljust(widths[h]) for h in headers) for r in rows
    )
    return f"{line}\n{sep}\n{body}"
