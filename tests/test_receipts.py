"""Receipt-capture tests: a redacted receipt records the provider's reported cost, with no PII or secrets."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.capture_receipts import capture_receipt, main


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_fake_provider(*, cost_usd: float | None, ok: bool = True):
    """Return a mock VoiceProvider whose fetch_call_cost returns a CostResult."""
    # Build a minimal CostResult-like object (avoids importing vapi_client at
    # the top level — keeps this test module import-safe itself).
    from app.vapi_client import CostResult

    cost_result = CostResult(ok=ok, cost_usd=cost_usd)
    provider = MagicMock()
    provider.fetch_call_cost.return_value = cost_result
    return provider


def _make_failing_provider(exc: Exception):
    """Return a mock VoiceProvider whose fetch_call_cost raises exc."""
    provider = MagicMock()
    provider.fetch_call_cost.side_effect = exc
    return provider


# ---------------------------------------------------------------------------
# SEC5 — receipts captured = provider cost
# ---------------------------------------------------------------------------

class TestCaptureReceipt:
    """SEC5: the captured receipt equals the fake provider's reported cost."""

    def test_receipt_cost_equals_provider_cost(self, tmp_path):
        """The cost_usd in the receipt must exactly equal the provider's reported cost."""
        provider = _make_fake_provider(cost_usd=0.3750)
        receipt = capture_receipt("call_abc123", provider, receipts_dir=tmp_path)
        assert receipt["cost_usd"] == pytest.approx(0.3750, abs=1e-9)

    def test_receipt_file_written(self, tmp_path):
        """capture_receipt writes a JSON file under receipts/<call_id>.json."""
        provider = _make_fake_provider(cost_usd=0.50)
        capture_receipt("call_test001", provider, receipts_dir=tmp_path)
        expected = tmp_path / "call_test001.json"
        assert expected.exists(), "receipt file must be written"

    def test_receipt_file_equals_provider_cost(self, tmp_path):
        """The file on disk reports the same cost as fetch_call_cost (verified, not asserted)."""
        expected_cost = 0.1234
        provider = _make_fake_provider(cost_usd=expected_cost)
        capture_receipt("call_verify", provider, receipts_dir=tmp_path)
        data = json.loads((tmp_path / "call_verify.json").read_text())
        assert data["cost_usd"] == pytest.approx(expected_cost, abs=1e-9), (
            "receipt file cost must equal the value reported by fetch_call_cost"
        )

    def test_receipt_contains_call_id(self, tmp_path):
        """The receipt includes the call_id field."""
        provider = _make_fake_provider(cost_usd=0.10)
        receipt = capture_receipt("call_xyz", provider, receipts_dir=tmp_path)
        assert receipt["call_id"] == "call_xyz"

    def test_receipt_contains_timestamp(self, tmp_path):
        """The receipt includes a UTC timestamp."""
        provider = _make_fake_provider(cost_usd=0.05)
        receipt = capture_receipt("call_ts", provider, receipts_dir=tmp_path)
        assert "timestamp" in receipt
        ts = receipt["timestamp"]
        # ISO-8601 UTC suffix
        assert ts.endswith("Z"), f"timestamp must end with Z (UTC); got {ts!r}"

    def test_receipt_has_no_extra_fields(self, tmp_path):
        """A successful receipt has exactly three top-level keys: call_id, cost_usd, timestamp."""
        provider = _make_fake_provider(cost_usd=0.20)
        receipt = capture_receipt("call_fields", provider, receipts_dir=tmp_path)
        assert set(receipt.keys()) == {"call_id", "cost_usd", "timestamp"}, (
            f"receipt must have exactly {{call_id, cost_usd, timestamp}}; "
            f"got {set(receipt.keys())}"
        )

    # --- redaction checks (LEAK2 / anti-leakage §5) ---

    def test_no_full_phone_in_receipt(self, tmp_path):
        """No E.164 phone number appears in the receipt file."""
        provider = _make_fake_provider(cost_usd=0.33)
        capture_receipt("call_nophone", provider, receipts_dir=tmp_path)
        raw = (tmp_path / "call_nophone.json").read_text()
        # An E.164 phone starts with + and has 7–15 digits — reject any match.
        import re
        phone_pattern = re.compile(r"\+[1-9]\d{6,14}")
        assert not phone_pattern.search(raw), (
            "receipt file must not contain any full E.164 phone number"
        )

    def test_no_api_key_in_receipt(self, tmp_path):
        """No API key or secret appears in the receipt file."""
        provider = _make_fake_provider(cost_usd=0.22)
        capture_receipt("call_nosecret", provider, receipts_dir=tmp_path)
        raw = (tmp_path / "call_nosecret.json").read_text().lower()
        for forbidden in ("api_key", "vapi_api_key", "openai_api_key", "bearer", "sk-"):
            assert forbidden not in raw, (
                f"receipt file must not contain {forbidden!r}"
            )

    # --- error cases (§6: never crash, surface as data) ---

    def test_provider_error_captured_as_data(self, tmp_path):
        """If fetch_call_cost returns ok=False, the receipt has an error field."""
        from app.vapi_client import CostResult
        provider = MagicMock()
        provider.fetch_call_cost.return_value = CostResult(
            ok=False, cost_usd=None, error="vapi_error", message="timeout"
        )
        receipt = capture_receipt("call_err", provider, receipts_dir=tmp_path)
        assert receipt["cost_usd"] is None
        assert "error" in receipt

    def test_provider_exception_captured_as_data(self, tmp_path):
        """If fetch_call_cost raises, the receipt has an error field (§6: never crash)."""
        provider = _make_failing_provider(RuntimeError("simulated failure"))
        # Must not raise
        receipt = capture_receipt("call_exc", provider, receipts_dir=tmp_path)
        assert receipt["cost_usd"] is None
        assert "error" in receipt
        assert "simulated failure" in receipt["error"]

    def test_error_receipt_written_to_disk(self, tmp_path):
        """An error receipt is still written to disk."""
        provider = _make_failing_provider(ValueError("no connection"))
        capture_receipt("call_diskwrite", provider, receipts_dir=tmp_path)
        assert (tmp_path / "call_diskwrite.json").exists()

    def test_receipt_directory_created_if_missing(self, tmp_path):
        """capture_receipt creates the receipts directory if it doesn't exist."""
        subdir = tmp_path / "new_subdir"
        assert not subdir.exists()
        provider = _make_fake_provider(cost_usd=0.10)
        capture_receipt("call_newdir", provider, receipts_dir=subdir)
        assert (subdir / "call_newdir.json").exists()


# ---------------------------------------------------------------------------
# main() entry point (import-safe / no live calls)
# ---------------------------------------------------------------------------

class TestCaptureReceiptsMain:
    """main() exits 1 with no args; exits 0 with a fake provider injected."""

    def test_main_returns_1_with_no_args(self):
        """main() returns 1 when no call_id is supplied."""
        result = main(argv=[], provider=MagicMock())
        assert result == 1

    def test_main_returns_0_for_successful_capture(self, tmp_path, monkeypatch):
        """main() returns 0 when capture succeeds with a fake provider."""
        provider = _make_fake_provider(cost_usd=0.55)
        # Redirect the receipts dir to tmp_path via monkeypatch to avoid touching
        # the real repo receipts/ directory.
        monkeypatch.setattr(
            "scripts.capture_receipts._receipts_dir",
            lambda: tmp_path,
        )
        # Also monkeypatch load_env to avoid .env dependency (ENV4).
        monkeypatch.setattr(
            "scripts.capture_receipts.main.__globals__['__builtins__']",
            None,
            raising=False,
        )

        import scripts.capture_receipts as cr
        monkeypatch.setattr(cr, "_receipts_dir", lambda: tmp_path)

        # We inject the provider so no real Vapi client is constructed.
        result = cr.main(argv=["call_main_test"], provider=provider)
        assert result == 0
        assert (tmp_path / "call_main_test.json").exists()

    def test_main_returns_1_for_provider_error(self, tmp_path, monkeypatch):
        """main() returns 1 when the provider returns an error."""
        from app.vapi_client import CostResult
        provider = MagicMock()
        provider.fetch_call_cost.return_value = CostResult(
            ok=False, cost_usd=None, error="vapi_error"
        )

        import scripts.capture_receipts as cr
        monkeypatch.setattr(cr, "_receipts_dir", lambda: tmp_path)

        result = cr.main(argv=["call_fail"], provider=provider)
        assert result == 1  # any_error → return 1
