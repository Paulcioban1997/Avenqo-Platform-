"""Tenant connector catalog, Shopify lifecycle, sync, and webhook routes."""

from __future__ import annotations

from urllib.parse import urlencode
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from backend.app.config.settings import get_settings
from backend.app.connectors.shopify import ShopifyConnectorError
from backend.app.core.permissions import permissions_for
from backend.app.dependencies.auth import CurrentIdentity, get_current_identity, require_permission
from backend.app.dependencies.commerce import (
    get_commerce_connection_service,
    get_commerce_connector_registry,
    get_commerce_sync_runner,
    get_commerce_sync_service,
)
from backend.app.dependencies.subscription import require_active_subscription
from backend.app.models import CommerceConnection, CommerceConnectionStatus
from backend.app.schemas.commerce import (
    CommerceConnectionResponse,
    CommerceSyncAcceptedResponse,
    CommerceWebhookResponse,
    ConnectorCatalogResponse,
    ShopifyAuthorizationRequest,
    ShopifyAuthorizationResponse,
    WooCommerceAuthorizationRequest,
    WooCommerceCallbackPayload,
    WooCommerceManualConnectionRequest,
)
from backend.app.services.commerce_connection_service import (
    CommerceAuthorizationError,
    CommerceConnectionError,
    CommerceConnectionNotFound,
    CommerceConnectionService,
)
from backend.app.services.commerce_sync_runner import CommerceSyncRunner
from backend.app.services.commerce_sync_service import (
    CommerceSyncAlreadyRunning,
    CommerceSyncDataError,
    CommerceSyncService,
)
from backend.app.services.artifact_storage_health import artifact_storage_health
from shared.ai_engine.connectors.commerce import ConnectorCustomerStatus
from shared.ai_engine.connectors.registry import CommerceConnectorRegistry
from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.exceptions import ConnectorNotRegisteredError

router = APIRouter(prefix="/connectors", tags=["connectors"])
manage_connectors = require_permission("data:manage")


def require_connector_read(
    identity: CurrentIdentity = Depends(get_current_identity),
) -> CurrentIdentity:
    if not {"data:read", "data:manage"}.intersection(
        permissions_for(identity.user.role)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission insuffisante",
        )
    return identity


def _tenant(identity: CurrentIdentity) -> TenantContext:
    return TenantContext(company_id=identity.user.company_id)


def _connection_response(connection: CommerceConnection) -> CommerceConnectionResponse:
    dataset_id = (connection.dataset_ids or {}).get("retail")
    try:
        parsed_dataset_id = UUID(str(dataset_id)) if dataset_id else None
    except (TypeError, ValueError):
        parsed_dataset_id = None
    connection_status = (
        "DISCONNECTED"
        if connection.status == CommerceConnectionStatus.DISCONNECTED.value
        else "REAUTH_REQUIRED"
        if connection.status == CommerceConnectionStatus.REAUTH_REQUIRED.value
        else "CONNECTED"
        if getattr(connection, "encrypted_credentials", None)
        else "CONNECTING"
    )
    sync_status = connection.status
    storage_status = artifact_storage_health.status
    if (
        sync_status == CommerceConnectionStatus.READY.value
        and storage_status is not None
        and storage_status.status != "ok"
    ):
        sync_status = "DEGRADED"
    return CommerceConnectionResponse(
        id=connection.id,
        provider=connection.provider,
        external_account_id=connection.external_account_id,
        display_name=connection.display_name,
        status=connection.status,
        connection_status=connection_status,
        sync_status=sync_status,
        capabilities=list(connection.capabilities or []),
        records_processed=connection.records_processed,
        current_entity=connection.current_entity,
        error_category=connection.error_category,
        last_successful_sync=connection.last_successful_sync,
        sync_started_at=connection.sync_started_at,
        dataset_id=parsed_dataset_id,
    )


def _internal_connector_test_allowed(
    identity: CurrentIdentity,
    registry: CommerceConnectorRegistry,
    provider: str,
) -> bool:
    settings = get_settings()
    return (
        settings.environment.lower() in {"sandbox", "staging"}
        and bool(getattr(identity.user, "is_platform_admin", False))
        and registry.definition(provider).customer_status
        == ConnectorCustomerStatus.COMING_SOON
        and registry.is_registered(provider)
    )


def _require_connector_launch_access(
    identity: CurrentIdentity,
    registry: CommerceConnectorRegistry,
    provider: str,
) -> None:
    if (
        registry.definition(provider).customer_status
        == ConnectorCustomerStatus.AVAILABLE
        or _internal_connector_test_allowed(identity, registry, provider)
    ):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Connector is not available",
    )


@router.get("", response_model=list[ConnectorCatalogResponse])
def connector_catalog(
    identity: CurrentIdentity = Depends(require_connector_read),
    __: TenantContext = Depends(require_active_subscription),
    registry: CommerceConnectorRegistry = Depends(get_commerce_connector_registry),
) -> list[ConnectorCatalogResponse]:
    settings = get_settings()
    return [
        ConnectorCatalogResponse(
            provider=item.provider,
            display_name=item.display_name,
            category=item.category.value,
            customer_status=item.customer_status.value,
            auth_method=item.auth_method.value,
            capabilities=sorted(capability.value for capability in item.capabilities),
            description_key=item.description_key,
            icon_key=item.icon_key,
            supported_regions=list(item.supported_regions),
            configuration_requirements=list(item.configuration_requirements),
            documentation_url=item.documentation_url,
            supports_oauth=item.supports_oauth,
            supports_webhooks=item.supports_webhooks,
            supports_incremental_sync=item.supports_incremental_sync,
            external_registration_required=item.external_registration_required,
            callback_urls_required=item.callback_urls_required,
            webhook_urls_required=item.webhook_urls_required,
            scopes_required=list(item.scopes_required),
            review_required=item.review_required,
            sandbox_available=item.sandbox_available,
            markets_supported=list(item.supported_regions),
            priority=item.priority,
            configured=(
                settings.shopify_connector_configured
                if item.provider == "shopify"
                else settings.woocommerce_connector_configured
                if item.provider == "woocommerce"
                else False
            ),
            internal_test_available=_internal_connector_test_allowed(
                identity,
                registry,
                item.provider,
            ),
        )
        for item in registry.catalog()
    ]


@router.get("/connections", response_model=list[CommerceConnectionResponse])
def list_connections(
    identity: CurrentIdentity = Depends(require_connector_read),
    _: TenantContext = Depends(require_active_subscription),
    service: CommerceConnectionService = Depends(get_commerce_connection_service),
) -> list[CommerceConnectionResponse]:
    return [
        _connection_response(item)
        for item in service.list_connections(_tenant(identity))
    ]


@router.get(
    "/connections/{connection_id}",
    response_model=CommerceConnectionResponse,
)
def connection_detail(
    connection_id: UUID,
    identity: CurrentIdentity = Depends(require_connector_read),
    _: TenantContext = Depends(require_active_subscription),
    service: CommerceConnectionService = Depends(get_commerce_connection_service),
) -> CommerceConnectionResponse:
    try:
        return _connection_response(
            service.get_connection(_tenant(identity), connection_id)
        )
    except CommerceConnectionNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/shopify/authorize",
    response_model=ShopifyAuthorizationResponse,
)
def authorize_shopify(
    request: ShopifyAuthorizationRequest,
    identity: CurrentIdentity = Depends(manage_connectors),
    _: TenantContext = Depends(require_active_subscription),
    service: CommerceConnectionService = Depends(get_commerce_connection_service),
    registry: CommerceConnectorRegistry = Depends(get_commerce_connector_registry),
) -> ShopifyAuthorizationResponse:
    _require_connector_launch_access(identity, registry, "shopify")
    try:
        result = service.begin_shopify_oauth(
            _tenant(identity),
            actor_user_id=identity.user.id,
            shop_domain=request.shop_domain,
        )
    except (CommerceConnectionError, ConnectorNotRegisteredError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    return ShopifyAuthorizationResponse(
        authorization_url=result.authorization_url,
        expires_at=result.expires_at,
    )


@router.post(
    "/woocommerce/authorize",
    response_model=ShopifyAuthorizationResponse,
)
def authorize_woocommerce(
    request: WooCommerceAuthorizationRequest,
    identity: CurrentIdentity = Depends(manage_connectors),
    _: TenantContext = Depends(require_active_subscription),
    service: CommerceConnectionService = Depends(get_commerce_connection_service),
    registry: CommerceConnectorRegistry = Depends(get_commerce_connector_registry),
) -> ShopifyAuthorizationResponse:
    _require_connector_launch_access(identity, registry, "woocommerce")
    try:
        result = service.begin_woocommerce_authorization(
            _tenant(identity),
            actor_user_id=identity.user.id,
            store_url=request.store_url,
        )
    except (CommerceConnectionError, ConnectorNotRegisteredError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ShopifyAuthorizationResponse(
        authorization_url=result.authorization_url,
        expires_at=result.expires_at,
    )


async def _finish_woocommerce_setup(
    connection: CommerceConnection,
    *,
    background_tasks: BackgroundTasks,
    service: CommerceConnectionService,
    sync: CommerceSyncService,
    runner: CommerceSyncRunner,
    registry: CommerceConnectorRegistry,
) -> CommerceConnection:
    tenant = TenantContext(company_id=connection.company_id)
    context = await service.sync_context(tenant, connection.id)
    try:
        await registry.get("woocommerce").register_webhooks(context)
        connection = service.mark_setup_complete(tenant, connection.id)
    except Exception:
        connection = service.mark_setup_degraded(
            tenant,
            connection.id,
            error_category="webhook_registration_failed",
        )
    sync.reserve(tenant, connection.id)
    background_tasks.add_task(runner.run_reserved, tenant, connection.id)
    return connection


@router.post(
    "/woocommerce/manual",
    response_model=CommerceConnectionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def connect_woocommerce_manual(
    request: WooCommerceManualConnectionRequest,
    background_tasks: BackgroundTasks,
    identity: CurrentIdentity = Depends(manage_connectors),
    _: TenantContext = Depends(require_active_subscription),
    service: CommerceConnectionService = Depends(get_commerce_connection_service),
    sync: CommerceSyncService = Depends(get_commerce_sync_service),
    runner: CommerceSyncRunner = Depends(get_commerce_sync_runner),
    registry: CommerceConnectorRegistry = Depends(get_commerce_connector_registry),
) -> CommerceConnectionResponse:
    _require_connector_launch_access(identity, registry, "woocommerce")
    try:
        connection = await service.connect_woocommerce_manual(
            _tenant(identity),
            actor_user_id=identity.user.id,
            store_url=request.store_url,
            consumer_key=request.consumer_key.get_secret_value(),
            consumer_secret=request.consumer_secret.get_secret_value(),
        )
        connection = await _finish_woocommerce_setup(
            connection,
            background_tasks=background_tasks,
            service=service,
            sync=sync,
            runner=runner,
            registry=registry,
        )
    except (CommerceAuthorizationError, CommerceConnectionError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ConnectorNotRegisteredError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return _connection_response(connection)


@router.post(
    "/woocommerce/callback",
    response_model=CommerceConnectionResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def woocommerce_callback(
    request: Request,
    payload: WooCommerceCallbackPayload,
    background_tasks: BackgroundTasks,
    service: CommerceConnectionService = Depends(get_commerce_connection_service),
    runner: CommerceSyncRunner = Depends(get_commerce_sync_runner),
) -> CommerceConnectionResponse:
    try:
        connection = await service.complete_woocommerce_authorization(
            raw_state=request.query_params.get("state", ""),
            callback_payload={
                "user_id": payload.user_id,
                "consumer_key": payload.consumer_key.get_secret_value(),
                "consumer_secret": payload.consumer_secret.get_secret_value(),
                "key_permissions": payload.key_permissions,
            },
        )
        background_tasks.add_task(
            runner.initialize_woocommerce,
            TenantContext(company_id=connection.company_id),
            connection.id,
        )
    except (CommerceAuthorizationError, CommerceConnectionError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ConnectorNotRegisteredError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return _connection_response(connection)


@router.get("/shopify/callback", include_in_schema=False)
async def shopify_callback(
    request: Request,
    background_tasks: BackgroundTasks,
    service: CommerceConnectionService = Depends(get_commerce_connection_service),
    sync: CommerceSyncService = Depends(get_commerce_sync_service),
    runner: CommerceSyncRunner = Depends(get_commerce_sync_runner),
    registry: CommerceConnectorRegistry = Depends(get_commerce_connector_registry),
) -> RedirectResponse:
    try:
        connection = await service.complete_shopify_oauth(dict(request.query_params))
        tenant = TenantContext(company_id=connection.company_id)
        context = await service.sync_context(tenant, connection.id)
        try:
            await registry.get("shopify").register_webhooks(context)
        except ShopifyConnectorError as exc:
            service.mark_setup_failed(
                tenant,
                connection.id,
                error_category="webhook_registration_failed",
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Shopify webhook registration failed",
            ) from exc
        service.mark_setup_complete(tenant, connection.id)
        sync.reserve(tenant, connection.id)
        background_tasks.add_task(runner.run_reserved, tenant, connection.id)
    except (CommerceAuthorizationError, CommerceConnectionError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ConnectorNotRegisteredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    query = urlencode({"connector": "shopify", "status": "connected"})
    return RedirectResponse(
        f"{get_settings().frontend_url.rstrip('/')}/connections?{query}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post(
    "/connections/{connection_id}/sync",
    response_model=CommerceSyncAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def synchronize_connection(
    connection_id: UUID,
    background_tasks: BackgroundTasks,
    identity: CurrentIdentity = Depends(manage_connectors),
    _: TenantContext = Depends(require_active_subscription),
    sync: CommerceSyncService = Depends(get_commerce_sync_service),
    runner: CommerceSyncRunner = Depends(get_commerce_sync_runner),
) -> CommerceSyncAcceptedResponse:
    tenant = _tenant(identity)
    try:
        sync.reserve(tenant, connection_id)
    except CommerceConnectionNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except CommerceSyncAlreadyRunning as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except CommerceConnectionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    background_tasks.add_task(runner.run_reserved, tenant, connection_id)
    return CommerceSyncAcceptedResponse(
        connection_id=connection_id,
        status="SYNCING",
    )


@router.post(
    "/connections/{connection_id}/disconnect",
    response_model=CommerceConnectionResponse,
)
async def disconnect_connection(
    connection_id: UUID,
    identity: CurrentIdentity = Depends(manage_connectors),
    _: TenantContext = Depends(require_active_subscription),
    service: CommerceConnectionService = Depends(get_commerce_connection_service),
) -> CommerceConnectionResponse:
    try:
        connection = await service.disconnect(
            _tenant(identity),
            connection_id,
            actor_user_id=identity.user.id,
        )
    except CommerceConnectionNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _connection_response(connection)


@router.post(
    "/shopify/webhook",
    response_model=CommerceWebhookResponse,
    include_in_schema=False,
)
async def shopify_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    sync: CommerceSyncService = Depends(get_commerce_sync_service),
    runner: CommerceSyncRunner = Depends(get_commerce_sync_runner),
) -> CommerceWebhookResponse:
    try:
        acceptance = await sync.accept_shopify_webhook(
            headers=dict(request.headers),
            body=await request.body(),
        )
    except CommerceSyncDataError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Shopify webhook",
        ) from exc
    if acceptance.should_process and acceptance.receipt_id is not None:
        background_tasks.add_task(runner.run_webhook, acceptance.receipt_id)
    return CommerceWebhookResponse(
        accepted=acceptance.connection_id is not None,
        duplicate=acceptance.duplicate,
    )


@router.post(
    "/woocommerce/webhook/{connection_id}",
    response_model=CommerceWebhookResponse,
    include_in_schema=False,
)
async def woocommerce_webhook(
    connection_id: UUID,
    request: Request,
    background_tasks: BackgroundTasks,
    sync: CommerceSyncService = Depends(get_commerce_sync_service),
    runner: CommerceSyncRunner = Depends(get_commerce_sync_runner),
) -> CommerceWebhookResponse:
    try:
        acceptance = await sync.accept_woocommerce_webhook(
            connection_id=connection_id,
            headers=dict(request.headers),
            body=await request.body(),
        )
    except CommerceSyncDataError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid WooCommerce webhook",
        ) from exc
    if acceptance.should_process and acceptance.receipt_id is not None:
        background_tasks.add_task(runner.run_webhook, acceptance.receipt_id)
    return CommerceWebhookResponse(
        accepted=acceptance.connection_id is not None,
        duplicate=acceptance.duplicate,
    )