"""Alta Outbound Voice Agent — app/consent.py

Single responsibility: the consent-allowlist gate — the SINGLE chokepoint that
controls whether a number may be dialed (CLAUDE.md §5 Policy 2, CON1).

Rules enforced here:
  - consent_allows(number) → True only for numbers on the loaded allowlist.
  - A non-allowlisted number is REFUSED; it never reaches place_call.
  - do_not_call=True suppresses a lead regardless of allowlist status (CON5).
  - The allowlist source validates on load: a malformed/empty allowlist is a
    clean explicit error, NOT silent allow-none (CON1 / Red-Team 2026-06-23).
  - mask_phone() masks all but the last 2 digits for safe logging (LEAK2/SEC1).

Import-safety (ENV4): no I/O, no file read, no .env read at import.
The allowlist is loaded lazily (load_allowlist()) only when called.

Allowlist format — JSON file:
  {"allowed_numbers": ["+15551234567", "+15559876543"]}
  Required key: "allowed_numbers" (list of E.164 strings, non-empty).
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from app.config import get_setting, REPO_ROOT

# ---------------------------------------------------------------------------
# Phone number helpers
# ---------------------------------------------------------------------------

# Basic E.164 pattern: + then 7–15 digits (ITU-T E.164 spec)
_E164_PATTERN = re.compile(r"^\+[1-9]\d{6,14}$")


def _is_e164(number: str) -> bool:
    """Return True if *number* looks like a valid E.164 string."""
    return bool(_E164_PATTERN.match(number))


def mask_phone(number: str) -> str:
    """Return a masked version of *number* safe for logging.

    Shows only the last 2 digits; masks the rest with '*'.
    Example: '+15551234567' → '+*********67'
    A number shorter than 3 characters is fully masked.
    """
    if len(number) < 3:
        return "*" * len(number)
    return number[0] + "*" * (len(number) - 3) + number[-2:]


# ---------------------------------------------------------------------------
# Allowlist loading + validation
# ---------------------------------------------------------------------------

class AllowlistError(ValueError):
    """Raised when the allowlist cannot be loaded or is invalid.

    This is a clean explicit error (CON1) — never silently allow-none.
    """


def _resolve_allowlist_path() -> Path:
    """Return the absolute path to the consent allowlist file.

    Reads CONSENT_ALLOWLIST_PATH from the environment if set,
    otherwise falls back to consent_allowlist.json in the repo root.
    Never reads the file at this point — just resolves the path.
    """
    env_path = get_setting("CONSENT_ALLOWLIST_PATH")
    if env_path:
        p = Path(env_path)
        return p if p.is_absolute() else REPO_ROOT / p
    return REPO_ROOT / "consent_allowlist.json"


def load_allowlist(path: Path | str | None = None) -> frozenset[str]:
    """Load and validate the consent allowlist from *path* (or the env default).

    Returns a frozenset of E.164 strings that are explicitly consented.

    Raises AllowlistError if:
      - the file does not exist
      - the file is not valid JSON
      - the JSON is missing the "allowed_numbers" key
      - "allowed_numbers" is empty
      - any entry is not a valid E.164 string
    """
    resolved: Path
    if path is None:
        resolved = _resolve_allowlist_path()
    else:
        resolved = Path(path) if not isinstance(path, Path) else path

    if not resolved.exists():
        raise AllowlistError(
            f"Consent allowlist not found at: {resolved}\n"
            "Create the file or set CONSENT_ALLOWLIST_PATH in .env.\n"
            "See consent_allowlist.example.json for the expected format."
        )

    try:
        raw = resolved.read_text(encoding="utf-8")
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AllowlistError(
            f"Consent allowlist at {resolved} is not valid JSON: {exc}"
        ) from exc

    if not isinstance(data, dict) or "allowed_numbers" not in data:
        raise AllowlistError(
            f"Consent allowlist at {resolved} must be a JSON object with "
            "an 'allowed_numbers' key. "
            "See consent_allowlist.example.json for the expected format."
        )

    numbers = data["allowed_numbers"]
    if not isinstance(numbers, list) or len(numbers) == 0:
        raise AllowlistError(
            f"'allowed_numbers' in {resolved} must be a non-empty list. "
            "A malformed or empty allowlist is refused — never silent allow-none."
        )

    invalid = [n for n in numbers if not isinstance(n, str) or not _is_e164(n)]
    if invalid:
        raise AllowlistError(
            f"'allowed_numbers' contains invalid E.164 entries: {invalid!r}. "
            "All entries must be strings in E.164 format (e.g. '+15551234567')."
        )

    return frozenset(numbers)


# ---------------------------------------------------------------------------
# Module-level lazy singleton
# ---------------------------------------------------------------------------

_allowlist: frozenset[str] | None = None


def _get_allowlist() -> frozenset[str]:
    """Return (loading on first call) the module-level allowlist.

    NOT loaded at import. The first caller triggers the load; subsequent
    calls return the cached set. Tests should call consent_allows() with
    an explicit *allowlist* argument to avoid touching the singleton.
    """
    global _allowlist
    if _allowlist is None:
        _allowlist = load_allowlist()
    return _allowlist


def reset_allowlist() -> None:
    """Reset the singleton (test helper — do NOT call in production code)."""
    global _allowlist
    _allowlist = None


# ---------------------------------------------------------------------------
# Public gate
# ---------------------------------------------------------------------------

def consent_allows(
    number: str,
    *,
    do_not_call: bool = False,
    allowlist: frozenset[str] | None = None,
) -> bool:
    """Return True only if *number* is on the allowlist AND not flagged do_not_call.

    This is the SINGLE chokepoint before place_call (CON1/CLAUDE.md §5 Policy 2).
    No number reaches the voice provider without passing here.

    Args:
        number:        The E.164 phone number to check.
        do_not_call:   If True, suppresses the lead regardless of allowlist status (CON5).
        allowlist:     If provided, use this set instead of the singleton (for tests).

    Returns:
        True  → the number is consented and not suppressed; dialing is permitted.
        False → the number is not allowed; caller must NOT call place_call.
    """
    if do_not_call:
        return False

    effective_allowlist = allowlist if allowlist is not None else _get_allowlist()
    return number in effective_allowlist
