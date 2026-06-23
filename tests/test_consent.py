"""Stage 1 — CON1 tests.

CON1: the consent-allowlist gate.
  - consent_allows() returns True only for allowlisted numbers.
  - Non-allowlisted numbers are refused (never reach place_call).
  - Allowlist validates on load (malformed/empty → clean explicit error, not allow-none).
  - do_not_call=True suppresses a lead regardless of allowlist status (CON5).
  - mask_phone() masks all but last 2 digits (LEAK2).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.consent import (
    AllowlistError,
    consent_allows,
    load_allowlist,
    mask_phone,
    reset_allowlist,
)


# ---------------------------------------------------------------------------
# mask_phone helper
# ---------------------------------------------------------------------------

class TestMaskPhone:
    def test_masks_all_but_last_two(self):
        assert mask_phone("+15551234567") == "+*********67"

    def test_short_number_fully_masked(self):
        # length < 3 → all masked
        assert mask_phone("+1") == "**"
        assert mask_phone("ab") == "**"

    def test_exactly_three_chars(self):
        # "+12" → "+*2" (first char kept, one masked, last two chars but we keep last 2)
        # len=3: first + '*'*(3-3) + last2 → '+' + '' + '12' → '+12'? No:
        # mask_phone: number[0] + '*'*(len-3) + number[-2:]
        # len=3: number[0] + '*'*0 + number[-2:] = number[0] + number[1:] = full number
        result = mask_phone("+12")
        assert result == "+12"  # length 3 → 0 stars

    def test_longer_number(self):
        result = mask_phone("+15550100001")
        assert result.endswith("01")
        assert "*" in result

    def test_preserves_plus_prefix(self):
        result = mask_phone("+15559990001")
        assert result.startswith("+")


# ---------------------------------------------------------------------------
# load_allowlist — validation on load (CON1 / Red-Team finding 9)
# ---------------------------------------------------------------------------

class TestLoadAllowlist:

    def test_loads_valid_allowlist(self, tmp_allowlist: Path):
        al = load_allowlist(tmp_allowlist)
        assert "+15559990001" in al

    def test_returns_frozenset(self, tmp_allowlist: Path):
        al = load_allowlist(tmp_allowlist)
        assert isinstance(al, frozenset)

    def test_raises_if_file_missing(self, tmp_path: Path):
        p = tmp_path / "nonexistent.json"
        with pytest.raises(AllowlistError, match="not found"):
            load_allowlist(p)

    def test_raises_if_invalid_json(self, tmp_path: Path):
        p = tmp_path / "bad.json"
        p.write_text("NOT JSON {{{", encoding="utf-8")
        with pytest.raises(AllowlistError, match="not valid JSON"):
            load_allowlist(p)

    def test_raises_if_missing_allowed_numbers_key(self, tmp_path: Path):
        p = tmp_path / "wrong.json"
        p.write_text(json.dumps({"numbers": ["+15559990001"]}), encoding="utf-8")
        with pytest.raises(AllowlistError, match="allowed_numbers"):
            load_allowlist(p)

    def test_raises_if_allowed_numbers_empty(self, tmp_path: Path):
        """Empty allowlist is a clean error — never silent allow-none (CON1)."""
        p = tmp_path / "empty.json"
        p.write_text(json.dumps({"allowed_numbers": []}), encoding="utf-8")
        with pytest.raises(AllowlistError, match="non-empty"):
            load_allowlist(p)

    def test_raises_if_entry_not_e164(self, tmp_path: Path):
        p = tmp_path / "bad_e164.json"
        p.write_text(json.dumps({"allowed_numbers": ["not-a-number"]}), encoding="utf-8")
        with pytest.raises(AllowlistError, match="E.164"):
            load_allowlist(p)

    def test_raises_if_entry_missing_plus(self, tmp_path: Path):
        p = tmp_path / "no_plus.json"
        p.write_text(json.dumps({"allowed_numbers": ["15559990001"]}), encoding="utf-8")
        with pytest.raises(AllowlistError, match="E.164"):
            load_allowlist(p)

    def test_raises_if_top_level_not_dict(self, tmp_path: Path):
        p = tmp_path / "list.json"
        p.write_text(json.dumps(["+15559990001"]), encoding="utf-8")
        with pytest.raises(AllowlistError, match="allowed_numbers"):
            load_allowlist(p)

    def test_multiple_numbers_all_loaded(self, tmp_path: Path):
        numbers = ["+15559990001", "+15559990002", "+15559990003"]
        p = tmp_path / "multi.json"
        p.write_text(json.dumps({"allowed_numbers": numbers}), encoding="utf-8")
        al = load_allowlist(p)
        for n in numbers:
            assert n in al


# ---------------------------------------------------------------------------
# consent_allows — the gate function (CON1)
# ---------------------------------------------------------------------------

class TestConsentAllows:

    def test_allows_listed_number(self, tmp_allowlist: Path, allowed_number: str):
        al = load_allowlist(tmp_allowlist)
        assert consent_allows(allowed_number, allowlist=al) is True

    def test_refuses_unlisted_number(self, tmp_allowlist: Path, absent_number: str):
        al = load_allowlist(tmp_allowlist)
        assert consent_allows(absent_number, allowlist=al) is False

    def test_do_not_call_suppresses_allowlisted_number(
        self, tmp_allowlist: Path, allowed_number: str
    ):
        """CON5: do_not_call=True suppresses a lead even if allowlisted."""
        al = load_allowlist(tmp_allowlist)
        assert consent_allows(allowed_number, do_not_call=True, allowlist=al) is False

    def test_do_not_call_suppresses_non_allowlisted_number(
        self, tmp_allowlist: Path, absent_number: str
    ):
        al = load_allowlist(tmp_allowlist)
        # Already refused, do_not_call makes it doubly refused
        assert consent_allows(absent_number, do_not_call=True, allowlist=al) is False

    def test_do_not_call_defaults_false(self, tmp_allowlist: Path, allowed_number: str):
        """do_not_call defaults to False — must not suppress unless explicitly True."""
        al = load_allowlist(tmp_allowlist)
        assert consent_allows(allowed_number, allowlist=al) is True

    def test_returns_bool_not_truthy(self, tmp_allowlist: Path, allowed_number: str):
        """Must return literal True/False, not a truthy/falsy value."""
        al = load_allowlist(tmp_allowlist)
        result = consent_allows(allowed_number, allowlist=al)
        assert result is True
        result2 = consent_allows("+15550000000", allowlist=al)
        assert result2 is False

    def test_empty_string_refused(self, tmp_allowlist: Path):
        al = load_allowlist(tmp_allowlist)
        assert consent_allows("", allowlist=al) is False

    def test_singleton_not_loaded_at_import(self):
        """The allowlist singleton is None until consent_allows() or load_allowlist() is called."""
        import app.consent as con
        con.reset_allowlist()
        assert con._allowlist is None


# ---------------------------------------------------------------------------
# CON1 — singleton lazy load triggered by consent_allows() without explicit allowlist
# ---------------------------------------------------------------------------

class TestConsentSingletonLazyLoad:
    """consent_allows() falls back to the module singleton — loaded lazily."""

    def test_singleton_loaded_on_first_call(self, tmp_allowlist: Path, monkeypatch):
        """The first call to consent_allows() without an allowlist arg loads the singleton."""
        import app.consent as con
        con.reset_allowlist()
        monkeypatch.setenv("CONSENT_ALLOWLIST_PATH", str(tmp_allowlist))

        # Before call: singleton is None
        assert con._allowlist is None

        # After call: singleton is populated
        result = consent_allows("+15559990001")  # allowed_number
        assert con._allowlist is not None
        assert result is True
        con.reset_allowlist()

    def test_singleton_raises_when_path_missing(self, monkeypatch):
        """Without a path set and no file, consent_allows() raises AllowlistError."""
        import app.consent as con
        con.reset_allowlist()
        monkeypatch.setenv("CONSENT_ALLOWLIST_PATH", "/tmp/does_not_exist_alta.json")
        with pytest.raises(AllowlistError):
            consent_allows("+15550000001")
        con.reset_allowlist()
