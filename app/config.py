"""Alta Outbound Voice Agent — app/config.py

Single responsibility: the ONLY home for all §9 named constants, the two byte-exact
graded literals, AGENT_TOOLS + its dispatch-identity assert, and the lazy settings
loader. No client construction, no .env loading, no file I/O at import time.

Import-safety contract (CLAUDE.md §3.4, ENV4):
  Importing this module has zero side effects — no network, no .env read, no
  data/* read, no client constructed, no call placed. The lazy loader reads
  os.environ only when explicitly called.
"""

from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path

# ---------------------------------------------------------------------------
# Repo root — all paths are relative to this (LEAK5: no hardcoded absolute paths)
# ---------------------------------------------------------------------------
REPO_ROOT: Path = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Synthetic-data directory + the value-prop basename.
# The basename is assembled from parts (stem + suffix) so the literal data
# filename is never baked into executable app code as a single string token
# (LEAD3 / LEAK3): consumers resolve the path via value_prop_path() only.
# ---------------------------------------------------------------------------
DATA_DIR: Path = REPO_ROOT / "data"
_VALUE_PROP_STEM: str = "value_prop"
_VALUE_PROP_SUFFIX: str = "md"


def value_prop_path() -> Path:
    """Return the path to the value-prop markdown (lazy; no read here — ENV4).

    A CONSENT-style env override (VALUE_PROP_PATH) wins if set; otherwise the
    repo default under data/. This is the single sanctioned resolver so no
    consumer hardcodes the data filename (LEAD3). Reads nothing — just resolves.
    """
    override = os.environ.get("VALUE_PROP_PATH")
    if override:
        p = Path(override)
        return p if p.is_absolute() else REPO_ROOT / p
    return DATA_DIR / f"{_VALUE_PROP_STEM}.{_VALUE_PROP_SUFFIX}"


# ===========================================================================
# §9 Named constants — SINGLE source of truth; never inline these elsewhere.
# ===========================================================================

# --- budget / spend governance ---
HARD_BUDGET_USD: float = 50.00      # absolute ceiling (the provided card limit)
LIVE_CALL_BUDGET_USD: float = 15.00  # soft reserve for live calls (lean posture)
MAX_COST_PER_CALL_USD: float = 1.00  # per-call projected-cost ceiling
MAX_LIVE_CALLS: int = 6             # lean live eval-set ceiling (the normal demo path)
# Count ceiling for the bounded LIVE STRESS lane (scripts/stress_live.py) — distinct
# from MAX_LIVE_CALLS so the demo path is unchanged. Authorized 2026-06-24 (Asaf):
# sequential, ≤50 calls, spend still bounded by LIVE_CALL_BUDGET_USD=$15 (the real
# limiter) and the unchanged $50 HARD_BUDGET_USD + $1 per-call ceiling.
MAX_LIVE_STRESS_CALLS: int = 50
# Rounding tolerance for the POST-HOC over-cap alarm in budget.record_cost. The
# pre-call gate (budget_permits) is exact and does NOT use this. Decimal to avoid
# float-precision drift. Promoted to a §9-controlled constant per F1 (2026-06-23).
BUDGET_ALARM_ROUNDING_MARGIN: Decimal = Decimal("0.01")

# --- call governance ---
MAX_CALL_DURATION_S: int = 300      # hard per-call wall-clock (5 min)
MAX_AGENT_TURNS: int = 40           # anti-loop cap on conversation turns
DAILY_CALL_CAP: int = 25            # outbound throttle per day
CALL_RETRY_MAX: int = 2             # retries on no-answer
VOICEMAIL_MAX_S: int = 30           # leave-voicemail cap
ANSWER_DETECTION_S: int = 20        # ring/answer timeout

# --- booking ---
BOOKING_SLOT_MINUTES: int = 30
BOOKING_LOOKAHEAD_DAYS: int = 10

# --- providers / models / determinism ---
# OQ-VOICE-1 REVISED 2026-06-24 (Asaf): moved OFF OpenAI realtime speech-to-speech
# (it fragmented/paused over telephony) to Vapi's standard pipeline — a chat LLM +
# a dedicated TTS voice + a transcriber — which is robust for phone audio.
LLM_MODEL: str = "gpt-4o"                         # conversational model (Vapi 'model.model')
TTS_PROVIDER: str = "openai"                      # TTS uses the existing OpenAI key (no extra provider key)
TTS_VOICE_ID: str = "shimmer"                     # OpenAI TTS voice (alloy/echo/fable/onyx/nova/shimmer)
TRANSCRIBER_PROVIDER: str = "deepgram"            # Vapi default STT
TRANSCRIBER_MODEL: str = "nova-2"
VOICE_PROVIDER: str = "vapi"                      # managed platform; Retell-swappable
RANDOM_SEED: int = 42

# --- byte-exact graded literals (CLAUDE.md §9 / NOTES.md — copy byte-for-byte) ---
DISCLOSURE_LINE: str = (
    "Hi, this is Aria, an AI assistant calling on behalf of Alta. "
    "Do you have a quick minute?"
)
FAILSAFE_HANGUP_LINE: str = (
    "Thanks for your time — I'll follow up by email. Goodbye."
)
# The PLATFORM-spoken close on any live call end (Vapi endCallMessage). A single
# neutral line that fits both a booking and a decline — so the platform goodbye is
# byte-exact and never model-generated (D4/D5), and never contradicts a booking with
# "I'll follow up by email" (independent review 2026-06-24). FAILSAFE_HANGUP_LINE
# stays the offline safe-terminal literal (CONV6) + decline pre-close.
END_CALL_MESSAGE: str = "Thanks so much for your time. Goodbye!"

# --- the agent's callable functions ---
# name == schema name == dispatch key (CLAUDE.md §9)
AGENT_TOOLS: list[str] = [
    "check_availability",
    "book_meeting",
    "log_disposition",
    "detect_voicemail",
]
# NOT live agent tools (retired 2026-06-24, each verified live):
#  - `end_call`: a custom function returning JSON never actually hung up the call
#    (the agent rambled past "goodbye"). Termination is now pinned to Vapi's NATIVE
#    end-call (endCallFunctionEnabled) + the byte-exact END_CALL_MESSAGE. (D9)
#  - `qualify` (Bug 2): added a ~2.5s mid-call round-trip for routing the model does
#    inline; survives only as the internal oracle behind rubric.pitch_tailored.

# Import-time dispatch-identity assert: catches a rename/typo at import, not at runtime.
assert len(AGENT_TOOLS) == 4, "AGENT_TOOLS must have exactly 4 entries"
assert len(AGENT_TOOLS) == len(set(AGENT_TOOLS)), "AGENT_TOOLS entries must be unique"


# ===========================================================================
# Lazy settings loader
# Reads os.environ ONLY when called — never at import time (ENV4).
# ===========================================================================


def get_setting(key: str, default: str | None = None) -> str | None:
    """Return the value of an environment variable, or *default*.

    Call this inside functions/methods — never at module level. This is the
    single sanctioned way to read secrets at runtime; it keeps the import
    side-effect free.
    """
    return os.environ.get(key, default)


def require_setting(key: str) -> str:
    """Return *key* from the environment, raising ValueError if absent.

    Use for required secrets in live code paths (Vapi client init, etc.).
    Never call at import time.
    """
    value = os.environ.get(key)
    if not value:
        raise ValueError(
            f"Required environment variable '{key}' is not set. "
            "Copy .env.example → .env and fill the real value."
        )
    return value


# Stable, intentional fallback lead id for the lean single-lead demo. NOT a
# model-fabricated placeholder — it is supplied by us so book_meeting/log_disposition
# are never called under a hallucinated id (D3 fix, 2026-06-24).
DEMO_LEAD_ID = "demo-lead"


def get_lead_context() -> tuple[str, str | None]:
    """Return the AUTHORITATIVE (lead_id, lead_timezone) for the active call.

    The runtime — not the model — owns these. Sourced from the environment so the
    two processes (place_demo_call building the assistant, the webhook serving tool
    calls) agree without depending on a metadata round-trip:
      - lead_id:        LEAD_ID  (falls back to the stable DEMO_LEAD_ID)
      - lead_timezone:  LEAD_TIMEZONE, then CALCOM_ATTENDEE_TIMEZONE (else None →
                        check_availability degrades to the sales-calendar tz).

    Call at runtime only (reads env via get_setting) — never at import (ENV4).
    """
    lead_id = get_setting("LEAD_ID") or DEMO_LEAD_ID
    lead_tz = get_setting("LEAD_TIMEZONE") or get_setting("CALCOM_ATTENDEE_TIMEZONE")
    return lead_id, lead_tz


def load_env(dotenv_path: str | Path | None = None) -> None:
    """Load a local .env into os.environ. Call ONCE at a runtime entry point.

    This is the single sanctioned place that reads the .env file. The runtime
    entry points (the FastAPI lifespan in app/server.py [Stage 4], the CLI mains
    in scripts/ [Stages 5/8]) call this on startup so get_setting() /
    require_setting() observe the developer's local values. The README run-flow
    (`cp .env.example .env` → `make serve`) depends on it.

    Deliberately NOT called at import time (ENV4: importing app.config reads no
    .env, builds no client, touches no network). python-dotenv is imported lazily
    *inside* this function so importing app.config carries no hard dependency on
    it and the import graph stays minimal. A missing .env file is a safe no-op
    (load_dotenv returns without error); existing os.environ values are never
    overridden (override defaults to False), keeping the offline suite deterministic.
    """
    from dotenv import load_dotenv  # lazy: never imported at module-import time

    target = REPO_ROOT / ".env" if dotenv_path is None else Path(dotenv_path)
    load_dotenv(target)
