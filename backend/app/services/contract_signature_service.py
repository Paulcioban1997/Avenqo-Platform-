"""Service de signature électronique et d'archivage des contrats commerciaux Avenqo.

Conforme à la Loi concernant le cadre juridique des technologies de l'information (Québec, c. C-1.1).
Fournit la preuve d'intégrité (empreinte SHA-256), l'horodatage UTC, l'enregistrement de l'audit
et l'archivage figé accessible aux deux parties.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from backend.app.services.audit_log_service import AuditLogService

CONTRACT_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "legal" / "contracts"
CONTRACT_ARCHIVES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "legal" / "archives"

AVAILABLE_CONTRACTS = {
    "SAAS_SUBSCRIPTION": {
        "fr": "avenqo_saas_subscription_agreement_fr.md",
        "en": "avenqo_saas_subscription_agreement_en.md",
        "version": "2026-V1",
    },
    "PRIVATE_LICENSE": {
        "fr": "avenqo_private_license_agreement_fr.md",
        "en": "avenqo_private_license_agreement_en.md",
        "version": "2026-V1",
    },
}


class ContractSignatureService:
    def __init__(self, db: Session, audit_service: AuditLogService | None = None) -> None:
        self._db = db
        self._audit = audit_service or AuditLogService(db)

    @staticmethod
    def compute_sha256(content: str) -> str:
        """Calcule l'empreinte cryptographique SHA-256 d'un texte contractuel."""
        return hashlib.sha256(content.strip().encode("utf-8")).hexdigest()

    def get_template(self, contract_type: str, language: str = "fr") -> dict[str, Any]:
        """Récupère le texte du contrat et son empreinte cryptographique d'intégrité."""
        if contract_type not in AVAILABLE_CONTRACTS:
            raise ValueError(f"Type de contrat inconnu : {contract_type}")
        lang = "fr" if language.lower().startswith("fr") else "en"
        meta = AVAILABLE_CONTRACTS[contract_type]
        filename = meta[lang]
        path = CONTRACT_TEMPLATES_DIR / filename
        if not path.exists():
            raise FileNotFoundError(f"Modèle de contrat introuvable : {path}")

        raw_text = path.read_text(encoding="utf-8")
        sha256 = self.compute_sha256(raw_text)
        return {
            "contract_type": contract_type,
            "language": lang,
            "version": meta["version"],
            "filename": filename,
            "content": raw_text,
            "sha256": sha256,
            "legal_notice": "BROUILLON SOUMIS À VALIDATION JURIDIQUE PAR UN AVOCAT QUÉBÉCOIS",
        }

    def sign_contract(
        self,
        *,
        company_id: UUID,
        user_id: UUID,
        user_email: str,
        user_name: str,
        contract_type: str,
        language: str = "fr",
        ip_address: str = "127.0.0.1",
        user_agent: str = "Avenqo-Web/1.0",
        consent_checkbox: bool = False,
    ) -> dict[str, Any]:
        """Exécute la signature électronique numérique avec preuve d'audit immuable."""
        if not consent_checkbox:
            raise ValueError("Le consentement exprès et explicite est obligatoire pour valider la signature.")

        template = self.get_template(contract_type, language)
        now = datetime.now(timezone.utc)
        receipt_id = uuid4()

        # Enregistrement dans le journal d'audit immuable
        audit_metadata = {
            "receipt_id": str(receipt_id),
            "contract_type": contract_type,
            "contract_version": template["version"],
            "contract_sha256": template["sha256"],
            "language": template["language"],
            "signer_email": user_email,
            "signer_name": user_name,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "consent_timestamp": now.isoformat(),
            "legal_framework": "RLRQ c. C-1.1 (Québec)",
        }

        entry = self._audit.record(
            actor_user_id=user_id,
            action="contract.digitally_signed",
            target_type="commercial_contract",
            target_id=str(receipt_id),
            company_id=company_id,
            metadata=audit_metadata,
            commit=True,
        )

        receipt = {
            "receipt_id": str(receipt_id),
            "audit_entry_id": str(entry.id),
            "company_id": str(company_id),
            "user_id": str(user_id),
            "signer_name": user_name,
            "signer_email": user_email,
            "signed_at": now.isoformat(),
            "contract_type": contract_type,
            "version": template["version"],
            "language": template["language"],
            "contract_sha256": template["sha256"],
            "ip_address": ip_address,
            "user_agent": user_agent,
            "status": "SIGNED_LEGALLY_BINDING_DRAFT",
            "provider": "PMC Solutions AI Inc.",
        }

        # Archivage permanent accessible aux deux parties
        tenant_archive_dir = CONTRACT_ARCHIVES_DIR / str(company_id)
        tenant_archive_dir.mkdir(parents=True, exist_ok=True)
        archive_file = tenant_archive_dir / f"{contract_type}_{receipt_id}.json"
        archive_payload = {
            "receipt": receipt,
            "contract_content": template["content"],
        }
        archive_file.write_text(json.dumps(archive_payload, indent=2, ensure_ascii=False), encoding="utf-8")

        return receipt
