"""Tests for NUTS reference service — search + country filtering."""
import pytest
from app.services.nuts_reference import search_nuts, NUTS_REFERENCE


@pytest.mark.unit
class TestNutsReference:
    """NUTS_REFERENCE data integrity."""

    def test_reference_not_empty(self):
        assert len(NUTS_REFERENCE) > 50

    def test_all_entries_have_code_and_label(self):
        for code, label in NUTS_REFERENCE:
            assert code, f"Empty code found"
            assert label, f"Empty label for {code}"

    def test_belgium_complete(self):
        """Belgium should have level 1, 2, and 3 entries."""
        be_codes = [c for c, _ in NUTS_REFERENCE if c.startswith("BE")]
        assert len(be_codes) >= 40  # BE has ~55+ entries
        # Level 1
        assert any(c == "BE1" for c in be_codes)
        assert any(c == "BE2" for c in be_codes)
        assert any(c == "BE3" for c in be_codes)
        # Level 2
        assert any(c == "BE21" for c in be_codes)  # Anvers
        # Level 3
        assert any(c == "BE231" for c in be_codes)  # Arr. Alost


@pytest.mark.unit
class TestSearchNuts:
    """search_nuts() function."""

    def test_empty_query_returns_first_N(self):
        results = search_nuts("", limit=5)
        assert len(results) == 5
        assert all("code" in r and "label" in r for r in results)

    def test_search_by_code(self):
        results = search_nuts("BE23")
        codes = [r["code"] for r in results]
        assert all(c.startswith("BE23") for c in codes)

    def test_search_by_label(self):
        results = search_nuts("Bruxelles")
        assert len(results) >= 1
        assert any("Bruxelles" in r["label"] for r in results)

    def test_search_case_insensitive(self):
        results = search_nuts("bruxelles")
        assert len(results) >= 1

    def test_filter_by_country_be(self):
        results = search_nuts("", countries=["BE"], limit=50)
        assert all(r["code"].startswith("BE") for r in results)

    def test_filter_by_country_fr(self):
        results = search_nuts("", countries=["FR"], limit=50)
        assert all(r["code"].startswith("FR") for r in results)

    def test_filter_by_multiple_countries(self):
        results = search_nuts("", countries=["BE", "FR"], limit=100)
        assert all(
            r["code"].startswith("BE") or r["code"].startswith("FR")
            for r in results
        )

    def test_filter_country_plus_search(self):
        results = search_nuts("Liège", countries=["BE"])
        assert len(results) >= 1
        assert all(r["code"].startswith("BE") for r in results)
        assert any("Liège" in r["label"] for r in results)

    def test_no_results(self):
        results = search_nuts("xxxxxxx")
        assert results == []

    def test_country_filter_empty_list(self):
        """Empty country list = no filter."""
        results = search_nuts("", countries=[], limit=5)
        assert len(results) == 5

    def test_limit_respected(self):
        results = search_nuts("", limit=3)
        assert len(results) == 3
