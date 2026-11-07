"""Service de gestion et de validation du profil juridique de l'entreprise cliente."""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.company import Company
from backend.app.models.company_legal_profile import CompanyLegalProfile


class LegalProfileValidationError(ValueError):
    """Erreur levée lors de la validation des données d'identité corporative."""

    def __init__(self, message: str, errors: list[dict[str, str]] | None = None) -> None:
        super().__init__(message)
        self.errors = errors or []


EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_REGEX = re.compile(r"^\+?[\d\s\-().]{7,25}$")
NEQ_REGEX = re.compile(r"^\d{10}$")

VALID_CAPACITIES = {
    "Owner",
    "President",
    "CEO",
    "Authorized Director",
    "Authorized Officer",
    "Authorized Representative",
    "Propriétaire",
    "Président",
    "Directeur Général",
    "Administrateur autorisé",
    "Mandataire autorisé",
}


class CompanyLegalProfileService:
    """Valide et persiste le profil juridique d'un locataire (tenant)."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_profile(self, company_id: UUID) -> CompanyLegalProfile | None:
        stmt = select(CompanyLegalProfile).where(CompanyLegalProfile.company_id == company_id)
        return self.db.scalars(stmt).first()

    def validate_profile_payload(self, data: dict[str, Any]) -> list[dict[str, str]]:
        errors: list[dict[str, str]] = []

        # 1. Validation de l'entité légale
        legal_name = (data.get("legal_name") or "").strip()
        if not legal_name or len(legal_name) < 2:
            errors.append({"field": "legal_name", "message": "La dénomination légale exacte est obligatoire (minimum 2 caractères)."})

        country = (data.get("country") or "").strip()
        if not country:
            errors.append({"field": "country", "message": "Le pays d'immatriculation est obligatoire."})

        province_state = (data.get("province_state") or "").strip()
        if not province_state:
            errors.append({"field": "province_state", "message": "La province, l'état ou la région d'immatriculation est obligatoire."})

        # Validation conditionnelle du NEQ québécois
        is_quebec = (
            country.lower() in ("canada", "ca")
            and province_state.lower() in ("quebec", "qc", "québec")
        )
        reg_number = (data.get("registration_number") or "").strip()
        if is_quebec and reg_number:
            clean_neq = re.sub(r"\D", "", reg_number)
            if not NEQ_REGEX.match(clean_neq):
                errors.append({
                    "field": "registration_number",
                    "message": "Le Numéro d'Entreprise du Québec (NEQ) doit contenir exactement 10 chiffres.",
                })

        # 2. Validation de l'adresse enregistrée
        for addr_field, label in [
            ("registered_address_street", "L'adresse de voirie enregistrée"),
            ("registered_address_city", "La ville enregistrée"),
            ("registered_address_state_province", "La province ou l'état enregistré"),
            ("registered_address_postal_code", "Le code postal enregistré"),
            ("registered_address_country", "Le pays enregistré"),
        ]:
            val = (data.get(addr_field) or "").strip()
            if not val:
                errors.append({"field": addr_field, "message": f"{label} est obligatoire."})

        # 3. Validation de l'adresse postale si différente
        if not data.get("mailing_address_same", True):
            for m_field, label in [
                ("mailing_address_street", "L'adresse postale"),
                ("mailing_address_city", "La ville postale"),
                ("mailing_address_postal_code", "Le code postal postal"),
                ("mailing_address_country", "Le pays postal"),
            ]:
                val = (data.get(m_field) or "").strip()
                if not val:
                    errors.append({"field": m_field, "message": f"{label} est obligatoire lorsque l'adresse postale diffère."})

        # 4. Coordonnées corporatives
        phone = (data.get("phone") or "").strip()
        if not phone or not PHONE_REGEX.match(phone):
            errors.append({"field": "phone", "message": "Un numéro de téléphone professionnel valide avec indicatif pays est requis."})

        gen_email = (data.get("general_email") or "").strip()
        if not gen_email or not EMAIL_REGEX.match(gen_email):
            errors.append({"field": "general_email", "message": "Le courriel professionnel général est invalide."})

        bill_email = (data.get("billing_email") or "").strip()
        if not bill_email or not EMAIL_REGEX.match(bill_email):
            errors.append({"field": "billing_email", "message": "Le courriel de facturation est invalide."})

        # 5. Représentant légal autorisé
        rep_first = (data.get("authorized_representative_first_name") or "").strip()
        rep_last = (data.get("authorized_representative_last_name") or "").strip()
        if not rep_first or not rep_last:
            errors.append({"field": "authorized_representative_first_name", "message": "Le prénom et le nom du signataire légal sont obligatoires."})

        rep_email = (data.get("authorized_representative_email") or "").strip()
        if not rep_email or not EMAIL_REGEX.match(rep_email):
            errors.append({"field": "authorized_representative_email", "message": "Le courriel du signataire autorisé est invalide."})

        rep_title = (data.get("authorized_representative_title") or "").strip()
        if not rep_title:
            errors.append({"field": "authorized_representative_title", "message": "Le titre ou la fonction du signataire est obligatoire."})

        rep_capacity = (data.get("authorized_representative_capacity") or "").strip()
        if rep_capacity not in VALID_CAPACITIES:
            errors.append({
                "field": "authorized_representative_capacity",
                "message": f"Qualité juridique non reconnue ({rep_capacity}). Choisissez parmi : {', '.join(sorted(VALID_CAPACITIES))}.",
            })

        if not data.get("authorized_representative_authority_confirmed", False):
            errors.append({
                "field": "authorized_representative_authority_confirmed",
                "message": "La déclaration attestant de l'autorité légale pour engager l'entreprise doit être cochée affirmativement.",
            })

        return errors

    def upsert_profile(self, company_id: UUID, data: dict[str, Any]) -> CompanyLegalProfile:
        errors = self.validate_profile_payload(data)
        if errors:
            raise LegalProfileValidationError("Données du profil juridique invalides", errors=errors)

        profile = self.get_profile(company_id)
        if profile is None:
            profile = CompanyLegalProfile(company_id=company_id)
            self.db.add(profile)

        # Mapping direct des champs validés
        profile.legal_name = data["legal_name"].strip()
        profile.trade_name = (data.get("trade_name") or "").strip() or None
        profile.country = data["country"].strip()
        profile.province_state = data["province_state"].strip()
        profile.registration_number = (data.get("registration_number") or "").strip() or None
        profile.business_number = (data.get("business_number") or "").strip() or None
        profile.tax_id_gst = (data.get("tax_id_gst") or "").strip() or None
        profile.tax_id_qst = (data.get("tax_id_qst") or "").strip() or None
        profile.tax_id_other = (data.get("tax_id_other") or "").strip() or None

        profile.registered_address_street = data["registered_address_street"].strip()
        profile.registered_address_city = data["registered_address_city"].strip()
        profile.registered_address_state_province = data["registered_address_state_province"].strip()
        profile.registered_address_postal_code = data["registered_address_postal_code"].strip()
        profile.registered_address_country = data["registered_address_country"].strip()

        profile.mailing_address_same = bool(data.get("mailing_address_same", True))
        if not profile.mailing_address_same:
            profile.mailing_address_street = (data.get("mailing_address_street") or "").strip() or None
            profile.mailing_address_city = (data.get("mailing_address_city") or "").strip() or None
            profile.mailing_address_state_province = (data.get("mailing_address_state_province") or "").strip() or None
            profile.mailing_address_postal_code = (data.get("mailing_address_postal_code") or "").strip() or None
            profile.mailing_address_country = (data.get("mailing_address_country") or "").strip() or None
        else:
            profile.mailing_address_street = None
            profile.mailing_address_city = None
            profile.mailing_address_state_province = None
            profile.mailing_address_postal_code = None
            profile.mailing_address_country = None

        profile.website = (data.get("website") or "").strip() or None
        profile.phone = data["phone"].strip()
        profile.general_email = data["general_email"].strip()
        profile.billing_email = data["billing_email"].strip()
        profile.industry = data.get("industry", "Technologies").strip()
        profile.legal_entity_type = data.get("legal_entity_type", "Corporation").strip()
        profile.preferred_language = data.get("preferred_language", "fr").strip().lower()

        profile.authorized_representative_first_name = data["authorized_representative_first_name"].strip()
        profile.authorized_representative_last_name = data["authorized_representative_last_name"].strip()
        profile.authorized_representative_email = data["authorized_representative_email"].strip()
        profile.authorized_representative_title = data["authorized_representative_title"].strip()
        profile.authorized_representative_capacity = data["authorized_representative_capacity"].strip()
        profile.authorized_representative_authority_confirmed = bool(data["authorized_representative_authority_confirmed"])

        # Synchronisation avec le modèle Company
        company = self.db.get(Company, company_id)
        if company:
            company.billing_email = profile.billing_email
            company.phone = profile.phone
            if profile.website:
                company.website = profile.website
            if profile.industry:
                company.industry = profile.industry
            company.preferred_language = profile.preferred_language

        self.db.commit()
        self.db.refresh(profile)
        return profile
