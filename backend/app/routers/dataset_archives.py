"""Secure ZIP archive ingestion for company datasets.

A ZIP is treated as a transport container only. Each supported data file inside
is ingested independently through the existing tenant-scoped universal dataset
pipeline, so cleaning, profiling, mapping and persistent artifact storage stay
identical to normal uploads.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from starlette.concurrency import run_in_threadpool

from backend.app.dependencies.auth import get_tenant_context
from backend.app.dependencies.datasets import get_company_dataset_ingestion_service
from backend.app.services.company_dataset_ingestion_service import CompanyDatasetIngestionService
from backend.app.services.data_import_policy import DataImportQuotaExceeded
from modules.entitlements import ModuleAccessDenied
from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.dataset_ingestion.exceptions import DatasetIngestionError
from shared.ai_engine.dataset_ingestion.loader import SUPPORTED_EXTENSIONS

router = APIRouter(prefix="/datasets", tags=["datasets"])

_MAX_ARCHIVE_FILES = 100
_MAX_COMPRESSION_RATIO = 100
_MAX_TOTAL_UNCOMPRESSED_BYTES = 512 * 1024 * 1024


def _safe_members(content: bytes):
    try:
        archive = ZipFile(BytesIO(content))
    except BadZipFile as exc:
        raise DatasetIngestionError("Archive ZIP invalide ou corrompue.") from exc

    supported = []
    total_uncompressed = 0
    for member in archive.infolist():
        if member.is_dir():
            continue
        path = PurePosixPath(member.filename)
        if path.is_absolute() or ".." in path.parts:
            archive.close()
            raise DatasetIngestionError("Archive ZIP non sécurisée : chemin de fichier invalide.")
        if Path(member.filename).suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        supported.append(member)
        total_uncompressed += member.file_size

    if not supported:
        archive.close()
        raise DatasetIngestionError(
            "Le ZIP ne contient aucun fichier de données supporté "
            f"({', '.join(SUPPORTED_EXTENSIONS)})."
        )
    if len(supported) > _MAX_ARCHIVE_FILES:
        archive.close()
        raise DatasetIngestionError(
            f"Le ZIP contient trop de fichiers ({len(supported)}). Maximum : {_MAX_ARCHIVE_FILES}."
        )
    if total_uncompressed > _MAX_TOTAL_UNCOMPRESSED_BYTES:
        archive.close()
        raise DatasetIngestionError("Le contenu décompressé du ZIP est trop volumineux.")
    if content and total_uncompressed > len(content) * _MAX_COMPRESSION_RATIO:
        archive.close()
        raise DatasetIngestionError("Archive ZIP refusée : ratio de compression anormal.")
    return archive, supported


def _ingest_archive(
    service: CompanyDatasetIngestionService,
    tenant: TenantContext,
    module_code: str,
    content: bytes,
):
    archive, members = _safe_members(content)
    imported = []
    errors: list[str] = []
    try:
        for member in members:
            filename = Path(member.filename).name
            if not filename:
                continue
            try:
                imported.append(
                    service.upload(tenant, module_code, filename, archive.read(member))
                )
            except (DatasetIngestionError, DataImportQuotaExceeded) as exc:
                errors.append(f"{filename}: {exc}")
    finally:
        archive.close()

    if not imported:
        detail = errors[0] if errors else "Aucun fichier du ZIP n'a pu être importé."
        raise DatasetIngestionError(detail)
    return imported, errors


@router.post("/archive", status_code=status.HTTP_201_CREATED)
async def upload_dataset_archive(
    module_code: str = Form(),
    file: UploadFile = File(),
    tenant: TenantContext = Depends(get_tenant_context),
    service: CompanyDatasetIngestionService = Depends(get_company_dataset_ingestion_service),
):
    """Extract a ZIP and import each supported member as an independent dataset."""

    filename = file.filename or "archive.zip"
    if Path(filename).suffix.lower() != ".zip":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cet endpoint accepte uniquement les archives ZIP.",
        )
    content = await file.read()
    try:
        imported, errors = await run_in_threadpool(
            _ingest_archive,
            service,
            tenant,
            module_code,
            content,
        )
    except ModuleAccessDenied as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except DataImportQuotaExceeded as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except DatasetIngestionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    # Keep the response backward-compatible with the current Flutter upload flow:
    # it only needs dataset_id to mark the selected file as successfully uploaded.
    first = imported[0]
    return {
        "dataset_id": str(first.id),
        "status": "ready" if not errors else "partial",
        "imported_count": len(imported),
        "failed_count": len(errors),
        "errors": errors,
        "dataset_ids": [str(dataset.id) for dataset in imported],
    }
