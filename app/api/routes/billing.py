"""
Billing routes: Stripe Checkout, Customer Portal, Subscription status, Webhook.

POST /api/billing/checkout       → Create Stripe Checkout Session
POST /api/billing/portal         → Create Stripe Customer Portal Session
GET  /api/billing/subscription   → Current subscription details
GET  /api/billing/plans          → Available plans & prices (public)
POST /api/billing/webhook        → Stripe webhook handler (no auth)
"""
import logging
from datetime import datetime, timezone
from typing import Optional

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.routes.auth import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models.user import User
from app.services.subscription import PLANS, effective_plan, get_plan_limits

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["billing"])


# ── Helpers ───────────────────────────────────────────────────────────


def _init_stripe() -> None:
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=503, detail="Stripe not configured")
    stripe.api_key = settings.stripe_secret_key


def _get_or_create_customer(user: User) -> str:
    if user.stripe_customer_id:
        return user.stripe_customer_id
    customer = stripe.Customer.create(
        email=user.email, name=user.name, metadata={"user_id": user.id},
    )
    return customer.id


def _resolve_price_id(plan: str, interval: str) -> str:
    price_map = {
        ("pro", "month"): settings.stripe_price_pro_monthly,
        ("pro", "year"): settings.stripe_price_pro_annual,
        ("business", "month"): settings.stripe_price_business_monthly,
        ("business", "year"): settings.stripe_price_business_annual,
    }
    price_id = price_map.get((plan, interval))
    if not price_id:
        raise HTTPException(status_code=400, detail=f"Invalid plan/interval: {plan}/{interval}")
    return price_id


# ── Schemas ───────────────────────────────────────────────────────────


class CheckoutRequest(BaseModel):
    plan: str          # "pro" or "business"
    interval: str = "month"  # "month" or "year"


class CheckoutResponse(BaseModel):
    checkout_url: str


class PortalResponse(BaseModel):
    portal_url: str


class SubscriptionResponse(BaseModel):
    plan: str
    effective_plan: str
    display_name: str
    status: str
    current_period_end: Optional[str] = None
    cancel_at_period_end: bool = False
    limits: dict


# ── Endpoints ─────────────────────────────────────────────────────────


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout_session(
    body: CheckoutRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CheckoutResponse:
    """Create a Stripe Checkout Session for upgrading."""
    _init_stripe()

    if body.plan not in ("pro", "business"):
        raise HTTPException(status_code=400, detail="Plan invalide. Choisissez 'pro' ou 'business'.")
    if body.interval not in ("month", "year"):
        raise HTTPException(status_code=400, detail="Interval invalide. Choisissez 'month' ou 'year'.")

    customer_id = _get_or_create_customer(current_user)
    if not current_user.stripe_customer_id:
        current_user.stripe_customer_id = customer_id
        db.commit()

    price_id = _resolve_price_id(body.plan, body.interval)
    app_url = settings.app_url.rstrip("/")

    session = stripe.checkout.Session.create(
        customer=customer_id,
        customer_update={"name": "auto", "address": "auto"},
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{app_url}/billing?session_id={{CHECKOUT_SESSION_ID}}&status=success",
        cancel_url=f"{app_url}/billing?status=canceled",
        metadata={"user_id": current_user.id, "plan": body.plan},
        allow_promotion_codes=True,
        billing_address_collection="auto",
        tax_id_collection={"enabled": True},
    )
    return CheckoutResponse(checkout_url=session.url)


@router.post("/portal", response_model=PortalResponse)
async def create_portal_session(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PortalResponse:
    """Create a Stripe Customer Portal session."""
    _init_stripe()
    if not current_user.stripe_customer_id:
        raise HTTPException(status_code=400, detail="Pas d'abonnement actif à gérer.")

    app_url = settings.app_url.rstrip("/")
    session = stripe.billing_portal.Session.create(
        customer=current_user.stripe_customer_id,
        return_url=f"{app_url}/billing",
    )
    return PortalResponse(portal_url=session.url)


@router.get("/subscription", response_model=SubscriptionResponse)
async def get_subscription(
    current_user: User = Depends(get_current_user),
) -> SubscriptionResponse:
    """Get current user's subscription details."""
    eff = effective_plan(current_user)
    limits = get_plan_limits(eff)

    cancel_at_period_end = False
    if current_user.stripe_subscription_id and settings.stripe_secret_key:
        try:
            stripe.api_key = settings.stripe_secret_key
            sub = stripe.Subscription.retrieve(current_user.stripe_subscription_id)
            cancel_at_period_end = sub.cancel_at_period_end
        except Exception:
            pass

    return SubscriptionResponse(
        plan=current_user.plan,
        effective_plan=eff,
        display_name=limits.display_name,
        status=current_user.subscription_status,
        current_period_end=(
            current_user.subscription_ends_at.isoformat()
            if current_user.subscription_ends_at else None
        ),
        cancel_at_period_end=cancel_at_period_end,
        limits={
            "max_watchlists": limits.max_watchlists,
            "max_results_per_watchlist": limits.max_results_per_watchlist,
            "email_digest": limits.email_digest,
            "csv_export": limits.csv_export,
            "api_access": limits.api_access,
            "ai_summaries_per_month": limits.ai_summaries_per_month,
            "max_seats": limits.max_seats,
            "history_days": limits.history_days,
        },
    )


@router.get("/plans")
async def get_plans() -> list[dict]:
    """Return available plans with pricing (public, no auth)."""
    return [
        {
            "name": name,
            "display_name": lim.display_name,
            "price_monthly_eur": {"free": 0, "pro": 4900, "business": 14900}.get(name, 0),
            "price_annual_eur": {"free": 0, "pro": 46800, "business": 142800}.get(name, 0),
            "features": {
                "max_watchlists": lim.max_watchlists,
                "max_results_per_watchlist": lim.max_results_per_watchlist,
                "email_digest": lim.email_digest,
                "realtime_alerts": lim.realtime_alerts,
                "csv_export": lim.csv_export,
                "api_access": lim.api_access,
                "ai_summaries_per_month": lim.ai_summaries_per_month,
                "max_seats": lim.max_seats,
                "history_days": lim.history_days,
            },
        }
        for name, lim in PLANS.items()
    ]


# ── Stripe Webhook ────────────────────────────────────────────────────


@router.post("/webhook", include_in_schema=False)
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """Handle Stripe webhook events (no auth — verified via signature)."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    webhook_secret = settings.stripe_webhook_secret
    if not webhook_secret:
        raise HTTPException(status_code=503, detail="Webhook not configured")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    except Exception as e:
        logger.error(f"Stripe webhook error: {e}")
        raise HTTPException(status_code=400, detail="Webhook error")

    event_type = event["type"]
    data = event["data"]["object"]
    logger.info(f"Stripe webhook: {event_type}")

    if event_type == "checkout.session.completed":
        _handle_checkout_completed(db, data)
    elif event_type == "customer.subscription.updated":
        _handle_subscription_updated(db, data)
    elif event_type == "customer.subscription.deleted":
        _handle_subscription_deleted(db, data)
    elif event_type == "invoice.payment_failed":
        _handle_payment_failed(db, data)

    return {"status": "ok"}


def _find_user_by_customer(db: Session, customer_id: str) -> Optional[User]:
    return db.query(User).filter(User.stripe_customer_id == customer_id).first()


def _handle_checkout_completed(db: Session, session: dict) -> None:
    customer_id = session.get("customer")
    subscription_id = session.get("subscription")
    metadata = session.get("metadata", {})
    plan = metadata.get("plan", "pro")
    user_id = metadata.get("user_id")

    user = None
    if user_id:
        user = db.query(User).filter(User.id == user_id).first()
    if not user and customer_id:
        user = _find_user_by_customer(db, customer_id)
    if not user:
        logger.error(f"checkout.session.completed: user not found (customer={customer_id})")
        return

    user.plan = plan
    user.stripe_customer_id = customer_id
    user.stripe_subscription_id = subscription_id
    user.subscription_status = "active"

    if subscription_id:
        try:
            stripe.api_key = settings.stripe_secret_key
            sub = stripe.Subscription.retrieve(subscription_id)
            user.subscription_ends_at = datetime.fromtimestamp(sub.current_period_end, tz=timezone.utc)
        except Exception as e:
            logger.warning(f"Could not fetch subscription details: {e}")

    db.commit()
    logger.info(f"Subscription activated: user={user.email} plan={plan}")


def _handle_subscription_updated(db: Session, subscription: dict) -> None:
    customer_id = subscription.get("customer")
    user = _find_user_by_customer(db, customer_id)
    if not user:
        return

    items = subscription.get("items", {}).get("data", [])
    if items:
        price_id = items[0].get("price", {}).get("id", "")
        plan = _price_to_plan(price_id)
        if plan:
            user.plan = plan

    user.stripe_subscription_id = subscription.get("id")
    user.subscription_status = subscription.get("status", "active")
    period_end = subscription.get("current_period_end")
    if period_end:
        user.subscription_ends_at = datetime.fromtimestamp(period_end, tz=timezone.utc)

    db.commit()
    logger.info(f"Subscription updated: user={user.email} status={user.subscription_status}")


def _handle_subscription_deleted(db: Session, subscription: dict) -> None:
    customer_id = subscription.get("customer")
    user = _find_user_by_customer(db, customer_id)
    if not user:
        return

    user.subscription_status = "canceled"
    period_end = subscription.get("current_period_end")
    if period_end:
        user.subscription_ends_at = datetime.fromtimestamp(period_end, tz=timezone.utc)

    db.commit()
    logger.info(f"Subscription canceled: user={user.email} grace_until={user.subscription_ends_at}")


def _handle_payment_failed(db: Session, invoice: dict) -> None:
    customer_id = invoice.get("customer")
    user = _find_user_by_customer(db, customer_id)
    if not user:
        return
    user.subscription_status = "past_due"
    db.commit()
    logger.warning(f"Payment failed: user={user.email}")


def _price_to_plan(price_id: str) -> Optional[str]:
    price_plan_map = {}
    if settings.stripe_price_pro_monthly:
        price_plan_map[settings.stripe_price_pro_monthly] = "pro"
    if settings.stripe_price_pro_annual:
        price_plan_map[settings.stripe_price_pro_annual] = "pro"
    if settings.stripe_price_business_monthly:
        price_plan_map[settings.stripe_price_business_monthly] = "business"
    if settings.stripe_price_business_annual:
        price_plan_map[settings.stripe_price_business_annual] = "business"
    return price_plan_map.get(price_id)
