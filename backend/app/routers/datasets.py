"""Routes minces d'import et de consultation des datasets."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from starlette.concurrency import run_in_threadpool

from backend.app.dependencies.auth import get_tenant_context
from backend.app.dependencies.datasets import (
    get_capability_execution_gate,
    get_company_dataset_ingestion_service,
    get_dataset_import_service,
)
from backend.app.dependencies.training import get_training_dispatcher
from backend.app.schemas.company_datasets import (
    CapabilityDatasetResponse,
    CapabilityReadinessResponse,
    ColumnMappingSuggestionResponse,
    ColumnProfileResponse,
    CompanyDatasetProfileResponse,
    CompanyDatasetUploadResponse,
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


def dataset_response(dataset) -> DatasetResponse:
    profile = dataset.profile
    quality = dataset.quality_report
    return DatasetResponse(
        id=dataset.id,
        name=dataset.name,
        type=dataset.type,
        module_code=profile.module_code,
        rows_count=dataset.rows_count,
        columns_count=dataset.columns_count,
        numerical_columns=profile.numerical_columns,
        categorical_columns=profile.categorical_columns,
        missing_values=quality.missing_values,
        duplicates=quality.duplicates,
        quality_score=quality.quality_score,
        status=dataset.status,
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
    return [dataset_response(dataset) for dataset in service.list(tenant)]


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