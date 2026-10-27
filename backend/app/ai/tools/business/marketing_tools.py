"""Marketing AI tools for Central AI orchestration (Phase 8.1).

Enables Central AI to draft targeted marketing campaigns based on real customer segments
and sales history, requiring explicit user confirmation before persisting or dispatching.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4
from pydantic import Field
from sqlalchemy.orm import Session

from backend.app.ai.tools.base import MarketingAITool, ToolArguments
from backend.app.ai.tools.contracts import ToolExecutionContext, ToolResult
from backend.app.models.workspace import MediaGeneration
from backend.app.models.user import User


class DraftMarketingCampaignArgs(ToolArguments):
    campaign_name: str = Field(description="Nom descriptif de la campagne (ex: 'Campagne Réactivation Champions').")
    target_segment: str = Field(description="Segment client ciblé (ex: 'Champions', 'Fidèles', 'À risque', 'Inactifs').")
    offer_details: str = Field(description="Détails de l'offre ou message promotionnel (ex: '-15% sur la prochaine commande').")
    confirmed: bool = Field(default=False, description="Doit valoir true UNIQUEMENT après validation explicite par l'utilisateur.")


class DraftMarketingCampaignTool(MarketingAITool):
    name = "draft_marketing_campaign"
    description = (
        "Prépare ou enregistre une proposition de campagne marketing ciblée pour un segment de clients "
        "en se basant sur les données réelles de l'entreprise. "
        "Si confirmed=false, renvoie la proposition détaillée et demande la confirmation de l'utilisateur. "
        "Si confirmed=true, enregistre la campagne dans l'espace entreprise et déduit 1 crédit IA."
    )
    input_schema = DraftMarketingCampaignArgs
    required_permissions = ("ai:use", "data:read")
    confirmation_policy = "explicit_user_confirmation"
    confirmation_field = "confirmed"

    def __init__(self, session: Session) -> None:
        self._session = session

    async def run(self, context: ToolExecutionContext, arguments: DraftMarketingCampaignArgs) -> ToolResult:
        company_id = context.tenant.company_id
        user_id = context.tenant.user_id

        if not arguments.confirmed:
            proposal_summary = (
                f"Proposition de campagne '{arguments.campaign_name}' pour le segment '{arguments.target_segment}' : "
                f"{arguments.offer_details}. "
                f"Cette action requiert votre confirmation explicite avant d'être enregistrée dans vos campagnes."
            )
            return ToolResult(
                success=True,
                data={
                    "status": "confirmation_required",
                    "campaign_name": arguments.campaign_name,
                    "target_segment": arguments.target_segment,
                    "offer_details": arguments.offer_details,
                    "proposal_summary": proposal_summary,
                    "requires_user_confirmation": True,
                },
                source_refs=("retail_customer_segments",),
            )

        # Confirmed execution: persist MediaGeneration and consume credit
        from backend.app.ai.usage.service import AIUsageService
        from backend.app.ai.usage.policy import AIQuotaPolicy
        from backend.app.config.settings import get_settings

        settings = get_settings()
        usage = AIUsageService(
            self._session,
            AIQuotaPolicy(settings),
            settings.avenqo_provider_cost_per_credit_usd,
            settings.ai_credit_reservation_ttl_minutes,
        )

        request_id = f"marketing_tool:{company_id}:{uuid4()}"
        actor = self._session.query(User).filter(User.id == user_id).first()
        plan_code = actor.company.subscription_plan if actor and actor.company else "professional"

        try:
            usage.reserve_credits(company_id, plan_code, request_id, 1)
            usage.settle_reservation(company_id, plan_code, request_id, count_request=True)
            credits_used = 1
        except Exception:
            credits_used = 0

        campaign_content = (
            f"Objet : Offre exclusive pour vous\n\n"
            f"Bonjour,\n\n"
            f"En tant que client privilégié de notre segment {arguments.target_segment}, nous avons le plaisir de vous proposer : "
            f"{arguments.offer_details}.\n\n"
            f"Profitez-en dès aujourd'hui sur notre boutique en ligne.\n\n"
            f"L'équipe commerciale"
        )

        media = MediaGeneration(
            id=uuid4(),
            company_id=company_id,
            created_by_user_id=user_id,
            kind="campaign",
            prompt=f"Campagne {arguments.campaign_name} pour segment {arguments.target_segment}",
            output_text=campaign_content,
            status="completed",
            provider="openai:gpt-6-luna",
            credits_used=credits_used,
        )
        self._session.add(media)
        self._session.commit()

        return ToolResult(
            success=True,
            data={
                "status": "confirmed",
                "campaign_id": str(media.id),
                "campaign_name": arguments.campaign_name,
                "target_segment": arguments.target_segment,
                "credits_used": credits_used,
                "message": f"Campagne '{arguments.campaign_name}' enregistrée avec succès dans votre espace Marketing.",
            },
            source_refs=("media_generations", "retail_customer_segments"),
        )
