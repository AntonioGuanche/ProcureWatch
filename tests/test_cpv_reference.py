"""Tests for CPV reference search."""
import pytest
from app.services.cpv_reference import search_cpv, CPV_REFERENCE


@pytest.mark.unit
class TestCpvReference:
    """CPV_REFERENCE data integrity."""

    def test_reference_not_empty(self):
        assert len(CPV_REFERENCE) > 100

    def test_all_entries_have_code_and_label(self):
        for code, label in CPV_REFERENCE:
            assert code, "Empty code"
            assert label, f"Empty label for {code}"
            assert len(code) == 8, f"CPV code {code} should be 8 digits"


@pytest.mark.unit
class TestSearchCpv:
    """search_cpv() function."""

    def test_empty_query_returns_results(self):
        results = search_cpv("", limit=10)
        assert len(results) == 10
        assert all("code" in r and "label" in r for r in results)

    def test_search_by_code_prefix(self):
        results = search_cpv("45")
        assert len(results) >= 5
        assert all(r["code"].startswith("45") for r in results)

    def test_search_by_label(self):
        results = search_cpv("construction")
        assert len(results) >= 1
        assert any("onstruction" in r["label"].lower() for r in results)

    def test_search_by_label_case_insensitive(self):
        results = search_cpv("CONSTRUCTION")
        assert len(results) >= 1

    def test_search_it_services(self):
        results = search_cpv("72")
        assert len(results) >= 1
        # substring match: "72" may appear anywhere in code or label
        assert any(r["code"].startswith("72") for r in results)

    def test_no_results(self):
        results = search_cpv("zzzzzzzzz")
        assert results == []

    def test_limit_respected(self):
        results = search_cpv("45", limit=3)
        assert len(results) <= 3
