"""OCR et assistance documentaire juridique — extraction réelle, pas de maquette."""

from __future__ import annotations

import json
import re
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.config.settings import get_settings
from backend.app.models import TenantDocument, User
from backend.app.services.document_extraction import (
    UnsupportedDocumentError,
    classify_document,
    extract_text,
    sha256_bytes,
)

LEGAL_DISCLAIMER = (
    "Avenqo Legal AI assiste la lecture de documents. Ce n'est pas un avis juridique, "
    "ni un substitut à un avocat. Faites vérifier tout point important par un professionnel."
)


class DocumentAIService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def ingest(
        self,
        actor: User,
        *,
        kind: str,
        filename: str,
        content: bytes,
        content_type: str,
    ) -> TenantDocument:
        if kind not in {"ocr", "legal"}:
            raise ValueError("Type de document invalide")
        text = extract_text(filename, content)
        digest = sha256_bytes(content)
        settings = get_settings()
        relative = Path("tenant_documents") / str(actor.company_id) / kind / f"{digest}{Path(filename).suffix.lower()}"
        destination = Path(settings.artifact_root) / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        analysis = self._analyze(kind, text, filename)
        row = TenantDocument(
            company_id=actor.company_id,
            uploaded_by_user_id=actor.id,
            kind=kind,
            filename=filename,
            content_type=content_type or "application/octet-stream",
            byte_size=len(content),
            sha256=digest,
            extracted_text=text,
            classification=classify_document(text, filename),
            analysis_json=json.dumps(analysis, ensure_ascii=False),
            analysis_disclaimer=LEGAL_DISCLAIMER if kind == "legal" else None,
            storage_path=str(relative).replace("\\", "/"),
        )
        self._session.add(row)
        self._session.commit()
        return row

    def list_documents(self, actor: User, kind: str) -> list[TenantDocument]:
        return list(
            self._session.scalars(
                select(TenantDocument)
                .where(TenantDocument.company_id == actor.company_id, TenantDocument.kind == kind)
                .order_by(TenantDocument.created_at.desc())
            )
        )

    def get_document(self, actor: User, document_id: UUID) -> TenantDocument:
        row = self._session.scalar(
            select(TenantDocument).where(
                TenantDocument.id == document_id,
                TenantDocument.company_id == actor.company_id,
            )
        )
        if row is None:
            raise LookupError("Document introuvable")
        return row

    def compare(self, actor: User, left_id: UUID, right_id: UUID) -> dict:
        left = self.get_document(actor, left_id)
        right = self.get_document(actor, right_id)
        left_lines = set(self._significant_lines(left.extracted_text))
        right_lines = set(self._significant_lines(right.extracted_text))
        return {
            "left_id": str(left.id),
            "right_id": str(right.id),
            "only_in_left": sorted(left_lines - right_lines)[:40],
            "only_in_right": sorted(right_lines - left_lines)[:40],
            "shared_line_count": len(left_lines & right_lines),
            "disclaimer": LEGAL_DISCLAIMER,
        }

    def _analyze(self, kind: str, text: str, filename: str) -> dict:
        clauses = self._extract_clauses(text)
        if kind == "legal":
            flags = []
            lowered = text.lower()
            for label, needle in (
                ("limitation_of_liability", "limitation of liability"),
                ("termination", "termination"),
                ("confidentiality", "confidential"),
                ("non_compete", "non-compete"),
                ("governing_law", "governing law"),
                ("resiliation", "résiliation"),
                ("confidentialite", "confidentialité"),
            ):
                if needle in lowered:
                    flags.append(label)
            return {
                "filename": filename,
                "summary": self._summarize(text),
                "clauses": clauses[:20],
                "review_flags": flags,
                "word_count": len(text.split()),
            }
        return {
            "filename": filename,
            "summary": self._summarize(text),
            "fields": self._extract_fields(text),
            "word_count": len(text.split()),
        }

    @staticmethod
    def _summarize(text: str) -> str:
        compact = " ".join(text.split())
        if not compact:
            return "Aucun texte extractible dans ce fichier."
        return compact[:400]

    @staticmethod
    def _extract_clauses(text: str) -> list[dict]:
        matches = re.findall(
            r"(?:^|\n)\s*((?:article|clause|section)\s+[\w.\-]+)\s*[:.\-]\s*(.+)",
            text,
            flags=re.IGNORECASE,
        )
        return [{"heading": heading.strip(), "excerpt": excerpt.strip()[:280]} for heading, excerpt in matches]

    @staticmethod
    def _extract_fields(text: str) -> dict[str, str]:
        fields: dict[str, str] = {}
        for label, pattern in (
            ("invoice_number", r"(?:invoice|facture)\s*#?\s*([A-Z0-9\-]{4,})"),
            ("total", r"(?:total|montant)\s*[:\s]*([$€£]?\s?\d[\d\s.,]+)"),
            ("date", r"(?:date)\s*[:\s]*(\d{1,4}[/-]\d{1,2}[/-]\d{1,4})"),
        ):
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                fields[label] = match.group(1).strip()
        return fields

    @staticmethod
    def _significant_lines(text: str) -> list[str]:
        return [line.strip() for line in text.splitlines() if len(line.strip()) >= 12]


__all__ = ["DocumentAIService", "LEGAL_DISCLAIMER", "UnsupportedDocumentError"]
