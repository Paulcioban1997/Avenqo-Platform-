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

_worker_lock = asyncio.Lock()


async def backup_loop(settings: Settings, stop_event: asyncio.Event) -> None:
    """Boucle planifiée exécutant les sauvegardes automatiques dans le contexte de l'API."""
    interval_seconds = max(settings.backup_scheduled_interval_hours * 3600, 3600)
    initial_delay = getattr(settings, "backup_scheduled_initial_delay_seconds", 15.0)

    logger.info(
        "scheduled_backup_worker_started interval_hours=%d initial_delay=%.1fs s3_enabled=%s artifact_root=%s",
        settings.backup_scheduled_interval_hours,
        initial_delay,
        settings.backup_s3_enabled,
        settings.artifact_root,
    )

    # Délai initial court après démarrage de l'API avant le premier backup
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=initial_delay)
        return
    except asyncio.TimeoutError:
        pass

    while not stop_event.is_set():
        if _worker_lock.locked():
            logger.warning("scheduled_backup_worker_skipped_already_in_progress")
        else:
            async with _worker_lock:
                try:
                    logger.info("scheduled_backup_worker_executing")
                    from backend.app.services.backup_service import BackupService

                    service = BackupService(settings)  # type: ignore[arg-type]

                    # Pré-vol : vérification des permissions avant le dump
                    metadata = await asyncio.to_thread(service.create_backup)
                    logger.info(
                        "scheduled_backup_worker_success backup_id=%s db_bytes=%s db_checksum=%s artifacts_checksum=%s artifacts_bytes=%s s3_uploaded=%s environment=%s",
                        metadata.backup_id,
                        metadata.size_bytes,
                        metadata.checksum_sha256,
                        metadata.artifacts_checksum_sha256,
                        metadata.artifacts_size_bytes,
                        bool(settings.backup_s3_enabled),
                        settings.environment,
                    )
                except Exception as exc:
                    logger.error("scheduled_backup_worker_failed: %s", exc, exc_info=True)

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError:
            continue
