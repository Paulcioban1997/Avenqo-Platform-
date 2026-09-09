"""FastAPI composition for commerce connectors and background sync."""

from __future__ import annotations

from pathlib import Path

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session, sessionmaker

from backend.app.config.settings import get_settings
from backend.app.connectors.shopify import ShopifyConnector
from backend.app.connectors.woocommerce import WooCommerceConnector
from backend.app.database import get_db
from backend.app.database.session import get_session_factory
from backend.app.dependencies.datasets import get_company_dataset_ingestion_service
from backend.app.dependencies.training import get_training_dispatcher
from backend.app.services.automatic_company_dataset_ingestion_service import (
    AutomaticCompanyDatasetIngestionService,
)
from backend.app.services.commerce_connection_service import CommerceConnectionService
from backend.app.services.commerce_sync_runner import CommerceSyncRunner
from backend.app.services.commerce_sync_service import CommerceSyncService
from backend.app.services.connector_secret_cipher import (
    ConnectorSecretCipher,
    ConnectorSecretError,
)
from backend.app.services.data_import_policy import DataImportPolicy
from backend.app.services.training_dispatcher import TrainingDispatcher
from shared.ai_engine.connectors.registry import CommerceConnectorRegistry
from shared.ai_engine.dataset_ingestion.storage import LocalDatasetStorage


def get_commerce_connector_registry() -> CommerceConnectorRegistry:
    settings = get_settings()
    registry = CommerceConnectorRegistry()
    if settings.shopify_connector_configured:
        registry.register(
            ShopifyConnector(
                client_id=settings.shopify_client_id or "",
                client_secret=settings.shopify_client_secret or "",
                redirect_uri=settings.shopify_redirect_uri or "",
                api_version=settings.shopify_api_version,
                scopes=settings.shopify_scopes,
                webhook_uri=settings.shopify_webhook_uri,
            )
        )
    if settings.woocommerce_connector_configured:
        registry.register(
            WooCommerceConnector(
                callback_uri=settings.woocommerce_callback_uri or "",
                return_uri=(
                    f"{settings.frontend_url.rstrip('/')}/connections"
                    "?connector=woocommerce&status=authorizing"
                ),
                webhook_uri=settings.woocommerce_webhook_uri or "",
                app_name=settings.woocommerce_app_name,
                allow_insecure_localhost=(
                    settings.woocommerce_allow_insecure_localhost
                    and settings.environment.lower() in {"development", "dev", "test"}
                ),
            )
        )
    return registry


def get_connector_secret_cipher() -> ConnectorSecretCipher:
    try:
        return ConnectorSecretCipher(get_settings().connector_encryption_keys)
    except ConnectorSecretError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Connector credential encryption is not configured",
        ) from exc


def get_commerce_connection_service(
    db: Session = Depends(get_db),
    registry: CommerceConnectorRegistry = Depends(get_commerce_connector_registry),
    cipher: ConnectorSecretCipher = Depends(get_connector_secret_cipher),
) -> CommerceConnectionService:
    return CommerceConnectionService(db, registry, cipher)


def get_commerce_sync_service(
    db: Session = Depends(get_db),
    registry: CommerceConnectorRegistry = Depends(get_commerce_connector_registry),
    connections: CommerceConnectionService = Depends(get_commerce_connection_service),
    ingestion=Depends(get_company_dataset_ingestion_service),
) -> CommerceSyncService:
    return CommerceSyncService(db, registry, connections, ingestion)


def get_commerce_sync_runner(
    session_factory: sessionmaker = Depends(get_session_factory),
    registry: CommerceConnectorRegistry = Depends(get_commerce_connector_registry),
    cipher: ConnectorSecretCipher = Depends(get_connector_secret_cipher),
    dispatcher: TrainingDispatcher = Depends(get_training_dispatcher),
) -> CommerceSyncRunner:
    settings = get_settings()

    def service_factory(session: Session) -> CommerceSyncService:
        connections = CommerceConnectionService(session, registry, cipher)
        ingestion = AutomaticCompanyDatasetIngestionService(
            session=session,
            storage=LocalDatasetStorage(
                Path(settings.artifact_root) / "company_datasets"
            ),
            quota=DataImportPolicy(session),
            max_upload_bytes=settings.dataset_max_upload_mb * 1024 * 1024,
            dispatcher=dispatcher,
        )
        return CommerceSyncService(session, registry, connections, ingestion)

    return CommerceSyncRunner(session_factory, service_factory)