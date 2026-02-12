"""Tests for VAT validation utility and company profile."""
import pytest
from app.utils.vat import validate_vat


class TestVatValidation:
    """Belgian VAT: BE0 + 9 digits, modulo-97 checksum."""

    def test_valid_be_full_format(self):
        """Standard format BE0XXXXXXXXX."""
        # BE0404616494 = Anthropic Belgium (fictive, but valid checksum)
        # Checksum: 97 - (04046164 % 97) = 97 - 03 = 94 → last 2 digits = 94 ✓
        ok, norm, err = validate_vat("BE0404616494")
        assert ok is True
        assert norm == "BE0404616494"
        assert err is None

    def test_valid_be_with_spaces(self):
        ok, norm, err = validate_vat("BE 0404 616 494")
        assert ok is True
        assert norm == "BE0404616494"

    def test_valid_be_with_dots(self):
        ok, norm, err = validate_vat("BE0.404.616.494")
        assert ok is True
        assert norm == "BE0404616494"

    def test_valid_be_without_prefix(self):
        """Just digits starting with 0."""
        ok, norm, err = validate_vat("0404616494")
        assert ok is True
        assert norm == "BE0404616494"

    def test_valid_be_lowercase(self):
        ok, norm, err = validate_vat("be0404616494")
        assert ok is True
        assert norm == "BE0404616494"

    def test_invalid_be_bad_checksum(self):
        ok, norm, err = validate_vat("BE0999999999")
        assert ok is False
        assert norm is None
        assert "checksum" in err.lower() or "invalide" in err.lower()

    def test_invalid_be_too_short(self):
        ok, norm, err = validate_vat("BE012345")
        assert ok is False

    def test_empty_is_ok(self):
        """Empty = field not filled, that's fine."""
        ok, norm, err = validate_vat("")
        assert ok is True
        assert norm is None

    def test_none_is_ok(self):
        ok, norm, err = validate_vat(None)
        assert ok is True
        assert norm is None

    def test_generic_eu_format(self):
        """French VAT: FR + 11 digits."""
        ok, norm, err = validate_vat("FR12345678901")
        assert ok is True
        assert norm == "FR12345678901"

    def test_unrecognized_format(self):
        ok, norm, err = validate_vat("XXXXXX")
        assert ok is False
        assert "non reconnu" in err


class TestBelgianChecksum:
    """Verify modulo-97 logic with known-good Belgian VAT numbers."""

    @pytest.mark.parametrize("vat", [
        "BE0202239951",  # Proximus
        "BE0403199702",  # Belfius
        "BE0404616494",  # Example
    ])
    def test_known_good_numbers(self, vat):
        ok, norm, err = validate_vat(vat)
        assert ok is True, f"{vat} should be valid but got: {err}"
        assert norm == vat
