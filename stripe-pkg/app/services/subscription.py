"""
Subscription plans: definitions, limits, and usage enforcement.

Plans:
  - free:     1 watchlist, 10 results/watchlist, TED+BOSA, no digest, no AI, 30d history
  - pro:      5 watchlists, unlimited results, daily digest, 20 AI/month, CSV, 1yr history
  - business: unlimited watchlists, unlimited results, realtime digest, unlimited AI, API, 3yr history
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ── Plan definitions ──────────────────────────────────────────────────


@dataclass(frozen=True)
class PlanLimits:
    """Limits for a subscription plan."""

    name: str
    display_name: str  # for UI
    max_watchlists: int  # -1 = unlimited
    max_results_per_watchlist: int  # -1 = unlimited
    email_digest: bool
    realtime_alerts: bool
    ai_summaries_per_month: int  # -1 = unlimited, 0 = none
    csv_export: bool
    api_access: bool
    max_seats: int
    history_days: int  # 30, 365, 1095


PLANS: dict[str, PlanLimits] = {
    "free": PlanLimits(
        name="free",
        display_name="Découverte",
        max_watchlists=1,
        max_results_per_watchlist=10,
        email_digest=False,
        realtime_alerts=False,
        ai_summaries_per_month=0,
        csv_export=False,
        api_access=False,
        max_seats=1,
        history_days=30,
    ),
    "pro": PlanLimits(
        name="pro",
        display_name="Pro",
        max_watchlists=5,
        max_results_per_watchlist=-1,
        email_digest=True,
        realtime_alerts=False,
        ai_summaries_per_month=20,
        csv_export=True,
        api_access=False,
        max_seats=1,
        history_days=365,
    ),
    "business": PlanLimits(
        name="business",
        display_name="Business",
        max_watchlists=-1,
        max_results_per_watchlist=-1,
        email_digest=True,
        realtime_alerts=True,
        ai_summaries_per_month=-1,
        csv_export=True,
        api_access=True,
        max_seats=5,
        history_days=1095,
    ),
}


def get_plan_limits(plan_name: str) -> PlanLimits:
    """Get limits for a plan. Defaults to free if unknown."""
    return PLANS.get(plan_name, PLANS["free"])


# ── Usage checks ──────────────────────────────────────────────────────


def check_watchlist_limit(db: Session, user) -> Optional[str]:
    """
    Check if user can create another watchlist.
    Returns error message or None if OK.
    """
    from app.models.watchlist import Watchlist

    limits = get_plan_limits(user.plan)
    if limits.max_watchlists == -1:
        return None

    count = db.query(Watchlist).filter(Watchlist.user_id == user.id).count()
    if count >= limits.max_watchlists:
        return (
            f"Votre plan {limits.display_name} est limité à {limits.max_watchlists} "
            f"veille{'s' if limits.max_watchlists > 1 else ''}. "
            f"Passez au plan supérieur pour en créer davantage."
        )
    return None


def check_feature_access(user, feature: str) -> Optional[str]:
    """
    Check if user's plan grants access to a feature.
    feature: 'email_digest' | 'csv_export' | 'api_access' | 'ai_summary' | 'realtime_alerts'
    Returns error message or None if OK.
    """
    limits = get_plan_limits(user.plan)

    checks = {
        "email_digest": (limits.email_digest, "le digest email"),
        "csv_export": (limits.csv_export, "l'export CSV"),
        "api_access": (limits.api_access, "l'accès API"),
        "ai_summary": (limits.ai_summaries_per_month != 0, "les résumés IA"),
        "realtime_alerts": (limits.realtime_alerts, "les alertes temps réel"),
    }

    allowed, feature_name = checks.get(feature, (True, feature))
    if not allowed:
        return (
            f"Votre plan {limits.display_name} n'inclut pas {feature_name}. "
            f"Passez au plan supérieur pour y accéder."
        )
    return None


def is_subscription_active(user) -> bool:
    """
    Check if user has an active paid subscription.
    Returns True for: active, trialing.
    Returns True if subscription_ends_at is in the future (grace period after cancel).
    """
    if user.plan == "free":
        return True  # free always "active"

    if user.subscription_status in ("active", "trialing"):
        return True

    # Grace period: canceled but period hasn't ended
    if (
        user.subscription_status == "canceled"
        and user.subscription_ends_at
        and user.subscription_ends_at > datetime.now(timezone.utc)
    ):
        return True

    return False


def effective_plan(user) -> str:
    """
    Return the user's effective plan, considering subscription status.
    If subscription expired/failed, downgrade to free.
    """
    if user.plan == "free":
        return "free"

    if is_subscription_active(user):
        return user.plan

    # Subscription not active → effectively free
    return "free"
