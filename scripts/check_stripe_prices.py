import os
import stripe

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")
print(f"Stripe API Key prefix: {stripe.api_key[:12] if stripe.api_key else 'None'}")

keys = [
    "STRIPE_PRICE_DEMO",
    "STRIPE_PRICE_BASE",
    "STRIPE_PRICE_PROFESSIONAL",
    "STRIPE_PRICE_ENTERPRISE",
    "STRIPE_PRICE_CREDIT_DEMO",
    "STRIPE_PRICE_CREDIT_PROFESSIONAL",
]

for k in keys:
    pid = os.environ.get(k)
    if pid:
        try:
            price = stripe.Price.retrieve(pid)
            print(f"{k} ({pid}): amount={price.unit_amount / 100:.2f} {price.currency.upper()} (recurring={getattr(price.recurring, 'interval', None)})")
        except Exception as e:
            print(f"{k} ({pid}) Error: {e}")
    else:
        print(f"{k}: NOT SET")
