"""Background-safe execution for commerce synchronization jobs."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.models import (
    CommerceConnection,
    CommerceConnectionStatus,
    CommerceWebhookReceipt,
)
from backend.app.services.commerce_sync_service import (
    CommerceSyncAlreadyRunning,
    CommerceSyncService,
)
from shared.ai_engine.contracts import TenantContext

logger = logging.getLogger(__name__)


class CommerceSyncRunner:
    """Open an independent session for work executed after the HTTP response."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        service_factory: Callable[[Session], CommerceSyncService],
    ) -> None:
        self._session_factory = session_factory
        self._service_factory = service_factory

    async def run_reserved(
        self,
        tenant: TenantContext,
        connection_id: UUID,
    ) -> None:
        with self._session_factory() as session:
            service = self._service_factory(session)
            try:
                await service.synchronize(tenant, connection_id, reserved=True)
                await self._drain_pending_webhooks(session, service, tenant, connection_id)
            except Exception:
                logger.exception(
                    "Commerce sync job failed company=%s connection=%s",
                    tenant.company_id,
                    connection_id,
                )

    async def run_webhook(self, receipt_id: UUID) -> None:
        with self._session_factory() as session:
            receipt = session.get(CommerceWebhookReceipt, receipt_id)
            if receipt is None or receipt.status == "PROCESSED":
                return
            tenant = TenantContext(company_id=receipt.company_id)
            service = self._service_factory(session)
            try:
                if service.is_active(tenant, receipt.connection_id):
                    return
                if receipt.topic.lower() == "app/uninstalled":
                    self._disconnect_uninstalled(session, receipt)
                    return
                service.reserve(tenant, receipt.connection_id)
                receipt.status = "PROCESSING"
                receipt.error_category = None
                session.commit()
                await service.synchronize(
                    tenant,
                    receipt.connection_id,
                    reserved=True,
                )
                self._mark_receipts_processed(session, [receipt])
                await self._drain_pending_webhooks(
                    session,
                    service,
                    tenant,
                    receipt.connection_id,
                )
            except CommerceSyncAlreadyRunning:
                receipt.status = "RECEIVED"
                session.commit()
            except Exception:
                session.rollback()
                failed = session.get(CommerceWebhookReceipt, receipt_id)
                if failed is not None:
                    failed.status = "ERROR"
                    failed.error_category = "reconciliation_failed"
                    session.commit()
                logger.exception("Commerce webhook reconciliation failed receipt=%s", receipt_id)

    async def _drain_pending_webhooks(
        self,
        session: Session,
        service: CommerceSyncService,
        tenant: TenantContext,
        connection_id: UUID,
    ) -> None:
        while True:
            pending = list(
                session.scalars(
                    select(CommerceWebhookReceipt)
                    .where(
                        CommerceWebhookReceipt.company_id == tenant.company_id,
                        CommerceWebhookReceipt.connection_id == connection_id,
                        CommerceWebhookReceipt.status == "RECEIVED",
                    )
                    .order_by(CommerceWebhookReceipt.created_at)
                ).all()
            )
            if not pending:
                return
            uninstall = next(
                (
                    item
                    for item in pending
                    if item.topic.lower() == "app/uninstalled"
                ),
                None,
            )
            if uninstall is not None:
                self._disconnect_uninstalled(session, uninstall)
                self._mark_receipts_processed(session, pending)
                return
            service.reserve(tenant, connection_id)
            for receipt in pending:
                receipt.status = "PROCESSING"
                receipt.error_category = None
            session.commit()
            try:
                await service.synchronize(tenant, connection_id, reserved=True)
            except Exception:
                session.rollback()
                for receipt_id in (item.id for item in pending):
                    failed = session.get(CommerceWebhookReceipt, receipt_id)
                    if failed is not None:
                        failed.status = "ERROR"
                        failed.error_category = "reconciliation_failed"
                session.commit()
                raise
            self._mark_receipts_processed(session, pending)

    @staticmethod
    def _mark_receipts_processed(
        session: Session,
        receipts: list[CommerceWebhookReceipt],
    ) -> None:
        processed_at = datetime.now(timezone.utc)
        for receipt in receipts:
            receipt.status = "PROCESSED"
            receipt.error_category = None
            receipt.processed_at = processed_at
        session.commit()

    @staticmethod
    def _disconnect_uninstalled(
        session: Session,
        receipt: CommerceWebhookReceipt,
    ) -> None:
        connection = session.scalar(
            select(CommerceConnection).where(
                CommerceConnection.id == receipt.connection_id,
                CommerceConnection.company_id == receipt.company_id,
            )
        )
        if connection is not None:
            connection.encrypted_credentials = None
            connection.status = CommerceConnectionStatus.DISCONNECTED.value
            connection.current_entity = None
            connection.error_category = None
            connection.sync_started_at = None
            connection.disconnected_at = datetime.now(timezone.utc)
            session.commit()
        receipt.status = "PROCESSED"
        receipt.error_category = None
        receipt.processed_at = datetime.now(timezone.utc)
        session.commit()