#!/usr/bin/env python3
"""
Create Stripe products and prices for ProcureWatch plans.
Run: STRIPE_SECRET_KEY=sk_test_xxx python scripts/stripe_setup.py
"""
import os, sys

try:
    import stripe
except ImportError:
    print("ERROR: pip install stripe"); sys.exit(1)


def main():
    api_key = os.environ.get("STRIPE_SECRET_KEY")
    if not api_key:
        print("ERROR: Set STRIPE_SECRET_KEY"); sys.exit(1)

    stripe.api_key = api_key
    print(f"Mode: {'TEST' if api_key.startswith('sk_test_') else 'PRODUCTION'}\n")

    pro = stripe.Product.create(
        name="ProcureWatch Pro",
        description="5 veilles, digest quotidien, 20 résumés IA/mois, export CSV, 1 an d'historique",
        metadata={"plan": "pro"},
    )
    biz = stripe.Product.create(
        name="ProcureWatch Business",
        description="Veilles illimitées, alertes temps réel, IA illimitée, API, 5 sièges, 3 ans d'historique",
        metadata={"plan": "business"},
    )

    prices = {
        "STRIPE_PRICE_PRO_MONTHLY": stripe.Price.create(
            product=pro.id, unit_amount=4900, currency="eur", recurring={"interval": "month"},
        ),
        "STRIPE_PRICE_PRO_ANNUAL": stripe.Price.create(
            product=pro.id, unit_amount=46800, currency="eur", recurring={"interval": "year"},
        ),
        "STRIPE_PRICE_BUSINESS_MONTHLY": stripe.Price.create(
            product=biz.id, unit_amount=14900, currency="eur", recurring={"interval": "month"},
        ),
        "STRIPE_PRICE_BUSINESS_ANNUAL": stripe.Price.create(
            product=biz.id, unit_amount=142800, currency="eur", recurring={"interval": "year"},
        ),
    }

    print("=" * 60)
    print("Add to Railway environment variables:")
    print("=" * 60)
    for key, price in prices.items():
        print(f"{key}={price.id}")
    print(f"\nSTRIPE_SECRET_KEY={api_key[:12]}...")
    print("STRIPE_WEBHOOK_SECRET=whsec_...  (from Stripe Dashboard)")
    print("\nWebhook URL: https://api.procurewatch.eu/api/billing/webhook")
    print("Events: checkout.session.completed, customer.subscription.updated,")
    print("        customer.subscription.deleted, invoice.payment_failed")


if __name__ == "__main__":
    main()
