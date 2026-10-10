"""Génération média textuelle à partir de la consigne utilisateur — jamais de KPI fictifs."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import MediaGeneration, User


class MediaGenerationService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def generate(self, actor: User, prompt: str, kind: str = "marketing_text") -> MediaGeneration:
        cleaned = prompt.strip()
        if len(cleaned) < 8:
            raise ValueError("La consigne est trop courte")
        output = (
            "Brouillon généré à partir de votre consigne uniquement. "
            "Aucun indicateur de performance n'a été inventé.\n\n"
            f"{cleaned}"
        )
        row = MediaGeneration(
            company_id=actor.company_id,
            created_by_user_id=actor.id,
            kind=kind if kind in {"marketing_text", "text"} else "text",
            prompt=cleaned,
            output_text=output,
            status="completed",
            provider="prompt_draft",
            credits_used=0,
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
