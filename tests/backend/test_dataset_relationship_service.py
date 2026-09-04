from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.models import Base, Dataset, DatasetRelationship, DatasetStatus
from backend.app.services.dataset_relationship_service import (
    DatasetRelationshipService,
    discover_relationships,
)
from shared.ai_engine.contracts import TenantContext


def test_discovers_overlapping_canonical_identifier_with_different_names() -> None:
    result = discover_relationships(
        [{"client_ref": "C1"}, {"client_ref": "C2"}, {"client_ref": "C3"}],
        {"client_ref": "customer_id"},
        [{"buyer_code": "C1"}, {"buyer_code": "C2"}, {"buyer_code": "C2"}],
        {"buyer_code": "customer_id"},
    )

    assert len(result) == 1
    assert result[0].canonical_field == "customer_id"
    assert result[0].overlap_ratio == 1.0


def test_does_not_link_non_identifiers_or_low_overlap() -> None:
    non_identifier = discover_relationships(
        [{"amount": 10}, {"amount": 20}], {"amount": "amount"},
        [{"total": 10}, {"total": 20}], {"total": "amount"},
    )
    low_overlap = discover_relationships(
        [{"client": "C1"}, {"client": "C2"}], {"client": "customer_id"},
        [{"buyer": "C9"}, {"buyer": "C10"}], {"buyer": "customer_id"},
    )

    assert non_identifier == ()
    assert low_overlap == ()


def test_persisted_relationship_discovery_is_tenant_scoped() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    tenant = TenantContext(uuid4())
    other_tenant = TenantContext(uuid4())
    left_id = uuid4()
    right_id = uuid4()
    left = Dataset(
        id=left_id,
        company_id=tenant.company_id, name="customers.csv", type="csv", source="left.csv",
        rows_count=3, columns_count=1, status=DatasetStatus.READY,
    )
    right = Dataset(
        id=right_id,
        company_id=tenant.company_id, name="orders.csv", type="csv", source="right.csv",
        rows_count=3, columns_count=1, status=DatasetStatus.READY,
    )
    foreign = Dataset(
        id=uuid4(),
        company_id=other_tenant.company_id, name="foreign.csv", type="csv", source="foreign.csv",
        rows_count=3, columns_count=1, status=DatasetStatus.READY,
    )
    prepared = {
        left.id: SimpleNamespace(
            rows=({"client_ref": "C1"}, {"client_ref": "C2"}, {"client_ref": "C3"}),
            canonical_columns={"client_ref": "customer_id"},
        ),
        right.id: SimpleNamespace(
            rows=({"buyer_code": "C1"}, {"buyer_code": "C2"}, {"buyer_code": "C2"}),
            canonical_columns={"buyer_code": "customer_id"},
        ),
        foreign.id: SimpleNamespace(
            rows=({"foreign_key": "C1"}, {"foreign_key": "C2"}, {"foreign_key": "C3"}),
            canonical_columns={"foreign_key": "customer_id"},
        ),
    }
    ingestion = SimpleNamespace(
        get_prepared_dataset=lambda _tenant, dataset_id: prepared[dataset_id]
    )

    with Session(engine) as session:
        session.add_all([left, right, foreign])
        session.commit()
        DatasetRelationshipService(session).refresh_for_dataset(tenant, right, ingestion)
        relationships = session.scalars(select(DatasetRelationship)).all()

    assert len(relationships) == 1
    assert relationships[0].company_id == tenant.company_id
    assert {relationships[0].left_dataset_id, relationships[0].right_dataset_id} == {
        left_id,
        right_id,
    }


def test_relationship_evidence_resolves_one_identifier_candidate() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    tenant = TenantContext(uuid4())
    candidate = Dataset(
        id=uuid4(), company_id=tenant.company_id, name="orders.csv", type="csv",
        source="candidate.csv", status=DatasetStatus.MAPPING_REQUIRED,
    )
    peer = Dataset(
        id=uuid4(), company_id=tenant.company_id, name="customers.csv", type="csv",
        source="peer.csv", status=DatasetStatus.READY,
    )
    candidate_rows = [
        {"account_ref": "C1", "shipment_ref": "S9"},
        {"account_ref": "C2", "shipment_ref": "S8"},
        {"account_ref": "C3", "shipment_ref": "S7"},
    ]
    prepared = SimpleNamespace(
        rows=({"customer_key": "C1"}, {"customer_key": "C2"}, {"customer_key": "C3"}),
        canonical_columns={"customer_key": "customer_id"},
    )
    ingestion = SimpleNamespace(
        _reload_current_version_rows=lambda _dataset: candidate_rows,
        get_prepared_dataset=lambda _tenant, _dataset_id: prepared,
    )

    with Session(engine) as session:
        session.add_all([candidate, peer])
        session.commit()
        evidence = DatasetRelationshipService(session).resolve_mapping_conflicts(
            tenant,
            candidate,
            [{"canonical_field": "customer_id", "columns": ["account_ref", "shipment_ref"]}],
            ingestion,
        )

    assert len(evidence) == 1
    assert evidence[0].source_column == "account_ref"
    assert evidence[0].peer_dataset_id == peer.id


def test_relationship_evidence_keeps_tied_candidates_unresolved() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    tenant = TenantContext(uuid4())
    candidate = Dataset(
        id=uuid4(), company_id=tenant.company_id, name="orders.csv", type="csv",
        source="candidate.csv", status=DatasetStatus.MAPPING_REQUIRED,
    )
    peer = Dataset(
        id=uuid4(), company_id=tenant.company_id, name="customers.csv", type="csv",
        source="peer.csv", status=DatasetStatus.READY,
    )
    values = [{"first_ref": "C1", "second_ref": "C1"}, {"first_ref": "C2", "second_ref": "C2"}]
    prepared = SimpleNamespace(
        rows=({"customer_key": "C1"}, {"customer_key": "C2"}),
        canonical_columns={"customer_key": "customer_id"},
    )
    ingestion = SimpleNamespace(
        _reload_current_version_rows=lambda _dataset: values,
        get_prepared_dataset=lambda _tenant, _dataset_id: prepared,
    )

    with Session(engine) as session:
        session.add_all([candidate, peer])
        session.commit()
        evidence = DatasetRelationshipService(session).resolve_mapping_conflicts(
            tenant,
            candidate,
            [{"canonical_field": "customer_id", "columns": ["first_ref", "second_ref"]}],
            ingestion,
        )

    assert evidence == ()