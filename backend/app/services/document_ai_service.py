"""OCR et assistance documentaire juridique — extraction réelle sans perte et vérification `Decimal`."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
import re
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.config.settings import get_settings
from backend.app.models import AccountingInvoice, TenantDocument, User
from .document_extraction import (
    DocumentExtractionBundle,
    UnsupportedDocumentError,
    bundle_from_extracted_text,
    classify_document,
    extract_document_bundle,
    extract_text,
    sha256_bytes,
)
from .invoice_extraction_service import (
    InvoiceExtractionReport,
    InvoiceExtractionService,
    parse_decimal_amount,
)

LEGAL_DISCLAIMER = (
    "Avenqo Legal AI assiste la lecture de documents. Ce n'est pas un avis juridique, "
    "ni un substitut à un avocat. Faites vérifier tout point important par un professionnel."
)


def _strip_markdown_star_artifacts(text: str) -> str:
    """Supprime les artefacts bruts `***` dans les résumés d'outils et aperçus."""
    if not text:
        return ""
    cleaned = re.sub(r"\*{3,}", "", text)
    return " ".join(cleaned.split()).strip()


class DocumentAIService:
    def __init__(self, session: Session, *, image_ocr=None, llm=None) -> None:
        self._session = session
        self._image_ocr = image_ocr
        self._llm = llm
        self._invoice_extractor = InvoiceExtractionService()

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
        bundle = extract_document_bundle(filename, content, image_ocr=self._image_ocr)
        text = bundle.full_text
        digest = bundle.sha256 or sha256_bytes(content)
        settings = get_settings()
        relative = Path("tenant_documents") / str(actor.company_id) / kind / f"{digest}{Path(filename).suffix.lower()}"
        destination = Path(settings.artifact_root) / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        classification = classify_document(text, filename)
        analysis = self._analyze(kind, text, filename, bundle=bundle, classification=classification)
        row = TenantDocument(
            company_id=actor.company_id,
            uploaded_by_user_id=actor.id,
            kind=kind,
            filename=filename,
            content_type=content_type or "application/octet-stream",
            byte_size=len(content),
            sha256=digest,
            extracted_text=text,
            classification=classification,
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

    def load_source_bundle(self, document: TenantDocument) -> DocumentExtractionBundle:
        """Recharge le fichier source intégral depuis le stockage tenant s'il est présent,
        sinon reconstruit le bundle depuis `extracted_text` en préservant honnêtement l'état de complétude."""
        if document.storage_path:
            settings = get_settings()
            candidates = [
                Path(settings.artifact_root) / document.storage_path,
                Path(document.storage_path),
            ]
            for disk_path in candidates:
                try:
                    if disk_path.is_file():
                        raw_bytes = disk_path.read_bytes()
                        if raw_bytes:
                            return extract_document_bundle(
                                document.filename,
                                raw_bytes,
                                image_ocr=self._image_ocr,
                            )
                except Exception:
                    continue
        is_confirmed_complete: bool | None = None
        if document.analysis_json:
            try:
                parsed_analysis = json.loads(document.analysis_json)
                ext_meta = parsed_analysis.get("extraction_metadata") if isinstance(parsed_analysis, dict) else None
                if isinstance(ext_meta, dict):
                    mode = str(ext_meta.get("extraction_mode") or "")
                    incomplete_flag = bool(ext_meta.get("is_incomplete_source", False))
                    if incomplete_flag or mode in {"pdf_scanned_unreadable", "pdf_mixed_partial_ocr", "legacy_partial_text"}:
                        is_confirmed_complete = False
                    elif mode in {"openpyxl_dual_pass", "rehydrated_multisheet_text", "docx_paragraphs_and_tables", "pdf_digital", "pdf_ocr_fallback", "pdf_mixed_digital_and_ocr", "tabular_text", "digital_text", "image_ocr"}:
                        is_confirmed_complete = True
            except Exception:
                is_confirmed_complete = None
        return bundle_from_extracted_text(
            document.filename,
            document.extracted_text or "",
            is_confirmed_complete=is_confirmed_complete,
        )

    def reprocess_existing_document(
        self,
        actor: User,
        document_id: UUID,
        *,
        raw_content_override: bytes | None = None,
    ) -> dict[str, Any]:
        """Retraite un document existant du tenant sans créer de doublon ni exiger un nouveau téléversement
        lorsque le binaire source (`storage_path`) ou le texte extrait est disponible."""
        doc = self.get_document(actor, document_id)
        raw_bytes = raw_content_override
        if raw_bytes is None and doc.storage_path:
            settings = get_settings()
            for candidate in (Path(settings.artifact_root) / doc.storage_path, Path(doc.storage_path)):
                try:
                    if candidate.is_file():
                        loaded = candidate.read_bytes()
                        if loaded:
                            raw_bytes = loaded
                            break
                except Exception:
                    continue

        if raw_bytes is not None:
            bundle = extract_document_bundle(doc.filename, raw_bytes, image_ocr=self._image_ocr)
            doc.extracted_text = bundle.full_text
            doc.sha256 = bundle.sha256 or sha256_bytes(raw_bytes)
            doc.byte_size = len(raw_bytes)
            reprocess_source = "binary_storage"
        else:
            bundle = self.load_source_bundle(doc)
            reprocess_source = "stored_extracted_text"

        doc.classification = classify_document(bundle.full_text or doc.extracted_text or "", doc.filename)
        prior_analysis: dict[str, Any] = {}
        if doc.analysis_json:
            try:
                prior_analysis = json.loads(doc.analysis_json)
            except Exception:
                prior_analysis = {}
        prev_version = int(prior_analysis.get("extraction_version", 1) or 1)
        new_analysis = self._analyze(
            doc.kind,
            bundle.full_text or doc.extracted_text or "",
            doc.filename,
            bundle=bundle,
            classification=doc.classification,
        )
        new_analysis["extraction_version"] = prev_version + 1
        new_analysis["reprocessed_at"] = datetime.now(timezone.utc).isoformat()
        new_analysis["reprocess_source"] = reprocess_source
        doc.analysis_json = json.dumps(new_analysis, ensure_ascii=False)
        self._session.add(doc)
        self._session.commit()
        return {
            "document_id": str(doc.id),
            "filename": doc.filename,
            "classification": doc.classification,
            "extraction_version": new_analysis["extraction_version"],
            "reprocess_source": reprocess_source,
            "extraction_mode": bundle.extraction_mode,
            "is_incomplete_source": bundle.is_incomplete_source,
            "invoice_extraction": new_analysis.get("invoice_extraction"),
        }

    def reprocess_tenant_documents(
        self,
        actor: User,
        *,
        kind: str | None = None,
        document_ids: list[UUID] | None = None,
    ) -> list[dict[str, Any]]:
        """Retraite en lot les anciens documents du tenant avec traçabilité de version et sans doublons."""
        stmt = select(TenantDocument).where(TenantDocument.company_id == actor.company_id)
        if kind:
            stmt = stmt.where(TenantDocument.kind == kind)
        if document_ids:
            stmt = stmt.where(TenantDocument.id.in_(document_ids))
        docs = list(self._session.scalars(stmt.order_by(TenantDocument.created_at.asc())))
        results: list[dict[str, Any]] = []
        for doc in docs:
            results.append(self.reprocess_existing_document(actor, doc.id))
        return results

    def extract_structured_invoice(
        self,
        document: TenantDocument,
        *,
        sheet_filter: str | None = None,
        invoice_filter: str | None = None,
    ) -> InvoiceExtractionReport:
        bundle = self.load_source_bundle(document)
        return self._invoice_extractor.extract_from_bundle(
            bundle,
            sheet_filter=sheet_filter,
            invoice_filter=invoice_filter,
        )

    def delete_document(self, actor: User, document_id: UUID) -> None:
        row = self.get_document(actor, document_id)
        if row.storage_path:
            try:
                settings = get_settings()
                disk_path = Path(settings.artifact_root) / row.storage_path
                if disk_path.exists():
                    disk_path.unlink()
            except Exception:
                pass
        self._session.delete(row)
        self._session.commit()

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

        report = self.extract_structured_invoice(document)
        if report.verification_status == "uncached_formula":
            raise ValueError(
                "Formule Excel sans valeur mise en cache détectée : impossible de confirmer le montant sans recalcul. Aucune écriture n'a été inventée."
            )
        if report.verification_status == "ambiguous_candidates":
            raise ValueError(
                "Plusieurs montants totaux candidats ambigus ont été détectés : confirmation humaine requise avant création d'écriture."
            )

        primary = report.primary_invoice
        amount_dec: Decimal | None = None
        currency = "CAD"
        vendor_name = "Fournisseur à confirmer"
        invoice_num_candidate: str | None = None

        if primary is not None and primary.total_amount is not None:
            amount_dec = primary.total_amount.amount
            if primary.currency and primary.currency != "MIXED_CURRENCY_CONFLICT":
                currency = primary.currency
            if primary.vendor:
                vendor_name = primary.vendor[:180]
            invoice_num_candidate = primary.invoice_number
        else:
            # Repli de compatibilité sur `analysis_json.fields` uniquement si aucune formule non cachée ni ambiguïté
            analysis: dict[str, Any] = {}
            try:
                analysis = json.loads(document.analysis_json or "{}")
            except json.JSONDecodeError:
                analysis = {}
            fields = analysis.get("fields") or self._extract_fields(document.extracted_text or "")
            raw_total = str(fields.get("total") or "")
            parsed = parse_decimal_amount(raw_total)
            if parsed is not None and parsed.amount > Decimal("0"):
                amount_dec = parsed.amount
                if parsed.currency:
                    currency = parsed.currency
            invoice_num_candidate = fields.get("invoice_number")

        if amount_dec is None or amount_dec <= Decimal("0"):
            raise ValueError("Aucun montant extractible : aucune écriture n'a été inventée.")

        invoice_number = str(invoice_num_candidate or f"OCR-{document.id}")[:100]
        existing = self._session.scalar(
            select(AccountingInvoice).where(
                AccountingInvoice.company_id == actor.company_id,
                AccountingInvoice.document_id == document.id,
            )
        )
        if existing is not None:
            return existing

        now = datetime.now(timezone.utc)
        cell_note = (
            f" ({primary.total_amount.cell_ref})"
            if primary is not None and primary.total_amount is not None
            else ""
        )
        row = AccountingInvoice(
            company_id=actor.company_id,
            invoice_number=invoice_number,
            invoice_type="payable",
            party_name=vendor_name,
            issue_date=now,
            due_date=now + timedelta(days=30),
            total_amount=float(amount_dec),
            paid_amount=0.0,
            currency=currency,
            status="unpaid",
            is_confirmed=False,
            notes=f"Proposition OCR document={document.id}{cell_note} — validation humaine requise.",
            document_id=document.id,
            source_module="ocr",
            file_sha256=document.sha256,
            verification_status="to_verify",
            accounting_status="proposed",
        )
        self._session.add(row)
        self._session.commit()
        return row

    def _analyze(
        self,
        kind: str,
        text: str,
        filename: str,
        *,
        bundle: DocumentExtractionBundle | None = None,
        classification: str | None = None,
    ) -> dict[str, Any]:
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
                summary = _strip_markdown_star_artifacts(self._llm_summary(text, summary))
            return {
                "filename": filename,
                "summary": summary,
                "summary_is_preview": len(text) > 400,
                "clauses": clauses[:20],
                "review_flags": flags,
                "word_count": len(text.split()),
                "source": "extracted_text",
                "extraction_metadata": bundle.to_metadata_dict() if bundle is not None else None,
            }

        eff_bundle = bundle or bundle_from_extracted_text(filename, text)
        inv_report = self._invoice_extractor.extract_from_bundle(eff_bundle)
        fields = self._build_structured_fields(text, inv_report)
        summary = self._summarize_ocr(text, inv_report)

        return {
            "filename": filename,
            "classification": classification or classify_document(text, filename),
            "summary": summary,
            "summary_is_preview": True,
            "fields": fields,
            "word_count": len(text.split()),
            "extraction_metadata": eff_bundle.to_metadata_dict(),
            "invoice_extraction": inv_report.to_dict(),
        }

    def _build_structured_fields(self, text: str, report: InvoiceExtractionReport) -> dict[str, str]:
        fields: dict[str, str] = {}
        primary = report.primary_invoice
        if primary is not None:
            if primary.invoice_number:
                fields["invoice_number"] = primary.invoice_number
            if primary.po_number:
                fields["po_number"] = primary.po_number
            if primary.issue_date:
                fields["date"] = primary.issue_date
            if primary.due_date:
                fields["due_date"] = primary.due_date
            if primary.vendor:
                fields["vendor"] = primary.vendor
            if primary.customer:
                fields["customer"] = primary.customer
            if primary.currency and primary.currency != "MIXED_CURRENCY_CONFLICT":
                fields["currency"] = primary.currency
            if primary.subtotal is not None:
                fields["subtotal"] = primary.subtotal.normalized_value
            if primary.tax_total > Decimal("0.00"):
                fields["tax_total"] = format(primary.tax_total, "f")
            if primary.total_amount is not None and report.verification_status in {
                "math_verified",
                "extracted_unverified_math",
            }:
                fields["total"] = primary.total_amount.normalized_value
                fields["total_cell_ref"] = primary.total_amount.cell_ref
                if primary.total_amount.sheet_name:
                    fields["total_sheet_name"] = primary.total_amount.sheet_name
            if primary.balance_due is not None:
                fields["balance_due"] = primary.balance_due.normalized_value
            fields["verification_status"] = report.verification_status
            fields["grounding_status"] = report.grounding_status
            return fields

        # Repli regex prudent si aucune structure de facture n'a été trouvée
        fallback = self._extract_fields(text)
        if report.verification_status in {"uncached_formula", "ambiguous_candidates"}:
            fallback.pop("total", None)
        fallback["verification_status"] = report.verification_status
        fallback["grounding_status"] = report.grounding_status
        return fallback

    def _summarize_ocr(self, text: str, report: InvoiceExtractionReport) -> str:
        if report.primary_invoice is not None and report.primary_invoice.direct_statement_fr:
            base = self._summarize(text)
            return _strip_markdown_star_artifacts(f"{report.primary_invoice.direct_statement_fr} | {base}"[:500])
        return self._summarize(text)

    def _llm_summary(self, text: str, fallback: str) -> str:
        if self._llm is None:
            return fallback
        llm = self._llm
        import asyncio

        async def _generate() -> str:
            generation = await llm.generate(
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
        parsed = parse_decimal_amount(raw)
        if parsed is None or parsed.amount <= Decimal("0"):
            return None
        return float(parsed.amount)

    @staticmethod
    def _summarize(text: str) -> str:
        compact = _strip_markdown_star_artifacts(text)
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
        return [
            {
                "heading": _strip_markdown_star_artifacts(heading),
                "excerpt": _strip_markdown_star_artifacts(excerpt)[:280],
            }
            for heading, excerpt in matches
        ]

    @staticmethod
    def _extract_fields(text: str) -> dict[str, str]:
        fields: dict[str, str] = {}
        for label, pattern in (
            ("invoice_number", r"(?:invoice|facture)\s*#?\s*([A-Z0-9\-]{4,})"),
            ("total", r"(?<!sous[- ])(?:total|montant)\s*[:\s]*([$€£]?\s?\d[\d\s.,]+)"),
            ("date", r"(?:date)\s*[:\s]*(\d{1,4}[/-]\d{1,2}[/-]\d{1,4})"),
        ):
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                val = match.group(1).strip()
                if label == "total" and val.startswith("="):
                    continue
                fields[label] = val
        return fields

    @staticmethod
    def _significant_lines(text: str) -> list[str]:
        return [line.strip() for line in text.splitlines() if len(line.strip()) >= 12]


__all__ = ["DocumentAIService", "LEGAL_DISCLAIMER", "UnsupportedDocumentError"]
