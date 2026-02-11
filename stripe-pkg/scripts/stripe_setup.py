#!/usr/bin/env python3
"""
Create Stripe products and prices for ProcureWatch plans.

Run once in test mode, then once in production:
  STRIPE_SECRET_KEY=sk_test_xxx python scripts/stripe_setup.py
  STRIPE_SECRET_KEY=sk_live_xxx python scripts/stripe_setup.py

Outputs the Price IDs to configure in Railway environment variables.
"""
import os
import sys

try:
    import stripe
except ImportError:
    print("ERROR: pip install stripe")
    sys.exit(1)


def main():
    api_key = os.environ.get("STRIPE_SECRET_KEY")
    if not api_key:
        print("ERROR: Set STRIPE_SECRET_KEY environment variable")
        sys.exit(1)

    stripe.api_key = api_key
    is_test = api_key.startswith("sk_test_")
    print(f"Mode: {'TEST' if is_test else 'PRODUCTION'}")
    print()

    # ── Create Products ───────────────────────────────────────────────

    pro_product = stripe.Product.create(
        name="ProcureWatch Pro",
        description=(
            "5 veilles actives, digest email quotidien, résumés IA (20/mois), "
            "export CSV, 1 an d'historique"
        ),
        metadata={"plan": "pro"},
    )
    print(f"✅ Product Pro: {pro_product.id}")

    business_product = stripe.Product.create(
        name="ProcureWatch Business",
        description=(
            "Veilles illimitées, alertes temps réel, IA illimitée, "
            "accès API, 5 sièges, 3 ans d'historique"
        ),
        metadata={"plan": "business"},
    )
    print(f"✅ Product Business: {business_product.id}")

    # ── Create Prices ─────────────────────────────────────────────────

    # Pro Monthly: 49€/mois
    pro_monthly = stripe.Price.create(
        product=pro_product.id,
        unit_amount=4900,
        currency="eur",
        recurring={"interval": "month"},
        metadata={"plan": "pro", "interval": "month"},
    )
    print(f"✅ Price Pro Monthly (49€): {pro_monthly.id}")

    # Pro Annual: 39€/mois → 468€/an
    pro_annual = stripe.Price.create(
        product=pro_product.id,
        unit_amount=46800,
        currency="eur",
        recurring={"interval": "year"},
        metadata={"plan": "pro", "interval": "year"},
    )
    print(f"✅ Price Pro Annual (468€/an = 39€/mo): {pro_annual.id}")

    # Business Monthly: 149€/mois
    business_monthly = stripe.Price.create(
        product=business_product.id,
        unit_amount=14900,
        currency="eur",
        recurring={"interval": "month"},
        metadata={"plan": "business", "interval": "month"},
    )
    print(f"✅ Price Business Monthly (149€): {business_monthly.id}")

    # Business Annual: 119€/mois → 1428€/an
    business_annual = stripe.Price.create(
        product=business_product.id,
        unit_amount=142800,
        currency="eur",
        recurring={"interval": "year"},
        metadata={"plan": "business", "interval": "year"},
    )
    print(f"✅ Price Business Annual (1428€/an = 119€/mo): {business_annual.id}")

    # ── Summary ───────────────────────────────────────────────────────

    print()
    print("=" * 60)
    print("Add these to Railway environment variables:")
    print("=" * 60)
    print(f"STRIPE_PRICE_PRO_MONTHLY={pro_monthly.id}")
    print(f"STRIPE_PRICE_PRO_ANNUAL={pro_annual.id}")
    print(f"STRIPE_PRICE_BUSINESS_MONTHLY={business_monthly.id}")
    print(f"STRIPE_PRICE_BUSINESS_ANNUAL={business_annual.id}")
    print()
    print("Also configure:")
    print(f"STRIPE_SECRET_KEY={api_key[:12]}...")
    print("STRIPE_WEBHOOK_SECRET=whsec_...  (from Stripe Dashboard → Webhooks)")
    print()
    print("Webhook URL: https://api.procurewatch.eu/api/billing/webhook")
    print("Events to subscribe:")
    print("  - checkout.session.completed")
    print("  - customer.subscription.updated")
    print("  - customer.subscription.deleted")
    print("  - invoice.payment_failed")


if __name__ == "__main__":
    main()
