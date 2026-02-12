"""VAT number validation and normalization.

Belgian VAT: BE0XXXXXXXXX (10 digits, starts with 0, modulo-97 check).
Also supports basic EU VAT format validation for future expansion.
"""
import re
from typing import Optional


# Country-specific patterns: (regex, checksum_fn | None)
_BE_PATTERN = re.compile(r"^BE\s?0?\d{9,10}$", re.IGNORECASE)


def _normalize_be(raw: str) -> str:
    """Strip spaces/dots, uppercase, ensure BE prefix and 10 digits."""
    cleaned = re.sub(r"[\s.\-]", "", raw).upper()
    # Add BE prefix if missing
    if cleaned.startswith("0") and len(cleaned) == 10:
        cleaned = "BE" + cleaned
    elif cleaned.startswith("BE0") and len(cleaned) == 12:
        pass  # Already good: BE0XXXXXXXXX
    elif cleaned.startswith("BE") and len(cleaned) == 11:
        # BE + 9 digits → insert 0
        cleaned = "BE0" + cleaned[2:]
    return cleaned


def _check_be(normalized: str) -> bool:
    """Belgian modulo-97 checksum: last 2 digits = 97 - (first 8 digits mod 97)."""
    digits = normalized[2:]  # strip 'BE'
    if len(digits) != 10 or not digits.isdigit():
        return False
    base = int(digits[:8])
    check = int(digits[8:])
    return check == 97 - (base % 97)


def validate_vat(raw: Optional[str]) -> tuple[bool, Optional[str], Optional[str]]:
    """Validate and normalize a VAT number.

    Returns:
        (is_valid, normalized_vat, error_message)

    Examples:
        >>> validate_vat("BE0123456789")
        (True, "BE0123456789", None)
        >>> validate_vat("0123 456 789")
        (True, "BE0123456789", None)
        >>> validate_vat("BE9999999999")
        (False, None, "Numéro de TVA invalide (checksum)")
    """
    if not raw or not raw.strip():
        return True, None, None  # empty = OK (field is optional)

    cleaned = re.sub(r"[\s.\-]", "", raw).upper()

    # Detect country
    if cleaned.startswith("BE") or (cleaned.startswith("0") and len(cleaned) in (9, 10)):
        normalized = _normalize_be(cleaned)
        if len(normalized) != 12:  # BE + 10 digits
            return False, None, "Format TVA belge attendu : BE0XXXXXXXXX"
        if not _check_be(normalized):
            return False, None, "Numéro de TVA invalide (checksum incorrecte)"
        return True, normalized, None

    # Generic EU VAT: 2-letter country + digits (no checksum validation)
    eu_match = re.match(r"^([A-Z]{2})(\d{8,12})$", cleaned)
    if eu_match:
        return True, cleaned, None

    return False, None, "Format TVA non reconnu. Attendu : BE0XXXXXXXXX ou XX + chiffres"
