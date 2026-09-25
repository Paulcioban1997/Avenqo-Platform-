import os
import stripe

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")

print("=== Stripe Products & Prices ===")
products = stripe.Product.list(limit=50)
for p in products.data:
    print(f"\nProduct ID={p.id} Name='{p.name}' Active={p.active}")
    prices = stripe.Price.list(product=p.id, limit=20)
    for pr in prices.data:
        amt = f"{pr.unit_amount / 100:.2f} {pr.currency.upper()}" if pr.unit_amount is not None else "N/A"
        rec = pr.recurring.interval if pr.recurring else "one_time"
        print(f"   Price ID={pr.id} Amount={amt} Type={rec} Active={pr.active}")
