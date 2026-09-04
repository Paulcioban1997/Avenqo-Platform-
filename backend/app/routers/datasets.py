"""Routes minces d'import et de consultation des datasets."""

import logging
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from starlette.concurrency import run_in_threadpool

from backend.app.core.permissions import permissions_for
from backend.app.dependencies.auth import CurrentIdentity, get_current_identity, get_tenant_context
from backend.app.dependencies.datasets import (
    get_capability_execution_gate,
    get_company_dataset_ingestion_service,
    get_dataset_cleaning_service,
    get_dataset_import_service,
)
from backend.app.dependencies.training import get_training_dispatcher
from backend.app.models import DatasetStatus, JobStatus
from backend.app.schemas.company_datasets import (
    CapabilityDatasetResponse,
    CapabilityReadinessResponse,
    ColumnMappingSuggestionResponse,
    ColumnProfileResponse,
    CompanyDatasetProfileResponse,
    CompanyDatasetUploadResponse,
    DatasetCleaningDetailResponse,
    DatasetReconciliationResponse,
    MappingOverrideRequest,
    MappingOverrideResponse,
)
from backend.app.schemas.datasets import DatasetResponse
from backend.app.services.capability_execution_gate import CapabilityExecutionGate
from backend.app.services.company_dataset_ingestion_service import (
    CompanyDatasetIngestionService,
    DatasetNotFoundError as CompanyDatasetNotFoundError,
    InvalidMappingError,
)
from backend.app.services.data_import_policy import DataImportQuotaExceeded
from backend.app.services.dataset_cleaning_service import (
    DatasetCleaningService,
    DatasetNotReadyForExport,
    DatasetSourceUnavailable,
    UnsupportedDatasetExport,
)
from backend.app.services.dataset_import_service import (
    DatasetImportError,
    DatasetImportService,
    DatasetNotFoundError,
)
from backend.app.services.training_dispatcher import TrainingDispatcher
from modules.entitlements import ModuleAccessDenied
from shared.ai_engine.capability_dataset.exceptions import CapabilityNotReady, UnknownCapability
from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.dataset_ingestion.exceptions import DatasetIngestionError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/datasets", tags=["datasets"])


def require_dataset_read(
    identity: CurrentIdentity = Depends(get_current_identity),
) -> CurrentIdentity:
    if not {"data:read", "data:manage"}.intersection(permissions_for(identity.user.role)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission insuffisante",
        )
    return identity


def _current_source_missing(dataset) -> bool:
    """Detect a dataset whose original raw artifact is gone from storage.

    This happens for records created before persistent storage existed (the
    file lived on ephemeral container disk). It must never be reported as
    "ready" or as a semantic "attention_required" mapping issue — it is a
    distinct, honest, reprocessing-required situation.
    """
    current_version = next((item for item in dataset.versions if item.is_current), None)
    if current_version is None or not current_version.artifact_path:
        return False
    expected_rows = int(current_version.row_count or dataset.rows_count or 0)
    if expected_rows <= 0:
        return False
    return not Path(current_version.artifact_path).is_file()


def _pipeline_status(dataset) -> str:
    if dataset.status in {DatasetStatus.FAILED, DatasetStatus.INVALID, DatasetStatus.REJECTED}:
        return "failed"
    if dataset.status == DatasetStatus.MAPPING_REQUIRED:
        return "attention_required"
    if dataset.status not in {DatasetStatus.READY, DatasetStatus.VALIDATED}:
        return "analyzing"
    if _current_source_missing(dataset):
        # Genuinely unrecoverable without a re-upload: report it as a
        # processing error rather than misleading "ready"/"attention_required"
        # (semantic-mapping) labels that do not describe the real problem.
        return "failed"
    return "ready"


def _training_status(dataset) -> str | None:
    if dataset.status not in {DatasetStatus.READY, DatasetStatus.VALIDATED}:
        return None
    if _current_source_missing(dataset):
        return None
    jobs = list(dataset.training_jobs)
    if not jobs:
        return "not_applicable"
    if any(job.status == JobStatus.RUNNING for job in jobs):
        return "training_ai"
    if any(job.status == JobStatus.PENDING for job in jobs):
        return "preparing_data"
    if any(job.status == JobStatus.FAILED for job in jobs):
        return "training_failed"
    if any(job.status == JobStatus.COMPLETED for job in jobs):
        return "ready"
    return "ready"


def dataset_response(dataset) -> DatasetResponse:
    profile = dataset.profile
    quality = dataset.quality_report
    training_status = _training_status(dataset)
    
    # Handle case where profile or quality_report might be None
    if profile is None:
        logger.warning(f"Dataset {dataset.id} has no profile")
        # Return minimal response without profile data
        return DatasetResponse(
            id=dataset.id,
            name=dataset.name,
            type=dataset.type,
            module_code="unknown",
            rows_count=dataset.rows_count,
            columns_count=dataset.columns_count,
            numerical_columns=[],
            categorical_columns=[],
            missing_values=0,
            duplicates=0,
            quality_score=0.0,
            status=dataset.status,
            pipeline_status=_pipeline_status(dataset),
            training_status=training_status,
            training_retryable=training_status == "training_failed",
            uploaded_at=dataset.uploaded_at,
            columns=[],
            distributions={},
        )
    
    if quality is None:
        logger.warning(f"Dataset {dataset.id} has no quality report")
        quality_data = {
            "missing_values": 0,
            "duplicates": 0,
            "quality_score": 0.0,
        }
    else:
        quality_data = {
            "missing_values": quality.missing_values,
            "duplicates": quality.duplicates,
            "quality_score": quality.quality_score,
        }
    
    return DatasetResponse(
        id=dataset.id,
        name=dataset.name,
        type=dataset.type,
        module_code=profile.module_code,
        rows_count=dataset.rows_count,
        columns_count=dataset.columns_count,
        numerical_columns=profile.numerical_columns,
        categorical_columns=profile.categorical_columns,
        missing_values=quality_data["missing_values"],
        duplicates=quality_data["duplicates"],
        quality_score=quality_data["quality_score"],
        status=dataset.status,
        pipeline_status=_pipeline_status(dataset),
        training_status=training_status,
        training_retryable=training_status == "training_failed",
        uploaded_at=dataset.uploaded_at,
        columns=profile.schema_json["columns"],
        distributions=profile.distribution_json,
    )


@router.post("/csv", response_model=DatasetResponse, status_code=status.HTTP_201_CREATED)
async def upload_csv(
    module_code: str = Form(),
    file: UploadFile = File(),
    tenant: TenantContext = Depends(get_tenant_context),
    service: DatasetImportService = Depends(get_dataset_import_service),
    dispatcher: TrainingDispatcher = Depends(get_training_dispatcher),
) -> DatasetResponse:
    try:
        # Le parsing/profilage CSV est CPU-bound et bloquerait la boucle
        # asyncio (donc TOUTE requête concurrente, ex. GET /datasets) si
        # appelé directement depuis une route async.
        dataset = await run_in_threadpool(
            service.import_csv,
            tenant,
            module_code,
            file.filename or "dataset.csv",
            await file.read(),
        )
    except ModuleAccessDenied as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except DataImportQuotaExceeded as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except DatasetImportError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    # L'utilisateur ne déclenche jamais manuellement l'entraînement : il
    # démarre automatiquement dès qu'un import réussit. Un échec de
    # planification ne doit jamais faire échouer la réponse d'import.
    try:
        dispatcher.dispatch(tenant, dataset)
    except Exception:
        logger.exception("Failed to dispatch automatic training for dataset %s", dataset.id)

    return dataset_response(dataset)


@router.post(
    "/upload",
    response_model=CompanyDatasetUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_company_dataset(
    module_code: str = Form(),
    file: UploadFile = File(),
    tenant: TenantContext = Depends(get_tenant_context),
    service: CompanyDatasetIngestionService = Depends(get_company_dataset_ingestion_service),
) -> CompanyDatasetUploadResponse:
    """Ingestion universelle CSV/XLSX/JSON/Parquet (Phase 26)."""

    try:
        # Idem : l'ingestion universelle (parsing XLSX/JSON/Parquet, mapping
        # sémantique, profilage) est CPU-bound et doit tourner hors event loop.
        dataset = await run_in_threadpool(
            service.upload,
            tenant,
            module_code,
            file.filename or "dataset",
            await file.read(),
        )
    except ModuleAccessDenied as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except DataImportQuotaExceeded as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except DatasetIngestionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    current_version = next((v for v in dataset.versions if v.is_current), dataset.versions[-1])
    return CompanyDatasetUploadResponse(
        dataset_id=dataset.id,
        version=current_version.version_number,
        status=dataset.status,
        rows=dataset.rows_count,
        columns=dataset.columns_count,
    )


@router.get("/{dataset_id}/profile", response_model=CompanyDatasetProfileResponse)
def get_company_dataset_profile(
    dataset_id: UUID,
    tenant: TenantContext = Depends(get_tenant_context),
    service: CompanyDatasetIngestionService = Depends(get_company_dataset_ingestion_service),
) -> CompanyDatasetProfileResponse:
    try:
        summary = service.get_profile_summary(tenant, dataset_id)
    except CompanyDatasetNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    mapping_payload = (
        summary.dataset.mapping.mapping_json if summary.dataset.mapping is not None else {}
    )
    return CompanyDatasetProfileResponse(
        dataset_id=summary.dataset.id,
        status=summary.dataset.status,
        uploaded_at=summary.dataset.uploaded_at,
        row_count=summary.profile.row_count,
        column_count=summary.profile.column_count,
        columns=tuple(
            ColumnProfileResponse(
                name=column.name,
                semantic_type=column.semantic_type.value,
                non_null_count=column.non_null_count,
                null_ratio=column.null_ratio,
                unique_count=column.unique_count,
                unique_ratio=column.unique_ratio,
                sample_values=column.sample_values,
                min_value=column.min_value,
                max_value=column.max_value,
                mean_value=column.mean_value,
                median_value=column.median_value,
                std_value=column.std_value,
                p25_value=column.p25_value,
                p75_value=column.p75_value,
                outlier_count=column.outlier_count,
                min_date=column.min_date,
                max_date=column.max_date,
                avg_text_length=column.avg_text_length,
            )
            for column in summary.profile.columns
        ),
        mapping_suggestions=tuple(
            ColumnMappingSuggestionResponse(
                original_column=s.original_column,
                suggested_field=s.suggested_field,
                confidence=s.confidence.value,
                score=s.score,
                alternatives=s.alternatives,
                reason=s.reason,
            )
            for s in summary.mapping_suggestions
        ),
        accepted_mapping=dict(mapping_payload.get("accepted") or {}),
        required_confirmation=tuple(
            mapping_payload.get("required_confirmation") or ()
        ),
        review_required=summary.review_required,
        quality_status=summary.quality_status.value if summary.quality_status else None,
        quality_reasons=summary.quality_reasons,
        capability_readiness=tuple(
            CapabilityReadinessResponse(
                capability=r.capability,
                ready=r.ready,
                missing_fields=r.missing_fields,
                warnings=r.warnings,
            )
            for r in summary.capability_readiness
        ),
    )


@router.post("/{dataset_id}/mapping", response_model=MappingOverrideResponse)
def submit_company_dataset_mapping(
    dataset_id: UUID,
    payload: MappingOverrideRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    service: CompanyDatasetIngestionService = Depends(get_company_dataset_ingestion_service),
) -> MappingOverrideResponse:
    try:
        dataset = service.submit_mapping(tenant, dataset_id, payload.mapping)
    except CompanyDatasetNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except InvalidMappingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    accepted = dataset.mapping.mapping_json.get("accepted", {}) if dataset.mapping else {}
    approved = dataset.mapping.approved if dataset.mapping else False
    return MappingOverrideResponse(
        dataset_id=dataset.id,
        status=dataset.status,
        mapping=accepted,
        approved=approved,
    )


@router.post("/reconcile", response_model=DatasetReconciliationResponse)
def reconcile_company_datasets(
    tenant: TenantContext = Depends(get_tenant_context),
    service: CompanyDatasetIngestionService = Depends(get_company_dataset_ingestion_service),
) -> DatasetReconciliationResponse:
    datasets = service.reconcile_existing(tenant)
    return DatasetReconciliationResponse(
        reviewed=len(datasets),
        promoted_to_ready=sum(item.status == DatasetStatus.READY for item in datasets),
        attention_required=sum(
            item.status == DatasetStatus.MAPPING_REQUIRED for item in datasets
        ),
    )


@router.get("/{dataset_id}/cleaning", response_model=DatasetCleaningDetailResponse)
def get_dataset_cleaning_detail(
    dataset_id: UUID,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
    tenant: TenantContext = Depends(get_tenant_context),
    _: CurrentIdentity = Depends(require_dataset_read),
    service: DatasetCleaningService = Depends(get_dataset_cleaning_service),
) -> DatasetCleaningDetailResponse:
    try:
        return DatasetCleaningDetailResponse.model_validate(
            service.detail(tenant, dataset_id, offset=offset, limit=limit)
        )
    except CompanyDatasetNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DatasetSourceUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except DatasetNotReadyForExport as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/{dataset_id}/export/{export_format}")
def export_cleaned_dataset(
    dataset_id: UUID,
    export_format: str,
    tenant: TenantContext = Depends(get_tenant_context),
    _: CurrentIdentity = Depends(require_dataset_read),
    service: DatasetCleaningService = Depends(get_dataset_cleaning_service),
) -> Response:
    try:
        content, media_type, filename = service.export(tenant, dataset_id, export_format)
    except CompanyDatasetNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DatasetSourceUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except DatasetNotReadyForExport as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except UnsupportedDatasetExport as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/{dataset_id}/capabilities/{capability}/prepare",
    response_model=CapabilityDatasetResponse,
)
def prepare_capability_dataset(
    dataset_id: UUID,
    capability: str,
    tenant: TenantContext = Depends(get_tenant_context),
    gate: CapabilityExecutionGate = Depends(get_capability_execution_gate),
) -> CapabilityDatasetResponse:
    """Phase 27 — prépare l'entrée canonique d'UNE capacité (aucun entraînement ici).

    `tenant` vient exclusivement du contexte serveur authentifié (jamais du
    corps de la requête) : aucun `company_id` client n'est jamais accepté, et
    aucun accès cross-tenant n'est possible (`get_prepared_dataset` masque
    déjà les datasets appartenant à un autre tenant derrière un 404, comme le
    reste de l'API Phase 26).
    """

    try:
        capability_dataset = gate.prepare(tenant, dataset_id, capability)
    except CompanyDatasetNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ModuleAccessDenied as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except UnknownCapability as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except DatasetIngestionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except CapabilityNotReady as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    return CapabilityDatasetResponse(
        dataset_id=capability_dataset.dataset_id,
        dataset_version=capability_dataset.dataset_version,
        capability=capability_dataset.capability,
        required_fields=capability_dataset.required_fields,
        available_fields=capability_dataset.available_fields,
        row_count=capability_dataset.row_count,
        warnings=capability_dataset.warnings,
        adapter_version=capability_dataset.adapter_version,
    )


@router.get("", response_model=list[DatasetResponse])
def list_datasets(
    tenant: TenantContext = Depends(get_tenant_context),
    service: DatasetImportService = Depends(get_dataset_import_service),
) -> list[DatasetResponse]:
    try:
        datasets = service.list(tenant)
        logger.info(f"List datasets: found {len(datasets)} datasets for tenant {tenant.company_id}")
        return [dataset_response(dataset) for dataset in datasets]
    except Exception as exc:
        logger.exception(f"Error listing datasets: {exc}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.delete("/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dataset(
    dataset_id: UUID,
    tenant: TenantContext = Depends(get_tenant_context),
    service: DatasetImportService = Depends(get_dataset_import_service),
) -> Response:
    """Supprime un fichier/dataset du tenant courant et ses artefacts locaux."""

    try:
        service.delete(tenant, dataset_id)
    except DatasetNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{dataset_id}", response_model=DatasetResponse)
def get_dataset(
    dataset_id: UUID,
    tenant: TenantContext = Depends(get_tenant_context),
    service: DatasetImportService = Depends(get_dataset_import_service),
) -> DatasetResponse:
    try:
        return dataset_response(service.get(tenant, dataset_id))
    except DatasetNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
