"""CPV code normalization (8 digits + optional check digit)."""
import re
from typing import Tuple


def normalize_cpv(raw: str | None) -> Tuple[str | None, str | None, str | None]:
    """
    Normalize a raw CPV code to (cpv_8, check_digit, display).

    Standard CPV format: 8 digits + optional check digit, display "########-#" or "########".
    Accepts inputs like "480000008", "48000000-8", "48000000", "48000000 8".

    Returns:
        (cpv_8, check_digit, display)
        - cpv_8: exactly 8 digits, or None if no digits found
        - check_digit: single digit if present, else None
        - display: "48000000-8" if check digit present, else "48000000", or None
    """
    if raw is None or not isinstance(raw, str):
        return (None, None, None)
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return (None, None, None)
    cpv_8 = digits[:8] if len(digits) >= 8 else None
    check_digit = digits[8:9] if len(digits) >= 9 else None
    if cpv_8 is None:
        return (None, None, None)
    display = f"{cpv_8}-{check_digit}" if check_digit else cpv_8
    return (cpv_8, check_digit if check_digit else None, display)
