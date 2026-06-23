"""Alta test suite — shared fixtures (QA_checklist.md §0).

Fixtures defined here:
  - tmp_leads_json     : a small schema-valid leads.synthetic.json path
  - tmp_icp_json       : a minimal valid icp.synthetic.json path
  - tmp_value_prop     : a minimal value_prop.md path
  - tmp_allowlist      : a consent allowlist with one allowed + one absent number
  - allowed_number     : the E.164 number that IS on tmp_allowlist
  - absent_number      : an E.164 number deliberately NOT on tmp_allowlist

These fixtures create real temporary files in tmp_path so the modules under
test can read them as they would in production. No network, no .env.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Synthetic leads fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_leads_json(tmp_path: Path) -> Path:
    """Write a minimal valid leads.synthetic.json and return its path.

    Includes:
      - lead-001: normal lead (do_not_call=false, required fields present)
      - lead-002: do_not_call=true lead (must be suppressed)
    """
    data = {
        "leads": [
            {
                "lead_id": "lead-001",
                "first_name": "Jordan",
                "company": "Momentum SaaS",
                "phone_e164": "+15550100001",
                "last_name": "Rivera",
                "role": "VP of Sales",
                "icp_tags": ["b2b-saas"],
                "timezone": "America/New_York",
                "do_not_call": False,
                "notes": "Fixture lead — normal",
            },
            {
                "lead_id": "lead-002",
                "first_name": "Taylor",
                "company": "Optimus Tech",
                "phone_e164": "+15550100004",
                "last_name": "Nguyen",
                "role": "Director of Sales",
                "icp_tags": ["b2b-saas"],
                "timezone": "America/Denver",
                "do_not_call": True,
                "notes": "Fixture lead — do_not_call",
            },
        ]
    }
    p = tmp_path / "leads.synthetic.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


@pytest.fixture()
def tmp_icp_json(tmp_path: Path) -> Path:
    """Write a minimal valid icp.synthetic.json and return its path."""
    data = {
        "icp": {
            "name": "Test ICP",
            "required_tags": ["b2b-saas"],
            "target_roles": ["VP of Sales"],
        }
    }
    p = tmp_path / "icp.synthetic.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


@pytest.fixture()
def tmp_value_prop(tmp_path: Path) -> Path:
    """Write a minimal value_prop.md and return its path."""
    content = "# Alta Value Prop\n\nAlta helps B2B SaaS teams book more meetings.\n"
    p = tmp_path / "value_prop.md"
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Allowlist fixtures
# ---------------------------------------------------------------------------

ALLOWED_NUMBER = "+15559990001"
ABSENT_NUMBER = "+15559990099"


@pytest.fixture()
def allowed_number() -> str:
    return ALLOWED_NUMBER


@pytest.fixture()
def absent_number() -> str:
    return ABSENT_NUMBER


@pytest.fixture()
def tmp_allowlist(tmp_path: Path) -> Path:
    """Write a consent allowlist with exactly one allowed number and return its path.

    The ABSENT_NUMBER is deliberately not on this list.
    """
    data = {"allowed_numbers": [ALLOWED_NUMBER]}
    p = tmp_path / "consent_allowlist.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p
