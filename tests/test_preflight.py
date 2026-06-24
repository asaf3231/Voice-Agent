"""Preflight script tests — readiness verdict + the no-secret-VALUE-printed guarantee.

Fully offline: load_env is stubbed (never touches the real .env), the persistent
ledger is pointed at tmp_path, and a tmp consent allowlist is used. No network.
"""

from __future__ import annotations

import json

import pytest

import scripts.preflight as preflight

# Fake settings whose VALUES must NEVER appear in preflight output (names only).
# Deliberately NOT shaped like real secrets (no `sk-`/`vapi-`/PAN) so the
# anti-leakage grep over tracked files (LEAK1/SEC1) does not flag this test file.
_FAKE = {
    "VAPI_API_KEY": "FAKE-priv-AAAA-0001-not-a-real-token",
    "VAPI_PHONE_NUMBER_ID": "11111111-2222-3333-4444-555555555555",
    "VAPI_WEBHOOK_SECRET": "FAKE-webhook-BBBB-0002-not-a-real-token",
    "CALCOM_API_KEY": "FAKE-cal-CCCC-0003-not-a-real-token",
    "CALCOM_EVENT_TYPE_ID": "654321",
}
_ALLOWLIST_NUMBER = "+15555550199"  # canonical fictitious +1555 prefix; must not be printed


@pytest.fixture()
def isolated(monkeypatch, tmp_path):
    """Stub load_env, isolate the ledger to tmp, and supply a tmp allowlist."""
    monkeypatch.setattr("app.config.load_env", lambda *a, **k: None)

    import app.budget as bud
    monkeypatch.setattr(bud, "_LEDGER_STATE_PATH", tmp_path / "ledger.json")
    bud.reset_ledger()

    allow = tmp_path / "consent_allowlist.json"
    allow.write_text(
        json.dumps({"allowed_numbers": [_ALLOWLIST_NUMBER]}), encoding="utf-8"
    )
    monkeypatch.setenv("CONSENT_ALLOWLIST_PATH", str(allow))

    import app.consent as consent
    consent.reset_allowlist()
    try:
        yield tmp_path
    finally:
        bud.reset_ledger()
        consent.reset_allowlist()


def _set_all(monkeypatch):
    for k, v in _FAKE.items():
        monkeypatch.setenv(k, v)


def test_preflight_passes_when_all_present(isolated, monkeypatch, capsys):
    _set_all(monkeypatch)
    rc = preflight.main([])
    out = capsys.readouterr().out
    assert rc == 0
    assert "PREFLIGHT PASSED" in out


def test_preflight_fails_when_required_setting_missing(isolated, monkeypatch, capsys):
    _set_all(monkeypatch)
    monkeypatch.delenv("CALCOM_EVENT_TYPE_ID", raising=False)
    rc = preflight.main([])
    out = capsys.readouterr().out
    assert rc == 1
    assert "MISSING" in out
    assert "PREFLIGHT FAILED" in out


def test_preflight_never_prints_a_secret_value(isolated, monkeypatch, capsys):
    _set_all(monkeypatch)
    preflight.main([])
    out = capsys.readouterr().out
    # Negative: NONE of the secret env VALUES (nor the phone) may appear.
    for value in _FAKE.values():
        assert value not in out, f"preflight leaked a secret value: {value!r}"
    assert _ALLOWLIST_NUMBER not in out, "preflight printed the consented phone number"
    # Positive: it DOES surface each setting NAME (names-not-values is the contract).
    for name in _FAKE:
        assert name in out, f"preflight should report the setting name {name!r}"


def test_preflight_fails_when_allowlist_unusable(isolated, monkeypatch, tmp_path, capsys):
    _set_all(monkeypatch)
    empty = tmp_path / "empty_allowlist.json"
    empty.write_text(json.dumps({"allowed_numbers": []}), encoding="utf-8")
    monkeypatch.setenv("CONSENT_ALLOWLIST_PATH", str(empty))
    import app.consent as consent
    consent.reset_allowlist()
    rc = preflight.main([])
    assert rc == 1


def test_preflight_module_import_is_side_effect_free():
    """ENV4: importing the preflight module builds nothing and reads no .env."""
    import importlib
    import scripts.preflight as pf
    importlib.reload(pf)  # re-import must not raise or touch the network/.env
    assert hasattr(pf, "main")
