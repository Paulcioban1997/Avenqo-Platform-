"""Phase 24 — RetailSenseAI : harmonisation complète de la couche Decision

Intelligence pour "demand", "price", "recommendation" et "segmentation".

Ces tests prouvent que chacune de ces quatre capacités suit désormais la
même chaîne que les capacités déjà intégrées (churn, recommendation Phase 22,
sentiment Phase 23) :

    prédiction réelle -> BusinessSignal -> BusinessInsight -> RecommendedAction
    -> BusinessDecisionService -> /portfolio-decisions

- "demand"/"price" utilisent une direction OPPORTUNITY/RISK/STABLE fondée sur
  une variation relative réelle (jamais un score technique) ;
- "recommendation" produit un message métier dédié (opportunités de vente
  croisée), sans jargon algorithmique ;
- "segmentation" identifie le segment dominant du portefeuille,
  indépendamment de tout risque de départ (contrairement au signal combiné
  churn+segmentation déjà existant) ;
- aucune régression sur sentiment (Phase 23) ni sur "synthetic_data"
  (toujours FUTURE_CAPABILITY) ;
- l'isolation multi-tenant et l'absence de jargon ML sont vérifiées pour les
  quatre nouvelles capacités.

Aucune logique Olist : tous les datasets ci-dessous sont génériques et
fictifs.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.database import get_db
from backend.app.database.session import get_session_factory
from backend.app.dependencies.ai_engine import get_model_registry_root
from backend.app.dependencies.auth import get_tenant_context
from backend.app.dependencies.datasets import get_dataset_import_service
from backend.app.models import Base, Company, CompanyModule, CompanyModuleStatus, Module
from backend.app.repositories import SQLAlchemyModuleEntitlements
from backend.app.services.artifact_service import ArtifactService
from backend.app.services.business_signal_bridge import signal_from_business_trend
from backend.app.services.dataset_import_service import DatasetImportService
from backend.app.services.data_import_policy import DataImportPolicy
from backend.main import create_application
from modules.entitlements import ModuleAccessService
from modules.retailsense.training_specs import CapabilityStatus, get_capability_status
from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.decision_intelligence.action_rules import build_default_action_registry
from shared.ai_engine.decision_intelligence.contracts import (
    BusinessSignal,
    DecisionContext,
    SignalDirection,
)
from shared.ai_engine.decision_intelligence.insight_rules import build_default_insight_registry
from shared.ai_engine.decision_intelligence.service import BusinessDecisionService

_FORBIDDEN_ML_JARGON = (
    "random forest",
    "gradient boosting",
    "gridsearch",
    "grid search",
    "hyperparameter",
    "sklearn",
    "kmeans",
    "clustering",
    "regression",
    "r2_score",
    "rmse",
    "cosine",
    "collaborative filtering",
    "pipeline",
    "model registry",
    "ai engine",
    ".joblib",
)


def _assert_no_ml_jargon(*texts: str) -> None:
    for text in texts:
        lowered = text.lower()
        for term in _FORBIDDEN_ML_JARGON:
            assert term not in lowered, f"jargon ML détecté ({term!r}) dans: {text!r}"


# ---------------------------------------------------------------------------
# Fixtures CSV (génériques, aucune donnée Olist)
# ---------------------------------------------------------------------------


def _demand_growth_price_flat_csv() -> bytes:
    """Quantité en forte hausse (opportunité), prix parfaitement stable."""

    rows = ["customer_id,order_date,product_id,quantity,price"]
    base_date = datetime(2024, 1, 1)
    for i in range(30):
        order_date = (base_date + timedelta(days=i)).strftime("%Y-%m-%d")
        quantity = 5 + i * 4
        rows.append(f"C{i},{order_date},P{i % 5},{quantity},20.0")
    return ("\n".join(rows) + "\n").encode("utf-8")


def _demand_decline_price_growth_csv() -> bytes:
    """Quantité en forte baisse (risque), prix en forte hausse (opportunité)."""

    rows = ["customer_id,order_date,product_id,quantity,price"]
    base_date = datetime(2024, 1, 1)
    for i in range(30):
        order_date = (base_date + timedelta(days=i)).strftime("%Y-%m-%d")
        quantity = 120 - i * 4
        price = round(10 + i * 1.5, 2)
        rows.append(f"C{i},{order_date},P{i % 5},{quantity},{price}")
    return ("\n".join(rows) + "\n").encode("utf-8")


def _segmentation_csv() -> bytes:
    """Colonnes RFM classiques : signal de segmentation uniquement."""

    rows = ["customer_id,recency,frequency,monetary_value"]
    for i in range(40):
        rows.append(f"C{i},{i},{i + 1},{round(50 + i * 2.5, 2)}")
    return ("\n".join(rows) + "\n").encode("utf-8")


def _recommendation_csv(label_prefix: str) -> bytes:
    """20 interactions client/produit avec chevauchement (Phase 22)."""

    customers = {
        "c1": ["p1", "p2", "p3"],
        "c2": ["p1", "p2", "p4"],
        "c3": ["p1", "p3", "p5"],
        "c4": ["p2", "p4", "p5"],
        "c5": ["p3", "p4", "p5"],
        "c_full": ["p1", "p2", "p3", "p4", "p5"],
    }
    rows = ["customer_id,product_id,quantity"]
    for customer, products in customers.items():
        for index, product in enumerate(products):
            rows.append(f"{label_prefix}_{customer},{label_prefix}_{product},{index + 1}")
    return ("\n".join(rows) + "\n").encode("utf-8")


def _all_capabilities_csv() -> bytes:
    """Un seul dataset satisfaisant demand+price+segmentation+recommendation.

    Réutilise le même schéma de chevauchement client/produit que
    `_recommendation_csv`, répété deux fois (40 lignes), en y ajoutant les
    colonnes de tendance (order_date/quantity/price) et RFM
    (recency/frequency/monetary_value).
    """

    customers = {
        "c1": ["p1", "p2", "p3"],
        "c2": ["p1", "p2", "p4"],
        "c3": ["p1", "p3", "p5"],
        "c4": ["p2", "p4", "p5"],
        "c5": ["p3", "p4", "p5"],
        "c_full": ["p1", "p2", "p3", "p4", "p5"],
    }
    rows = ["customer_id,product_id,order_date,quantity,price,recency,frequency,monetary_value"]
    base_date = datetime(2024, 1, 1)
    row_index = 0
    for _ in range(2):
        for customer, products in customers.items():
            for product in products:
                order_date = (base_date + timedelta(days=row_index)).strftime("%Y-%m-%d")
                # Décorrélées (modulos distincts) pour éviter une matrice de
                # caractéristiques quasi colinéaire (convergence ElasticNet).
                quantity = 5 + (row_index * 3) % 37
                price = round(15 + (row_index * 7) % 23 * 1.3, 2)
                recency = (row_index * 5) % 31
                frequency = 1 + (row_index * 11) % 17
                monetary_value = round(50 + (row_index * 13) % 29 * 2.1, 2)
                rows.append(
                    f"{customer},{product},{order_date},{quantity},{price},"
                    f"{recency},{frequency},{monetary_value}"
                )
                row_index += 1
    return ("\n".join(rows) + "\n").encode("utf-8")


def _sentiment_csv() -> bytes:
    """20 avis clients (moitié positive, moitié négative) : sentiment Tier 1."""

    positive = "This product was great, love it"
    negative = "Terrible experience, very disappointed"
    rows = ["customer_id,order_date,review_text"]
    base_date = datetime(2024, 1, 1)
    for i in range(20):
        text = positive if i < 10 else negative
        order_date = (base_date + timedelta(days=i)).strftime("%Y-%m-%d")
        rows.append(f"C{i},{order_date},\"{text}\"")
    return ("\n".join(rows) + "\n").encode("utf-8")


@pytest.fixture
def phase24_environment(tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'phase24.db'}",
        connect_args={"check_same_thread": False},
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)

    def _create_company(name: str) -> TenantContext:
        with session_factory() as session:
            company = Company(
                name=name,
                slug=name.lower().replace(" ", "-") + f"-{uuid4().hex[:6]}",
                email=f"{name.lower().replace(' ', '')}@example.ca",
                country="Canada",
                timezone="America/Toronto",
                industry="Retail",
                subscription_plan="professional",
            )
            module = session.scalar(select(Module).where(Module.code == "retail"))
            if module is None:
                module = Module(name="RetailSenseAI", code="retail", is_active=True)
                session.add(module)
                session.flush()
            session.add(company)
            session.flush()
            session.add(
                CompanyModule(
                    company_id=company.id,
                    module_id=module.id,
                    activated_at=datetime.now(timezone.utc) - timedelta(minutes=1),
                    status=CompanyModuleStatus.ACTIVE,
                )
            )
            session.commit()
            return TenantContext(company.id)

    artifact_root = tmp_path / "artifacts"
    model_root = tmp_path / "models"
    app = create_application()

    def override_db() -> Generator[Session, None, None]:
        with session_factory() as session:
            yield session

    def override_dataset_service() -> Generator[DatasetImportService, None, None]:
        with session_factory() as session:
            yield DatasetImportService(
                session=session,
                artifacts=ArtifactService(artifact_root),
                quota=DataImportPolicy(session),
                max_upload_bytes=1024 * 1024,
            )

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_dataset_import_service] = override_dataset_service
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    app.dependency_overrides[get_model_registry_root] = lambda: model_root

    default_tenant = _create_company("Default Co")
    app.dependency_overrides[get_tenant_context] = lambda: default_tenant

    with TestClient(app) as client:
        yield client, session_factory, model_root, app, _create_company


def _set_tenant(app, tenant: TenantContext) -> None:
    app.dependency_overrides[get_tenant_context] = lambda: tenant


# ---------------------------------------------------------------------------
# 1. Unit — signal_from_business_trend (seuil centralisé OPPORTUNITY/RISK/STABLE)
# ---------------------------------------------------------------------------


def test_signal_from_business_trend_detects_opportunity() -> None:
    signal = signal_from_business_trend(
        uuid4(), "retail", "demand", "30 produits", "demand", value=150.0, previous_value=100.0
    )
    assert signal.direction == SignalDirection.OPPORTUNITY
    # Phase 25 : capability = fonction métier ("demand"), plus "regression".
    assert signal.capability == "demand"


def test_signal_from_business_trend_detects_risk() -> None:
    signal = signal_from_business_trend(
        uuid4(), "retail", "price", "30 produits", "price", value=50.0, previous_value=100.0
    )
    assert signal.direction == SignalDirection.RISK


def test_signal_from_business_trend_detects_stable_for_small_change() -> None:
    signal = signal_from_business_trend(
        uuid4(), "retail", "price", "30 produits", "price", value=102.0, previous_value=100.0
    )
    assert signal.direction == SignalDirection.STABLE


def test_signal_from_business_trend_stable_without_baseline() -> None:
    signal = signal_from_business_trend(
        uuid4(), "retail", "demand", "30 produits", "demand", value=100.0, previous_value=None
    )
    assert signal.direction == SignalDirection.STABLE


# ---------------------------------------------------------------------------
# 2. Unit — insight/action rules (demand/price), sans entraînement réel
# ---------------------------------------------------------------------------


def _regression_signal(task_code: str, direction: SignalDirection, **overrides) -> BusinessSignal:
    defaults = dict(
        company_id=uuid4(),
        module_code="retail",
        task_code=task_code,
        capability=task_code,
        entity="30 produits",
        metric=task_code,
        value=150.0,
        previous_value=100.0,
        direction=direction,
        confidence=0.6,
    )
    defaults.update(overrides)
    return BusinessSignal(**defaults)


def test_demand_insight_wording_for_opportunity() -> None:
    service = BusinessDecisionService()
    signal = _regression_signal("demand", SignalDirection.OPPORTUNITY)
    context = DecisionContext(company_id=signal.company_id, module_code="retail")

    bundle = service.build_bundle(context, [signal])

    decision = bundle.decisions[0]
    assert decision.insight.title == "La demande devrait augmenter sensiblement."
    _assert_no_ml_jargon(decision.insight.title, decision.insight.summary, *decision.insight.reasons)


def test_demand_insight_wording_for_risk() -> None:
    service = BusinessDecisionService()
    signal = _regression_signal("demand", SignalDirection.RISK)
    context = DecisionContext(company_id=signal.company_id, module_code="retail")

    bundle = service.build_bundle(context, [signal])

    decision = bundle.decisions[0]
    assert decision.insight.title == "Une baisse de demande est anticipée."
    action = decision.recommended_actions[0]
    assert action.requires_approval is True
    _assert_no_ml_jargon(action.title, action.description)


def test_demand_insight_wording_for_stable() -> None:
    service = BusinessDecisionService()
    signal = _regression_signal("demand", SignalDirection.STABLE)
    context = DecisionContext(company_id=signal.company_id, module_code="retail")

    bundle = service.build_bundle(context, [signal])

    assert bundle.decisions[0].insight.title == "La demande demeure relativement stable."


def test_price_insight_wording_for_opportunity() -> None:
    service = BusinessDecisionService()
    signal = _regression_signal("price", SignalDirection.OPPORTUNITY)
    context = DecisionContext(company_id=signal.company_id, module_code="retail")

    bundle = service.build_bundle(context, [signal])

    decision = bundle.decisions[0]
    assert decision.insight.title == "Une opportunité d'ajustement de prix a été détectée."
    _assert_no_ml_jargon(decision.insight.title, decision.insight.summary)


def test_price_insight_wording_for_risk() -> None:
    service = BusinessDecisionService()
    signal = _regression_signal("price", SignalDirection.RISK)
    context = DecisionContext(company_id=signal.company_id, module_code="retail")

    bundle = service.build_bundle(context, [signal])

    assert bundle.decisions[0].insight.title == "Le prix observé s'écarte sensiblement de la tendance attendue."


def test_price_insight_wording_for_stable() -> None:
    service = BusinessDecisionService()
    signal = _regression_signal("price", SignalDirection.STABLE)
    context = DecisionContext(company_id=signal.company_id, module_code="retail")

    bundle = service.build_bundle(context, [signal])

    decision = bundle.decisions[0]
    assert decision.insight.title == "Aucun changement significatif de prix n'est actuellement détecté."
    action = decision.recommended_actions[0]
    assert action.title == "Conserver la stratégie de prix actuelle."


# ---------------------------------------------------------------------------
# 3. Unit — insight/action rules (recommendation/segmentation)
# ---------------------------------------------------------------------------


def test_recommendation_insight_wording_for_opportunity() -> None:
    registry = build_default_insight_registry()
    action_registry = build_default_action_registry()
    signal = BusinessSignal(
        company_id=uuid4(),
        module_code="retail",
        task_code="recommendation",
        capability="recommendation",
        entity="12 clients",
        metric="recommended_items_count",
        value=5.0,
        direction=SignalDirection.OPPORTUNITY,
        confidence=0.6,
        metadata={"recommended_items": ("P1", "P2")},
    )

    insight = registry.build(signal)
    action = action_registry.build(insight)

    assert insight.title == "Des opportunités de ventes additionnelles ont été identifiées."
    assert "vente croisée" in action.title.lower()
    _assert_no_ml_jargon(insight.title, insight.summary, action.title, action.description)


def test_recommendation_insight_wording_when_no_opportunity() -> None:
    registry = build_default_insight_registry()
    signal = BusinessSignal(
        company_id=uuid4(),
        module_code="retail",
        task_code="recommendation",
        capability="recommendation",
        entity="0 clients",
        metric="recommended_items_count",
        value=0.0,
        direction=SignalDirection.STABLE,
        confidence=0.5,
    )

    insight = registry.build(signal)

    assert "aucune opportunité" in insight.title.lower()


def test_segmentation_insight_wording_for_segment_share() -> None:
    registry = build_default_insight_registry()
    action_registry = build_default_action_registry()
    signal = BusinessSignal(
        company_id=uuid4(),
        module_code="retail",
        task_code="segmentation",
        capability="segmentation",
        entity="segment 2",
        metric="segment_share",
        value=0.42,
        direction=SignalDirection.STABLE,
        confidence=0.6,
    )

    insight = registry.build(signal)
    action = action_registry.build(insight)

    assert "42 %" in insight.summary
    assert action.title == "Examiner une campagne ciblée pour ce segment de clients."
    _assert_no_ml_jargon(insight.title, insight.summary, action.title, action.description)


def test_segmentation_insight_wording_backward_compatible_for_legacy_metric() -> None:
    """Le signal combiné churn+segmentation (Phase 22, metric différent) doit

    conserver son message générique existant (aucune régression)."""

    registry = build_default_insight_registry()
    signal = BusinessSignal(
        company_id=uuid4(),
        module_code="retail",
        task_code="segmentation",
        capability="segmentation",
        entity="segment 1",
        metric="high_value_at_risk_count",
        value=3.0,
        direction=SignalDirection.STABLE,
        confidence=0.6,
    )

    insight = registry.build(signal)

    assert insight.title == "Segment « segment 1 » identifié"


# ---------------------------------------------------------------------------
# 4. Intégration — /portfolio-decisions (pipeline réel, aucune donnée Olist)
# ---------------------------------------------------------------------------


def test_demand_opportunity_and_price_stable_through_real_pipeline(phase24_environment) -> None:
    client, _session_factory, _model_root, app, create_company = phase24_environment
    tenant = create_company("Company Growth")
    _set_tenant(app, tenant)

    upload = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("orders.csv", _demand_growth_price_flat_csv(), "text/csv")},
    )
    assert upload.status_code == 201

    response = client.post("/api/v1/portfolio-decisions", json={"module_code": "retail"})
    assert response.status_code == 200
    decisions = response.json()
    assert decisions

    titles = [decision["title"] for decision in decisions]
    assert "La demande devrait augmenter sensiblement." in titles
    assert "Aucun changement significatif de prix n'est actuellement détecté." in titles
    for decision in decisions:
        _assert_no_ml_jargon(decision["title"], decision["impact"], decision["recommendation"])


def test_demand_risk_and_price_opportunity_through_real_pipeline(phase24_environment) -> None:
    client, _session_factory, _model_root, app, create_company = phase24_environment
    tenant = create_company("Company Decline")
    _set_tenant(app, tenant)

    upload = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("orders.csv", _demand_decline_price_growth_csv(), "text/csv")},
    )
    assert upload.status_code == 201

    response = client.post("/api/v1/portfolio-decisions", json={"module_code": "retail"})
    assert response.status_code == 200
    titles = [decision["title"] for decision in response.json()]

    assert "Une baisse de demande est anticipée." in titles
    assert "Une opportunité d'ajustement de prix a été détectée." in titles


def test_segmentation_signal_reaches_portfolio_decisions(phase24_environment) -> None:
    client, _session_factory, _model_root, app, create_company = phase24_environment
    tenant = create_company("Company Segments")
    _set_tenant(app, tenant)

    upload = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("customers.csv", _segmentation_csv(), "text/csv")},
    )
    assert upload.status_code == 201

    response = client.post("/api/v1/portfolio-decisions", json={"module_code": "retail"})
    assert response.status_code == 200
    decisions = response.json()
    assert any("segment" in decision["title"].lower() for decision in decisions)
    for decision in decisions:
        _assert_no_ml_jargon(decision["title"], decision["impact"], decision["recommendation"])


def test_recommendation_signal_reaches_portfolio_decisions_with_business_title(phase24_environment) -> None:
    client, _session_factory, _model_root, app, create_company = phase24_environment
    tenant = create_company("Company Recs")
    _set_tenant(app, tenant)

    upload = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("orders.csv", _recommendation_csv("rec"), "text/csv")},
    )
    assert upload.status_code == 201

    response = client.post("/api/v1/portfolio-decisions", json={"module_code": "retail"})
    assert response.status_code == 200
    titles = [decision["title"] for decision in response.json()]
    assert "Des opportunités de ventes additionnelles ont été identifiées." in titles


def test_all_four_new_capabilities_present_in_single_portfolio_decision_call(phase24_environment) -> None:
    """Un seul dataset satisfaisant les quatre capacités Phase 24 simultanément."""

    client, _session_factory, _model_root, app, create_company = phase24_environment
    tenant = create_company("Company All Capabilities")
    _set_tenant(app, tenant)

    upload = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("orders.csv", _all_capabilities_csv(), "text/csv")},
    )
    assert upload.status_code == 201

    response = client.post("/api/v1/portfolio-decisions", json={"module_code": "retail"})
    assert response.status_code == 200
    decisions = response.json()
    assert len(decisions) >= 3
    for decision in decisions:
        assert set(decision.keys()) == {"title", "impact", "recommendation", "priority"}
        _assert_no_ml_jargon(decision["title"], decision["impact"], decision["recommendation"])


def test_no_duplicate_decisions_for_same_business_population(phase24_environment) -> None:
    """Même dataset combiné : aucune décision strictement identique (mêmes

    titre/impact/recommandation) ne doit apparaître deux fois."""

    client, _session_factory, _model_root, app, create_company = phase24_environment
    tenant = create_company("Company No Duplicates")
    _set_tenant(app, tenant)

    client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("orders.csv", _all_capabilities_csv(), "text/csv")},
    )
    response = client.post("/api/v1/portfolio-decisions", json={"module_code": "retail"})
    decisions = response.json()

    seen = set()
    for decision in decisions:
        key = (decision["title"], decision["impact"], decision["recommendation"])
        assert key not in seen, f"decision dupliquee: {key}"
        seen.add(key)


def test_tenant_isolation_across_new_capabilities(phase24_environment) -> None:
    """Company A (croissance) et Company B (baisse) restent totalement

    isolées : aucune décision/entité de l'une n'apparaît chez l'autre."""

    client, _session_factory, _model_root, app, create_company = phase24_environment

    company_a = create_company("Company Isolation A")
    _set_tenant(app, company_a)
    client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("orders.csv", _demand_growth_price_flat_csv(), "text/csv")},
    )
    response_a = client.post("/api/v1/portfolio-decisions", json={"module_code": "retail"})
    titles_a = [decision["title"] for decision in response_a.json()]
    assert "La demande devrait augmenter sensiblement." in titles_a

    company_b = create_company("Company Isolation B")
    _set_tenant(app, company_b)
    response_b_before_upload = client.post("/api/v1/portfolio-decisions", json={"module_code": "retail"})
    assert response_b_before_upload.status_code == 409

    client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("orders.csv", _demand_decline_price_growth_csv(), "text/csv")},
    )
    response_b = client.post("/api/v1/portfolio-decisions", json={"module_code": "retail"})
    titles_b = [decision["title"] for decision in response_b.json()]

    assert "Une baisse de demande est anticipée." in titles_b
    assert "La demande devrait augmenter sensiblement." not in titles_b


def test_sentiment_phase23_has_no_regression(phase24_environment) -> None:
    """Le sentiment (Phase 23) continue de fonctionner après Phase 24."""

    client, _session_factory, _model_root, app, create_company = phase24_environment
    tenant = create_company("Company Sentiment Check")
    _set_tenant(app, tenant)

    upload = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("reviews.csv", _sentiment_csv(), "text/csv")},
    )
    assert upload.status_code == 201

    response = client.post("/api/v1/portfolio-decisions", json={"module_code": "retail"})
    assert response.status_code == 200
    assert any("sentiment" in decision["title"].lower() for decision in response.json())


# ---------------------------------------------------------------------------
# 5. synthetic_data — aucun changement
# ---------------------------------------------------------------------------


def test_synthetic_data_remains_future_capability() -> None:
    assert get_capability_status("retail", "synthetic_data") is CapabilityStatus.FUTURE_CAPABILITY


def test_all_ten_capabilities_status_snapshot() -> None:
    """Photographie de l'état des 10 capacités après Phase 24 (aucune capacité

    EXECUTABLE ne redevient DETECTED_NOT_EXECUTABLE ou inversement, hors
    changement volontaire)."""

    executable_tasks = (
        "bad_review",
        "price",
        "demand",
        "segmentation",
        "anomaly",
        "weekly_forecast",
        "churn",
        "recommendation",
        "sentiment",
    )
    for task_code in executable_tasks:
        assert get_capability_status("retail", task_code) is CapabilityStatus.EXECUTABLE
    assert get_capability_status("retail", "synthetic_data") is CapabilityStatus.FUTURE_CAPABILITY
