"""Politique centralisée et cohérente d'autorisation pour les contrats et documents Avenqo.

Règles fondamentales :
1. Contrats Avenqo du socle (pilot, saas subscription, mutual nda, dpa, terms) :
   Accessibles aux utilisateurs autorisés de leur propre entreprise sans forcer l'achat
   du module 'legal'.
2. Contrats tiers (fournisseurs externes, conventions client personnalisées,
   metadata is_third_party=True) :
   Nécessitent expressément le module 'legal' actif pour l'entreprise ainsi que la
   permission 'data:read', en recherche, consultation, génération de jeton et téléchargement.
3. Documents de nature légale (TenantDocument avec kind='legal') :
   Nécessitent expressément le module 'legal' actif.
4. Isolation multi-tenant stricte :
   Aucun utilisateur ne peut accéder à un contrat d'une autre entreprise.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy.orm import Session

from backend.app.models.company_contract import CompanyContract
from backend.app.models.workspace import TenantDocument
from backend.app.services.module_entitlement_service import ModuleEntitlementService
from shared.ai_engine.contracts import TenantContext


# Types de contrats officiellement inclus dans le socle de la plateforme Avenqo
PLATFORM_CONTRACT_TYPES = frozenset({
    "pilot",
    "saas_pilot_commercial_agreement",
    "pilot_agreement",
    "saas_subscription",
    "saas_master_subscription_agreement",
    "master_subscription_agreement",
    "mutual_nda",
    "nda",
    "data_processing_addendum",
    "dpa",
    "private_license",
    "enterprise",
    "enterprise_agreement",
    "terms_of_service",
    "terms",
    "service_level_agreement",
})

THIRD_PARTY_CONTRACT_TYPES = frozenset({
    "third_party",
    "third_party_vendor",
    "client_custom",
    "custom_third_party",
    "vendor_agreement",
    "vendor",
    "supplier",
})


def is_third_party_contract(contract: CompanyContract | None) -> bool:
    """Détermine côté serveur si un contrat est un contrat tiers ou un contrat du socle."""
    if contract is None:
        return False

    # 1. Marqueur explicite dans les métadonnées serveur
    if contract.metadata_json and bool(contract.metadata_json.get("is_third_party")):
        return True

    # 2. Type de contrat explicitement tiers
    contract_type_norm = (contract.contract_type or "").strip().lower()
    if contract_type_norm in THIRD_PARTY_CONTRACT_TYPES:
        return True

    # 3. Si le type est explicitement dans le socle reconnu
    if contract_type_norm in PLATFORM_CONTRACT_TYPES or (contract.contract_type or "").strip().upper() in {
        "MUTUAL_NDA",
        "SAAS_SUBSCRIPTION",
        "DATA_PROCESSING_ADDENDUM",
        "PRIVATE_LICENSE",
    }:
        return False

    # 4. Par défaut : si ce n'est pas un contrat du socle officiel et qu'il n'est pas marqué,
    # pour garantir la sécurité zéro-fuite, tout contrat non-socle requiert le module Legal
    return True


class ContractAuthorizationService:
    """Service centralisé de validation des droits sur les contrats et documents légaux."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._entitlements = ModuleEntitlementService(session)

    def has_legal_module(self, tenant: TenantContext) -> bool:
        """Indique si l'entreprise dispose du module 'legal' actif."""
        return self._entitlements.can_use_module(tenant, "legal")

    def has_ocr_module(self, tenant: TenantContext) -> bool:
        """Indique si l'entreprise dispose du module 'ocr' actif."""
        return self._entitlements.can_use_module(tenant, "ocr")

    def can_access_contract(
        self,
        tenant: TenantContext,
        contract: CompanyContract | None,
        permissions: frozenset[str] = frozenset(),
    ) -> tuple[bool, str | None]:
        """Vérifie l'accès à un contrat CompanyContract."""
        if contract is None or contract.company_id != tenant.company_id:
            return False, "Contrat introuvable ou vous n'avez pas l'autorisation d'y accéder."

        if permissions and "data:read" not in permissions:
            return False, "Permissions insuffisantes pour consulter les contrats de l'entreprise."

        if is_third_party_contract(contract):
            if not self.has_legal_module(tenant):
                return False, "Le module Juridique / Contrats est requis pour consulter ce contrat tiers."

        return True, None

    def filter_accessible_contracts(
        self,
        tenant: TenantContext,
        contracts: list[CompanyContract],
        permissions: frozenset[str] = frozenset(),
    ) -> list[CompanyContract]:
        """Filtre la liste des contrats accessibles pour la recherche."""
        if permissions and "data:read" not in permissions:
            return []

        has_legal = self.has_legal_module(tenant)
        result: list[CompanyContract] = []
        for contract in contracts:
            if contract.company_id != tenant.company_id:
                continue
            if is_third_party_contract(contract) and not has_legal:
                continue
            result.append(contract)
        return result

    def can_access_document(
        self,
        tenant: TenantContext,
        doc: TenantDocument | None,
        permissions: frozenset[str] = frozenset(),
    ) -> tuple[bool, str | None]:
        """Vérifie l'accès à un document TenantDocument."""
        if doc is None or doc.company_id != tenant.company_id:
            return False, "Document introuvable ou vous n'avez pas l'autorisation d'y accéder."

        if permissions and "data:read" not in permissions:
            return False, "Permissions insuffisantes pour consulter ce document."

        if doc.kind == "legal" and not self.has_legal_module(tenant):
            return False, "Le module Juridique est requis pour accéder à ce document légal."

        return True, None

    def filter_accessible_documents(
        self,
        tenant: TenantContext,
        docs: list[TenantDocument],
        permissions: frozenset[str] = frozenset(),
    ) -> list[TenantDocument]:
        """Filtre les documents retournés en recherche."""
        if permissions and "data:read" not in permissions:
            return []

        has_legal = self.has_legal_module(tenant)
        result: list[TenantDocument] = []
        for doc in docs:
            if doc.company_id != tenant.company_id:
                continue
            if doc.kind == "legal" and not has_legal:
                continue
            result.append(doc)
        return result
