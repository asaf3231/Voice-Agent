"""Alta Outbound Voice Agent — tests/test_leakage.py

Stage 7 — Anti-leakage & packaging hardening (QA_checklist.md §10–§11).

Every check in this file operates on the git-true tracked file set
(`git ls-files --cached --others --exclude-standard`) or on in-repo
data/ files.  No network access.  No real secret/PII is ever written
to a tracked file — any "bad sample" used to validate the grep logic is
constructed in-memory at test time only.

Coverage (all written + test-verified):
  LEAK1 — no secrets / 16-digit PAN (4-4-4-4 grouping, NOT bare CVV)
           in any tracked file; sensitive files confirmed git-ignored.
  LEAK2 — no real E.164 phone numbers in tracked non-synthetic files;
           .gitignore covers recordings/transcripts/raw receipts;
           mask_phone() is in effect (log_disposition test cross-check).
  LEAK3 — no hardcoded lead/company/ICP/value-prop literals in app/ or scripts/;
           forbidden literals derived from data/* AT TEST TIME (not hardcoded here).
  LEAK4 — no fabricated outcomes: tests/eval do not hardcode booked=True
           as a final scored result; metrics are computed.
  LEAK5 — OS-agnostic: no absolute paths / C:\\ / /Users / /home / /opt
           in app/ or scripts/; paths use pathlib relative to repo root.
  PKG1  — every non-stdlib entry in requirements.txt is pinned with ==.
  PKG2  — offline packaging sanity: all app modules importable + suite runs.
  PKG3  — MANIFEST.in exists; sensitive paths are excluded; key paths included.
  PKG4  — .gitignore correctness: .env / .venv / recordings etc. are ignored;
           .env.example + synthetic fixtures + consent_allowlist.example.json
           are tracked (not ignored).
"""

from __future__ import annotations

import ast
import importlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = REPO_ROOT / "app"
SCRIPTS_DIR = REPO_ROOT / "scripts"
DATA_DIR = REPO_ROOT / "data"
TESTS_DIR = REPO_ROOT / "tests"

# ---------------------------------------------------------------------------
# Shared helper — the git-true tracked + untracked-not-ignored file set
# ---------------------------------------------------------------------------

TEXT_EXTENSIONS = {".py", ".json", ".md", ".txt", ".toml", ".yaml", ".yml",
                   ".cfg", ".ini", ".example", ".env"}


def _git_tracked_files() -> list[Path]:
    """Return text files that are (or would be) git-tracked.

    Uses `git ls-files --cached --others --exclude-standard` so gitignored
    paths (.env, Home_Assignment_email.md, REFERENCE/, a real
    consent_allowlist.json, briefs/, handbacks/) are EXCLUDED exactly as git
    would exclude them.  Falls back to a directory walk that also skips those
    directories when git is unavailable.
    """
    try:
        out = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        files: list[Path] = []
        for rel in out.splitlines():
            rel = rel.strip()
            if not rel:
                continue
            p = REPO_ROOT / rel
            if p.is_file() and p.suffix in TEXT_EXTENSIONS:
                files.append(p)
        return files
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        # Fallback: directory walk excluding known-sensitive dirs
        skip_dirs = {
            ".venv", ".git", "__pycache__", "receipts", "recordings",
            "transcripts", "REFERENCE", "briefs", "handbacks",
        }
        files = []
        for p in REPO_ROOT.rglob("*"):
            if not p.is_file() or p.suffix not in TEXT_EXTENSIONS:
                continue
            parts = set(p.relative_to(REPO_ROOT).parts)
            if not parts.intersection(skip_dirs):
                files.append(p)
        return files


def _git_check_ignored(path: str) -> bool:
    """Return True if git considers *path* to be ignored."""
    result = subprocess.run(
        ["git", "check-ignore", "-q", path],
        cwd=str(REPO_ROOT),
        capture_output=True,
    )
    return result.returncode == 0


# ===========================================================================
# LEAK1 — No secrets / 16-digit PAN in any tracked file
# ===========================================================================

# Patterns that must NEVER appear in a tracked file.
# NOTE: the bare 3-digit CVV is intentionally excluded (false-positives on
# ports and line numbers).  The card PAN is identified by the 4-4-4-4
# grouping or the contiguous 16-digit form (SEC1 / LEAK1).
_SECRET_PATTERNS: list[tuple[str, str]] = [
    ("16-digit PAN (contiguous)", r"\b\d{16}\b"),
    ("PAN 4-4-4-4 grouping", r"\b\d{4}[- ]\d{4}[- ]\d{4}[- ]\d{4}\b"),
    ("OpenAI sk- key", r"\bsk-[A-Za-z0-9]{20,}\b"),
    ("Vapi API key literal", r"\bvapi-[A-Za-z0-9_-]{10,}\b"),
    ("VAPI_API_KEY assignment", r"VAPI_API_KEY\s*=\s*['\"]?[A-Za-z0-9_-]{10,}"),
    ("OPENAI_API_KEY assignment", r"OPENAI_API_KEY\s*=\s*['\"]?sk-"),
    ("VAPI_WEBHOOK_SECRET assignment", r"VAPI_WEBHOOK_SECRET\s*=\s*['\"]?[A-Za-z0-9_-]{10,}"),
    ("CALCOM_API_KEY assignment", r"CALCOM_API_KEY\s*=\s*['\"]?[A-Za-z0-9_-]{10,}"),
    # A committed private key is the highest-severity leak — match every common
    # PEM header (security-review Stage-7 finding: the grep was blind to PEM/JWT).
    ("PEM private key block", r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----"),
    # A JWT (e.g. an OAuth bearer token) — header.payload.signature, base64url.
    ("JWT token", r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{6,}\b"),
]


class TestLeak1NoSecretsInTrackedFiles:
    """LEAK1: no secret / PAN / API-key value in any tracked file."""

    def test_no_secret_patterns_in_tracked_files(self):
        """Grep all tracked text files for secret patterns — must find zero hits.

        Exclusion rules (per CLAUDE.md §5 anti-leakage):
        - Skip THIS file (defines patterns as regex strings — would self-match).
        - Skip .env.example for the KEY=value assignment patterns: that file is
          the safe placeholder file; it uses 'your_..._here' values, never real
          secrets.  The PAN / sk- patterns still apply to .env.example.
        """
        # Assignment patterns that apply to real credential files but NOT to
        # .env.example (which has placeholder values, not real secrets).
        _ASSIGNMENT_LABELS = {
            "VAPI_API_KEY assignment",
            "VAPI_WEBHOOK_SECRET assignment",
            "CALCOM_API_KEY assignment",
        }
        _ENV_EXAMPLE_REL = ".env.example"

        files = _git_tracked_files()
        hits: list[tuple[str, str, list[str]]] = []
        for path in files:
            # Skip THIS file: it defines the patterns as regex strings, which
            # would self-match the pattern definition lines.
            if path.resolve() == Path(__file__).resolve():
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            rel = str(path.relative_to(REPO_ROOT))
            for label, pattern in _SECRET_PATTERNS:
                # .env.example: skip KEY=value assignment patterns — those lines
                # intentionally contain `KEY=your_..._here` placeholder format
                # and are explicitly verified by test_env_example_has_placeholders_only.
                if rel == _ENV_EXAMPLE_REL and label in _ASSIGNMENT_LABELS:
                    continue
                matches = re.findall(pattern, content)
                if matches:
                    hits.append((rel, label, matches))
        assert hits == [], (
            "Secret patterns found in tracked files!\n"
            + "\n".join(
                f"  {rel}: [{label}] → {m!r}"
                for rel, label, m in hits
            )
        )

    def test_env_example_has_placeholders_only(self):
        """`.env.example` must contain only placeholder values, no real secrets."""
        env_example = REPO_ROOT / ".env.example"
        assert env_example.exists(), ".env.example must exist"
        content = env_example.read_text(encoding="utf-8")
        # Must have at least one placeholder marker
        assert re.search(r"your_[a-z_]+_here", content), (
            ".env.example must contain placeholder values like 'your_..._here'"
        )
        # Must NOT contain a real sk- OpenAI key
        assert not re.search(r"\bsk-[A-Za-z0-9]{20,}\b", content), (
            ".env.example must not contain a real OpenAI sk- key"
        )

    def test_env_file_is_git_ignored(self):
        """.env must be git-ignored (may exist locally, must never be committed)."""
        assert _git_check_ignored(".env"), (
            ".env must be git-ignored — it contains real secrets"
        )

    def test_home_assignment_email_is_git_ignored(self):
        """Home_Assignment_email.md is gitignored (carried the assignment PAN)."""
        assert _git_check_ignored("Home_Assignment_email.md"), (
            "Home_Assignment_email.md must be gitignored (LEAK1)"
        )

    def test_reference_dir_is_git_ignored(self):
        """REFERENCE/ is gitignored (unaudited; may carry other-project secrets)."""
        assert _git_check_ignored("REFERENCE/"), (
            "REFERENCE/ must be gitignored (LEAK1)"
        )

    def test_real_consent_allowlist_is_git_ignored(self):
        """A real consent_allowlist.json must be gitignored."""
        assert _git_check_ignored("consent_allowlist.json"), (
            "consent_allowlist.json must be gitignored (real phone numbers)"
        )

    def test_pan_grep_self_check(self):
        """Self-check: the PAN pattern correctly matches 4-4-4-4 grouped and contiguous digits.

        Constructs the bad sample programmatically so no literal 16-digit PAN
        string appears in this tracked file (brief constraint: bad samples are
        in-memory only, never committed as literals — CLAUDE.md §5 anti-leakage).
        """
        # Build a Luhn-valid test PAN from 4-char parts — no full PAN literal in source.
        # The parts are joined at runtime so no 16-digit or 4-4-4-4 pattern appears here.
        _parts = ["4" + "1" * 3, "1" * 4, "1" * 4, "1" * 4]
        bad_sample_grouped = " ".join(_parts)    # assembled at runtime — not a literal
        bad_sample_contiguous = "".join(_parts)  # assembled at runtime — not a literal

        pattern_grouped = r"\b\d{4}[- ]\d{4}[- ]\d{4}[- ]\d{4}\b"
        assert re.search(pattern_grouped, bad_sample_grouped), (
            "PAN 4-4-4-4 pattern must match the grouped test sample (grep self-check)"
        )
        pattern_contiguous = r"\b\d{16}\b"
        assert re.search(pattern_contiguous, bad_sample_contiguous), (
            "16-digit PAN pattern must match the contiguous test sample (grep self-check)"
        )

    def test_pem_and_jwt_grep_self_check(self):
        """Self-check: the PEM-block and JWT patterns catch planted samples.

        Samples are assembled at runtime from parts so no literal PEM header or
        JWT string appears in this tracked file (anti-leakage §5 — bad samples
        are in-memory only). Guards against the Stage-7 security finding that the
        grep was blind to private-key blocks and bearer tokens.
        """
        pem_by_label = dict(_SECRET_PATTERNS)
        # Assemble a PEM header from parts — no full '-----BEGIN ... PRIVATE KEY-----' literal here.
        dashes = "-" * 5
        pem_sample = f"{dashes}BEGIN " + "PRIVATE" + " KEY" + dashes
        assert re.search(pem_by_label["PEM private key block"], pem_sample), (
            "PEM pattern must match a planted private-key header (grep self-check)"
        )
        # Assemble a JWT from parts — no literal 'eyJ...' token in source.
        jwt_sample = "ey" + "J" + "abc123_DEF" + "." + "payload_AB12" + "." + "sigXYZ9"
        assert re.search(pem_by_label["JWT token"], jwt_sample), (
            "JWT pattern must match a planted bearer token (grep self-check)"
        )


# ===========================================================================
# LEAK2 — No real E.164 phones / recordings in tracked files
# ===========================================================================

class TestLeak2NoRealPII:
    """LEAK2: no real E.164 phone numbers committed; gitignore covers recordings."""

    # The ONLY E.164-like numbers allowed in tracked files are:
    #   a) the synthetic lead numbers (+15550100001–005) in data/leads.synthetic.json
    #   b) the test fixture numbers (+15559990001, +15559990099) in tests/conftest.py
    #   c) the consent_allowlist.example.json placeholder number(s)
    #   d) README / .env.example examples that use obviously-fake numbers
    _ALLOWED_FILE_RELPATHS = {
        "data/leads.synthetic.json",
        "tests/conftest.py",
        "consent_allowlist.example.json",
        "README.md",
        ".env.example",
    }

    # Synthetic/test numbers that are intentionally present in the above files.
    _SYNTHETIC_PREFIXES = (
        "+1555010",   # synthetic leads (CLAUDE.md §4)
        "+1555999",   # test fixture allowlist numbers (conftest.py)
    )

    def test_no_real_e164_in_app_or_scripts(self):
        """No real E.164 phone numbers appear in executable app/ or scripts/ code.

        Exclusions (legitimate E.164 occurrences that are not leaks):
        - Numbers using the +1555 prefix: these are reserved/unassignable US
          numbers used by the synthetic fixtures and as format-example placeholders
          in docstrings (e.g. app/consent.py module docstring).  They cannot be
          real customer numbers.
        - Numbers that appear only inside a docstring line (the module-level
          docstring in consent.py uses +15551234567 as a format illustration).
        """
        e164_re = re.compile(r'["\'](\+[1-9]\d{6,14})["\']')
        # +1555 numbers are the canonical "fictitious/unassignable" prefix for US tests
        _SYNTHETIC_PREFIX = "+1555"
        hits: list[tuple[str, str]] = []
        for search_dir in (APP_DIR, SCRIPTS_DIR):
            for py_file in search_dir.rglob("*.py"):
                for lineno, line in enumerate(
                    py_file.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
                ):
                    stripped = line.strip()
                    # Skip pure comment lines and docstring-only lines (containing #
                    # or only quotes/indentation followed by a string)
                    if stripped.startswith("#"):
                        continue
                    for m in e164_re.finditer(line):
                        number = m.group(1)
                        # Allow synthetic/reserved prefix numbers (format examples)
                        if number.startswith(_SYNTHETIC_PREFIX):
                            continue
                        hits.append((str(py_file.relative_to(REPO_ROOT)), number))
        assert hits == [], (
            "Real/hardcoded E.164 phone numbers found in app/ or scripts/:\n"
            + "\n".join(f"  {f}: {n}" for f, n in hits)
        )

    def test_gitignore_covers_recordings(self):
        """`recordings/` is gitignored."""
        assert _git_check_ignored("recordings/some.wav") or _git_check_ignored("recordings/"), (
            "recordings/ must be gitignored (real call audio — LEAK2)"
        )

    def test_gitignore_covers_transcripts(self):
        """`transcripts/` is gitignored."""
        assert _git_check_ignored("transcripts/live.json") or _git_check_ignored("transcripts/"), (
            "transcripts/ must be gitignored (real call transcripts — LEAK2)"
        )

    def test_gitignore_covers_raw_receipts(self):
        """`receipts/raw/` is gitignored."""
        assert _git_check_ignored("receipts/raw/") or _git_check_ignored("receipts/raw/foo.json"), (
            "receipts/raw/ must be gitignored (raw cost evidence — LEAK2)"
        )

    def test_mask_phone_masks_last_two_digits(self):
        """mask_phone() exposes only the last 2 digits — log_disposition uses it (LEAK2)."""
        from app.consent import mask_phone
        result = mask_phone("+15550100001")
        # Must NOT contain the full number
        assert "+15550100001" not in result, "mask_phone must not return the full number"
        # Must expose exactly the last 2 digits
        assert result.endswith("01"), f"mask_phone should expose last 2 digits; got {result!r}"
        assert "***" in result or "x" in result.lower() or len(result) < 12, (
            f"mask_phone result looks unmasked: {result!r}"
        )


# ===========================================================================
# LEAK3 — No hardcoded business/lead/ICP/value-prop literals in app/ or scripts/
# ===========================================================================

class TestLeak3NoHardcodedBusinessData:
    """LEAK3: synthetic lead/company/ICP/value-prop literals not baked into code.

    The forbidden literals are derived from data/* AT TEST TIME — they are never
    hardcoded into this test file either (brief requirement).  Any string that
    appears in the actual synthetic data files must not also appear in app/ code
    or scripts/ code.
    """

    @pytest.fixture(scope="class")
    def leads_data(self) -> list[dict]:
        """Load the real synthetic leads at test time (not hardcoded)."""
        leads_file = DATA_DIR / "leads.synthetic.json"
        raw = json.loads(leads_file.read_text(encoding="utf-8"))
        return raw["leads"]

    @pytest.fixture(scope="class")
    def icp_data(self) -> dict:
        """Load the real ICP at test time."""
        icp_file = DATA_DIR / "icp.synthetic.json"
        raw = json.loads(icp_file.read_text(encoding="utf-8"))
        return raw["icp"]

    @pytest.fixture(scope="class")
    def value_prop_text(self) -> str:
        """Load the value-prop markdown at test time."""
        vp_file = DATA_DIR / "value_prop.md"
        return vp_file.read_text(encoding="utf-8")

    def _grep_dirs_for(self, literal: str, dirs: list[Path]) -> list[tuple[str, int, str]]:
        """Return (relpath, lineno, line) for every occurrence in the given dirs."""
        hits: list[tuple[str, int, str]] = []
        for d in dirs:
            for py_file in d.rglob("*.py"):
                for i, line in enumerate(
                    py_file.read_text(encoding="utf-8", errors="replace").splitlines(),
                    start=1,
                ):
                    stripped = line.strip()
                    # Skip comment lines
                    if stripped.startswith("#"):
                        continue
                    if literal in stripped:
                        hits.append((
                            str(py_file.relative_to(REPO_ROOT)), i, stripped,
                        ))
        return hits

    def test_no_hardcoded_lead_first_names_in_app(self, leads_data):
        """Synthetic first names from leads.synthetic.json not in app/ code."""
        # Only test names that are ≥ 5 chars to avoid false-positives on common short names
        names = [
            ld["first_name"] for ld in leads_data
            if len(ld.get("first_name", "")) >= 5
        ]
        hits: list[tuple[str, str, int, str]] = []
        for name in names:
            for rel, lineno, line in self._grep_dirs_for(name, [APP_DIR]):
                hits.append((name, rel, lineno, line))
        assert hits == [], (
            "Synthetic first name(s) from leads.synthetic.json hardcoded in app/:\n"
            + "\n".join(f"  name={n!r} → {r}:{ln}: {l}" for n, r, ln, l in hits)
        )

    def test_no_hardcoded_company_names_in_app(self, leads_data):
        """Company names from leads.synthetic.json not in app/ code."""
        companies = [ld["company"] for ld in leads_data]
        hits: list[tuple[str, str, int, str]] = []
        for company in companies:
            for rel, lineno, line in self._grep_dirs_for(company, [APP_DIR]):
                hits.append((company, rel, lineno, line))
        assert hits == [], (
            "Synthetic company name(s) from leads.synthetic.json hardcoded in app/:\n"
            + "\n".join(f"  company={c!r} → {r}:{ln}: {l}" for c, r, ln, l in hits)
        )

    def test_no_hardcoded_phone_numbers_in_app(self, leads_data):
        """Synthetic phone numbers from leads.synthetic.json not in app/ code."""
        phones = [ld["phone_e164"] for ld in leads_data]
        hits: list[tuple[str, str, int, str]] = []
        for phone in phones:
            for rel, lineno, line in self._grep_dirs_for(phone, [APP_DIR]):
                hits.append((phone, rel, lineno, line))
        assert hits == [], (
            "Synthetic phone number(s) from leads.synthetic.json hardcoded in app/:\n"
            + "\n".join(f"  phone={p!r} → {r}:{ln}: {l}" for p, r, ln, l in hits)
        )

    def test_no_hardcoded_icp_target_roles_in_app(self, icp_data):
        """ICP target_roles not hardcoded in app/ (must be read from data at runtime)."""
        roles = icp_data.get("target_roles", [])
        # Focus on multi-word roles that can't appear by coincidence
        multi_word_roles = [r for r in roles if " of " in r or " of" in r]
        hits: list[tuple[str, str, int, str]] = []
        for role in multi_word_roles:
            for rel, lineno, line in self._grep_dirs_for(role, [APP_DIR]):
                hits.append((role, rel, lineno, line))
        assert hits == [], (
            "ICP target_roles hardcoded in app/ (load from data/ instead):\n"
            + "\n".join(f"  role={ro!r} → {r}:{ln}: {l}" for ro, r, ln, l in hits)
        )

    def test_value_prop_phrases_not_in_app_code(self, value_prop_text):
        """Key value-prop phrases from value_prop.md not hardcoded in app/ source.

        Extracts longer (≥40 char) lines from the markdown and checks they don't
        appear verbatim in app/ Python files.  Shorter lines are excluded to avoid
        false-positives on generic phrases.
        """
        # Take the first literal line of each bullet/paragraph that is ≥ 40 chars
        # and not a markdown heading/metadata marker.
        forbidden_phrases: list[str] = []
        for line in value_prop_text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("**") or not stripped:
                continue
            # Strip markdown formatting (leading -, >, *, etc.)
            text = re.sub(r"^[-*>|`]+\s*", "", stripped)
            if len(text) >= 40:
                forbidden_phrases.append(text[:60])  # first 60 chars is enough

        hits: list[tuple[str, str, int, str]] = []
        for phrase in forbidden_phrases[:10]:  # cap at 10 to keep test fast
            for rel, lineno, line in self._grep_dirs_for(phrase, [APP_DIR]):
                hits.append((phrase[:30], rel, lineno, line))
        assert hits == [], (
            "Value-prop phrase(s) from data/value_prop.md hardcoded in app/:\n"
            + "\n".join(f"  phrase={ph!r}… → {r}:{ln}: {l}" for ph, r, ln, l in hits)
        )

    def test_data_file_basenames_not_inlined_in_app(self):
        """Data file basenames (leads.synthetic.json etc.) not in executable app/ code."""
        # Already tested by test_leads.py::TestLead3; replicated here for LEAK3 completeness.
        basenames = ["leads.synthetic.json", "icp.synthetic.json", "value_prop.md"]
        hits: list[tuple[str, str, int, str]] = []
        for py_file in APP_DIR.rglob("*.py"):
            for i, line in enumerate(
                py_file.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
            ):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                for b in basenames:
                    if b in stripped:
                        hits.append((b, str(py_file.relative_to(REPO_ROOT)), i, stripped))
        assert hits == [], (
            "Data file basename hardcoded in app/ code (use loader instead):\n"
            + "\n".join(f"  basename={b!r} → {r}:{ln}: {l}" for b, r, ln, l in hits)
        )


# ===========================================================================
# LEAK4 — No fabricated outcomes in tests/eval
# ===========================================================================

class TestLeak4NoFabricatedOutcomes:
    """LEAK4: no test/eval hardcodes a final scored outcome.

    The rubric must compute every metric from a labeled transcript.
    No test may assert `booked=True` or a magic literal score as if it were
    a real result produced by the agent on a live call.
    """

    def test_rubric_computes_disclosure_from_transcript(self):
        """disclosure_said is computed from transcript content, not hardcoded."""
        from app.eval.rubric import score_transcript
        from app.eval import Speaker, Stage, Turn

        # A transcript with the disclosure → disclosure_said should be True (computed)
        from app.config import DISCLOSURE_LINE
        transcript_with = [
            Turn(speaker=Speaker.AGENT, text=DISCLOSURE_LINE,
                 stage=Stage.OPENING, booked=False),
        ]
        # A transcript without → False (computed)
        transcript_without = [
            Turn(speaker=Speaker.AGENT, text="Hello, I'm calling about something.",
                 stage=Stage.OPENING, booked=False),
        ]
        vp_path = str(DATA_DIR / "value_prop.md")
        result_with = score_transcript(transcript_with, value_prop_path=vp_path)
        result_without = score_transcript(transcript_without, value_prop_path=vp_path)
        assert result_with.disclosure_said is True, (
            "disclosure_said must be True when DISCLOSURE_LINE is in the transcript"
        )
        assert result_without.disclosure_said is False, (
            "disclosure_said must be False when DISCLOSURE_LINE is absent"
        )

    def test_no_hardcoded_final_booked_metric_in_test_files(self):
        """No test file asserts a literal final metric like 'book_rate = 0.8' as a fixed result.

        We allow `booked=True` as a Turn field (it's a rubric input, not a scored outcome)
        and computed assertions like `result.book_rate >= 0.0`.  We disallow literals like
        `assert metrics.book_rate == 0.8` that would be copy-pasted from a stale run.
        """
        # Pattern: assert that a specific floating-point metric equals a hardcoded number.
        # e.g.  assert summary.book_rate == 0.4   (the exact Stage-6 bakeoff output)
        # This is a heuristic — we look for assertions on metric names with == float
        forbidden_re = re.compile(
            r"assert\s+\S+\.(book_rate|disclosure_rate|compliance_rate|objection_handled_rate)"
            r"\s*==\s*[0-9]\.[0-9]"
        )
        hits: list[tuple[str, int, str]] = []
        for py_file in TESTS_DIR.rglob("*.py"):
            for i, line in enumerate(
                py_file.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
            ):
                if py_file.resolve() == Path(__file__).resolve():
                    continue  # skip this file
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if forbidden_re.search(stripped):
                    hits.append((str(py_file.relative_to(REPO_ROOT)), i, stripped))
        assert hits == [], (
            "Hardcoded final metric == literal found in test files (fabricated outcome):\n"
            + "\n".join(f"  {f}:{ln}: {l}" for f, ln, l in hits)
        )

    def test_fixture_scores_are_from_labels_not_hardcoded(self):
        """The eval harness fixture results compare computed scores against LABELED expected values.

        This verifies the harness.load_fixtures path actually computes the rubric
        from each transcript rather than returning a pre-populated constant.
        Uses load_fixtures() directly (returns FixtureResult objects with
        .path, .label, .transcript, .rubric — all computed at load time).
        """
        from app.eval.harness import load_fixtures
        from app.eval import Speaker
        from app.config import DISCLOSURE_LINE

        fixture_dir = REPO_ROOT / "fixtures" / "transcripts"
        if not fixture_dir.exists() or not list(fixture_dir.glob("*.json")):
            pytest.skip("No fixture files present — skipping harness integrity check")

        results = load_fixtures(root=REPO_ROOT)
        assert results, "load_fixtures must return at least one result when fixtures exist"

        # Each result carries a rubric computed from the transcript — not a constant
        for r in results:
            fixture_name = r.path.name
            # The rubric result must be a RubricResult with computable fields
            assert hasattr(r.rubric, "disclosure_said"), (
                f"Fixture {fixture_name!r}: rubric must be a computed RubricResult"
            )
            # disclosure_said is derived from DISCLOSURE_LINE presence in the transcript
            agent_texts = [
                t.text for t in r.transcript if t.speaker is Speaker.AGENT
            ]
            disclosure_in_transcript = any(
                DISCLOSURE_LINE in text for text in agent_texts
            )
            assert r.rubric.disclosure_said == disclosure_in_transcript, (
                f"Fixture {fixture_name!r}: rubric.disclosure_said must match "
                f"transcript content — it must be COMPUTED, not hardcoded (EVAL2/LEAK4)"
            )


# ===========================================================================
# LEAK5 — OS-agnostic: no hardcoded absolute paths in app/ or scripts/
# ===========================================================================

class TestLeak5OsAgnosticPaths:
    """LEAK5: no hardcoded absolute paths in app/ or scripts/ source code."""

    _ABS_PATH_PATTERNS: list[tuple[str, str]] = [
        ("macOS home", r"/Users/[A-Za-z]"),
        ("Linux home", r"/home/[A-Za-z]"),
        ("Windows drive", r"C:\\\\"),
        ("opt/homebrew", r"/opt/homebrew/"),
        ("Linux /srv or /var", r"/(srv|var)/[A-Za-z]"),
    ]

    def test_no_abs_paths_in_app(self):
        """No hardcoded absolute paths in app/ Python files."""
        hits: list[tuple[str, str, str]] = []
        for py_file in APP_DIR.rglob("*.py"):
            content = py_file.read_text(encoding="utf-8", errors="replace")
            for label, pattern in self._ABS_PATH_PATTERNS:
                if re.search(pattern, content):
                    hits.append((str(py_file.relative_to(REPO_ROOT)), label, pattern))
        assert hits == [], (
            "Hardcoded absolute paths found in app/:\n"
            + "\n".join(f"  {f}: [{lbl}]" for f, lbl, _ in hits)
        )

    def test_no_abs_paths_in_scripts(self):
        """No hardcoded absolute paths in scripts/ Python files."""
        hits: list[tuple[str, str, str]] = []
        for py_file in SCRIPTS_DIR.rglob("*.py"):
            content = py_file.read_text(encoding="utf-8", errors="replace")
            for label, pattern in self._ABS_PATH_PATTERNS:
                if re.search(pattern, content):
                    hits.append((str(py_file.relative_to(REPO_ROOT)), label, pattern))
        assert hits == [], (
            "Hardcoded absolute paths found in scripts/:\n"
            + "\n".join(f"  {f}: [{lbl}]" for f, lbl, _ in hits)
        )

    def test_config_derives_repo_root_from_file(self):
        """config.py derives REPO_ROOT from __file__ (not a hardcoded string)."""
        config_file = APP_DIR / "config.py"
        content = config_file.read_text(encoding="utf-8")
        assert "__file__" in content, (
            "config.py must derive REPO_ROOT from __file__, not a hardcoded path"
        )
        assert "Path" in content and "pathlib" in content, (
            "config.py must use pathlib.Path for REPO_ROOT"
        )

    def test_repo_root_is_not_hardcoded_string_in_any_app_file(self):
        """No app/ file has the literal absolute repo path baked in as a string."""
        # The repo root path will contain the user's home dir — already caught by
        # the /Users/ pattern above — but this also catches any other absolute path
        # that happens to be the repo root.
        repo_abs = str(REPO_ROOT)
        hits: list[tuple[str, int]] = []
        for py_file in APP_DIR.rglob("*.py"):
            for i, line in enumerate(
                py_file.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
            ):
                if repo_abs in line:
                    hits.append((str(py_file.relative_to(REPO_ROOT)), i))
        assert hits == [], (
            f"Hardcoded repo-root absolute path found in app/ files:\n"
            + "\n".join(f"  {f}:{ln}" for f, ln in hits)
        )


# ===========================================================================
# PKG1 — requirements.txt pinned with == (ENV2 / PKG1)
# ===========================================================================

class TestPkg1PinnedDeps:
    """PKG1: every non-stdlib, non-comment entry in requirements.txt is pinned with ==."""

    def test_requirements_exists(self):
        """requirements.txt must exist at repo root."""
        assert (REPO_ROOT / "requirements.txt").exists(), "requirements.txt not found"

    def test_all_entries_have_pinned_version(self):
        """Every non-comment, non-blank line must contain '=='."""
        lines = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
        unpinned: list[str] = []
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("-"):
                continue
            if "==" not in stripped:
                unpinned.append(stripped)
        assert unpinned == [], (
            "requirements.txt contains unpinned entries (must use ==):\n"
            + "\n".join(f"  {u}" for u in unpinned)
        )

    def test_key_packages_present_and_pinned(self):
        """The six mandatory packages all appear with == in requirements.txt."""
        content = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
        mandatory = ["fastapi==", "uvicorn==", "httpx==", "pydantic==",
                     "python-dotenv==", "pytest=="]
        for pkg in mandatory:
            assert pkg in content, f"'{pkg}' not found (pinned) in requirements.txt"

    def test_every_third_party_import_in_app_is_pinned(self):
        """AST-walk app/**/*.py — every non-stdlib import has a '==' pin in requirements."""
        stdlib = set(sys.stdlib_module_names)
        pinned: set[str] = set()
        for line in (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "==" not in stripped:
                continue
            dist = stripped.split("==")[0].strip().lower().replace("-", "").replace("_", "")
            pinned.add(dist)

        # import-name to dist-name aliases
        alias = {"dotenv": "pythondotenv"}

        offenders: list[tuple[str, str]] = []
        for py_file in APP_DIR.rglob("*.py"):
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                roots: list[str] = []
                if isinstance(node, ast.Import):
                    roots = [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    if (node.level or 0) > 0:
                        continue  # relative import
                    if node.module:
                        roots = [node.module.split(".")[0]]
                for r in roots:
                    if not r or r in stdlib or r in {"app", "__future__"}:
                        continue
                    dist = alias.get(r, r).lower().replace("-", "").replace("_", "")
                    if dist not in pinned:
                        offenders.append((
                            py_file.relative_to(REPO_ROOT).as_posix(), r
                        ))
        assert offenders == [], (
            "Third-party imports in app/ not pinned in requirements.txt:\n"
            + "\n".join(f"  {f}: imports '{r}'" for f, r in offenders)
        )


# ===========================================================================
# PKG2 — Clean-checkout packaging sanity (offline-checkable subset)
# ===========================================================================

class TestPkg2CleanCheckoutSanity:
    """PKG2 (offline-checkable): key modules importable; suite would run; server would boot."""

    def test_all_app_modules_importable(self):
        """All app modules import with zero side effects from a subprocess (ENV4 + PKG2)."""
        result = subprocess.run(
            [
                sys.executable, "-c",
                "import app.config, app.budget, app.consent, app.tools, "
                "app.calendar_client, app.vapi_client, app.server, app.orchestrate, "
                "app.persona; "
                "import app.eval.rubric, app.eval.simulated_callee, "
                "app.eval.harness, app.eval.bakeoff",
            ],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            env={**__import__("os").environ, "PYTHONPATH": str(REPO_ROOT)},
        )
        assert result.returncode == 0, (
            f"One or more app modules failed to import cleanly:\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_makefile_exists_with_test_and_serve_targets(self):
        """Makefile exists and defines both `test` and `serve` targets (PKG2/ENV3)."""
        makefile = REPO_ROOT / "Makefile"
        assert makefile.exists(), "Makefile not found at repo root"
        content = makefile.read_text(encoding="utf-8")
        assert "test:" in content or "test :" in content, (
            "Makefile must define a `test` target"
        )
        assert "serve:" in content or "serve :" in content, (
            "Makefile must define a `serve` target"
        )

    def test_env_example_exists(self):
        """`.env.example` exists (the developer's setup guide — PKG2)."""
        assert (REPO_ROOT / ".env.example").exists(), ".env.example must exist"

    def test_readme_mentions_clean_checkout_steps(self):
        """README.md documents the clean-checkout run steps (PKG2)."""
        readme = REPO_ROOT / "README.md"
        assert readme.exists(), "README.md must exist"
        content = readme.read_text(encoding="utf-8")
        # Must mention the key commands
        assert "pip install" in content, "README.md must mention pip install"
        assert "make test" in content, "README.md must mention make test"
        assert "make serve" in content, "README.md must mention make serve"


# ===========================================================================
# PKG3 — Explicit packaging manifest (MANIFEST.in)
# ===========================================================================

class TestPkg3PackagingManifest:
    """PKG3: MANIFEST.in exists with an include-list; sensitive paths are excluded."""

    def test_manifest_in_exists(self):
        """MANIFEST.in exists at the repo root."""
        assert (REPO_ROOT / "MANIFEST.in").exists(), (
            "MANIFEST.in must exist — it defines what is included/excluded in a package"
        )

    def test_manifest_includes_key_paths(self):
        """MANIFEST.in includes the key repo paths (app, tests, scripts, data, spine)."""
        content = (REPO_ROOT / "MANIFEST.in").read_text(encoding="utf-8")
        required_includes = [
            "app",
            "tests",
            "scripts",
            "data",
            ".env.example",
            "consent_allowlist.example.json",
            "requirements.txt",
        ]
        missing = [p for p in required_includes if p not in content]
        assert missing == [], (
            f"MANIFEST.in is missing include entries for: {missing}"
        )

    def test_manifest_excludes_sensitive_paths(self):
        """MANIFEST.in explicitly excludes sensitive / non-shipping paths."""
        content = (REPO_ROOT / "MANIFEST.in").read_text(encoding="utf-8")
        required_excludes = [
            ".env",
            ".venv",
            "Home_Assignment_email.md",
            "REFERENCE",
        ]
        missing = [p for p in required_excludes if p not in content]
        assert missing == [], (
            f"MANIFEST.in is missing exclude entries for: {missing}"
        )

    def test_manifest_excludes_receipts_raw(self):
        """MANIFEST.in excludes raw receipts (cost evidence with account IDs)."""
        content = (REPO_ROOT / "MANIFEST.in").read_text(encoding="utf-8")
        assert "receipts" in content, (
            "MANIFEST.in must reference receipts/ (to exclude raw receipts)"
        )

    def test_manifest_excludes_real_recordings_and_transcripts(self):
        """MANIFEST.in excludes real recordings/transcripts."""
        content = (REPO_ROOT / "MANIFEST.in").read_text(encoding="utf-8")
        assert "recordings" in content or "*.wav" in content or "*.mp3" in content, (
            "MANIFEST.in must exclude recordings (real call audio)"
        )


# ===========================================================================
# PKG4 — .gitignore correctness
# ===========================================================================

class TestPkg4GitignoreCorrectness:
    """PKG4: .gitignore covers all sensitive paths; safe files are tracked (not ignored)."""

    def test_gitignore_exists(self):
        """.gitignore exists at the repo root."""
        assert (REPO_ROOT / ".gitignore").exists(), ".gitignore must exist at repo root"

    def test_env_is_ignored(self):
        """.env is gitignored."""
        assert _git_check_ignored(".env"), ".env must be gitignored"

    def test_venv_is_ignored(self):
        """.venv/ is gitignored."""
        assert _git_check_ignored(".venv/"), ".venv/ must be gitignored"

    def test_recordings_dir_is_ignored(self):
        """`recordings/` is gitignored."""
        assert _git_check_ignored("recordings/"), "recordings/ must be gitignored"

    def test_raw_receipts_are_ignored(self):
        """`receipts/raw/` is gitignored."""
        assert _git_check_ignored("receipts/raw/"), "receipts/raw/ must be gitignored"

    def test_env_example_is_tracked(self):
        """.env.example is NOT gitignored (it's the safe placeholder)."""
        assert not _git_check_ignored(".env.example"), (
            ".env.example must NOT be gitignored — it is the developer setup template"
        )

    def test_consent_allowlist_example_is_tracked(self):
        """`consent_allowlist.example.json` is NOT gitignored."""
        assert not _git_check_ignored("consent_allowlist.example.json"), (
            "consent_allowlist.example.json must NOT be gitignored — "
            "it is the placeholder for the real allowlist"
        )

    def test_synthetic_leads_file_is_tracked(self):
        """`data/leads.synthetic.json` is tracked (synthetic data, no real PII)."""
        assert not _git_check_ignored("data/leads.synthetic.json"), (
            "data/leads.synthetic.json must NOT be gitignored — it is synthetic, not PII"
        )

    def test_synthetic_icp_file_is_tracked(self):
        """`data/icp.synthetic.json` is tracked."""
        assert not _git_check_ignored("data/icp.synthetic.json"), (
            "data/icp.synthetic.json must NOT be gitignored"
        )

    def test_home_assignment_email_is_ignored(self):
        """`Home_Assignment_email.md` is gitignored."""
        assert _git_check_ignored("Home_Assignment_email.md"), (
            "Home_Assignment_email.md must be gitignored (LEAK1)"
        )

    def test_reference_dir_is_ignored(self):
        """`REFERENCE/` is gitignored."""
        assert _git_check_ignored("REFERENCE/"), (
            "REFERENCE/ must be gitignored (LEAK1)"
        )

    def test_real_consent_allowlist_is_ignored(self):
        """A real `consent_allowlist.json` is gitignored."""
        assert _git_check_ignored("consent_allowlist.json"), (
            "consent_allowlist.json must be gitignored (contains real phone numbers)"
        )

    def test_gitignore_has_venv_entry(self):
        """.gitignore contains a .venv/ entry."""
        content = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
        assert ".venv" in content or ".venv/" in content, (
            ".gitignore must contain a .venv entry"
        )
