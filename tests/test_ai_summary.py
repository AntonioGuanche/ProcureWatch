"""Tests for AI summary service (prompt building, usage checks)."""
import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

from app.services.ai_summary import _build_prompt, check_ai_usage


def _make_notice(**kwargs):
    """Create a mock notice with defaults."""
    n = MagicMock()
    n.title = kwargs.get("title", "Marché de nettoyage")
    n.description = kwargs.get("description", "Nettoyage des bureaux du SPF Finances")
    n.cpv_main_code = kwargs.get("cpv_main_code", "90910000-9")
    n.organisation_names = kwargs.get("organisation_names", {"fra": "SPF Finances", "nld": "FOD Financiën"})
    n.estimated_value = kwargs.get("estimated_value", Decimal("50000.00"))
    n.deadline = kwargs.get("deadline", datetime(2026, 3, 15, 12, 0, 0))
    n.notice_type = kwargs.get("notice_type", "cn")
    n.form_type = kwargs.get("form_type", "competition")
    n.nuts_codes = kwargs.get("nuts_codes", ["BE100"])
    n.award_winner_name = kwargs.get("award_winner_name", None)
    n.award_value = kwargs.get("award_value", None)
    n.number_tenders_received = kwargs.get("number_tenders_received", None)
    return n


class TestBuildPrompt:
    def test_cn_prompt_structure(self):
        """Contract Notice prompt has 5-point structure."""
        notice = _make_notice()
        prompt = _build_prompt(notice, lang="fr")
        assert "Objet" in prompt
        assert "Qui" in prompt
        assert "Échéance" in prompt
        assert "SPF Finances" in prompt
        assert "90910000-9" in prompt
        assert "soumissionnaire" in prompt

    def test_can_prompt_structure(self):
        """Contract Award Notice prompt has award-specific structure."""
        notice = _make_notice(
            award_winner_name="CleanCorp SA",
            award_value=Decimal("45000.00"),
            number_tenders_received=5,
        )
        prompt = _build_prompt(notice, lang="fr")
        assert "Adjudicataire" in prompt
        assert "CleanCorp SA" in prompt
        assert "45,000.00" in prompt or "45000" in prompt
        assert "5" in prompt
        assert "attribution" in prompt.lower()

    def test_multilang_prompt(self):
        """Prompts in different languages."""
        notice = _make_notice()
        fr = _build_prompt(notice, lang="fr")
        nl = _build_prompt(notice, lang="nl")
        en = _build_prompt(notice, lang="en")
        assert "Réponds en français" in fr
        assert "Antwoord in het Nederlands" in nl
        assert "Reply in English" in en

    def test_long_description_truncated(self):
        """Long descriptions are truncated to 2000 chars."""
        notice = _make_notice(description="A" * 5000)
        prompt = _build_prompt(notice, lang="fr")
        assert "..." in prompt
        # Should not contain full 5000 chars
        assert len(prompt) < 5000

    def test_missing_fields_handled(self):
        """Prompt handles None fields gracefully."""
        notice = _make_notice(
            description=None,
            estimated_value=None,
            deadline=None,
            nuts_codes=None,
        )
        prompt = _build_prompt(notice, lang="fr")
        assert "Marché de nettoyage" in prompt
        assert "Valeur estimée" not in prompt


class TestCheckAiUsage:
    def test_free_plan_blocked(self):
        """Free plan users cannot use AI."""
        user = MagicMock()
        user.plan = "free"
        user.subscription_status = "none"
        user.subscription_ends_at = None
        user.ai_usage_count = 0
        user.ai_usage_reset_at = None
        db = MagicMock()
        error = check_ai_usage(db, user)
        assert error is not None
        assert "Découverte" in error

    def test_pro_plan_allowed(self):
        """Pro plan users can use AI (within limits)."""
        user = MagicMock()
        user.plan = "pro"
        user.subscription_status = "active"
        user.subscription_ends_at = None
        user.ai_usage_count = 5
        user.ai_usage_reset_at = datetime.now(timezone.utc)
        db = MagicMock()
        error = check_ai_usage(db, user)
        assert error is None

    def test_pro_plan_exhausted(self):
        """Pro plan users blocked after 20 uses."""
        user = MagicMock()
        user.plan = "pro"
        user.subscription_status = "active"
        user.subscription_ends_at = None
        user.ai_usage_count = 20
        user.ai_usage_reset_at = datetime.now(timezone.utc)
        db = MagicMock()
        error = check_ai_usage(db, user)
        assert error is not None
        assert "20" in error

    def test_business_unlimited(self):
        """Business plan has unlimited AI."""
        user = MagicMock()
        user.plan = "business"
        user.subscription_status = "active"
        user.subscription_ends_at = None
        user.ai_usage_count = 999
        user.ai_usage_reset_at = datetime.now(timezone.utc)
        db = MagicMock()
        error = check_ai_usage(db, user)
        assert error is None
