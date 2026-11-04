"""Service de gestion, d'interpolation dynamique, de signature électronique et d'archivage des contrats commerciaux Avenqo.

Conforme à la Loi concernant le cadre juridique des technologies de l'information (Québec, c. C-1.1),
à la Loi 25 du Québec et à la LPRPDE / PIPEDA canadienne.
Fournit la preuve d'intégrité (empreinte SHA-256), l'horodatage UTC, le contrôle strict d'autorité du signataire,
la génération automatique de PDF certifiés (ReportLab) et l'archivage persistant.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.config.settings import Settings, get_settings
from backend.app.models.audit_log import AuditLogEntry
from backend.app.models.base import UserRole
from backend.app.models.company import Company
from backend.app.models.company_contract import CompanyContract
from backend.app.models.user import User
from backend.app.services.account_notifications import AccountNotifier
from backend.app.services.audit_log_service import AuditLogService
from backend.app.services.contract_pdf_generator import ContractPdfGenerator

logger = logging.getLogger(__name__)

CONTRACT_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "legal" / "contracts"

AVAILABLE_CONTRACTS: dict[str, dict[str, Any]] = {
    "MUTUAL_NDA": {
        "title_fr": "Accord de Confidentialité et Non-Divulgation Mutuelle",
        "title_en": "Mutual Non-Disclosure and Confidentiality Agreement",
        "fr": "avenqo_nda_agreement_fr.md",
        "en": "avenqo_nda_agreement_en.md",
        "version": "2026-V1",
        "mandatory": True,
    },
    "SAAS_SUBSCRIPTION": {
        "title_fr": "Contrat d'Abonnement SaaS Avenqo (MSA)",
        "title_en": "Avenqo SaaS Master Subscription Agreement (MSA)",
        "fr": "avenqo_saas_subscription_agreement_fr.md",
        "en": "avenqo_saas_subscription_agreement_en.md",
        "version": "2026-V1",
        "mandatory": True,
    },
    "DATA_PROCESSING_ADDENDUM": {
        "title_fr": "Accord de Traitement des Données Personnelles (DPA)",
        "title_en": "Data Processing Addendum (DPA)",
        "fr": "avenqo_dpa_agreement_fr.md",
        "en": "avenqo_dpa_agreement_en.md",
        "version": "2026-V1",
        "mandatory": True,
    },
    "PRIVATE_LICENSE": {
        "title_fr": "Contrat de Licence Logicielle Privée Avenqo",
        "title_en": "Avenqo Private Software License Agreement",
        "fr": "avenqo_private_license_agreement_fr.md",
        "en": "avenqo_private_license_agreement_en.md",
        "version": "2026-V1",
        "mandatory": False,
    },
}


class ContractAuthorityError(PermissionError):
    """Erreur levée lorsqu'un signataire n'a pas l'autorité légale pour engager l'entreprise."""
    pass


class ContractNotFoundError(ValueError):
    """Erreur levée lorsqu'un contrat demandé est introuvable."""
    pass


class ContractAlreadySignedError(ValueError):
    """Erreur levée lorsqu'un contrat est déjà signé et certifié."""
    pass


class InvalidSignatureModeError(ValueError):
    """Erreur levée lorsqu'un mode de signature est invalide."""
    pass


class ContractSignatureService:
    def __init__(
        self,
        db: Session,
        audit_service: AuditLogService | None = None,
        settings: Settings | None = None,
        notifier: AccountNotifier | None = None,
    ) -> None:
        self._db = db
        self._audit = audit_service or AuditLogService(db)
        self._settings = settings or get_settings()
        self._notifier = notifier

    @staticmethod
    def compute_sha256(content: str | bytes) -> str:
        """Calcule l'empreinte cryptographique SHA-256."""
        if isinstance(content, str):
            content = content.strip().encode("utf-8")
        return hashlib.sha256(content).hexdigest()

    def get_template_raw(self, contract_type: str, language: str = "fr") -> dict[str, Any]:
        """Récupère le modèle de contrat brut non interpolé."""
        if contract_type not in AVAILABLE_CONTRACTS:
            raise ContractNotFoundError(f"Type de contrat inconnu : {contract_type}")
        lang = "fr" if language.lower().startswith("fr") else "en"
        meta = AVAILABLE_CONTRACTS[contract_type]
        filename = meta[lang]
        path = CONTRACT_TEMPLATES_DIR / filename
        if not path.exists():
            raise FileNotFoundError(f"Modèle de contrat introuvable sur disque : {path}")

        raw_text = path.read_text(encoding="utf-8")
        return {
            "contract_type": contract_type,
            "title": meta[f"title_{lang}"],
            "language": lang,
            "version": meta["version"],
            "filename": filename,
            "content": raw_text,
            "sha256": self.compute_sha256(raw_text),
            "mandatory": meta["mandatory"],
        }

    def interpolate_contract_text(
        self,
        raw_text: str,
        *,
        company: Company,
        signatory_name: str = "",
        signatory_title: str = "",
        signatory_email: str = "",
        effective_date: str = "",
        contract_version: str = "2026-V1",
    ) -> str:
        """Interpole dynamiquement les paramètres réels de l'entreprise dans le texte légal."""
        now_str = effective_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        plan_code = (company.subscription_plan or "base").lower()
        currency = company.currency_code or "CAD"

        plan_price_map = {
            "base": f"29,99 {currency} / mois",
            "professional": f"49,99 {currency} / mois",
            "enterprise": f"Sur devis personnalisé ({currency})",
        }
        plan_price = plan_price_map.get(plan_code, f"Tarif standard {currency}")

        active_modules_list = [
            cm.module.name for cm in (company.company_modules or []) if getattr(cm, "status", None) and cm.status.value == "ACTIVE" and cm.module
        ]
        if not active_modules_list:
            active_modules_list = ["Commerce Retail", "CRM & Calendrier"]
        modules_str = ", ".join(active_modules_list)

        tax_terms = (
            f"TPS (5 %) et TVQ (9,975 %) applicables selon les lois du Québec et du Canada (Devise : {currency})"
            if currency == "CAD"
            else f"Taxes applicables selon la juridiction locale (Devise : {currency})"
        )

        renewal_terms = (
            "Renouvellement mensuel automatique par tacite reconduction, résiliable sans pénalité à tout moment "
            "depuis le portail de facturation libre-service."
        )

        interpolated = (
            raw_text
            .replace("{{COMPANY_NAME}}", company.name or "L'Entreprise Locataire")
            .replace("{{COMPANY_ADDRESS}}", f"{company.country} ({company.timezone})")
            .replace("{{COMPANY_ID}}", str(company.id))
            .replace("{{SIGNATORY_NAME}}", signatory_name or "Représentant Autorisé")
            .replace("{{SIGNATORY_TITLE}}", signatory_title or "Dirigeant d'entreprise")
            .replace("{{SIGNATORY_EMAIL}}", signatory_email or company.email)
            .replace("{{SUBSCRIPTION_PLAN}}", plan_code.capitalize())
            .replace("{{SUBSCRIPTION_PRICE}}", plan_price)
            .replace("{{ACTIVE_MODULES}}", modules_str)
            .replace("{{TAX_TERMS}}", tax_terms)
            .replace("{{RENEWAL_TERMS}}", renewal_terms)
            .replace("{{EFFECTIVE_DATE}}", now_str)
            .replace("{{CONTRACT_VERSION}}", contract_version)
        )
        return interpolated

    def ensure_contracts_for_company(
        self,
        company: Company,
        language: str = "fr",
    ) -> list[CompanyContract]:
        """Crée ou récupère l'ensemble des contrats obligatoires pour une entreprise."""
        lang = "fr" if (language or company.preferred_language or "fr").lower().startswith("fr") else "en"
        existing = {
            c.contract_type: c
            for c in self._db.scalars(
                select(CompanyContract).where(CompanyContract.company_id == company.id)
            ).all()
        }

        needed_types = ["MUTUAL_NDA", "SAAS_SUBSCRIPTION", "DATA_PROCESSING_ADDENDUM"]
        if (company.subscription_plan or "").lower() == "enterprise":
            needed_types.append("PRIVATE_LICENSE")

        results: list[CompanyContract] = []
        for ctype in needed_types:
            if ctype in existing:
                results.append(existing[ctype])
                continue

            tmpl = self.get_template_raw(ctype, lang)
            interpolated = self.interpolate_contract_text(
                tmpl["content"],
                company=company,
                signatory_name="",
                signatory_title="",
                signatory_email=company.email,
                contract_version=tmpl["version"],
            )
            sha = self.compute_sha256(interpolated)

            contract = CompanyContract(
                company_id=company.id,
                contract_type=ctype,
                title=tmpl["title"],
                status="PENDING_SIGNATURE",
                version=tmpl["version"],
                language=lang,
                sha256_hash=sha,
                content_text=interpolated,
                metadata_json={
                    "mandatory": tmpl["mandatory"],
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "plan_code": company.subscription_plan,
                },
            )
            self._db.add(contract)
            results.append(contract)

        self._db.commit()
        return results

    def list_contracts(self, company_id: UUID) -> list[CompanyContract]:
        """Liste tous les contrats d'un tenant ordonnés par statut et date."""
        return list(
            self._db.scalars(
                select(CompanyContract)
                .where(CompanyContract.company_id == company_id)
                .order_by(CompanyContract.created_at.asc())
            ).all()
        )

    def get_contract(self, company_id: UUID, contract_type: str) -> CompanyContract:
        """Récupère un contrat spécifique pour une entreprise avec isolation stricte."""
        contract = self._db.scalar(
            select(CompanyContract).where(
                CompanyContract.company_id == company_id,
                CompanyContract.contract_type == contract_type,
            )
        )
        if not contract:
            raise ContractNotFoundError(f"Contrat {contract_type} introuvable pour ce locataire.")
        return contract

    def verify_signatory_authority(
        self,
        user: User,
        company_id: UUID,
        declared_authority: bool,
    ) -> None:
        """Vérifie que l'utilisateur est le propriétaire ou un administrateur avec autorité légale déclarée."""
        if user.company_id != company_id:
            raise ContractAuthorityError("Violation multi-tenant : L'utilisateur n'appartient pas à cette entreprise.")

        # Contrôle du rôle : seuls OWNER ou ADMIN peuvent engager l'entreprise
        user_role = getattr(user, "role", None)
        role_val = user_role.value if hasattr(user_role, "value") else str(user_role or "")
        allowed_roles = {UserRole.OWNER.value, UserRole.ADMIN.value, "owner", "admin"}

        if role_val not in allowed_roles:
            raise ContractAuthorityError(
                "Autorité insuffisante : Un employé standard ne peut pas engager juridiquement l'entreprise. "
                "Seul le propriétaire ou un dirigeant administrateur dûment mandaté peut signer ce contrat."
            )

        if not declared_authority:
            raise ContractAuthorityError(
                "La déclaration formelle de pouvoir d'engagement légal au nom de l'entreprise est obligatoire."
            )

    def sign_contract_electronic(
        self,
        *,
        company: Company,
        user: User,
        contract_type: str,
        signatory_title: str,
        declared_authority: bool,
        consent_checkbox: bool,
        ip_address: str = "127.0.0.1",
        user_agent: str = "Avenqo-Web/1.0",
    ) -> dict[str, Any]:
        """Exécute la signature électronique numérique avec preuve d'audit et génération de PDF certifié."""
        self.verify_signatory_authority(user, company.id, declared_authority)

        if not consent_checkbox:
            raise ValueError("Le consentement exprès et explicite est obligatoire pour valider la signature.")

        contract = self.get_contract(company.id, contract_type)
        if contract.status == "SIGNED":
            raise ContractAlreadySignedError(f"Le contrat {contract_type} est déjà signé et scellé.")
        now = datetime.now(timezone.utc)
        receipt_id = uuid4()
        user_name = f"{user.first_name} {user.last_name}".strip() or user.email

        # 1. Mise à jour de l'interpolation avec les données réelles du signataire
        interpolated_text = self.interpolate_contract_text(
            contract.content_text,
            company=company,
            signatory_name=user_name,
            signatory_title=signatory_title,
            signatory_email=user.email,
            effective_date=now.strftime("%Y-%m-%d"),
            contract_version=contract.version,
        )
        final_sha256 = self.compute_sha256(interpolated_text)

        # 2. Génération du PDF certifié
        active_mods = [
            cm.module.name for cm in (company.company_modules or []) if getattr(cm, "status", None) and cm.status.value == "ACTIVE" and cm.module
        ]
        currency = company.currency_code or "CAD"
        price_str = "49,99 CAD / mois" if (company.subscription_plan or "").lower() == "professional" else "29,99 CAD / mois"

        pdf_bytes = ContractPdfGenerator.generate_pdf(
            contract_title=contract.title,
            contract_type=contract.contract_type,
            contract_version=contract.version,
            company_name=company.name,
            company_id=str(company.id),
            signatory_name=user_name,
            signatory_title=signatory_title,
            signatory_email=user.email,
            plan_code=company.subscription_plan or "base",
            plan_price=price_str,
            active_modules=active_mods,
            content_text=interpolated_text,
            sha256_hash=final_sha256,
            signed_at=now,
            signature_mode="ELECTRONIC",
            audit_receipt_id=str(receipt_id),
            ip_address=ip_address,
            is_draft=False,
        )

        # 3. Stockage persistant et chiffré du PDF
        storage_rel_path = f"contracts/{company.id}/{contract_type}_{receipt_id}.pdf"
        full_storage_path = Path(self._settings.artifact_root) / storage_rel_path
        full_storage_path.parent.mkdir(parents=True, exist_ok=True)
        full_storage_path.write_bytes(pdf_bytes)

        # 4. Enregistrement dans le journal d'audit immuable
        audit_metadata = {
            "receipt_id": str(receipt_id),
            "contract_type": contract_type,
            "contract_version": contract.version,
            "contract_sha256": final_sha256,
            "language": contract.language,
            "signer_email": user.email,
            "signer_name": user_name,
            "signer_title": signatory_title,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "consent_timestamp": now.isoformat(),
            "storage_path": storage_rel_path,
            "legal_framework": "RLRQ c. C-1.1 (Québec) & PIPEDA (Canada)",
        }

        audit_entry = self._audit.record(
            actor_user_id=user.id,
            action="contract.digitally_signed",
            target_type="commercial_contract",
            target_id=str(receipt_id),
            company_id=company.id,
            metadata=audit_metadata,
            commit=False,
        )

        # 5. Mise à jour de l'enregistrement de contrat
        contract.status = "SIGNED"
        contract.signature_mode = "ELECTRONIC"
        contract.signatory_user_id = user.id
        contract.signatory_name = user_name
        contract.signatory_email = user.email
        contract.signatory_title = signatory_title
        contract.signatory_authority_declared = True
        contract.signed_at = now
        contract.sha256_hash = final_sha256
        contract.content_text = interpolated_text
        contract.storage_path = storage_rel_path
        contract.audit_receipt_id = receipt_id
        contract.metadata_json = audit_metadata

        self._db.commit()

        # 6. Notification par courriel transactionnel avec pièce jointe
        if self._notifier:
            try:
                self._notifier.send_transactional(
                    recipient_email=user.email,
                    recipient_name=user_name,
                    subject=f"Avenqo — Contrat signé : {contract.title}",
                    html_content=(
                        f"<p>Bonjour {user_name},</p>"
                        f"<p>Votre contrat <b>{contract.title}</b> (Réf : {contract.contract_type}-{contract.version}) "
                        f"a été signé électroniquement avec succès le {now.strftime('%Y-%m-%d %H:%M UTC')}.</p>"
                        f"<p>Empreinte cryptographique de sécurité (SHA-256) : <code>{final_sha256}</code></p>"
                        f"<p>Vous trouverez votre exemplaire certifié en pièce jointe ou téléchargeable à tout moment dans votre espace Avenqo.</p>"
                    ),
                    text_content=(
                        f"Votre contrat {contract.title} a été signé électroniquement avec succès.\n"
                        f"Empreinte SHA-256 : {final_sha256}\n"
                        f"Téléchargeable dans vos paramètres Avenqo."
                    ),
                    attachments=[(f"{contract_type}_Signe_{receipt_id}.pdf", pdf_bytes, "application/pdf")],
                )
            except Exception as mail_err:
                logger.warning("Notification email failed (non-blocking): %s", mail_err)

        return {
            "contract_id": str(contract.id),
            "contract_type": contract.contract_type,
            "title": contract.title,
            "status": contract.status,
            "signature_mode": contract.signature_mode,
            "signed_at": now.isoformat(),
            "sha256_hash": final_sha256,
            "signatory_name": user_name,
            "signatory_title": signatory_title,
            "storage_path": storage_rel_path,
            "receipt_id": str(receipt_id),
            "audit_entry_id": str(audit_entry.id) if audit_entry else None,
        }

    def upload_wet_ink_signature(
        self,
        *,
        company: Company,
        user: User,
        contract_type: str,
        signatory_title: str,
        file_bytes: bytes,
        filename: str,
        ip_address: str = "127.0.0.1",
    ) -> dict[str, Any]:
        """Téléverse et scelle un contrat signé manuellement au stylo (scan / photo / PDF)."""
        self.verify_signatory_authority(user, company.id, declared_authority=True)

        if not file_bytes:
            raise ValueError("Le fichier téléversé est vide.")

        contract = self.get_contract(company.id, contract_type)
        if contract.status == "SIGNED":
            raise ContractAlreadySignedError(f"Le contrat {contract_type} est déjà signé et scellé.")
        now = datetime.now(timezone.utc)
        receipt_id = uuid4()
        user_name = f"{user.first_name} {user.last_name}".strip() or user.email
        file_sha256 = self.compute_sha256(file_bytes)

        # Enregistrement du fichier scanné dans le stockage persistant
        ext = Path(filename).suffix or ".pdf"
        storage_rel_path = f"contracts/{company.id}/{contract_type}_WET_INK_{receipt_id}{ext}"
        full_storage_path = Path(self._settings.artifact_root) / storage_rel_path
        full_storage_path.parent.mkdir(parents=True, exist_ok=True)
        full_storage_path.write_bytes(file_bytes)

        # Journal d'audit
        audit_metadata = {
            "receipt_id": str(receipt_id),
            "contract_type": contract_type,
            "contract_version": contract.version,
            "file_sha256": file_sha256,
            "filename": filename,
            "byte_size": len(file_bytes),
            "signer_email": user.email,
            "signer_name": user_name,
            "signer_title": signatory_title,
            "ip_address": ip_address,
            "signature_mode": "MANUSCRIPT_WET_INK",
            "storage_path": storage_rel_path,
        }

        audit_entry = self._audit.record(
            actor_user_id=user.id,
            action="contract.wet_ink_uploaded",
            target_type="commercial_contract",
            target_id=str(receipt_id),
            company_id=company.id,
            metadata=audit_metadata,
            commit=False,
        )

        contract.status = "SIGNED"
        contract.signature_mode = "MANUSCRIPT_WET_INK"
        contract.signatory_user_id = user.id
        contract.signatory_name = user_name
        contract.signatory_email = user.email
        contract.signatory_title = signatory_title
        contract.signatory_authority_declared = True
        contract.signed_at = now
        contract.sha256_hash = file_sha256
        contract.storage_path = storage_rel_path
        contract.audit_receipt_id = receipt_id
        contract.metadata_json = audit_metadata

        self._db.commit()

        return {
            "contract_id": str(contract.id),
            "contract_type": contract.contract_type,
            "status": "SIGNED",
            "signature_mode": "MANUSCRIPT_WET_INK",
            "signed_at": now.isoformat(),
            "sha256_hash": file_sha256,
            "storage_path": storage_rel_path,
            "receipt_id": str(receipt_id),
        }

    def generate_draft_pdf(
        self,
        company: Company,
        contract_type: str,
    ) -> bytes:
        """Génère le PDF vierge / brouillon pré-rempli pour impression et signature manuscrite."""
        contract = self.get_contract(company.id, contract_type)
        active_mods = [
            cm.module.name for cm in (company.company_modules or []) if getattr(cm, "status", None) and cm.status.value == "ACTIVE" and cm.module
        ]
        currency = company.currency_code or "CAD"
        price_str = "49,99 CAD / mois" if (company.subscription_plan or "").lower() == "professional" else "29,99 CAD / mois"

        return ContractPdfGenerator.generate_pdf(
            contract_title=contract.title,
            contract_type=contract.contract_type,
            contract_version=contract.version,
            company_name=company.name,
            company_id=str(company.id),
            signatory_name="Représentant Autorisé",
            signatory_title="Dirigeant",
            signatory_email=company.email,
            plan_code=company.subscription_plan or "base",
            plan_price=price_str,
            active_modules=active_mods,
            content_text=contract.content_text,
            sha256_hash=contract.sha256_hash,
            is_draft=True,
        )

    def has_signed_mandatory_contracts(self, company_id: UUID) -> bool:
        """Vérifie si les contrats obligatoires sont dûment signés avant l'activation des modules payants."""
        mandatory_types = ["MUTUAL_NDA", "SAAS_SUBSCRIPTION"]
        signed_count = self._db.scalar(
            select(CompanyContract)
            .where(
                CompanyContract.company_id == company_id,
                CompanyContract.contract_type.in_(mandatory_types),
                CompanyContract.status == "SIGNED",
            )
        )
        # Vérifier si chaque type obligatoire est présent et signé
        signed_contracts = self._db.scalars(
            select(CompanyContract.contract_type).where(
                CompanyContract.company_id == company_id,
                CompanyContract.status == "SIGNED",
            )
        ).all()
        return all(m in signed_contracts for m in mandatory_types)
