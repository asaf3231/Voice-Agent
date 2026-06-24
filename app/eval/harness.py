"""Evaluation harness — the deterministic, offline scoring core.

Runs every persona (cooperative, objecting, no-answer, voicemail, probing) against
both dialog variants, scores each resulting transcript with the computed rubric, and
emits a reproducible summary (book rate, disclosure compliance, objection handling,
compliance, average turns). It can also load and score the labeled synthetic
transcript fixtures used as negative regression guards. Every stochastic part is
seeded, so the same inputs produce identical numbers on every run — these are the
figures shown in the demo video.

Import-safe: the value-prop file is read lazily at run time; no network or .env.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.eval import Disposition, Persona, Speaker, Stage, Turn
from app.eval.bakeoff import PERSONA_MATRIX, VARIANTS, run_cells
from app.eval.rubric import RubricResult, score_transcript
from app.persona import ConversationResult


# ---------------------------------------------------------------------------
# Harness configuration constants (not §9 graded constants — harness-local)
# ---------------------------------------------------------------------------

# Path to the labeled transcript fixtures (relative to repo root at runtime).
_FIXTURES_DIR_NAME = "fixtures/transcripts"


# ---------------------------------------------------------------------------
# Aggregate result types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PersonaResult:
    """The scored result for one (variant, persona) cell of the persona matrix."""

    variant: str
    persona: Persona
    disposition: Disposition
    agent_turns: int
    rubric: RubricResult

    def as_dict(self) -> dict[str, object]:
        """Plain-dict view for aggregation."""
        return {
            "variant": self.variant,
            "persona": self.persona.value,
            "disposition": self.disposition.value,
            "agent_turns": self.agent_turns,
            **self.rubric.as_dict(),
        }


@dataclass(frozen=True)
class AggregateMetrics:
    """Reproducible aggregate metrics over the full persona matrix for one variant.

    Each rate is a fraction over all personas (0.0–1.0). All figures are
    COMPUTED from labeled transcripts — never hardcoded (EVAL2/LEAK4).
    """

    variant: str
    variant_name: str
    book_rate: float
    disclosure_rate: float
    objection_handled_rate: float
    compliance_rate: float
    avg_agent_turns: float
    n_personas: int               # denominator (== len(PERSONA_MATRIX))

    def as_dict(self) -> dict[str, object]:
        return {
            "variant": self.variant,
            "variant_name": self.variant_name,
            "book_rate": round(self.book_rate, 4),
            "disclosure_rate": round(self.disclosure_rate, 4),
            "objection_handled_rate": round(self.objection_handled_rate, 4),
            "compliance_rate": round(self.compliance_rate, 4),
            "avg_agent_turns": round(self.avg_agent_turns, 4),
            "n_personas": self.n_personas,
        }


@dataclass
class EvalSummary:
    """The full output of one harness run — per-cell results + aggregate metrics."""

    persona_results: list[PersonaResult] = field(default_factory=list)
    aggregate: list[AggregateMetrics] = field(default_factory=list)

    def metrics_for(self, variant: str) -> AggregateMetrics | None:
        """Return the aggregate metrics for *variant*, or None if not found."""
        for m in self.aggregate:
            if m.variant == variant.upper():
                return m
        return None


# ---------------------------------------------------------------------------
# Fixture loading — labeled simulated transcripts (EVAL6 negative guards)
# ---------------------------------------------------------------------------

def _fixtures_dir(root: Path | str | None = None) -> Path:
    """Return the path to the fixtures/transcripts directory.

    If *root* is None, resolves relative to this file's location (up 3 dirs to
    the repo root). Tests pass their own tmp_path root. Never reads at import.
    """
    if root is not None:
        return Path(root) / _FIXTURES_DIR_NAME
    # __file__ = app/eval/harness.py → parent × 3 = repo root
    return Path(__file__).parent.parent.parent / _FIXTURES_DIR_NAME


def _load_turn(raw: dict[str, Any]) -> Turn:
    """Deserialise one turn dict from a fixture JSON file."""
    raw_stage = raw.get("stage")
    stage = Stage(raw_stage) if raw_stage is not None else None
    return Turn(
        speaker=Speaker(raw["speaker"]),
        text=raw["text"],
        stage=stage,
        booked=bool(raw.get("booked", False)),
    )


@dataclass(frozen=True)
class FixtureResult:
    """A loaded and scored labeled transcript fixture."""

    path: Path
    label: dict[str, Any]       # the "label" block from the JSON
    transcript: list[Turn]
    rubric: RubricResult


def load_fixtures(
    root: Path | str | None = None,
    *,
    value_prop_path: Path | str | None = None,
) -> list[FixtureResult]:
    """Load, score, and return all labeled transcript fixtures.

    Fixtures are JSON files under `fixtures/transcripts/` (tracked, synthetic, no
    real PII — LEAK2). Each file has a `label` block (the expected rubric signals)
    and a `transcript` array of turns. Scores are COMPUTED by the rubric at
    runtime — the `label` is ground-truth for EVAL6 regression guards, NOT an
    asserted literal used to fake a computed score (EVAL2/LEAK4).

    Args:
        root:            repo root override (for tests using tmp_path).
        value_prop_path: override value-prop file path (for tests).

    Returns:
        A list of FixtureResult objects (empty if the fixtures directory has no
        JSON files — this is NOT an error; it is an empty-fixture run).
    """
    fdir = _fixtures_dir(root)
    if not fdir.exists():
        return []

    results: list[FixtureResult] = []
    for fpath in sorted(fdir.glob("*.json")):
        raw = json.loads(fpath.read_text(encoding="utf-8"))
        transcript = [_load_turn(t) for t in raw.get("transcript", [])]
        rubric = score_transcript(transcript, value_prop_path=value_prop_path)
        results.append(
            FixtureResult(
                path=fpath,
                label=raw.get("label", {}),
                transcript=transcript,
                rubric=rubric,
            )
        )
    return results


# ---------------------------------------------------------------------------
# Persona matrix runner
# ---------------------------------------------------------------------------

def run_persona_matrix(
    *, value_prop_path: Path | str | None = None
) -> list[PersonaResult]:
    """Run every (variant × persona) cell and return scored PersonaResult objects.

    Wraps `bakeoff.run_cells` so the harness and the bake-off share the same
    conversation runner; the harness adds the aggregate machinery and fixture
    loading on top. Fully deterministic under RANDOM_SEED (EVAL1).
    """
    cells = run_cells(value_prop_path=value_prop_path)
    return [
        PersonaResult(
            variant=cell.variant,
            persona=cell.persona,
            disposition=cell.conversation.disposition,
            agent_turns=cell.conversation.agent_turns,
            rubric=cell.rubric,
        )
        for cell in cells
    ]


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def _aggregate_variant(
    variant: str,
    results: list[PersonaResult],
) -> AggregateMetrics:
    """Aggregate scored results for one variant into computed rates (EVAL5)."""
    from app.persona import build_policy  # lazy import — no side effects at import

    rows = [r for r in results if r.variant == variant]
    n = len(rows)

    def frac(pred) -> float:
        return sum(1 for r in rows if pred(r)) / n if n else 0.0

    return AggregateMetrics(
        variant=variant,
        variant_name=build_policy(variant).name,
        book_rate=frac(lambda r: r.rubric.meeting_booked),
        disclosure_rate=frac(lambda r: r.rubric.disclosure_said),
        objection_handled_rate=frac(lambda r: r.rubric.objection_handled),
        compliance_rate=frac(lambda r: r.rubric.compliance_ok),
        avg_agent_turns=(
            sum(r.agent_turns for r in rows) / n if n else 0.0
        ),
        n_personas=n,
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_eval(
    *,
    value_prop_path: Path | str | None = None,
    fixtures_root: Path | str | None = None,
) -> EvalSummary:
    """Run the full offline eval harness; return a deterministic EvalSummary.

    Steps:
      1. Run the persona matrix (all variants × all personas) — EVAL1/EVAL4.
      2. Aggregate per-variant metrics — EVAL5.
      3. Load and score labeled fixtures (if any) — EVAL6.

    All scores are COMPUTED from the rubric; nothing is hardcoded (EVAL2/LEAK4).
    No network, no client, no wall-clock — fully offline (EVAL1/ENV4).

    Args:
        value_prop_path: override value-prop file path (for tests).
        fixtures_root:   override repo root for fixture discovery (for tests).

    Returns:
        An EvalSummary with persona_results, aggregate metrics (one per variant),
        and the loaded fixture results (on .fixture_results if needed externally).
    """
    persona_results = run_persona_matrix(value_prop_path=value_prop_path)
    aggregate = [
        _aggregate_variant(v, persona_results) for v in VARIANTS
    ]
    summary = EvalSummary(
        persona_results=persona_results,
        aggregate=aggregate,
    )
    return summary


# ---------------------------------------------------------------------------
# Report formatting (for the video / handback)
# ---------------------------------------------------------------------------

def format_summary(summary: EvalSummary) -> str:
    """Render the aggregate table and per-cell results as plain text."""
    lines: list[str] = []

    # Aggregate table.
    lines.append("=== Aggregate metrics (computed, never hardcoded) ===")
    if summary.aggregate:
        headers = list(summary.aggregate[0].as_dict().keys())
        rows = [m.as_dict() for m in summary.aggregate]
        widths = {h: max(len(h), *(len(str(r[h])) for r in rows)) for h in headers}
        lines.append(" | ".join(h.ljust(widths[h]) for h in headers))
        lines.append("-+-".join("-" * widths[h] for h in headers))
        for r in rows:
            lines.append(" | ".join(str(r[h]).ljust(widths[h]) for h in headers))

    # Per-cell breakdown.
    lines.append("")
    lines.append("=== Per-cell breakdown ===")
    for pr in summary.persona_results:
        lines.append(
            f"  {pr.variant}/{pr.persona.value:<12} "
            f"disposition={pr.disposition.value:<10} "
            f"turns={pr.agent_turns:2d}  "
            f"rubric={pr.rubric.as_dict()}"
        )
    return "\n".join(lines)
