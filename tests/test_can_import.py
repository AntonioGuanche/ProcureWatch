"""Tests for CAN (Contract Award Notice) field extraction from TED data."""
import pytest
from decimal import Decimal

from app.services.notice_service import _map_ted_item_to_notice, _safe_int, _extract_award_criteria


class TestSafeInt:
    def test_none(self):
        assert _safe_int(None) is None

    def test_int(self):
        assert _safe_int(5) == 5

    def test_string(self):
        assert _safe_int("5") == 5

    def test_float_string(self):
        assert _safe_int("5.7") == 5

    def test_nested_dict(self):
        assert _safe_int({"eng": "3"}) == 3

    def test_nested_list(self):
        assert _safe_int(["7"]) == 7

    def test_invalid(self):
        assert _safe_int("abc") is None


class TestExtractAwardCriteria:
    def test_with_criteria(self):
        item = {"award-criteria-type": "price"}
        result = _extract_award_criteria(item)
        assert result == {"type": "price"}

    def test_without_criteria(self):
        item = {}
        result = _extract_award_criteria(item)
        assert result is None

    def test_multilang_criteria(self):
        item = {"award-criteria-type": {"eng": ["quality"]}}
        result = _extract_award_criteria(item)
        assert result is not None
        assert "quality" in result["type"]


class TestMapTedCAN:
    """Test that CAN-specific fields are correctly extracted."""

    def _sample_can_item(self) -> dict:
        return {
            "publication-number": "2026/S 025-012345",
            "publication-date": "2026-02-10",
            "notice-title": {"eng": ["Road Construction Award"]},
            "notice-type": "can",
            "notice-subtype": "25",
            "buyer-name": {"eng": ["City of Brussels"]},
            "main-classification-proc": "45233120",
            "place-of-performance": ["BE100"],
            "winner-name": {"eng": ["BuildCorp NV"], "nld": ["BuildCorp NV"]},
            "total-value": "1500000.00",
            "contract-value-lot": "1500000.00",
            "number-of-tenders": "7",
            "award-criteria-type": "price",
            "award-date": "2026-01-15",
            "procedure-identifier": "proc-abc-123",
            "reference-number": "REF-2025-789",
        }

    def test_can_winner_name(self):
        item = self._sample_can_item()
        result = _map_ted_item_to_notice(item, "2026/S 025-012345")
        assert result["award_winner_name"] is not None
        assert "BuildCorp" in result["award_winner_name"]

    def test_can_award_value(self):
        item = self._sample_can_item()
        result = _map_ted_item_to_notice(item, "2026/S 025-012345")
        assert result["award_value"] is not None
        assert result["award_value"] == Decimal("1500000.00")

    def test_can_number_tenders(self):
        item = self._sample_can_item()
        result = _map_ted_item_to_notice(item, "2026/S 025-012345")
        assert result["number_tenders_received"] == 7

    def test_can_award_date(self):
        item = self._sample_can_item()
        result = _map_ted_item_to_notice(item, "2026/S 025-012345")
        assert result["award_date"] is not None
        assert result["award_date"].year == 2026
        assert result["award_date"].month == 1
        assert result["award_date"].day == 15

    def test_can_award_criteria(self):
        item = self._sample_can_item()
        result = _map_ted_item_to_notice(item, "2026/S 025-012345")
        assert result["award_criteria_json"] is not None
        assert result["award_criteria_json"]["type"] == "price"

    def test_can_procedure_id(self):
        item = self._sample_can_item()
        result = _map_ted_item_to_notice(item, "2026/S 025-012345")
        assert result["procedure_id"] == "proc-abc-123"

    def test_can_reference_number(self):
        item = self._sample_can_item()
        result = _map_ted_item_to_notice(item, "2026/S 025-012345")
        assert result["reference_number"] == "REF-2025-789"

    def test_cn_no_award_fields(self):
        """Regular Contract Notice should have None award fields."""
        item = {
            "publication-number": "2026/S 025-099999",
            "publication-date": "2026-02-10",
            "notice-title": {"eng": ["Road Construction Tender"]},
            "notice-type": "cn",
            "buyer-name": {"eng": ["City of Brussels"]},
            "main-classification-proc": "45233120",
        }
        result = _map_ted_item_to_notice(item, "2026/S 025-099999")
        assert result["award_winner_name"] is None
        assert result["award_value"] is None
        assert result["number_tenders_received"] is None
        assert result["award_date"] is None
