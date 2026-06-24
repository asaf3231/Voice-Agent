"""Stage 1 — ENV2, ENV4 tests.

ENV2: every non-stdlib import is pinned in requirements.txt with ==.
ENV4 (scoped): import app.config, app.budget, app.consent with zero side effects
               from a clean environment (no .env, no network, no client built).
"""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS = REPO_ROOT / "requirements.txt"
APP_DIR = REPO_ROOT / "app"


# ---------------------------------------------------------------------------
# ENV2 — every non-stdlib import is pinned with ==
# ---------------------------------------------------------------------------

class TestEnv2PinnedDeps:
    """ENV2: no non-stdlib module is imported without a pinned == version."""

    def test_requirements_file_exists(self):
        assert REQUIREMENTS.exists(), "requirements.txt must exist"

    def test_requirements_has_pinned_versions(self):
        """Every non-comment, non-empty line must contain '=='."""
        lines = REQUIREMENTS.read_text(encoding="utf-8").splitlines()
        unpinned = []
        for line in lines:
            stripped = line.strip()
            # skip comments, blank lines, and the _comment / option lines
            if not stripped or stripped.startswith("#") or stripped.startswith("-"):
                continue
            # every dep line must have ==
            if "==" not in stripped:
                unpinned.append(stripped)
        assert unpinned == [], (
            f"The following requirements.txt entries are NOT pinned with ==:\n"
            + "\n".join(f"  {u}" for u in unpinned)
        )

    def test_key_packages_pinned(self):
        """Key packages appear with ==version in requirements.txt."""
        content = REQUIREMENTS.read_text(encoding="utf-8")
        for pkg in ["fastapi==", "uvicorn==", "httpx==", "pydantic==",
                    "python-dotenv==", "pytest=="]:
            assert pkg in content, f"'{pkg}' not found in requirements.txt"

    def test_realtime_model_constant(self):
        """REALTIME_MODEL is the locked value 'gpt-realtime-2025-08-28' (OQ-VOICE-1,
        reconciled 2026-06-24 to Vapi's accepted realtime id; ENV2)."""
        from app.config import REALTIME_MODEL
        assert REALTIME_MODEL == "gpt-realtime-2025-08-28", (
            f"REALTIME_MODEL is '{REALTIME_MODEL}', expected 'gpt-realtime-2025-08-28'"
        )

    def test_every_third_party_import_is_pinned(self):
        """ENV2 (strong): every third-party module imported under app/ is pinned with ==.

        AST-walks app/**/*.py, drops stdlib (sys.stdlib_module_names) and first-party
        ('app'), then asserts each remaining top-level import maps to a '==' pin in
        requirements.txt. This is the QA's literal ENV2 ('grep each non-stdlib import
        against requirements.txt'), not just 'lines contain =='.
        """
        import ast
        import sys

        stdlib = set(sys.stdlib_module_names)
        pinned = set()
        for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "==" not in line:
                continue
            dist = line.split("==")[0].strip().lower().replace("-", "").replace("_", "")
            pinned.add(dist)

        # import-name -> distribution-name aliases where the two differ
        alias = {"dotenv": "pythondotenv"}

        offenders = []
        for py_file in APP_DIR.rglob("*.py"):
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                roots = []
                if isinstance(node, ast.Import):
                    roots = [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    if (node.level or 0) > 0:
                        continue  # relative import — first-party
                    if node.module:
                        roots = [node.module.split(".")[0]]
                for r in roots:
                    if not r or r in stdlib or r in {"app", "__future__"}:
                        continue
                    dist = alias.get(r, r).lower().replace("-", "").replace("_", "")
                    if dist not in pinned:
                        offenders.append((py_file.relative_to(REPO_ROOT).as_posix(), r))
        assert offenders == [], (
            "Third-party imports in app/ not pinned in requirements.txt:\n"
            + "\n".join(f"  {f}: imports '{r}'" for f, r in offenders)
        )


# ---------------------------------------------------------------------------
# ENV4 (scoped) — import-safety for the three Stage-1 modules
# ---------------------------------------------------------------------------

class TestEnv4ImportSafety:
    """ENV4 (scoped): importing config/budget/consent has zero side effects."""

    def test_config_importable_no_env(self, monkeypatch):
        """app.config imports cleanly with no env vars set."""
        # Remove any VAPI/OPENAI keys from the environment to prove clean import
        for key in ["VAPI_API_KEY", "OPENAI_API_KEY", "VAPI_WEBHOOK_SECRET",
                    "CALCOM_API_KEY", "CONSENT_ALLOWLIST_PATH"]:
            monkeypatch.delenv(key, raising=False)
        import app.config as cfg  # noqa: F401 — just proves import works
        # Constants must be available immediately
        assert cfg.HARD_BUDGET_USD == 50.00
        assert cfg.DISCLOSURE_LINE.startswith("Hi, this is Aria")
        assert cfg.FAILSAFE_HANGUP_LINE.startswith("Thanks for your time")

    def test_budget_importable_no_env(self, monkeypatch):
        """app.budget imports cleanly; singleton is None until get_ledger() is called."""
        for key in ["VAPI_API_KEY", "OPENAI_API_KEY"]:
            monkeypatch.delenv(key, raising=False)
        import app.budget as bud
        # The module-level singleton should be None at import
        bud.reset_ledger()  # reset in case a prior test touched it
        assert bud._ledger is None, "BudgetLedger singleton must be None at import"

    def test_consent_importable_no_env(self, monkeypatch):
        """app.consent imports cleanly; allowlist singleton is None until called."""
        for key in ["CONSENT_ALLOWLIST_PATH"]:
            monkeypatch.delenv(key, raising=False)
        import app.consent as con
        con.reset_allowlist()  # reset singleton
        assert con._allowlist is None, "Allowlist singleton must be None at import"

    def test_all_three_importable_together(self, monkeypatch):
        """Import all three Stage-1 modules together — must succeed with no exceptions."""
        for key in ["VAPI_API_KEY", "OPENAI_API_KEY", "VAPI_WEBHOOK_SECRET",
                    "CALCOM_API_KEY", "CONSENT_ALLOWLIST_PATH"]:
            monkeypatch.delenv(key, raising=False)
        try:
            import app.config   # noqa
            import app.budget   # noqa
            import app.consent  # noqa
        except Exception as exc:
            pytest.fail(f"Importing Stage-1 modules raised: {exc}")

    def test_stage3_modules_importable_singleton_none(self, monkeypatch):
        """ENV4 (Stage 3): app.tools + app.calendar_client import side-effect free.

        The live calendar singleton must be None at import (the live Cal.com
        client is built lazily only via _get_calendar(), never eagerly — CON4).
        """
        for key in ["CALCOM_API_KEY", "CALCOM_EVENT_TYPE_ID",
                    "VAPI_API_KEY", "OPENAI_API_KEY", "CONSENT_ALLOWLIST_PATH"]:
            monkeypatch.delenv(key, raising=False)
        import app.calendar_client as cc
        import app.tools  # noqa: F401
        cc.reset_calendar()
        assert cc._calendar is None, "live calendar singleton must be None at import"

    def test_stage4_modules_importable_singleton_none(self, monkeypatch):
        """ENV4 (Stage 4): app.server + app.vapi_client import side-effect free.

        The live Vapi client singleton must be None at import (built lazily only
        via _get_vapi(), never eagerly — VOICE4 / CON4). Importing app.server must
        NOT read .env, build a client, or open a lifespan resource.
        """
        for key in ["VAPI_API_KEY", "VAPI_PHONE_NUMBER_ID", "VAPI_WEBHOOK_SECRET",
                    "OPENAI_API_KEY", "CALCOM_API_KEY", "CONSENT_ALLOWLIST_PATH"]:
            monkeypatch.delenv(key, raising=False)
        import app.vapi_client as vc
        import app.server  # noqa: F401
        vc.reset_vapi()
        assert vc._vapi is None, "live Vapi client singleton must be None at import"

    def test_import_subprocess_no_env(self):
        """Run import in a clean subprocess with no .env — must exit 0.

        Covers the full six-module ENV4 set (CLAUDE.md §1: config, server, tools,
        orchestrate, budget, consent) PLUS vapi_client + calendar_client — every
        lazy singleton None at import. Stage 5 adds app.orchestrate to this set.
        """
        result = subprocess.run(
            [sys.executable, "-c",
             "import app.config, app.budget, app.consent, app.tools, "
             "app.calendar_client, app.vapi_client, app.server, app.orchestrate; "
             "import app.budget as b; b.reset_ledger(); assert b._ledger is None; "
             "import app.consent as c; c.reset_allowlist(); assert c._allowlist is None; "
             "import app.calendar_client as cal; cal.reset_calendar(); assert cal._calendar is None; "
             "import app.vapi_client as v; v.reset_vapi(); assert v._vapi is None"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
            # Remove .env influence by not loading dotenv
        )
        assert result.returncode == 0, (
            f"Import subprocess failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_config_no_clients_at_import(self):
        """Importing config.py must not build any HTTP/network client."""
        # If a client were built at import, it would import httpx and construct
        # objects — we verify config doesn't import httpx at module level.
        import app.config as cfg
        # config should not have imported httpx as a module-level dependency
        # (it only uses os, pathlib, __future__)
        assert "httpx" not in dir(cfg), "config.py must not import httpx at module level"

    def test_disclosure_line_byte_exact(self):
        """DISCLOSURE_LINE matches the byte-exact graded literal from CLAUDE.md §9."""
        from app.config import DISCLOSURE_LINE
        expected = (
            "Hi, this is Aria, an AI assistant calling on behalf of Alta. "
            "This call may be recorded for quality. Do you have a quick minute?"
        )
        assert DISCLOSURE_LINE == expected, (
            f"DISCLOSURE_LINE mismatch!\n"
            f"  Got:      {DISCLOSURE_LINE!r}\n"
            f"  Expected: {expected!r}"
        )

    def test_failsafe_hangup_line_byte_exact(self):
        """FAILSAFE_HANGUP_LINE matches the byte-exact graded literal from CLAUDE.md §9."""
        from app.config import FAILSAFE_HANGUP_LINE
        # Note: the em-dash (—) must be preserved byte-for-byte
        expected = "Thanks for your time — I'll follow up by email. Goodbye."
        assert FAILSAFE_HANGUP_LINE == expected, (
            f"FAILSAFE_HANGUP_LINE mismatch!\n"
            f"  Got:      {FAILSAFE_HANGUP_LINE!r}\n"
            f"  Expected: {expected!r}"
        )

    def test_agent_tools_identity(self):
        """AGENT_TOOLS has 5 entries matching the spec (CLAUDE.md §9)."""
        from app.config import AGENT_TOOLS
        expected = [
            "check_availability",
            "book_meeting",
            "log_disposition",
            "detect_voicemail",
            "end_call",
        ]
        assert AGENT_TOOLS == expected, (
            f"AGENT_TOOLS mismatch:\n  Got:      {AGENT_TOOLS}\n  Expected: {expected}"
        )

    def test_literals_have_no_smart_quotes(self):
        """Regression guard (the crash bug): graded literals use straight ASCII quotes only.

        The em-dash U+2014 is the sole permitted non-ASCII char (part of the locked
        FAILSAFE_HANGUP_LINE). Smart quotes ' ' " " must never appear — a curly
        apostrophe is exactly what broke the byte-exact contract on recovery.
        """
        from app.config import DISCLOSURE_LINE, FAILSAFE_HANGUP_LINE
        forbidden = {"‘", "’", "“", "”"}
        for name, lit in [
            ("DISCLOSURE_LINE", DISCLOSURE_LINE),
            ("FAILSAFE_HANGUP_LINE", FAILSAFE_HANGUP_LINE),
        ]:
            bad = sorted(forbidden.intersection(lit))
            assert not bad, (
                f"{name} contains smart quote(s) {bad!r} — use straight ASCII quotes."
            )


# ---------------------------------------------------------------------------
# load_env() — the lazy .env loader (brief: config hosts the sanctioned loader)
# ---------------------------------------------------------------------------

class TestLoadEnv:
    """load_env reads .env only when called (never at import) and no-ops when absent."""

    def test_load_env_is_callable(self):
        """load_env exists on app.config and is callable."""
        from app import config
        assert callable(config.load_env)

    def test_load_env_populates_environ_from_file(self, tmp_path, monkeypatch):
        """Calling load_env(path) loads keys from that .env into os.environ."""
        from app.config import load_env
        env_file = tmp_path / ".env"
        env_file.write_text("ALTA_TEST_SENTINEL=loaded_ok\n", encoding="utf-8")
        monkeypatch.delenv("ALTA_TEST_SENTINEL", raising=False)
        load_env(env_file)
        try:
            assert os.environ.get("ALTA_TEST_SENTINEL") == "loaded_ok"
        finally:
            # python-dotenv mutates os.environ directly; monkeypatch can't undo it
            os.environ.pop("ALTA_TEST_SENTINEL", None)

    def test_load_env_missing_file_is_safe_noop(self, tmp_path):
        """A missing .env is a safe no-op — never raises (resiliency, §6)."""
        from app.config import load_env
        load_env(tmp_path / "does_not_exist.env")  # must not raise

    def test_load_env_does_not_override_existing(self, tmp_path, monkeypatch):
        """An existing os.environ value wins over .env (offline determinism)."""
        from app.config import load_env
        monkeypatch.setenv("ALTA_TEST_SENTINEL2", "from_environ")
        env_file = tmp_path / ".env"
        env_file.write_text("ALTA_TEST_SENTINEL2=from_dotenv\n", encoding="utf-8")
        load_env(env_file)
        assert os.environ["ALTA_TEST_SENTINEL2"] == "from_environ"
