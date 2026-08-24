"""`CapabilityExecutionGate` — Phase 27.

Point d'entrée unique et sécurisé pour toute capacité RetailSenseAI qui
consomme un dataset préparé (Phase 26). Flux imposé :

    TenantContext (serveur, authentifié)
        -> resolve PreparedCompanyDataset (tenant-scoped)
        -> vérifie l'appartenance + le statut READY (via
           `CompanyDatasetIngestionService.get_prepared_dataset`, qui lève
           déjà `DatasetNotFoundError` pour tout dataset n'appartenant pas au
           tenant, cf. Phase 26)
        -> `CapabilityDatasetAdapter`
        -> `CapabilityDataset`

Aucun bypass raw n'est exposé ici : ni chemin de fichier, ni DataFrame brut,
ni octets CSV — uniquement `(tenant, dataset_id, capability)`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from backend.app.services.company_dataset_ingestion_service import CompanyDatasetIngestionService
from shared.ai_engine.capability_dataset.adapter import CapabilityDatasetAdapter
from shared.ai_engine.capability_dataset.contracts import (
    CapabilityDataset,
    CapabilityDatasetValidation,
)
from shared.ai_engine.contracts import TenantContext

if TYPE_CHECKING:
    from modules.entitlements import ModuleAccessService


class CapabilityExecutionGate:
    """Porte d'entrée unique entre l'API et les capacités RetailSenseAI."""

    def __init__(
        self,
        ingestion_service: CompanyDatasetIngestionService,
        adapter: CapabilityDatasetAdapter | None = None,
        access: ModuleAccessService | None = None,
    ) -> None:
        self._ingestion = ingestion_service
        self._adapter = adapter or CapabilityDatasetAdapter()
        # L'ingestion de données reste une capacité CORE (jamais gatée par un
        # module) : c'est ICI, à l'EXÉCUTION d'une capacité métier optionnelle
        # sur un dataset déjà importé, que l'activation du module reste
        # requise. `access` est optionnel pour ne pas casser les appelants
        # existants qui ne gèrent pas encore de capacités multi-modules.
        self._access = access

    def _require_module_access(self, tenant: TenantContext, dataset_id: UUID) -> None:
        if self._access is None:
            return
        module_code = self._ingestion.get_module_code(tenant, dataset_id)
        if module_code:
            self._access.require_active(tenant, module_code)

    def check_readiness(
        self,
        tenant: TenantContext,
        dataset_id: UUID,
        capability: str,
    ) -> CapabilityDatasetValidation:
        """Vérification non-levante (hors résolution du dataset lui-même)."""

        self._require_module_access(tenant, dataset_id)
        prepared = self._ingestion.get_prepared_dataset(tenant, dataset_id)
        return self._adapter.validate(prepared, capability)

    def prepare(
        self,
        tenant: TenantContext,
        dataset_id: UUID,
        capability: str,
    ) -> CapabilityDataset:
        """Résout le dataset (tenant-scoped) puis l'adapte pour `capability`.

        Lève `DatasetNotFoundError` (cross-tenant ou inexistant),
        `ModuleAccessDenied` (module optionnel requis pour cette capacité
        non actif), ou `DatasetIngestionError` (dataset pas prêt) depuis
        `get_prepared_dataset`, ou `MissingCapabilityFields`/
        `InvalidCapabilityDataset` depuis l'adapter.
        """

        self._require_module_access(tenant, dataset_id)
        prepared = self._ingestion.get_prepared_dataset(tenant, dataset_id)
        return self._adapter.prepare(prepared, capability)



def prepare_training_input(
    gate: CapabilityExecutionGate,
    tenant: TenantContext,
    dataset_id: UUID,
    capability: str,
) -> CapabilityDataset:
    """Training handoff (Phase 27, section 20/26).

    Retourne un `CapabilityDataset` prêt pour la feature engineering et
    l'entraînement existants. N'entraîne AUCUN modèle : seule la préparation
    des données passe par ce point d'entrée.
    """

    return gate.prepare(tenant, dataset_id, capability)
