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


@dataclass(frozen=True)
class PlanLimits:
    name: str
    display_name: str
    max_watchlists: int          # -1 = unlimited
    max_results_per_watchlist: int
    email_digest: bool
    digest_frequency: str        # "none", "weekly", "daily", "realtime"
    realtime_alerts: bool
    ai_summaries_per_month: int  # -1 = unlimited, 0 = none
    csv_export: bool
    api_access: bool
    max_seats: int
    history_days: int


PLANS: dict[str, PlanLimits] = {
    "free": PlanLimits(
        name="free", display_name="Découverte",
        max_watchlists=1, max_results_per_watchlist=10,
        email_digest=True, digest_frequency="weekly", realtime_alerts=False,
        ai_summaries_per_month=0, csv_export=False,
        api_access=False, max_seats=1, history_days=30,
    ),
    "pro": PlanLimits(
        name="pro", display_name="Pro",
        max_watchlists=5, max_results_per_watchlist=-1,
        email_digest=True, digest_frequency="daily", realtime_alerts=False,
        ai_summaries_per_month=20, csv_export=True,
        api_access=False, max_seats=1, history_days=365,
    ),
    "business": PlanLimits(
        name="business", display_name="Business",
        max_watchlists=-1, max_results_per_watchlist=-1,
        email_digest=True, digest_frequency="realtime", realtime_alerts=True,
        ai_summaries_per_month=-1, csv_export=True,
        api_access=True, max_seats=5, history_days=1095,
    ),
}


def get_plan_limits(plan_name: str) -> PlanLimits:
    return PLANS.get(plan_name, PLANS["free"])


def check_watchlist_limit(db: Session, user) -> Optional[str]:
    """Return error message if user hit watchlist limit, else None."""
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
    """Return error message if feature not available on user's plan, else None."""
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
    if user.plan == "free":
        return True
    if user.subscription_status in ("active", "trialing"):
        return True
    if (
        user.subscription_status == "canceled"
        and user.subscription_ends_at
        and user.subscription_ends_at > datetime.now(timezone.utc)
    ):
        return True
    return False


def effective_plan(user) -> str:
    """Return effective plan (downgrades to free if subscription expired)."""
    if user.plan == "free":
        return "free"
    return user.plan if is_subscription_active(user) else "free"
