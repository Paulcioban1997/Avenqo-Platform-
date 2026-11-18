"""Progressive chunked streaming spooler and tenant concurrency protection for large dataset imports."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import logging
from pathlib import Path
import shutil
import tempfile
from typing import AsyncIterator
from uuid import UUID

from fastapi import HTTPException, UploadFile, status

from backend.app.services.data_import_policy import (
    DataImportFileTooLargeError,
    DataImportPolicy,
    DataImportQuotaExceeded,
    DataImportStorageUnavailableError,
)
from shared.ai_engine.contracts import TenantContext

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1024 * 1024  # 1 MB progressive ingestion chunk
MAX_CONCURRENT_UPLOADS_PER_TENANT = 3
MIN_HOST_DISK_FREE_MARGIN_BYTES = 50 * 1024 * 1024  # 50 MB safety margin on host volume


class TenantUploadReservation:
    """Suivi dynamique du volume en cours d'ingestion pour une requête de téléversement."""

    def __init__(self, tracker: TenantUploadConcurrencyTracker, tenant_id: UUID) -> None:
        self._tracker = tracker
        self.tenant_id = tenant_id
        self.in_flight_bytes = 0

    def update_bytes(self, total_bytes: int) -> None:
        delta = total_bytes - self.in_flight_bytes
        self.in_flight_bytes = total_bytes
        self._tracker.adjust_in_flight(self.tenant_id, delta)


class TenantUploadConcurrencyTracker:
    """Garantit l'isolation de concurrence par tenant et prévient le contournement de quota."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._active_counts: dict[UUID, int] = {}
        self._in_flight_bytes: dict[UUID, int] = {}

    def get_in_flight_bytes(self, tenant_id: UUID) -> int:
        return self._in_flight_bytes.get(tenant_id, 0)

    def adjust_in_flight(self, tenant_id: UUID, delta: int) -> None:
        current = self._in_flight_bytes.get(tenant_id, 0)
        new_val = max(0, current + delta)
        if new_val == 0:
            self._in_flight_bytes.pop(tenant_id, None)
        else:
            self._in_flight_bytes[tenant_id] = new_val

    @asynccontextmanager
    async def reserve(
        self,
        tenant_id: UUID,
        max_concurrent: int = MAX_CONCURRENT_UPLOADS_PER_TENANT,
    ) -> AsyncIterator[TenantUploadReservation]:
        async with self._lock:
            current_active = self._active_counts.get(tenant_id, 0)
            if current_active >= max_concurrent:
                logger.warning(
                    "tenant_upload_concurrency_limit_reached tenant_id=%s active=%d limit=%d",
                    tenant_id, current_active, max_concurrent,
                )
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Trop de téléversements simultanés ({current_active}/{max_concurrent}) pour votre organisation. Veuillez patienter.",
                )
            self._active_counts[tenant_id] = current_active + 1

        reservation = TenantUploadReservation(self, tenant_id)
        try:
            yield reservation
        finally:
            async with self._lock:
                reservation.update_bytes(0)
                active = self._active_counts.get(tenant_id, 1) - 1
                if active <= 0:
                    self._active_counts.pop(tenant_id, None)
                    self._in_flight_bytes.pop(tenant_id, None)
                else:
                    self._active_counts[tenant_id] = active


# Singleton partagé pour l'ensemble des routes d'ingestion
global_tenant_upload_tracker = TenantUploadConcurrencyTracker()


@asynccontextmanager
async def spool_progressive_upload(
    file: UploadFile,
    tenant: TenantContext,
    policy: DataImportPolicy,
    tracker: TenantUploadConcurrencyTracker = global_tenant_upload_tracker,
) -> AsyncIterator[tuple[Path, int]]:
    """Ingère un flux UploadFile par blocs de 1 Mo, spoule sur disque et vérifie les quotas en continu."""

    # 1. Vérification préliminaire fail-fast (avant toute lecture réseau)
    policy.check_storage_quota(tenant, incoming_bytes=0)
    max_file_bytes = policy.max_upload_bytes(tenant)
    quota_info = policy.storage_quota_for_tenant(tenant)
    max_storage_bytes = int(quota_info["max_storage_bytes"])  # type: ignore
    current_storage = int(quota_info["used_storage_bytes"])    # type: ignore

    async with tracker.reserve(tenant.company_id) as reservation:
        other_in_flight = tracker.get_in_flight_bytes(tenant.company_id) - reservation.in_flight_bytes

        spool = tempfile.NamedTemporaryFile(mode="w+b", delete=False, suffix=".upload.spool")
        spool_path = Path(spool.name)

        bytes_read = 0
        try:
            while True:
                chunk = await file.read(CHUNK_SIZE)
                if not chunk:
                    break
                bytes_read += len(chunk)
                reservation.update_bytes(bytes_read)

                # Vérification unitaire par fichier
                if bytes_read > max_file_bytes:
                    raise DataImportFileTooLargeError(
                        f"Taille de fichier ({bytes_read} octets) supérieure à la limite autorisée ({max_file_bytes} octets) pour votre offre."
                    )

                # Vérification quota cumulé avec uploads concurrents en vol
                if current_storage + other_in_flight + bytes_read > max_storage_bytes:
                    raise DataImportQuotaExceeded(
                        f"Quota de stockage de l'offre ({max_storage_bytes} octets) dépassé. "
                        f"Consommation actuelle: {current_storage} octets, en transit: {other_in_flight + bytes_read} octets."
                    )

                # Vérification capacité physique du volume local (Railway)
                try:
                    host_free = shutil.disk_usage(spool_path.parent).free
                    if host_free < MIN_HOST_DISK_FREE_MARGIN_BYTES:
                        raise DataImportStorageUnavailableError(
                            "Capacité physique du volume hôte insuffisante pour accueillir l'import."
                        )
                except (DataImportStorageUnavailableError, OSError):
                    raise

                spool.write(chunk)

            spool.flush()
            spool.close()

            if bytes_read == 0:
                raise ValueError("Le fichier envoyé est vide.")

            yield spool_path, bytes_read
        finally:
            try:
                spool.close()
            except Exception:
                pass
            if spool_path.exists():
                try:
                    spool_path.unlink(missing_ok=True)
                except OSError:
                    pass
