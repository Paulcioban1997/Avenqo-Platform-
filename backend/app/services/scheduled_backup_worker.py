"""Worker asynchrone d'arrière-plan pour les sauvegardes automatiques complètes (Option A).

Exécute la sauvegarde PostgreSQL et l'archivage complet du volume /data/artifacts
directement depuis le contexte conteneur de l'API (qui a un accès direct au volume monté).
Fonctionne de manière non-bloquante via asyncio.to_thread, sans impacter le trafic HTTP.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.app.config.settings import Settings

logger = logging.getLogger("avenqo.backup.scheduled")


async def backup_loop(settings: Settings, stop_event: asyncio.Event) -> None:
    """Boucle planifiée exécutant les sauvegardes automatiques dans le contexte de l'API."""
    interval_seconds = max(settings.backup_scheduled_interval_hours * 3600, 3600)
    logger.info(
        "scheduled_backup_worker_started interval_hours=%d s3_enabled=%s artifact_root=%s",
        settings.backup_scheduled_interval_hours,
        settings.backup_s3_enabled(),
        settings.artifact_root,
    )

    # Délai initial de 5 minutes après démarrage de l'API avant le premier backup
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=300.0)
        return
    except asyncio.TimeoutError:
        pass

    while not stop_event.is_set():
        try:
            logger.info("scheduled_backup_worker_executing")
            from backend.app.services.backup_service import BackupService

            service = BackupService(settings)  # type: ignore[arg-type]
            metadata = await asyncio.to_thread(service.create_backup)
            logger.info(
                "scheduled_backup_worker_success backup_id=%s db_bytes=%s artifacts_checksum=%s artifacts_bytes=%s",
                metadata.backup_id,
                metadata.size_bytes,
                metadata.artifacts_checksum_sha256,
                metadata.artifacts_size_bytes,
            )
        except Exception as exc:
            logger.exception("scheduled_backup_worker_failed: %s", exc)

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError:
            continue
