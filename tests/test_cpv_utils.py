"""Unit tests for CPV normalization."""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.utils.cpv import normalize_cpv


def test_normalize_cpv_9_digits_no_dash() -> None:
    """480000008 -> cpv_8=48000000, check=8, display=48000000-8."""
    cpv_8, check, display = normalize_cpv("480000008")
    assert cpv_8 == "48000000"
    assert check == "8"
    assert display == "48000000-8"


def test_normalize_cpv_with_dash() -> None:
    """48000000-8 -> same as above."""
    cpv_8, check, display = normalize_cpv("48000000-8")
    assert cpv_8 == "48000000"
    assert check == "8"
    assert display == "48000000-8"


def test_normalize_cpv_8_digits_only() -> None:
    """48000000 -> no check digit, display=48000000."""
    cpv_8, check, display = normalize_cpv("48000000")
    assert cpv_8 == "48000000"
    assert check is None
    assert display == "48000000"


def test_normalize_cpv_space_separated() -> None:
    """48000000 8 -> cpv_8=48000000, check=8, display=48000000-8."""
    cpv_8, check, display = normalize_cpv("48000000 8")
    assert cpv_8 == "48000000"
    assert check == "8"
    assert display == "48000000-8"


def test_normalize_cpv_none_and_empty() -> None:
    """None and empty return (None, None, None)."""
    assert normalize_cpv(None) == (None, None, None)
    assert normalize_cpv("") == (None, None, None)
    assert normalize_cpv("  ") == (None, None, None)


def test_normalize_cpv_no_digits() -> None:
    """Non-digit string returns (None, None, None)."""
    assert normalize_cpv("abc") == (None, None, None)


def test_normalize_cpv_fewer_than_8_digits() -> None:
    """Fewer than 8 digits: cpv_8 is None (we require 8 digits)."""
    cpv_8, check, display = normalize_cpv("1234567")
    assert cpv_8 is None
    assert check is None
    assert display is None
