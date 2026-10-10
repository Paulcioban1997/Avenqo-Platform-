"""Commercial release checks for voluntary CAD packs, without repricing history."""
from decimal import Decimal
from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from backend.app.models import AICreditPackOffer, TenantAIProviderAttempt
from backend.app.config.settings import Settings

def profitability_report(db: Session, offer: AICreditPackOffer, settings: Settings) -> dict:
    # Stress conversion, rather than pretending an unverified spot FX quote is live.
    fx = Decimal("1.50")
    provider_cap = Decimal(offer.credits) * settings.avenqo_provider_cost_per_credit_usd / settings.ai_credit_margin_protection_factor
    revenue = Decimal(offer.price_cents) / 100
    # Conservative card-processing budget; actual fees and fixed overhead still require reconciliation.
    processing_budget = revenue * Decimal("0.04") + Decimal("0.35")
    rows = db.execute(select(TenantAIProviderAttempt.provider, TenantAIProviderAttempt.operation,
        func.count(), func.sum(TenantAIProviderAttempt.provider_cost_usd)).where(
            TenantAIProviderAttempt.success.is_(True), TenantAIProviderAttempt.provider_cost_usd > 0,
        ).group_by(TenantAIProviderAttempt.provider, TenantAIProviderAttempt.operation)).all()
    seen = {"gemini" if row[0] == "vertex" else row[0] for row in rows}
    voice_seen = any(str(row[1]).startswith("voice_") for row in rows)
    missing = sorted({"openai", "gemini", "anthropic"} - seen)
    if not voice_seen:
        missing.append("voice")
    contribution = revenue - provider_cap * fx - processing_budget
    return {"checked_at": datetime.now(timezone.utc).isoformat(), "currency": "CAD",
        "provider_cost_cap_usd": str(provider_cap), "stress_usd_cad": str(fx),
        "processing_budget_cad": str(processing_budget), "contribution_before_overhead_cad": str(contribution),
        "missing_successful_provider_samples": missing,
        "sources": ["https://developers.openai.com/api/docs/pricing", "https://ai.google.dev/gemini-api/docs/pricing", "https://platform.claude.com/docs/en/about-claude/pricing"],
        "status": "ready_for_review" if not missing and contribution > 0 else "pending",
        "limitations": "Excludes hosting, PSTN, taxes, refunds and included Central usage; actual provider invoices must be reconciled before commercial activation."}

def pack_payload(db: Session, offer: AICreditPackOffer, settings: Settings) -> dict:
    return {"code": offer.code, "name": offer.name, "credits": offer.credits,
        "price_cents": offer.price_cents, "currency": "CAD", "enabled": offer.enabled,
        "profitability": profitability_report(db, offer, settings), "review": offer.profitability_review}
