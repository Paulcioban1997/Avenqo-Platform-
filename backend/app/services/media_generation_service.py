"""Génération marketing via le gateway LLM réel — jamais de KPI fictifs."""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.ai.llm.exceptions import AIProvidersUnavailableError, LLMProviderError
from backend.app.models import MediaGeneration, User


class MediaUnavailableError(RuntimeError):
    pass


class MediaGenerationError(RuntimeError):
    pass


def resolve_media_llm():
    from backend.app.ai.llm.factory import LLMProviderFactory
    from backend.app.config.settings import get_settings

    settings = get_settings()
    if not any(
        (
            settings.openai_api_key,
            settings.anthropic_api_key,
            settings.google_ai_api_key,
            settings.vertex_enabled,
        )
    ):
        return None
    try:
        return LLMProviderFactory.create_gateway(settings)
    except Exception:
        return None


def _run(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise MediaGenerationError("La génération média doit s'exécuter hors d'une boucle asynchrone existante")


class MediaGenerationService:
    def __init__(self, session: Session, llm=None) -> None:
        self._session = session
        self._llm = llm

    def generate(self, actor: User, prompt: str, kind: str = "marketing_text") -> MediaGeneration:
        cleaned = prompt.strip()
        if len(cleaned) < 8:
            raise ValueError("La consigne est trop courte")
        llm = self._llm if self._llm is not None else resolve_media_llm()
        if llm is None:
            raise MediaUnavailableError(
                "Aucun fournisseur IA n'est configuré pour Media AI. "
                "Aucune campagne n'a été inventée."
            )
        request_id = f"media:{actor.company_id}:{uuid.uuid4()}"
        credits_used = 0
        usage = None
        reserved = False
        plan_code = actor.company.subscription_plan if actor.company else None
        try:
            from backend.app.ai.usage.service import UsageTrackingService

            usage = UsageTrackingService(self._session)
            usage.reserve_credits(actor.company_id, plan_code, request_id, 1)
            reserved = True
        except Exception:
            usage = None
        try:
            generation = _run(
                llm.generate(
                    system_instruction=(
                        "Tu rédiges des textes marketing pour l'entreprise cliente. "
                        "N'invente jamais de chiffres, ROI, ventes ou témoignages. "
                        "Si une donnée manque, dis-le clairement."
                    ),
                    prompt=cleaned,
                )
            )
        except (AIProvidersUnavailableError, LLMProviderError, MediaGenerationError) as exc:
            if reserved and usage is not None:
                usage.release_reservation(actor.company_id, request_id, reason="media_generation_failed")
            raise MediaUnavailableError("La génération IA a échoué. Aucun crédit n'a été débité.") from exc
        except Exception:
            if reserved and usage is not None:
                usage.release_reservation(actor.company_id, request_id, reason="media_generation_failed")
            raise
        output = (getattr(generation, "content", None) or "").strip()
        if not output:
            if reserved and usage is not None:
                usage.release_reservation(actor.company_id, request_id, reason="empty_media_output")
            raise MediaUnavailableError("Le fournisseur IA n'a renvoyé aucun texte.")
        if reserved and usage is not None:
            usage.settle_reservation(actor.company_id, plan_code, request_id, count_request=True)
            credits_used = 1
        row = MediaGeneration(
            company_id=actor.company_id,
            created_by_user_id=actor.id,
            kind=kind if kind in {"marketing_text", "campaign", "email", "product_description", "text"} else "text",
            prompt=cleaned,
            output_text=output,
            status="completed",
            provider=getattr(generation, "provider", None) or getattr(llm, "name", "llm"),
            credits_used=credits_used,
        )
        self._session.add(row)
        self._session.commit()
        return row

    def history(self, actor: User) -> list[MediaGeneration]:
        return list(
            self._session.scalars(
                select(MediaGeneration)
                .where(MediaGeneration.company_id == actor.company_id)
                .order_by(MediaGeneration.created_at.desc())
            )
        )
