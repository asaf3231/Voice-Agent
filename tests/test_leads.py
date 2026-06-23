"""Stage 1 — LEAD1, LEAD2, LEAD3 tests.

LEAD1: data/leads.synthetic.json parsed by name; required fields present;
       missing/renamed field → clean explicit startup error, not later KeyError.
LEAD2: data/icp.synthetic.json + data/value_prop.md load and validate.
LEAD3: no lead name/company/phone/ICP/value-prop literal hardcoded in app/ code.

Stage 5 update: load_leads() and load_icp() are now the canonical app loaders
promoted into app/orchestrate.py. This module imports them from there — no
duplicated logic (CLAUDE.md §8 / brief Stage 5). All tests remain identical.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

# Stage 5: import the promoted loaders from the app (no duplicated logic, §8)
from app.orchestrate import load_leads, load_icp  # noqa: F401 — re-exported for tests

REPO_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = REPO_ROOT / "app"
DATA_DIR = REPO_ROOT / "data"

LEADS_FILE = DATA_DIR / "leads.synthetic.json"
ICP_FILE = DATA_DIR / "icp.synthetic.json"
VALUE_PROP_FILE = DATA_DIR / "value_prop.md"

REQUIRED_LEAD_FIELDS = {"lead_id", "first_name", "company", "phone_e164"}


# ---------------------------------------------------------------------------
# LEAD1 — validate on load
# ---------------------------------------------------------------------------

class TestLead1ValidateOnLoad:

    def test_loads_actual_data_file(self):
        """The real data/leads.synthetic.json loads without error."""
        leads = load_leads(LEADS_FILE)
        assert len(leads) >= 1

    def test_real_file_has_required_fields(self):
        """Every lead in the real file has all required fields."""
        leads = load_leads(LEADS_FILE)
        for lead in leads:
            missing = REQUIRED_LEAD_FIELDS - set(lead.keys())
            assert not missing, f"Lead {lead.get('lead_id')!r} missing: {missing}"

    def test_real_file_has_do_not_call_lead(self):
        """The real file has at least one do_not_call=True lead (fixtures requirement)."""
        leads = load_leads(LEADS_FILE)
        dnc = [l for l in leads if l.get("do_not_call") is True]
        assert len(dnc) >= 1, "At least one do_not_call=True lead must exist"

    def test_real_file_has_normal_lead(self):
        """The real file has at least one normal (do_not_call=False) lead."""
        leads = load_leads(LEADS_FILE)
        normal = [l for l in leads if not l.get("do_not_call")]
        assert len(normal) >= 1, "At least one normal lead must exist"

    def test_missing_required_field_raises_value_error(self, tmp_path: Path):
        """A lead missing a required field raises ValueError (not KeyError)."""
        data = {
            "leads": [
                {
                    "lead_id": "x-001",
                    "first_name": "NoCompany",
                    # missing: company, phone_e164
                }
            ]
        }
        p = tmp_path / "bad_leads.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(ValueError, match="required fields"):
            load_leads(p)

    def test_missing_leads_key_raises_value_error(self, tmp_path: Path):
        p = tmp_path / "no_leads_key.json"
        p.write_text(json.dumps({"data": []}), encoding="utf-8")
        with pytest.raises(ValueError, match="'leads' key"):
            load_leads(p)

    def test_invalid_json_raises_value_error(self, tmp_path: Path):
        p = tmp_path / "bad.json"
        p.write_text("NOT JSON", encoding="utf-8")
        with pytest.raises(ValueError, match="not valid JSON"):
            load_leads(p)

    def test_missing_file_raises_file_not_found(self, tmp_path: Path):
        p = tmp_path / "missing.json"
        with pytest.raises(FileNotFoundError):
            load_leads(p)

    def test_tmp_fixture_loads_correctly(self, tmp_leads_json: Path):
        """The shared conftest fixture is schema-valid."""
        leads = load_leads(tmp_leads_json)
        assert len(leads) == 2
        ids = {l["lead_id"] for l in leads}
        assert "lead-001" in ids

    def test_phone_e164_format_in_real_file(self):
        """All phone numbers in the real file look like E.164 (+digits)."""
        leads = load_leads(LEADS_FILE)
        e164_re = re.compile(r"^\+[1-9]\d{6,14}$")
        for lead in leads:
            phone = lead["phone_e164"]
            assert e164_re.match(phone), f"Lead {lead['lead_id']!r}: {phone!r} not E.164"


# ---------------------------------------------------------------------------
# LEAD2 — ICP + value-prop load
# ---------------------------------------------------------------------------

class TestLead2IcpAndValueProp:

    def test_icp_file_exists(self):
        assert ICP_FILE.exists(), f"data/icp.synthetic.json not found at {ICP_FILE}"

    def test_value_prop_file_exists(self):
        assert VALUE_PROP_FILE.exists(), f"data/value_prop.md not found at {VALUE_PROP_FILE}"

    def test_icp_loads_without_error(self):
        icp = load_icp(ICP_FILE)
        assert isinstance(icp, dict)

    def test_icp_has_required_tags(self):
        icp = load_icp(ICP_FILE)
        assert "required_tags" in icp, "ICP must have 'required_tags'"

    def test_value_prop_not_empty(self):
        content = VALUE_PROP_FILE.read_text(encoding="utf-8")
        assert len(content.strip()) > 100, "value_prop.md is suspiciously short"

    def test_value_prop_is_markdown(self):
        content = VALUE_PROP_FILE.read_text(encoding="utf-8")
        assert "#" in content, "value_prop.md should contain markdown headings"

    def test_icp_missing_key_raises(self, tmp_path: Path):
        p = tmp_path / "bad_icp.json"
        p.write_text(json.dumps({"qualification": {}}), encoding="utf-8")
        with pytest.raises(ValueError, match="'icp' key"):
            load_icp(p)

    def test_tmp_icp_fixture_loads(self, tmp_icp_json: Path):
        icp = load_icp(tmp_icp_json)
        assert "required_tags" in icp


# ---------------------------------------------------------------------------
# LEAD3 — no hardcoded input values in app/ code (grep check)
# ---------------------------------------------------------------------------

class TestLead3NoHardcodedInputValues:
    """LEAD3: no lead/ICP/value-prop literal appears hardcoded in app/ code."""

    def _grep_app_for(self, pattern: str) -> list[tuple[Path, int, str]]:
        """Return (file, lineno, line) for every match of *pattern* in app/."""
        hits = []
        for py_file in APP_DIR.rglob("*.py"):
            for i, line in enumerate(
                py_file.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
            ):
                if re.search(pattern, line):
                    hits.append((py_file, i, line.strip()))
        return hits

    def test_no_hardcoded_phone_numbers(self):
        """No E.164 phone number literals appear in app/ code."""
        # Matches +15550100001 style (the synthetic numbers)
        hits = self._grep_app_for(r"\+1555010\d{4}")
        assert hits == [], (
            "Hardcoded phone number found in app/:\n"
            + "\n".join(f"  {f}:{n}: {l}" for f, n, l in hits)
        )

    def test_no_hardcoded_company_names(self):
        """Synthetic company names from leads.synthetic.json not in app/ code."""
        companies = ["Momentum SaaS", "CloudScale", "Nexus CRM", "Optimus Tech", "Prism Analytics"]
        for company in companies:
            hits = self._grep_app_for(re.escape(company))
            assert hits == [], (
                f"Hardcoded company '{company}' found in app/:\n"
                + "\n".join(f"  {f}:{n}: {l}" for f, n, l in hits)
            )

    def test_no_hardcoded_lead_names(self):
        """Synthetic prospect names not in app/ code."""
        names = ["Jordan Rivera", "Alex Chen", "Morgan Patel", "Taylor Nguyen", "Sam Wallace"]
        for name in names:
            hits = self._grep_app_for(re.escape(name))
            assert hits == [], (
                f"Hardcoded name '{name}' found in app/:\n"
                + "\n".join(f"  {f}:{n}: {l}" for f, n, l in hits)
            )

    def test_app_code_has_no_data_file_path_literals(self):
        """LEAD3: no app/ module hardcodes a synthetic data-file basename in executable code.

        The synthetic inputs are read from data/* by a loader at runtime; their
        names/paths must not be baked into app code. (Comment lines are exempt;
        the AST-level loader check lands with the loader module in later stages.)
        """
        basenames = ["leads.synthetic.json", "icp.synthetic.json", "value_prop.md"]
        offenders = []
        for py_file in APP_DIR.rglob("*.py"):
            for i, line in enumerate(
                py_file.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
            ):
                if line.strip().startswith("#"):
                    continue
                for b in basenames:
                    if b in line:
                        offenders.append((py_file.relative_to(REPO_ROOT).as_posix(), i, line.strip()))
        assert offenders == [], (
            "Hardcoded data-file path literal found in app/ (load from data/* via a loader instead):\n"
            + "\n".join(f"  {f}:{n}: {l}" for f, n, l in offenders)
        )
