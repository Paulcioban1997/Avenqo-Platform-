from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

import jwt


def valid_cost(value):
    try:
        cost = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("Provider pricing is unavailable") from None
    if not cost.is_finite() or cost < 0:
        raise ValueError("Provider pricing is unavailable")
    return format(cost.normalize(), "f")


def signed_number_quote(settings, tenant_id, user_id, offer):
    costs = offer.get("cost_information") or {}
    currency = str(costs.get("currency") or "")
    if len(currency) != 3 or not currency.isalpha() or not offer.get("is_orderable"):
        raise ValueError("Provider number or currency is unavailable")
    now = datetime.now(timezone.utc)
    data = {"type": "voice_number_quote", "tenant_id": str(tenant_id), "user_id": str(user_id),
        "phone_number": offer["phone_number"], "country_code": offer["country_code"], "number_type": offer["number_type"],
        "monthly_cost": valid_cost(costs.get("monthly_cost")), "upfront_cost": valid_cost(costs.get("upfront_cost")),
        "currency": currency.upper(), "regulatory_status": offer["regulatory_status"],
        "requirements": offer["regulatory_requirements"], "iat": now, "exp": now + timedelta(minutes=5),
        "iss": settings.auth_jwt_issuer, "aud": settings.auth_jwt_audience}
    return jwt.encode(data, settings.auth_jwt_secret, algorithm=settings.auth_jwt_algorithm)


def verify_number_quote(settings, token, tenant_id, user_id, phone_number):
    try:
        data = jwt.decode(token or "", settings.auth_jwt_secret, algorithms=[settings.auth_jwt_algorithm],
            issuer=settings.auth_jwt_issuer, audience=settings.auth_jwt_audience,
            options={"require": ["exp", "iat", "type", "tenant_id", "user_id", "phone_number"]})
    except jwt.InvalidTokenError:
        raise ValueError("A current confirmed number quote is required") from None
    if data["type"] != "voice_number_quote" or data["tenant_id"] != str(tenant_id) or data["user_id"] != str(user_id) or data["phone_number"] != phone_number:
        raise PermissionError("Number quote does not belong to this tenant actor")
    return data