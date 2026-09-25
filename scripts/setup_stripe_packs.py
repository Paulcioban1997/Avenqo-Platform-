import os
import stripe

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")

# Check if $35 price exists for 25k credits
prod_25k_id = "prod_VBdMnuDMgpjvFg"
prices_25k = stripe.Price.list(product=prod_25k_id).data
price_35 = next((p for p in prices_25k if p.unit_amount == 3500 and p.currency == "usd"), None)
if not price_35:
    price_35 = stripe.Price.create(
        product=prod_25k_id,
        unit_amount=3500,
        currency="usd",
        metadata={"credits": "25000", "code": "credits_25000"}
    )
    print(f"Created $35 USD price for 25k credits: {price_35.id}")
else:
    print(f"Existing $35 USD price for 25k credits: {price_35.id}")

# Check if product for 65k credits exists
products = stripe.Product.list(limit=50).data
prod_65k = next((p for p in products if "65,000" in p.name or "65000" in p.name), None)
if not prod_65k:
    prod_65k = stripe.Product.create(
        name="Avenqo – 65,000 AI Credits",
        description="Pack de 65 000 crédits IA Avenqo sans expiration.",
        metadata={"credits": "65000", "code": "credits_65000"}
    )
    print(f"Created product for 65k credits: {prod_65k.id}")
else:
    print(f"Existing product for 65k credits: {prod_65k.id}")

prices_65k = stripe.Price.list(product=prod_65k.id).data
price_80 = next((p for p in prices_65k if p.unit_amount == 8000 and p.currency == "usd"), None)
if not price_80:
    price_80 = stripe.Price.create(
        product=prod_65k.id,
        unit_amount=8000,
        currency="usd",
        metadata={"credits": "65000", "code": "credits_65000"}
    )
    print(f"Created $80 USD price for 65k credits: {price_80.id}")
else:
    print(f"Existing $80 USD price for 65k credits: {price_80.id}")

print("\nSummary of Prices:")
print(f"Base ($29.99 CAD): price_1UHtTqGuYLaLvT3YZ6mlhdfr")
print(f"Professional ($49.99 CAD): price_1UHtUmGuYLaLvT3YVLCMOEJD")
print(f"Credits 6,500 ($10 USD): price_1UBFdiGuYLaLvT3YiqDDgvui")
print(f"Credits 25,000 ($35 USD): {price_35.id}")
print(f"Credits 65,000 ($80 USD): {price_80.id}")
