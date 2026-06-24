"""Secret-hygiene tests: no secret, key, or card number appears in a log line or a tracked file."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# Patterns to grep for (never echo a real value here — these are patterns only)
# Note: bare 3-digit CVV is intentionally excluded (false-positives on ports/line nums)
SECRET_PATTERNS = [
    # 16-digit PAN or 4-4-4-4 grouping (credit card)
    r"\b\d{4}[- ]\d{4}[- ]\d{4}[- ]\d{4}\b",
    r"\b\d{16}\b",
    # API key patterns (sk-, vapi-, etc.)
    r"\bsk-[A-Za-z0-9]{20,}\b",
    r"\bvapi-[A-Za-z0-9_-]{10,}\b",
    # Literal assignments of real secrets in .env style
    r"VAPI_API_KEY\s*=\s*['\"]?[A-Za-z0-9_-]{10,}",
    r"OPENAI_API_KEY\s*=\s*['\"]?sk-",
    r"VAPI_WEBHOOK_SECRET\s*=\s*['\"]?[A-Za-z0-9_-]{10,}",
    r"CALCOM_API_KEY\s*=\s*['\"]?[A-Za-z0-9_-]{10,}",
]

# Files to check — the TRUE would-be-tracked set per the SEC1 contract
# ("across all tracked files"). We ask git for tracked + untracked-not-ignored
# files so gitignored secrets (.env, Home_Assignment_email.md, REFERENCE/, a real
# consent_allowlist.json) are correctly EXCLUDED — not scanned by a loose heuristic
# that both over-scans ignored files and never consults git's actual ignore rules.
TEXT_EXTENSIONS = {".py", ".json", ".md", ".txt", ".toml", ".yaml", ".yml", ".cfg", ".ini"}


def _tracked_files() -> list[Path]:
    """Return text files that are (or would be) git-tracked, excluding gitignored ones.

    Primary: `git ls-files --cached --others --exclude-standard` — exactly the set
    git would track (committed + new-but-not-ignored). Fallback (git unavailable):
    a suffix/dir heuristic that also skips REFERENCE/.
    """
    try:
        out = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        files = []
        for rel in out.splitlines():
            rel = rel.strip()
            if not rel:
                continue
            p = REPO_ROOT / rel
            if p.is_file() and p.suffix in TEXT_EXTENSIONS:
                files.append(p)
        return files
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        skip_dirs = {".venv", ".git", "__pycache__", "receipts", "recordings",
                     "transcripts", "REFERENCE"}
        files = []
        for p in REPO_ROOT.rglob("*"):
            if p.is_file() and p.suffix in TEXT_EXTENSIONS:
                parts = set(p.relative_to(REPO_ROOT).parts)
                if not parts.intersection(skip_dirs):
                    files.append(p)
        return files


class TestSec1NoSecretsInTrackedFiles:

    def test_no_secret_patterns_in_tracked_files(self):
        """Grep all tracked candidate files for secret patterns — must find zero hits."""
        files = _tracked_files()
        hits = []
        for path in files:
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for pattern in SECRET_PATTERNS:
                matches = re.findall(pattern, content)
                if matches:
                    # Filter out the pattern definitions in THIS file (test_sec1.py)
                    if path == Path(__file__):
                        continue
                    hits.append((path.relative_to(REPO_ROOT), pattern, matches))
        assert hits == [], (
            "Secret patterns found in tracked files!\n"
            + "\n".join(
                f"  {p}: pattern={patt!r} matches={m!r}"
                for p, patt, m in hits
            )
        )

    def test_env_example_placeholders_only(self):
        """'.env.example' must not contain real secrets — only placeholder strings."""
        env_example = REPO_ROOT / ".env.example"
        assert env_example.exists(), ".env.example must exist"
        content = env_example.read_text(encoding="utf-8")
        # Check placeholder values (must say 'your_..._here' or similar, not real values)
        assert "your_vapi_api_key_here" in content or "your_" in content, (
            ".env.example must contain placeholder values (e.g. 'your_..._here')"
        )
        # Must NOT have a real sk- key
        assert not re.search(r"\bsk-[A-Za-z0-9]{20,}\b", content), (
            ".env.example must not contain a real OpenAI sk- key"
        )

    def test_env_file_does_not_exist_or_is_gitignored(self):
        """.env must not be committed (it's gitignored)."""
        env_file = REPO_ROOT / ".env"
        if env_file.exists():
            # If it exists locally (developer's .env), check it's in .gitignore
            gitignore = REPO_ROOT / ".gitignore"
            content = gitignore.read_text(encoding="utf-8")
            assert ".env" in content, ".env must be listed in .gitignore"
            # This is fine — .env can exist locally, just not committed

    def test_gitignore_covers_env(self):
        """.gitignore covers .env and .env.* (except .env.example)."""
        gitignore = REPO_ROOT / ".gitignore"
        assert gitignore.exists(), ".gitignore must exist"
        content = gitignore.read_text(encoding="utf-8")
        assert ".env" in content, ".gitignore must contain '.env'"
        assert "!.env.example" in content, ".gitignore must have !.env.example negation"

    def test_gitignore_covers_home_assignment_email(self):
        """Home_Assignment_email.md must be gitignored (may carry the PAN)."""
        gitignore = REPO_ROOT / ".gitignore"
        content = gitignore.read_text(encoding="utf-8")
        assert "Home_Assignment_email.md" in content, (
            "Home_Assignment_email.md must be gitignored (SEC1/LEAK1)"
        )

    def test_gitignore_covers_reference_dir(self):
        """REFERENCE/ must be gitignored (unaudited; may carry other-project secrets)."""
        gitignore = REPO_ROOT / ".gitignore"
        content = gitignore.read_text(encoding="utf-8")
        assert "REFERENCE/" in content, "REFERENCE/ must be gitignored"

    def test_gitignore_covers_consent_allowlist(self):
        """consent_allowlist.* and allowlist.* must be gitignored (real numbers)."""
        gitignore = REPO_ROOT / ".gitignore"
        content = gitignore.read_text(encoding="utf-8")
        assert "consent_allowlist.*" in content or "allowlist.*" in content, (
            "Consent allowlist files must be gitignored"
        )

    def test_consent_allowlist_example_is_tracked(self):
        """consent_allowlist.example.json should NOT be gitignored (it's the placeholder)."""
        gitignore = REPO_ROOT / ".gitignore"
        content = gitignore.read_text(encoding="utf-8")
        assert "!consent_allowlist.example.json" in content, (
            ".gitignore must have !consent_allowlist.example.json negation "
            "so the example is tracked"
        )


# ---------------------------------------------------------------------------
# LEAK5 — OS-agnostic paths (no hardcoded absolute paths in app/)
# ---------------------------------------------------------------------------

class TestLeak5OsAgnosticPaths:
    """LEAK5: grep for hardcoded absolute paths in app/ code."""

    def test_no_hardcoded_absolute_paths_in_app(self):
        """No /Users/..., /home/..., C:\\ etc. in app/ Python files."""
        app_dir = REPO_ROOT / "app"
        abs_path_patterns = [
            r"/Users/[A-Za-z]",   # macOS home
            r"/home/[A-Za-z]",    # Linux home
            r"C:\\\\",            # Windows drive
            r"/opt/homebrew/",    # specific machine path
        ]
        hits = []
        for py_file in app_dir.rglob("*.py"):
            content = py_file.read_text(encoding="utf-8", errors="replace")
            for pattern in abs_path_patterns:
                if re.search(pattern, content):
                    hits.append((py_file.relative_to(REPO_ROOT), pattern))
        assert hits == [], (
            "Hardcoded absolute paths found in app/:\n"
            + "\n".join(f"  {f}: {p}" for f, p in hits)
        )

    def test_config_uses_pathlib_for_repo_root(self):
        """config.py defines REPO_ROOT via pathlib.Path, not a hardcoded string."""
        config_file = REPO_ROOT / "app" / "config.py"
        content = config_file.read_text(encoding="utf-8")
        assert "pathlib" in content or "Path" in content, (
            "config.py must use pathlib.Path for REPO_ROOT"
        )
        assert "__file__" in content, (
            "config.py must derive REPO_ROOT from __file__ (not hardcoded)"
        )
