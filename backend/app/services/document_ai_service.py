"""OCR et assistance documentaire juridique — extraction réelle, pas de maquette."""

from __future__ import annotations

import json
import re
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.config.settings import get_settings
from backend.app.models import AccountingInvoice, TenantDocument, User
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
    def __init__(self, session: Session, *, image_ocr=None, llm=None) -> None:
        self._session = session
        self._image_ocr = image_ocr
        self._llm = llm

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
        text = extract_text(filename, content, image_ocr=self._image_ocr)
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
        try:
            from backend.app.services.automation_service import AutomationService

            AutomationService(self._session).dispatch(
                actor.company_id,
                "document_uploaded",
                {"kind": kind, "document_id": str(row.id), "classification": row.classification},
                actor=actor,
            )
        except Exception:
            pass
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

    def propose_accounting_entry(self, actor: User, document_id: UUID) -> AccountingInvoice:
        document = self.get_document(actor, document_id)
        if document.kind != "ocr":
            raise ValueError("Seuls les documents OCR peuvent préparer une écriture")
        import json as _json

        analysis = {}
        try:
            analysis = _json.loads(document.analysis_json or "{}")
        except _json.JSONDecodeError:
            analysis = {}
        fields = analysis.get("fields") or self._extract_fields(document.extracted_text or "")
        raw_total = str(fields.get("total") or "")
        amount = self._parse_amount(raw_total)
        if amount is None:
            raise ValueError("Aucun montant extractible : aucune écriture n'a été inventée.")
        invoice_number = str(fields.get("invoice_number") or f"OCR-{document.id}")[:100]
        existing = self._session.scalar(
            select(AccountingInvoice).where(
                AccountingInvoice.company_id == actor.company_id,
                AccountingInvoice.invoice_number == invoice_number,
                AccountingInvoice.is_confirmed.is_(False),
            )
        )
        if existing is not None:
            return existing
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)
        row = AccountingInvoice(
            company_id=actor.company_id,
            invoice_number=invoice_number,
            invoice_type="payable",
            party_name="Fournisseur à confirmer",
            issue_date=now,
            due_date=now + timedelta(days=30),
            total_amount=amount,
            paid_amount=0.0,
            currency="CAD",
            status="unpaid",
            is_confirmed=False,
            notes=f"Proposition OCR document={document.id} — validation humaine requise.",
        )
        self._session.add(row)
        self._session.commit()
        return row

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
            summary = self._summarize(text)
            if self._llm is not None:
                summary = self._llm_summary(text, summary)
            return {
                "filename": filename,
                "summary": summary,
                "clauses": clauses[:20],
                "review_flags": flags,
                "word_count": len(text.split()),
                "source": "extracted_text",
            }
        return {
            "filename": filename,
            "summary": self._summarize(text),
            "fields": self._extract_fields(text),
            "word_count": len(text.split()),
        }

    def _llm_summary(self, text: str, fallback: str) -> str:
        import asyncio

        async def _generate() -> str:
            generation = await self._llm.generate(
                system_instruction=(
                    f"{LEGAL_DISCLAIMER} Résume uniquement les passages fournis. "
                    "Cite les extraits. N'invente aucune clause absente."
                ),
                prompt=text[:8000],
            )
            return (generation.content or "").strip() or fallback

        try:
            return asyncio.run(_generate())
        except Exception:
            return fallback

    @staticmethod
    def _parse_amount(raw: str) -> float | None:
        digits = re.sub(r"[^\d,.\-]", "", raw)
        if not digits:
            return None
        if digits.count(",") == 1 and digits.count(".") == 0:
            digits = digits.replace(",", ".")
        else:
            digits = digits.replace(",", "")
        try:
            value = float(digits)
        except ValueError:
            return None
        if value <= 0:
            return None
        return value

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
