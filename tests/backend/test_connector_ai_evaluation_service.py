from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import pytest

from backend.app.models import (
    Base,
    ConnectorDatasetEvaluation,
    Dataset,
    DatasetEvaluationStatus,
    DatasetStatus,
    DatasetVersion,
    DatasetVersionStatus,
)
from backend.app.services.commerce_sync_service import CommerceSyncService
from backend.app.services.connector_ai_evaluation_service import ConnectorAIEvaluationService
from shared.ai_engine.contracts import TenantContext


class _Dispatcher:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def evaluate_connector_dataset(self, tenant, dataset_id, generation, connection_id):
        self.calls.append((tenant.company_id, connection_id, dataset_id, generation))
        return {
            "decision": "no_action",
            "reason": "policy_threshold_not_met",
            "drift": {"forecast": {"severity": "none"}},
            "ai_job_ids": [],
        }


def _session_factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _evaluation(*, company_id, connection_id, dataset_id, generation, status=DatasetEvaluationStatus.PENDING, lease_expires_at=None):
    return ConnectorDatasetEvaluation(
        company_id=company_id,
        connection_id=connection_id,
        dataset_id=dataset_id,
        dataset_generation=generation,
        changed_records=1,
        status=status,
        due_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        lease_token=uuid4() if status == DatasetEvaluationStatus.CLAIMED else None,
        lease_expires_at=lease_expires_at,
    )


def test_due_evaluations_coalesce_per_source_and_keep_tenants_isolated() -> None:
    factory = _session_factory()
    dispatcher = _Dispatcher()
    company_a, company_b = uuid4(), uuid4()
    connection_a, connection_b = uuid4(), uuid4()
    dataset_a, dataset_b = uuid4(), uuid4()
    with factory() as session:
        session.add_all(
            [
                _evaluation(company_id=company_a, connection_id=connection_a, dataset_id=dataset_a, generation=1),
                _evaluation(company_id=company_a, connection_id=connection_a, dataset_id=dataset_a, generation=2),
                _evaluation(company_id=company_b, connection_id=connection_b, dataset_id=dataset_b, generation=1),
            ]
        )
        session.commit()

    processed = ConnectorAIEvaluationService(factory, dispatcher).run_due()

    assert processed == 2
    assert {(call[0], call[1], call[3]) for call in dispatcher.calls} == {
        (company_a, connection_a, 2),
        (company_b, connection_b, 1),
    }
    with factory() as session:
        rows = session.scalars(
            select(ConnectorDatasetEvaluation).order_by(
                ConnectorDatasetEvaluation.company_id,
                ConnectorDatasetEvaluation.dataset_generation,
            )
        ).all()
    assert sum(row.status == DatasetEvaluationStatus.COMPLETED for row in rows) == 2
    assert sum(row.status == DatasetEvaluationStatus.COALESCED for row in rows) == 1


def test_expired_lease_is_retried_but_active_lease_is_not_reclaimed() -> None:
    factory = _session_factory()
    dispatcher = _Dispatcher()
    company_id = uuid4()
    with factory() as session:
        session.add_all(
            [
                _evaluation(
                    company_id=company_id,
                    connection_id=uuid4(),
                    dataset_id=uuid4(),
                    generation=1,
                    status=DatasetEvaluationStatus.CLAIMED,
                    lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
                ),
                _evaluation(
                    company_id=company_id,
                    connection_id=uuid4(),
                    dataset_id=uuid4(),
                    generation=1,
                    status=DatasetEvaluationStatus.CLAIMED,
                    lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
                ),
            ]
        )
        session.commit()

    service = ConnectorAIEvaluationService(factory, dispatcher)
    assert service.run_due() == 1
    assert len(dispatcher.calls) == 1
    assert service.run_due() == 0


@pytest.mark.parametrize("provider", ["shopify", "woocommerce"])
def test_connector_snapshot_queues_one_evaluation_per_generation(provider) -> None:
    factory = _session_factory()
    company_id, connection_id = uuid4(), uuid4()
    with factory() as session:
        dataset = Dataset(
            company_id=company_id,
            name=f"{provider}-retail.csv",
            type="csv",
            source="snapshot.csv",
            rows_count=1,
            columns_count=1,
            status=DatasetStatus.READY,
        )
        session.add(dataset)
        session.flush()
        session.add(
            DatasetVersion(
                dataset_id=dataset.id,
                version_number=2,
                name=dataset.name,
                status=DatasetVersionStatus.READY,
                is_current=True,
            )
        )
        session.commit()

        ingestion = type(
            "Ingestion",
            (),
            {"upload": lambda self, *args: dataset, "delete_if_exists": lambda *args: None},
        )()
        service = CommerceSyncService(
            session,
            None,
            None,
            ingestion,
            evaluation_debounce_seconds=60,
        )
        service.build_retail_snapshot = lambda *args: b"amount\n1\n"
        connection = type("Connection", (), {"id": connection_id, "provider": provider})()
        tenant = TenantContext(company_id=company_id)

        service._materialize_retail_snapshot(tenant, connection, changed_records=3)
        service._materialize_retail_snapshot(tenant, connection, changed_records=3)

        evaluations = session.scalars(select(ConnectorDatasetEvaluation)).all()
        assert len(evaluations) == 1
        assert evaluations[0].dataset_generation == 2
        assert evaluations[0].changed_records == 3
        assert evaluations[0].connection_id == connection_id
