"""Repair a stale local denial only from a verified, already linked subscription."""
from datetime import datetime, timezone


def reconcile_subscription(account, provider, settings) -> bool:
    if not account.stripe_customer_id or not account.stripe_subscription_id:
        return False
    subscription = provider.retrieve_subscription(account.stripe_subscription_id)
    if (
        subscription.get("id") != account.stripe_subscription_id
        or subscription.get("customer") != account.stripe_customer_id
        or (subscription.get("metadata") or {}).get("avenqo_company_id") != str(account.company_id)
    ):
        return False
    items = (subscription.get("items") or {}).get("data") or []
    if len(items) != 1:
        return False
    price_id = (items[0].get("price") or {}).get("id")
    plan = settings.stripe_plan_code(price_id) if price_id else None
    if plan not in {"demo", "professional"}:
        return False
    status = subscription.get("status")
    if status not in {"active", "trialing"}:
        return False
    end = subscription.get("current_period_end") or items[0].get("current_period_end")
    period_end = datetime.fromtimestamp(int(end), timezone.utc) if end else None
    if period_end is None or period_end <= datetime.now(timezone.utc):
        return False
    account.plan_code = plan
    account.company.subscription_plan = plan
    account.status = status
    account.current_period_end = period_end
    account.cancel_at_period_end = bool(subscription.get("cancel_at_period_end", False))
    return True
