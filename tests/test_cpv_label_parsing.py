"""Unit tests for CPV label parsing logic."""
import sys
from pathlib import Path

# Ensure project root on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.connectors.bosa.official_client import _extract_label_from_cpv_item


def test_extract_label_direct_string_fields() -> None:
    """Test extraction from direct string fields."""
    # Test direct label field
    item = {"code": "45000000", "label": "Construction work"}
    assert _extract_label_from_cpv_item(item, "FR") == "Construction work"
    
    # Test direct description field
    item = {"code": "45000000", "description": "Travaux de construction"}
    assert _extract_label_from_cpv_item(item, "FR") == "Travaux de construction"
    
    # Test direct name field
    item = {"code": "45000000", "name": "Construction"}
    assert _extract_label_from_cpv_item(item, "FR") == "Construction"


def test_extract_label_language_specific_fields() -> None:
    """Test extraction from language-specific fields."""
    # Test descriptionFR
    item = {"code": "45000000", "descriptionFR": "Travaux de construction", "descriptionNL": "Bouwwerkzaamheden"}
    assert _extract_label_from_cpv_item(item, "FR") == "Travaux de construction"
    
    # Test descriptionNL
    item = {"code": "45000000", "descriptionFR": "Travaux de construction", "descriptionNL": "Bouwwerkzaamheden"}
    assert _extract_label_from_cpv_item(item, "NL") == "Bouwwerkzaamheden"


def test_extract_label_descriptions_array() -> None:
    """Test extraction from descriptions array (existing pattern)."""
    item = {
        "code": "45000000",
        "descriptions": [
            {"language": "FR", "text": "Travaux de construction"},
            {"language": "NL", "text": "Bouwwerkzaamheden"},
        ],
    }
    assert _extract_label_from_cpv_item(item, "FR") == "Travaux de construction"
    assert _extract_label_from_cpv_item(item, "NL") == "Bouwwerkzaamheden"


def test_extract_label_translations_array() -> None:
    """Test extraction from translations array."""
    item = {
        "code": "45000000",
        "translations": [
            {"language": "FR", "text": "Travaux de construction"},
            {"language": "NL", "text": "Bouwwerkzaamheden"},
        ],
    }
    assert _extract_label_from_cpv_item(item, "FR") == "Travaux de construction"
    assert _extract_label_from_cpv_item(item, "NL") == "Bouwwerkzaamheden"


def test_extract_label_fallback_to_any_language() -> None:
    """Test fallback to first available label if language match not found."""
    item = {
        "code": "45000000",
        "descriptions": [
            {"language": "EN", "text": "Construction work"},
            {"language": "DE", "text": "Bauarbeiten"},
        ],
    }
    # Should return first available label when FR not found
    assert _extract_label_from_cpv_item(item, "FR") == "Construction work"


def test_extract_label_nested_variants() -> None:
    """Test extraction from various nested field name variants."""
    # Test with "label" in description dict
    item = {
        "code": "45000000",
        "descriptions": [
            {"language": "FR", "label": "Travaux de construction"},
        ],
    }
    assert _extract_label_from_cpv_item(item, "FR") == "Travaux de construction"
    
    # Test with "name" in description dict
    item = {
        "code": "45000000",
        "descriptions": [
            {"language": "FR", "name": "Travaux de construction"},
        ],
    }
    assert _extract_label_from_cpv_item(item, "FR") == "Travaux de construction"
    
    # Test with "description" in description dict
    item = {
        "code": "45000000",
        "descriptions": [
            {"language": "FR", "description": "Travaux de construction"},
        ],
    }
    assert _extract_label_from_cpv_item(item, "FR") == "Travaux de construction"


def test_extract_label_returns_none_for_invalid_input() -> None:
    """Test that extraction returns None for invalid inputs."""
    # Non-dict input
    assert _extract_label_from_cpv_item(None, "FR") is None
    assert _extract_label_from_cpv_item("not a dict", "FR") is None
    
    # Empty dict
    assert _extract_label_from_cpv_item({}, "FR") is None
    
    # Dict without any label fields
    assert _extract_label_from_cpv_item({"code": "45000000"}, "FR") is None
    
    # Dict with empty descriptions
    assert _extract_label_from_cpv_item({"code": "45000000", "descriptions": []}, "FR") is None
