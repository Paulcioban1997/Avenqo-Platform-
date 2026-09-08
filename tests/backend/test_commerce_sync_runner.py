from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.models import (
    Base,
    CommerceConnection,
    CommerceConnectionStatus,
    CommerceWebhookReceipt,
    Company,
)
from backend.app.services.commerce_sync_runner import CommerceSyncRunner
from shared.ai_engine.contracts import TenantContext


class _ArrivingWebhookService:
    def __init__(self, session, connection: CommerceConnection) -> None:
        self._session = session
        self._connection = connection
        self.sync_calls = 0

    def reserve(self, tenant, connection_id) -> None:
        assert tenant.company_id == self._connection.company_id
        assert connection_id == self._connection.id

    async def synchronize(self, tenant, connection_id, *, reserved: bool = False) -> None:
        assert reserved is True
        self.sync_calls += 1
        if self.sync_calls <= 2:
            self._session.add(
                CommerceWebhookReceipt(
                    company_id=tenant.company_id,
                    connection_id=connection_id,
                    provider="shopify",
                    webhook_id=f"arrival-{self.sync_calls}",
                    topic="orders/updated",
                    payload_hash=f"hash-{self.sync_calls}",
                )
            )
            self._session.commit()


@pytest.mark.asyncio
async def test_runner_drains_webhooks_arriving_during_multiple_rounds(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'commerce-runner.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        company = Company(
            name="Runner",
            slug="runner",
            email="runner@example.com",
            country="Canada",
            timezone="America/Toronto",
            industry="Retail",
            subscription_plan="professional",
        )
        session.add(company)
        session.flush()
        connection = CommerceConnection(
            company_id=company.id,
            provider="shopify",
            external_account_id="runner.myshopify.com",
            encrypted_credentials="unused-by-test",
            status=CommerceConnectionStatus.READY.value,
            capabilities=["orders"],
        )
        session.add(connection)
        session.flush()
        session.add(
            CommerceWebhookReceipt(
                company_id=company.id,
                connection_id=connection.id,
                provider="shopify",
                webhook_id="initial",
                topic="orders/create",
                payload_hash="initial-hash",
            )
        )
        session.commit()

        service = _ArrivingWebhookService(session, connection)
        runner = CommerceSyncRunner(factory, lambda _: service)
        await runner._drain_pending_webhooks(
            session,
            service,
            TenantContext(company_id=company.id),
            connection.id,
        )

        receipts = session.scalars(
            select(CommerceWebhookReceipt).order_by(CommerceWebhookReceipt.webhook_id)
        ).all()
        assert service.sync_calls == 3
        assert len(receipts) == 3
        assert all(receipt.status == "PROCESSED" for receipt in receipts)
        assert all(receipt.processed_at is not None for receipt in receipts)