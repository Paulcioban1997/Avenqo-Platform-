"""Politique CORE d'import de données — indépendante des modules optionnels.

L'ingestion de données (Connections / "Charger mes données") est une
capacité de plateforme disponible dès l'offre Demo, sans activer aucun
module métier optionnel (retail/crm/accounting). Seules des limites
dépendant du plan (nombre de datasets, taille de fichier) s'appliquent ici.
L'activation d'un module optionnel reste requise uniquement pour EXÉCUTER
une capacité métier sur un dataset déjà importé (voir
`CapabilityExecutionGate`).
"""

from __future__ import annotations

from pathlib import Path
import shutil

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models import Company, Dataset
from payments.plans import data_import_limits_for
from shared.ai_engine.contracts import TenantContext


class DataImportQuotaExceeded(ValueError):
    """Le nombre de datasets ou le volume de stockage cumulé dépasse la limite de l'offre."""


class DataImportFileTooLargeError(DataImportQuotaExceeded):
    """La taille du fichier unitaire dépasse la limite autorisée par l'offre."""


class DataImportStorageUnavailableError(DataImportQuotaExceeded):
    """La capacité physique du volume de stockage hôte (ex. Railway) est insuffisante."""


class DataImportPolicy:
    """Résout les limites CORE d'import de données pour le plan d'un tenant."""

    def __init__(self, session: Session, artifact_root: Path | None = None) -> None:
        self._session = session
        if artifact_root is None:
            try:
                from backend.app.config.settings import get_settings
                self._artifact_root = Path(get_settings().artifact_root).resolve()
            except Exception:
                self._artifact_root = Path("./artifacts").resolve()
        else:
            self._artifact_root = Path(artifact_root).resolve()

    def current_storage_bytes(self, tenant: TenantContext) -> int:
        """Calcule la consommation de stockage réelle en octets pour ce tenant."""
        company_id = str(tenant.company_id)
        total = 0
        tenant_dirs = [
            self._artifact_root / company_id,
            self._artifact_root / "company_datasets" / company_id,
        ]
        for t_dir in tenant_dirs:
            if t_dir.exists() and t_dir.is_dir():
                for p in t_dir.rglob("*"):
                    if p.is_file():
                        try:
                            total += p.stat().st_size
                        except OSError:
                            pass
        return total

    def max_upload_bytes(self, tenant: TenantContext, global_ceiling_bytes: int | None = None) -> int:
        """Le plan définit la taille maximale d'un fichier à charger."""
        limits = data_import_limits_for(self._plan_code(tenant))
        plan_bytes = limits.max_file_mb * 1024 * 1024
        if global_ceiling_bytes is not None and global_ceiling_bytes > 0:
            return min(global_ceiling_bytes, plan_bytes)
        return plan_bytes

    def storage_quota_for_tenant(self, tenant: TenantContext) -> dict[str, object]:
        """Retourne les quotas d'import et de stockage alloués pour l'abonnement du tenant."""
        plan = self._plan_code(tenant)
        limits = data_import_limits_for(plan)
        count = self._session.scalar(
            select(func.count()).select_from(Dataset).where(Dataset.company_id == tenant.company_id)
        ) or 0
        used_bytes = self.current_storage_bytes(tenant)
        max_bytes = limits.max_storage_gb * 1024 * 1024 * 1024
        max_file_bytes = limits.max_file_mb * 1024 * 1024
        available_bytes = max(0, max_bytes - used_bytes)

        host_free_bytes: int | None = None
        try:
            if self._artifact_root.exists():
                host_free_bytes = shutil.disk_usage(self._artifact_root).free
        except Exception:
            pass

        return {
            "plan": plan,
            "max_storage_gb": limits.max_storage_gb,
            "max_storage_label": limits.max_storage_label,
            "max_storage_bytes": max_bytes,
            "used_storage_bytes": used_bytes,
            "used_storage_mb": round(used_bytes / (1024 * 1024), 2),
            "used_storage_gb": round(used_bytes / (1024 * 1024 * 1024), 4),
            "available_storage_bytes": available_bytes,
            "max_file_mb": limits.max_file_mb,
            "max_file_bytes": max_file_bytes,
            "max_datasets": limits.max_datasets,
            "current_datasets_count": count,
            "host_disk_free_bytes": host_free_bytes,
        }

    def check_dataset_quota(self, tenant: TenantContext) -> None:
        limits = data_import_limits_for(self._plan_code(tenant))
        count = self._session.scalar(
            select(func.count()).select_from(Dataset).where(Dataset.company_id == tenant.company_id)
        ) or 0
        if count >= limits.max_datasets:
            raise DataImportQuotaExceeded(
                f"Limite de {limits.max_datasets} jeux de données atteinte pour votre offre {limits.max_storage_label}."
            )

    def check_storage_quota(self, tenant: TenantContext, incoming_bytes: int = 0) -> None:
        """Vérifie la limite unitaire, le quota cumulé du plan et la capacité physique du volume."""
        plan = self._plan_code(tenant)
        limits = data_import_limits_for(plan)
        max_file_bytes = limits.max_file_mb * 1024 * 1024
        max_storage_bytes = limits.max_storage_gb * 1024 * 1024 * 1024

        # 1. Vérification limite unitaire par fichier
        if incoming_bytes > max_file_bytes:
            incoming_mb = round(incoming_bytes / (1024 * 1024), 2)
            raise DataImportFileTooLargeError(
                f"La taille du fichier ({incoming_mb} Mo) dépasse le plafond autorisé de {limits.max_file_mb} Mo pour votre forfait {limits.max_storage_label}."
            )

        # 2. Vérification quota cumulatif tenant
        used_bytes = self.current_storage_bytes(tenant)
        if (used_bytes + incoming_bytes) > max_storage_bytes:
            incoming_mb = round(incoming_bytes / (1024 * 1024), 2)
            available_mb = round(max(0, max_storage_bytes - used_bytes) / (1024 * 1024), 2)
            raise DataImportQuotaExceeded(
                f"Quota de stockage de l'offre {limits.max_storage_label} dépassé : l'import nécessite {incoming_mb} Mo mais l'espace disponible est de {available_mb} Mo."
            )

        # 3. Vérification de la capacité physique de l'hôte (volume Railway / disque)
        try:
            if self._artifact_root.exists():
                free_bytes = shutil.disk_usage(self._artifact_root).free
                if incoming_bytes > free_bytes:
                    incoming_mb = round(incoming_bytes / (1024 * 1024), 2)
                    free_mb = round(free_bytes / (1024 * 1024), 2)
                    raise DataImportStorageUnavailableError(
                        f"Capacité de stockage d'infrastructure temporairement insuffisante ({incoming_mb} Mo requis, {free_mb} Mo réels disponibles sur le volume Railway). Veuillez contacter le support."
                    )
        except (DataImportStorageUnavailableError, DataImportQuotaExceeded):
            raise
        except Exception:
            pass

    def _plan_code(self, tenant: TenantContext) -> str:
        plan = self._session.scalar(
            select(Company.subscription_plan).where(Company.id == tenant.company_id)
        )
        return plan or "demo"
