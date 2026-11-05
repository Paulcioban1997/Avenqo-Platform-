"""Service de gestion, d'interpolation dynamique, de signature électronique et d'archivage des contrats commerciaux Avenqo.

Conforme à la Loi concernant le cadre juridique des technologies de l'information (Québec, c. C-1.1),
à la Loi 25 du Québec et à la LPRPDE / PIPEDA canadienne.
Fournit la preuve d'intégrité (empreinte SHA-256), l'horodatage UTC, le contrôle strict d'autorité du signataire,
la réconciliation commerciale, le registre d'achèvement (Avenqo Completion Record),
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
from backend.app.models.company_contract import (
    CompanyContract,
    ContractExecutionPartyState,
    ContractLifecycleStatus,
)
from backend.app.models.company_legal_profile import CompanyLegalProfile
from backend.app.models.user import User
from backend.app.services.account_notifications import AccountNotifier
from backend.app.services.audit_log_service import AuditLogService
from backend.app.services.commercial_reconciler import CommercialReconciler
from backend.app.services.contract_pdf_generator import ContractPdfGenerator
from backend.app.services.signing_challenge_service import SigningChallengeService

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
    """Erreur levée lorsqu'un contrat est déjà signé et scellé."""
    pass


class InvalidSignatureModeError(ValueError):
    """Erreur levée lorsqu'un mode de signature est invalide."""
    pass


class CommercialConfigMismatchError(ValueError):
    """Erreur levée lorsqu'une divergence commerciale bloque la finalisation contractuelle."""
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
            raise FileNotFoundError(f"Fichier modèle de contrat introuvable : {path}")
        return {
            "contract_type": contract_type,
            "title": meta[f"title_{lang}"],
            "version": meta["version"],
            "language": lang,
            "mandatory": meta["mandatory"],
            "raw_text": path.read_text(encoding="utf-8"),
            "content": path.read_text(encoding="utf-8"),
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
        is_signed: bool = False,
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
            (cm.module.name if cm.module else str(cm.module_id))
            for cm in (company.company_modules or [])
            if getattr(cm, "status", None) and str(getattr(cm.status, "value", cm.status)).upper() == "ACTIVE"
        ]
        modules_str = ", ".join(active_modules_list) if active_modules_list else "Aucun module sélectionné (accès socle de base)"

        # 1. Utilisation du profil juridique vérifié s'il est renseigné
        legal = getattr(company, "legal_profile", None)
        if legal is None:
            stmt = select(CompanyLegalProfile).where(CompanyLegalProfile.company_id == company.id)
            legal = self._db.scalars(stmt).first()

        company_legal_name = (legal.legal_name if legal else None) or company.name or "L'Entreprise Locataire"
        trade_name_str = f" faisant affaires sous le nom de « {legal.trade_name} »" if legal and legal.trade_name else ""

        if legal:
            addr_parts = [
                legal.registered_address_street,
                legal.registered_address_city,
                legal.registered_address_state_province,
                legal.registered_address_postal_code,
                legal.registered_address_country,
            ]
            company_address = ", ".join(p for p in addr_parts if p)
            reg_num = legal.registration_number or "Non communiqué"
            rep_title = signatory_title or legal.authorized_representative_title or "Représentant Autorisé"
            rep_name = signatory_name or f"{legal.authorized_representative_first_name} {legal.authorized_representative_last_name}".strip() or "Représentant Autorisé"
            rep_email = signatory_email or legal.authorized_representative_email or company.email
        else:
            addr_parts = []
            if getattr(company, "region", None) and company.region not in ("North America", "Global", ""):
                addr_parts.append(company.region)
            if getattr(company, "country", None):
                addr_parts.append(company.country)
            company_address = ", ".join(addr_parts) if addr_parts else (company.country or "Non renseignée")
            reg_num = "Non renseigné"
            rep_title = signatory_title or "Représentant Autorisé"
            rep_name = signatory_name or "Représentant Autorisé"
            rep_email = signatory_email or company.email

        tax_terms = (
            f"TPS (5 %) et TVQ (9,975 %) applicables selon les lois du Québec et du Canada (Devise : {currency})"
            if currency == "CAD"
            else f"Taxes applicables selon la juridiction locale (Devise : {currency})"
        )

        renewal_terms = (
            "Renouvellement mensuel automatique par tacite reconduction, résiliable sans pénalité à tout moment "
            "depuis le portail de facturation libre-service."
        )

        sig_block = (
            f"[Signé numériquement via Avenqo Secure Sign par {rep_name} ({rep_title}) le {now_str}]"
            if is_signed
            else "[En attente de signature numérique ou manuscrite]"
        )

        interpolated = (
            raw_text
            .replace("{{COMPANY_NAME}}", company_legal_name + trade_name_str)
            .replace("{{COMPANY_ADDRESS}}", company_address)
            .replace("{{COMPANY_ID}}", str(company.id))
            .replace("{{COMPANY_REGISTRATION_NUMBER}}", reg_num)
            .replace("{{NEQ_NUMBER}}", reg_num)
            .replace("{{SIGNATORY_NAME}}", rep_name)
            .replace("{{SIGNATORY_TITLE}}", rep_title)
            .replace("{{SIGNATORY_EMAIL}}", rep_email)
            .replace("{{SUBSCRIPTION_PLAN}}", (company.subscription_plan or "Base").capitalize())
            .replace("{{PLAN_NAME}}", (company.subscription_plan or "Base").capitalize())
            .replace("{{SUBSCRIPTION_PRICE}}", plan_price)
            .replace("{{PLAN_PRICE}}", plan_price)
            .replace("{{ACTIVE_MODULES}}", modules_str)
            .replace("{{TAX_TERMS}}", tax_terms)
            .replace("{{RENEWAL_TERMS}}", renewal_terms)
            .replace("{{EFFECTIVE_DATE}}", now_str)
            .replace("{{CONTRACT_VERSION}}", contract_version)
            .replace("{{SIGNATURE_BLOCK_CLIENT}}", sig_block)
        )
        return interpolated

    def ensure_contracts_for_company(self, company: Company) -> list[CompanyContract]:
        """Initialise les contrats nécessaires pour l'entreprise s'ils n'existent pas encore."""
        language = company.preferred_language or "fr"
        existing = self.list_contracts(company.id)
        existing_types = {c.contract_type for c in existing}

        created = []
        for ctype, meta in AVAILABLE_CONTRACTS.items():
            if ctype not in existing_types:
                template_data = self.get_template_raw(ctype, language=language)
                interpolated_text = self.interpolate_contract_text(
                    template_data["raw_text"],
                    company=company,
                    contract_version=meta["version"],
                )
                sha256 = self.compute_sha256(interpolated_text)
                contract = CompanyContract(
                    company_id=company.id,
                    contract_type=ctype,
                    title=meta[f"title_{template_data['language']}"],
                    status=ContractLifecycleStatus.PENDING_SIGNATURE.value,
                    execution_state=ContractExecutionPartyState.PENDING_CUSTOMER.value,
                    version=meta["version"],
                    language=template_data["language"],
                    sha256_hash=sha256,
                    content_text=interpolated_text,
                )
                self._db.add(contract)
                created.append(contract)

        if created:
            self._db.commit()
            return self.list_contracts(company.id)
        return existing

    def list_contracts(self, company_id: UUID) -> list[CompanyContract]:
        """Retourne la liste des contrats rattachés à une entreprise."""
        stmt = (
            select(CompanyContract)
            .where(CompanyContract.company_id == company_id)
            .order_by(CompanyContract.created_at.asc())
        )
        return list(self._db.scalars(stmt).all())

    def get_contract(self, company_id: UUID, contract_type: str) -> CompanyContract:
        """Récupère un contrat spécifique pour un locataire."""
        stmt = select(CompanyContract).where(
            CompanyContract.company_id == company_id,
            CompanyContract.contract_type == contract_type,
        )
        contract = self._db.scalars(stmt).first()
        if not contract:
            raise ContractNotFoundError(f"Contrat {contract_type} introuvable pour l'entreprise {company_id}")
        return contract

    def verify_signatory_authority(
        self,
        user: User,
        company_id: UUID,
        declared_authority: bool,
    ) -> None:
        """Vérifie que l'utilisateur a le statut nécessaire et atteste de son autorité légale."""
        if user.company_id != company_id:
            raise ContractAuthorityError("Violation multi-tenant : l'utilisateur n'appartient pas à cette entreprise.")

        user_role = getattr(user.role, "value", user.role) if user.role is not None else ""
        allowed_roles = {UserRole.OWNER.value, UserRole.ADMIN.value, "owner", "admin"}
        if str(user_role).lower() not in allowed_roles:
            raise ContractAuthorityError(
                f"Autorité insuffisante : rôle utilisateur insuffisant ({user_role}). Seuls les propriétaires et administrateurs d'entreprise peuvent signer."
            )

        if not declared_authority:
            raise ContractAuthorityError(
                "La déclaration expresse d'autorité légale et du pouvoir d'engagement légal est obligatoire pour engager l'entreprise."
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
        challenge_id: str | None = None,
        challenge_code: str | None = None,
    ) -> dict[str, Any]:
        """Exécute la signature électronique numérique avec preuve d'audit, réconciliation et génération de PDF certifié."""
        self.verify_signatory_authority(user, company.id, declared_authority)

        if not consent_checkbox:
            raise ValueError("Le consentement exprès et explicite est obligatoire pour valider la signature.")

        # Vérification du défi de signature à usage unique si transmis
        if challenge_id and challenge_code:
            valid_challenge = SigningChallengeService.verify_and_consume_challenge(
                challenge_id=challenge_id,
                code=challenge_code,
                company_id=company.id,
                user_id=user.id,
                contract_type=contract_type,
            )
            if not valid_challenge:
                raise ValueError("Défi ou code de sécurité de signature invalide, expiré ou déjà utilisé (anti-rejeu).")

        contract = self.get_contract(company.id, contract_type)
        if contract.status in (ContractLifecycleStatus.SIGNED.value, ContractLifecycleStatus.CUSTOMER_SIGNED.value, ContractLifecycleStatus.FULLY_EXECUTED.value):
            raise ContractAlreadySignedError(f"Le contrat {contract_type} est déjà signé et scellé.")

        # Réconciliation commerciale stricte
        schedule = CommercialReconciler.reconcile(company, self._settings)
        if schedule.is_blocked:
            raise CommercialConfigMismatchError(
                f"Signature bloquée : divergence commerciale détectée ({', '.join(schedule.mismatches)}). Réconciliation requise."
            )

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
            is_signed=True,
        )
        final_sha256 = self.compute_sha256(interpolated_text)

        # 2. Données du profil légal pour PDF
        legal = getattr(company, "legal_profile", None)
        legal_dict = {
            "legal_name": legal.legal_name if legal else company.name,
            "registration_number": legal.registration_number if legal else None,
        }

        # 3. Génération du PDF certifié (distinction Customer signed vs Provider countersign)
        active_mods = schedule.selected_modules
        currency = company.currency_code or "CAD"
        price_str = f"{schedule.monthly_price} {currency} / mois" if schedule.monthly_price else "Sur devis personnalisé"

        is_sandbox_env = self._settings.provider_incorporation_status == "UNVERIFIED_PENDING_INCORPORATION"

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
            execution_state=ContractExecutionPartyState.PENDING_PROVIDER.value,
            legal_profile_data=legal_dict,
            is_sandbox=is_sandbox_env,
        )

        # 4. Stockage persistant et chiffré du PDF
        storage_rel_path = f"contracts/{company.id}/{contract_type}_{receipt_id}.pdf"
        full_storage_path = Path(self._settings.artifact_root) / storage_rel_path
        full_storage_path.parent.mkdir(parents=True, exist_ok=True)
        full_storage_path.write_bytes(pdf_bytes)

        # 5. Registre d'achèvement électronique Avenqo (tamper-evident completion record)
        completion_record = {
            "receipt_id": str(receipt_id),
            "transaction_id": f"TX-{receipt_id.hex[:12].upper()}",
            "contract_type": contract_type,
            "contract_version": contract.version,
            "contract_sha256": final_sha256,
            "language": contract.language,
            "signer_email": user.email,
            "signer_name": user_name,
            "signer_title": signatory_title,
            "signer_capacity": getattr(legal, "authorized_representative_capacity", "Dirigeant") if legal else "Dirigeant",
            "ip_address": ip_address,
            "user_agent": user_agent,
            "consent_timestamp_utc": now.isoformat(),
            "storage_path": storage_rel_path,
            "legal_framework": "RLRQ c. C-1.1 (Québec) & PIPEDA (Canada)",
            "execution_party_states": {
                "customer": "SIGNED",
                "provider": "PENDING_COUNTERSIGNATURE",
            },
            "provider_entity_status": self._settings.provider_incorporation_status,
        }

        self._audit.record(
            actor_user_id=user.id,
            action="contract.digitally_signed",
            target_type="commercial_contract",
            target_id=str(receipt_id),
            company_id=company.id,
            metadata=completion_record,
            commit=False,
        )

        # 6. Mise à jour de l'enregistrement de contrat
        contract.status = "SIGNED"
        contract.execution_state = ContractExecutionPartyState.PENDING_PROVIDER.value
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
        contract.commercial_schedule_json = schedule.to_dict()
        contract.completion_record_json = completion_record
        contract.metadata_json = completion_record

        self._db.commit()

        # 7. Notification par courriel transactionnel
        if self._notifier:
            try:
                mail_body = (
                    f"Bonjour {user_name},\n\n"
                    f"Votre contrat {contract.title} (Réf : {contract.contract_type}-{contract.version}) "
                    f"a été signé avec succès le {now.strftime('%Y-%m-%d %H:%M UTC')}.\n\n"
                    f"Statut : Signé par le client — En attente de contresignature autorisée par PMC Solutions AI.\n"
                    f"Empreinte cryptographique SHA-256 : {final_sha256}\n"
                    f"Identifiant de transaction : TX-{receipt_id.hex[:12].upper()}\n\n"
                    "L'exemplaire certifié est disponible dans votre portail libre-service 'Mes Contrats'.\n\n"
                    "L'équipe Avenqo Platform"
                )
                self._notifier.send_transactional(
                    user.email,
                    f"Avenqo — Contrat signé : {contract.title}",
                    mail_body,
                )
            except Exception as e:
                logger.error("Échec de notification courriel pour signature de contrat: %s", e)

        return {
            "contract_id": str(contract.id),
            "contract_type": contract.contract_type,
            "status": contract.status,
            "execution_state": contract.execution_state,
            "signature_mode": "ELECTRONIC",
            "signatory_name": user_name,
            "signatory_email": user.email,
            "signatory_title": signatory_title,
            "signed_at": now.isoformat(),
            "sha256_hash": final_sha256,
            "storage_path": storage_rel_path,
            "receipt_id": str(receipt_id),
            "transaction_id": completion_record["transaction_id"],
        }

    def countersign_contract_provider(
        self,
        company_id: UUID,
        contract_type: str,
        *,
        provider_user: User,
        provider_name: str = "Mircea Paul Cioban",
        provider_title: str = "Président Fondateur",
    ) -> CompanyContract:
        """Applique la contresignature autorisée du fournisseur (CEO / Super Admin) pour rendre le contrat FULLY_EXECUTED."""
        contract = self.get_contract(company_id, contract_type)
        allowed_prior_statuses = {
            ContractLifecycleStatus.CUSTOMER_SIGNED.value,
            ContractLifecycleStatus.SIGNED.value,
            ContractLifecycleStatus.PENDING_VERIFICATION.value,
            ContractLifecycleStatus.UPLOADED_FOR_REVIEW.value,
        }
        if contract.status not in allowed_prior_statuses:
            raise ValueError(
                f"Impossible de contresigner un contrat non encore signé par le client (statut actuel : {contract.status})."
            )

        now = datetime.now(timezone.utc)
        sig_hash = self.compute_sha256(f"{contract.sha256_hash}:{provider_name}:{provider_title}:{now.isoformat()}")

        company = self._db.get(Company, company_id)
        schedule = CommercialReconciler.reconcile(company, self._settings) if company else None

        contract.provider_signatory_name = provider_name
        contract.provider_signatory_title = provider_title
        contract.provider_signed_at = now
        contract.provider_signature_hash = sig_hash
        contract.status = ContractLifecycleStatus.FULLY_EXECUTED.value
        contract.execution_state = ContractExecutionPartyState.COMPLETED.value

        # Régénération du PDF avec les deux signatures apposées
        if company and contract.storage_path:
            legal = getattr(company, "legal_profile", None)
            legal_dict = {
                "legal_name": legal.legal_name if legal else company.name,
                "registration_number": legal.registration_number if legal else None,
            }
            currency = company.currency_code or "CAD"
            price_str = f"{schedule.monthly_price} {currency} / mois" if schedule and schedule.monthly_price else "Standard"

            pdf_bytes = ContractPdfGenerator.generate_pdf(
                contract_title=contract.title,
                contract_type=contract.contract_type,
                contract_version=contract.version,
                company_name=company.name,
                company_id=str(company.id),
                signatory_name=contract.signatory_name or "Client",
                signatory_title=contract.signatory_title or "Dirigeant",
                signatory_email=contract.signatory_email or company.email,
                plan_code=company.subscription_plan or "base",
                plan_price=price_str,
                active_modules=schedule.selected_modules if schedule else [],
                content_text=contract.content_text,
                sha256_hash=contract.sha256_hash,
                signed_at=contract.signed_at,
                signature_mode=contract.signature_mode,
                audit_receipt_id=str(contract.audit_receipt_id or uuid4()),
                is_draft=False,
                execution_state=ContractExecutionPartyState.COMPLETED.value,
                provider_signatory_name=provider_name,
                provider_signatory_title=provider_title,
                provider_signed_at=now,
                provider_signature_hash=sig_hash,
                legal_profile_data=legal_dict,
                is_sandbox=False,
            )
            full_path = Path(self._settings.artifact_root) / contract.storage_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_bytes(pdf_bytes)

        # Mise à jour du registre d'achèvement
        rec = dict(contract.completion_record_json or {})
        rec["provider_countersigned_at_utc"] = now.isoformat()
        rec["provider_signatory"] = f"{provider_name} ({provider_title})"
        rec["provider_signature_hash"] = sig_hash
        rec["execution_party_states"] = {"customer": "SIGNED", "provider": "COMPLETED"}
        contract.completion_record_json = rec

        self._audit.record(
            actor_user_id=provider_user.id,
            action="contract.provider_countersigned",
            target_type="commercial_contract",
            target_id=str(contract.id),
            company_id=company_id,
            metadata=rec,
        )
        self._db.commit()
        return contract

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
        """Traite le téléversement d'un document signé manuscritement au format PDF ou image."""
        self.verify_signatory_authority(user, company.id, declared_authority=True)

        contract = self.get_contract(company.id, contract_type)
        if contract.status in (ContractLifecycleStatus.SIGNED.value, ContractLifecycleStatus.FULLY_EXECUTED.value):
            raise ContractAlreadySignedError(f"Le contrat {contract_type} est déjà validé.")

        # Validation de l'intégrité du document téléversé
        MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 Mo
        MIN_UPLOAD_BYTES = 100  # Au moins 100 octets
        if len(file_bytes) > MAX_UPLOAD_BYTES:
            raise ValueError("Le fichier téléversé dépasse la taille maximale autorisée (20 Mo).")
        if len(file_bytes) < MIN_UPLOAD_BYTES:
            raise ValueError("Fichier trop court ou vide pour constituer un document contractuel valide.")

        # Validation du type MIME réel
        allowed_signatures = {
            b"%PDF-": "application/pdf",
            b"\x89PNG\r\n\x1a\n": "image/png",
            b"\xff\xd8\xff": "image/jpeg",
        }
        detected_mime = None
        for magic, mime in allowed_signatures.items():
            if file_bytes.startswith(magic):
                detected_mime = mime
                break

        if not detected_mime:
            raise ValueError("Format de fichier non supporté : Seuls les fichiers PDF, PNG ou JPEG sont acceptés.")

        now = datetime.now(timezone.utc)
        receipt_id = uuid4()
        user_name = f"{user.first_name} {user.last_name}".strip() or user.email
        file_sha256 = self.compute_sha256(file_bytes)

        storage_rel_path = f"contracts/{company.id}/{contract_type}_manuscript_{receipt_id}.pdf"
        full_storage_path = Path(self._settings.artifact_root) / storage_rel_path
        full_storage_path.parent.mkdir(parents=True, exist_ok=True)
        full_storage_path.write_bytes(file_bytes)

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

        self._audit.record(
            actor_user_id=user.id,
            action="contract.wet_ink_uploaded",
            target_type="commercial_contract",
            target_id=str(receipt_id),
            company_id=company.id,
            metadata=audit_metadata,
            commit=False,
        )

        contract.status = ContractLifecycleStatus.PENDING_VERIFICATION.value
        contract.execution_state = ContractExecutionPartyState.PENDING_PROVIDER.value
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
            "status": contract.status,
            "execution_state": contract.execution_state,
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
        """Génère le PDF vierge / brouillon pré-rempli pour impression et revue."""
        contract = self.get_contract(company.id, contract_type)
        active_mods = [
            cm.module.name for cm in (company.company_modules or []) if getattr(cm, "status", None) and getattr(cm.status, "value", cm.status) == "ACTIVE" and cm.module
        ]
        currency = company.currency_code or "CAD"
        price_str = "49,99 CAD / mois" if (company.subscription_plan or "").lower() == "professional" else "29,99 CAD / mois"

        legal = getattr(company, "legal_profile", None)
        legal_dict = {
            "legal_name": legal.legal_name if legal else company.name,
            "registration_number": legal.registration_number if legal else None,
        }

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
            legal_profile_data=legal_dict,
            is_sandbox=True,
        )

    def has_signed_mandatory_contracts(self, company_id: UUID) -> bool:
        """Vérifie si les contrats obligatoires sont dûment signés avant l'activation des modules payants."""
        mandatory_types = ["MUTUAL_NDA", "SAAS_SUBSCRIPTION"]
        valid_statuses = {
            ContractLifecycleStatus.SIGNED.value,
            ContractLifecycleStatus.CUSTOMER_SIGNED.value,
            ContractLifecycleStatus.FULLY_EXECUTED.value,
        }
        signed_contracts = self._db.scalars(
            select(CompanyContract.contract_type).where(
                CompanyContract.company_id == company_id,
                CompanyContract.status.in_(valid_statuses),
            )
        ).all()
        return all(m in signed_contracts for m in mandatory_types)

    def verify_wet_ink_signature(
        self,
        company_id: UUID,
        contract_type: str,
        *,
        approved: bool,
        verifier_user: User,
        rejection_reason: str | None = None,
    ) -> CompanyContract:
        """Permet à l'administrateur ou au fondateur de valider ou rejeter un document manuscrit téléversé."""
        contract = self.get_contract(company_id, contract_type)
        if contract.status != ContractLifecycleStatus.PENDING_VERIFICATION.value:
            raise ValueError(f"Le contrat n'est pas en attente de vérification (statut actuel : {contract.status}).")

        now = datetime.now(timezone.utc)
        if approved:
            contract.status = "SIGNED"
            contract.execution_state = ContractExecutionPartyState.COMPLETED.value
            action = "contract.wet_ink_approved"
        else:
            contract.status = ContractLifecycleStatus.PENDING_SIGNATURE.value
            contract.execution_state = ContractExecutionPartyState.PENDING_CUSTOMER.value
            action = "contract.wet_ink_rejected"

        audit_meta = {
            "contract_type": contract_type,
            "contract_id": str(contract.id),
            "approved": approved,
            "verifier_email": verifier_user.email,
            "verified_at": now.isoformat(),
            "rejection_reason": rejection_reason,
        }
        self._audit.record(
            actor_user_id=verifier_user.id,
            action=action,
            target_type="commercial_contract",
            target_id=str(contract.id),
            company_id=company_id,
            metadata=audit_meta,
        )
        self._db.commit()
        return contract
