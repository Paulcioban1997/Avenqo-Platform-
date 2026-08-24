"""Phase 25 — RetailSenseAI : Business Opportunity Engine.

Dernier maillon de la couche Decision Intelligence (Phase 20-24) :

    BusinessSignal -> BusinessInsight -> BusinessDecision -> BusinessOpportunity

Ces tests prouvent que :
- `capability` sur `BusinessOpportunity` est toujours une fonction métier
  (jamais "regression"/"classification" brut) ;
- `priority`/`severity` sont réutilisés tels quels depuis la couche Decision
  Intelligence existante (aucun second moteur de scoring) ;
- `confidence` n'est jamais inventée (toujours celle, réelle, de l'insight) ;
- `estimated_impact`/`impact_unit` ne sont JAMAIS des montants financiers
  inventés : uniquement des pourcentages de variation réelle ou des comptages
  de clients réels, `None` sinon ;
- les signaux STABLE seuls ne produisent jamais d'opportunité (pas de bruit) ;
- la déduplication cross-capacité fonctionne (un même signal source ne
  produit jamais deux opportunités) ;
- l'ordre de `rank_decisions()` est réutilisé tel quel (aucun second
  classement concurrent) ;
- `/portfolio-opportunities` respecte l'isolation multi-tenant stricte et
  n'accepte jamais un `company_id` fourni par le client ;
- "synthetic_data" ne peut jamais atteindre le moteur d'opportunités ;
- aucun jargon ML n'apparaît jamais dans les réponses.

Aucune logique Olist : tous les datasets ci-dessous sont génériques et fictifs.
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
from backend.app.services.dataset_import_service import DatasetImportService
from backend.app.services.data_import_policy import DataImportPolicy
from backend.main import create_application
from modules.entitlements import ModuleAccessService
from modules.retailsense.training_specs import CapabilityStatus, get_capability_status
from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.decision_intelligence.contracts import (
    BusinessSignal,
    DecisionContext,
    Severity,
    SignalDirection,
)
from shared.ai_engine.decision_intelligence.opportunity import (
    BusinessOpportunityService,
    OpportunityStatus,
    deduplicate_decisions,
)
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
    "ml_family",
)


def _assert_no_ml_jargon(*texts: str) -> None:
    for text in texts:
        lowered = str(text).lower()
        for term in _FORBIDDEN_ML_JARGON:
            assert term not in lowered, f"jargon ML détecté ({term!r}) dans: {text!r}"


def _signal(
    task_code: str,
    capability: str,
    entity: str,
    metric: str,
    value: float,
    direction: SignalDirection,
    previous_value: float | None = None,
    confidence: float = 0.6,
    metadata: dict | None = None,
) -> BusinessSignal:
    return BusinessSignal(
        company_id=uuid4(),
        module_code="retail",
        task_code=task_code,
        capability=capability,
        entity=entity,
        metric=metric,
        value=value,
        direction=direction,
        confidence=confidence,
        previous_value=previous_value,
        metadata=metadata or {},
    )


def _bundle_for(*signals: BusinessSignal):
    context = DecisionContext(company_id=signals[0].company_id, module_code="retail")
    return BusinessDecisionService().build_bundle(context, signals)


# ---------------------------------------------------------------------------
# 1. Unit — capacité métier / jamais de jargon technique
# ---------------------------------------------------------------------------


def test_opportunity_capability_is_business_named_for_demand_and_price() -> None:
    demand = _signal("demand", "demand", "30 produits", "demand", 150.0, SignalDirection.OPPORTUNITY, previous_value=100.0)
    price = _signal("price", "price", "30 produits", "price", 50.0, SignalDirection.RISK, previous_value=100.0)
    opportunities = BusinessOpportunityService().from_bundle(_bundle_for(demand, price))
    capabilities = {opportunity.capability for opportunity in opportunities}
    assert capabilities == {"demand", "price"}


def test_opportunity_capability_disambiguates_classification_via_task_code() -> None:
    churn = _signal("churn", "classification", "C1", "churn_probability", 0.9, SignalDirection.RISK)
    bad_review = _signal("bad_review", "classification", "C2", "bad_review_probability", 0.9, SignalDirection.RISK)
    opportunities = BusinessOpportunityService().from_bundle(_bundle_for(churn, bad_review))
    capabilities = {opportunity.capability for opportunity in opportunities}
    assert capabilities == {"churn", "bad_review"}


def test_opportunity_capability_weekly_forecast_and_anomaly_labels() -> None:
    forecast = _signal(
        "weekly_forecast", "forecasting", "P1", "demand", 200.0, SignalDirection.UP, previous_value=100.0
    )
    anomaly = _signal("anomaly", "anomaly_detection", "P1", "anomaly_score", 0.9, SignalDirection.ANOMALY)
    opportunities = BusinessOpportunityService().from_bundle(_bundle_for(forecast, anomaly))
    capabilities = {opportunity.capability for opportunity in opportunities}
    assert capabilities == {"weekly_forecast", "anomaly"}


def test_no_ml_jargon_anywhere_in_generated_opportunities() -> None:
    signals = [
        _signal("demand", "demand", "P1", "demand", 150.0, SignalDirection.OPPORTUNITY, previous_value=100.0),
        _signal("churn", "classification", "C1", "churn_probability", 0.9, SignalDirection.RISK),
    ]
    opportunities = BusinessOpportunityService().from_bundle(_bundle_for(*signals))
    for opportunity in opportunities:
        _assert_no_ml_jargon(opportunity.title, opportunity.summary, opportunity.recommended_action, opportunity.capability)


# ---------------------------------------------------------------------------
# 2. Unit — priority / severity / confidence (jamais inventés)
# ---------------------------------------------------------------------------


def test_priority_and_severity_are_reused_from_decision_layer_not_recomputed() -> None:
    demand = _signal("demand", "demand", "P1", "demand", 200.0, SignalDirection.OPPORTUNITY, previous_value=50.0, confidence=0.9)
    bundle = _bundle_for(demand)
    decision = bundle.decisions[0]
    opportunity = BusinessOpportunityService().from_bundle(bundle)[0]
    assert opportunity.priority == decision.priority
    assert opportunity.severity == decision.insight.severity
    assert isinstance(opportunity.priority, Severity)
    assert isinstance(opportunity.severity, Severity)


def test_confidence_is_never_invented_matches_insight_confidence() -> None:
    demand = _signal("demand", "demand", "P1", "demand", 150.0, SignalDirection.OPPORTUNITY, previous_value=100.0, confidence=0.73)
    bundle = _bundle_for(demand)
    opportunity = BusinessOpportunityService().from_bundle(bundle)[0]
    assert opportunity.confidence == bundle.decisions[0].insight.confidence
    assert opportunity.confidence == pytest.approx(0.73)


# ---------------------------------------------------------------------------
# 3. Unit — estimated_impact / impact_unit (CRITIQUE : jamais de montant inventé)
# ---------------------------------------------------------------------------


def test_estimated_impact_is_percent_change_for_demand_and_price() -> None:
    demand = _signal("demand", "demand", "P1", "demand", 150.0, SignalDirection.OPPORTUNITY, previous_value=100.0)
    opportunity = BusinessOpportunityService().from_bundle(_bundle_for(demand))[0]
    assert opportunity.impact_unit == "percent"
    assert opportunity.estimated_impact == pytest.approx(50.0)


def test_estimated_impact_none_without_previous_value_for_demand() -> None:
    demand = _signal("demand", "demand", "P1", "demand", 150.0, SignalDirection.OPPORTUNITY, previous_value=None)
    opportunity = BusinessOpportunityService().from_bundle(_bundle_for(demand))[0]
    assert opportunity.estimated_impact is None
    assert opportunity.impact_unit is None


def test_estimated_impact_never_invented_for_bad_review_or_anomaly() -> None:
    bad_review = _signal("bad_review", "classification", "C1", "bad_review_probability", 0.9, SignalDirection.RISK)
    anomaly = _signal("anomaly", "anomaly_detection", "P1", "anomaly_score", 0.9, SignalDirection.ANOMALY)
    opportunities = BusinessOpportunityService().from_bundle(_bundle_for(bad_review, anomaly))
    for opportunity in opportunities:
        assert opportunity.estimated_impact is None
        assert opportunity.impact_unit is None


def test_estimated_impact_is_customer_count_for_churn_segmentation_combo() -> None:
    from modules.retailsense.decision_policies import register_retail_decision_policies
    from shared.ai_engine.decision_intelligence.action_rules import build_default_action_registry
    from shared.ai_engine.decision_intelligence.cross_capability import CrossCapabilityRuleRegistry
    from shared.ai_engine.decision_intelligence.insight_rules import build_default_insight_registry

    cross_registry = CrossCapabilityRuleRegistry()
    action_registry = build_default_action_registry()
    register_retail_decision_policies(cross_registry, action_registry)
    service = BusinessDecisionService(
        insight_registry=build_default_insight_registry(),
        action_registry=action_registry,
        cross_capability_registry=cross_registry,
    )

    churn = _signal("churn", "classification", "portfolio", "churn_probability", 0.9, SignalDirection.RISK)
    segmentation = _signal(
        "churn", "segmentation", "portfolio", "high_value_at_risk_count", 34.0, SignalDirection.STABLE
    )
    context = DecisionContext(company_id=churn.company_id, module_code="retail")
    bundle = service.build_bundle(context, [churn, segmentation])
    opportunities = BusinessOpportunityService().from_bundle(bundle)

    churn_opportunity = next(o for o in opportunities if o.capability == "churn")
    assert churn_opportunity.estimated_impact == 34.0
    assert churn_opportunity.impact_unit == "customers"


def test_estimated_impact_is_customer_count_for_recommendation_opportunity() -> None:
    recommendation = _signal(
        "recommendation", "recommendation", "portfolio", "cross_sell_opportunity_count", 12.0, SignalDirection.OPPORTUNITY
    )
    opportunity = BusinessOpportunityService().from_bundle(_bundle_for(recommendation))[0]
    assert opportunity.estimated_impact == 12.0
    assert opportunity.impact_unit == "customers"


def test_estimated_impact_none_for_recommendation_without_opportunity_direction() -> None:
    recommendation = _signal(
        "recommendation", "recommendation", "portfolio", "cross_sell_opportunity_count", 0.0, SignalDirection.STABLE
    )
    opportunities = BusinessOpportunityService().from_bundle(_bundle_for(recommendation))
    assert opportunities == ()  # signal STABLE seul -> filtré (voir section 4)


def test_estimated_impact_is_percent_for_sentiment() -> None:
    sentiment = _signal(
        "sentiment",
        "sentiment_analysis",
        "portfolio",
        "negative_rate",
        0.4,
        SignalDirection.RISK,
        metadata={"negative_count": 4, "total_analyzed": 10, "trend": "worsening"},
    )
    opportunity = BusinessOpportunityService().from_bundle(_bundle_for(sentiment))[0]
    assert opportunity.impact_unit == "percent"
    assert opportunity.estimated_impact == pytest.approx(40.0)


def test_estimated_impact_is_percent_for_segmentation_share() -> None:
    segmentation = _signal(
        "segmentation", "segmentation", "segment 1", "segment_share", 0.35, SignalDirection.OPPORTUNITY
    )
    opportunity = BusinessOpportunityService().from_bundle(_bundle_for(segmentation))[0]
    assert opportunity.impact_unit == "percent"
    assert opportunity.estimated_impact == pytest.approx(35.0)


# ---------------------------------------------------------------------------
# 4. Unit — filtrage du bruit (signaux STABLE seuls)
# ---------------------------------------------------------------------------


def test_stable_only_signal_never_becomes_an_opportunity() -> None:
    price = _signal("price", "price", "P1", "price", 101.0, SignalDirection.STABLE, previous_value=100.0)
    opportunities = BusinessOpportunityService().from_bundle(_bundle_for(price))
    assert opportunities == ()


def test_risk_or_opportunity_signal_always_kept() -> None:
    demand = _signal("demand", "demand", "P1", "demand", 150.0, SignalDirection.OPPORTUNITY, previous_value=100.0)
    opportunities = BusinessOpportunityService().from_bundle(_bundle_for(demand))
    assert len(opportunities) == 1


# ---------------------------------------------------------------------------
# 5. Unit — déduplication cross-capacité
# ---------------------------------------------------------------------------


def test_deduplicate_keeps_combo_decision_over_generic_when_sharing_signal() -> None:
    from modules.retailsense.decision_policies import register_retail_decision_policies
    from shared.ai_engine.decision_intelligence.action_rules import build_default_action_registry
    from shared.ai_engine.decision_intelligence.cross_capability import CrossCapabilityRuleRegistry
    from shared.ai_engine.decision_intelligence.insight_rules import build_default_insight_registry

    cross_registry = CrossCapabilityRuleRegistry()
    action_registry = build_default_action_registry()
    register_retail_decision_policies(cross_registry, action_registry)
    service = BusinessDecisionService(
        insight_registry=build_default_insight_registry(),
        action_registry=action_registry,
        cross_capability_registry=cross_registry,
    )

    churn = _signal("churn", "classification", "portfolio", "churn_probability", 0.9, SignalDirection.RISK)
    segmentation = _signal(
        "churn", "segmentation", "portfolio", "high_value_at_risk_count", 34.0, SignalDirection.STABLE
    )
    context = DecisionContext(company_id=churn.company_id, module_code="retail")
    bundle = service.build_bundle(context, [churn, segmentation])

    deduplicated = deduplicate_decisions(bundle.decisions)
    # Le signal "churn" isolé (classification) et la décision combo
    # churn+segmentation partagent le même signal churn -> une seule décision
    # doit être conservée, et ce doit être la combo (plus spécifique).
    matching = [d for d in deduplicated if churn in d.insight.signals]
    assert len(matching) == 1
    assert matching[0].insight.capability.startswith("cross_capability.")


def test_deduplicate_keeps_both_decisions_when_no_shared_signal() -> None:
    demand = _signal("demand", "demand", "P1", "demand", 150.0, SignalDirection.OPPORTUNITY, previous_value=100.0)
    price = _signal("price", "price", "P1", "price", 50.0, SignalDirection.RISK, previous_value=100.0)
    bundle = _bundle_for(demand, price)
    deduplicated = deduplicate_decisions(bundle.decisions)
    assert len(deduplicated) == 2


# ---------------------------------------------------------------------------
# 6. Unit — ranking réutilisé (aucun second moteur)
# ---------------------------------------------------------------------------


def test_ranking_order_is_preserved_from_rank_decisions() -> None:
    high_confidence_risk = _signal(
        "price", "price", "P1", "price", 10.0, SignalDirection.RISK, previous_value=100.0, confidence=0.95
    )
    low_confidence_opportunity = _signal(
        "demand", "demand", "P2", "demand", 105.0, SignalDirection.OPPORTUNITY, previous_value=100.0, confidence=0.3
    )
    bundle = _bundle_for(high_confidence_risk, low_confidence_opportunity)
    opportunities = BusinessOpportunityService().from_bundle(bundle)
    decision_order = [d.insight.title for d in bundle.decisions]
    opportunity_order = [o.title for o in opportunities]
    assert opportunity_order == decision_order


# ---------------------------------------------------------------------------
# 7. Unit — statut / traçabilité
# ---------------------------------------------------------------------------


def test_status_is_always_new_since_no_persistence() -> None:
    demand = _signal("demand", "demand", "P1", "demand", 150.0, SignalDirection.OPPORTUNITY, previous_value=100.0)
    opportunity = BusinessOpportunityService().from_bundle(_bundle_for(demand))[0]
    assert opportunity.status == OpportunityStatus.NEW


def test_opportunity_status_enum_has_expected_members() -> None:
    assert {member.value for member in OpportunityStatus} == {"new", "reviewed", "dismissed", "actioned"}


def test_source_signals_are_deterministic_natural_keys() -> None:
    demand = _signal("demand", "demand", "P1", "demand", 150.0, SignalDirection.OPPORTUNITY, previous_value=100.0)
    opportunity = BusinessOpportunityService().from_bundle(_bundle_for(demand))[0]
    assert opportunity.source_signals == ("demand:demand:P1",)


def test_synthetic_data_is_a_future_capability_never_reaching_the_opportunity_engine() -> None:
    assert get_capability_status("retail", "synthetic_data") == CapabilityStatus.FUTURE_CAPABILITY


# ---------------------------------------------------------------------------
# 8. Intégration — /portfolio-opportunities (pipeline réel, aucune donnée Olist)
# ---------------------------------------------------------------------------


def _demand_growth_price_flat_csv() -> bytes:
    rows = ["customer_id,order_date,product_id,quantity,price"]
    base_date = datetime(2024, 1, 1)
    for i in range(30):
        order_date = (base_date + timedelta(days=i)).strftime("%Y-%m-%d")
        quantity = 5 + i * 4
        rows.append(f"C{i},{order_date},P{i % 5},{quantity},20.0")
    return ("\n".join(rows) + "\n").encode("utf-8")


def _churn_segmentation_csv(company_bias: int) -> bytes:
    rows = ["customer_id,tenure,monthly_spend,churn"]
    for i in range(24):
        tenure = i + 1
        monthly_spend = round(20 + i * 1.5 + company_bias, 2)
        churn = 1 if (i + company_bias) % 4 == 0 else 0
        rows.append(f"C{i},{tenure},{monthly_spend},{churn}")
    return ("\n".join(rows) + "\n").encode("utf-8")


def _recommendation_csv() -> bytes:
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
            rows.append(f"{customer},{product},{index + 1}")
    return ("\n".join(rows) + "\n").encode("utf-8")


def _sentiment_csv(worsening: bool) -> bytes:
    positive_texts = [
        "This product was great, love it",
        "Excellent service, very satisfied",
        "Amazing experience, highly recommend",
        "Perfect and fast delivery",
        "Wonderful, friendly staff",
    ]
    negative_texts = [
        "Terrible experience, very disappointed",
        "Awful product, complete waste",
        "Bad service, delayed delivery",
        "Worst purchase ever, broken on arrival",
        "Poor quality, hated it",
    ]
    first_half = positive_texts if worsening else negative_texts
    second_half = negative_texts if worsening else positive_texts
    rows = ["customer_id,order_date,review_text"]
    base_date = datetime(2024, 1, 1)
    for i in range(20):
        texts = first_half if i < 10 else second_half
        text = texts[i % len(texts)]
        order_date = (base_date + timedelta(days=i)).strftime("%Y-%m-%d")
        rows.append(f"C{i},{order_date},\"{text}\"")
    return ("\n".join(rows) + "\n").encode("utf-8")


@pytest.fixture
def phase25_environment(tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'phase25.db'}",
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


def test_endpoint_demand_opportunity_reaches_response(phase25_environment) -> None:
    client, _session_factory, _model_root, app, create_company = phase25_environment
    tenant = create_company("Company Growth")
    _set_tenant(app, tenant)

    upload = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("orders.csv", _demand_growth_price_flat_csv(), "text/csv")},
    )
    assert upload.status_code == 201

    response = client.post("/api/v1/portfolio-opportunities", json={"module_code": "retail"})
    assert response.status_code == 200
    body = response.json()

    assert body["company_id"] == str(tenant.company_id)
    assert body["opportunity_count"] == len(body["opportunities"])
    titles = [opportunity["title"] for opportunity in body["opportunities"]]
    assert "La demande devrait augmenter sensiblement." in titles
    # Le prix est parfaitement stable dans ce dataset -> jamais une opportunité de bruit.
    assert "Aucun changement significatif de prix n'est actuellement détecté." not in titles
    for opportunity in body["opportunities"]:
        _assert_no_ml_jargon(opportunity["title"], opportunity["summary"], opportunity["recommended_action"])
        assert opportunity["status"] == "new"
        assert opportunity["priority"] in {s.value for s in Severity}
        assert opportunity["severity"] in {s.value for s in Severity}


def test_endpoint_churn_segmentation_opportunity_has_customer_impact(phase25_environment) -> None:
    client, _session_factory, _model_root, app, create_company = phase25_environment
    tenant = create_company("Company Churn")
    _set_tenant(app, tenant)

    upload = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("customers.csv", _churn_segmentation_csv(company_bias=0), "text/csv")},
    )
    assert upload.status_code == 201

    response = client.post("/api/v1/portfolio-opportunities", json={"module_code": "retail"})
    assert response.status_code == 200
    body = response.json()

    churn_opportunities = [o for o in body["opportunities"] if o["capability"] == "churn"]
    assert len(churn_opportunities) == 1
    opportunity = churn_opportunities[0]
    assert opportunity["impact_unit"] == "customers"
    assert opportunity["estimated_impact"] is not None
    assert opportunity["estimated_impact"] > 0
    assert opportunity["priority"] in {"high", "critical"}


def test_endpoint_recommendation_opportunity_present(phase25_environment) -> None:
    client, _session_factory, _model_root, app, create_company = phase25_environment
    tenant = create_company("Company Recommendation")
    _set_tenant(app, tenant)

    upload = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("orders.csv", _recommendation_csv(), "text/csv")},
    )
    assert upload.status_code == 201

    response = client.post("/api/v1/portfolio-opportunities", json={"module_code": "retail"})
    assert response.status_code == 200
    body = response.json()
    assert any(o["capability"] == "recommendation" for o in body["opportunities"])


def test_endpoint_sentiment_opportunity_present(phase25_environment) -> None:
    client, _session_factory, _model_root, app, create_company = phase25_environment
    tenant = create_company("Company Sentiment")
    _set_tenant(app, tenant)

    upload = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("reviews.csv", _sentiment_csv(worsening=True), "text/csv")},
    )
    assert upload.status_code == 201

    response = client.post("/api/v1/portfolio-opportunities", json={"module_code": "retail"})
    assert response.status_code == 200
    body = response.json()
    sentiment_opportunities = [o for o in body["opportunities"] if o["capability"] == "sentiment"]
    assert len(sentiment_opportunities) == 1
    assert sentiment_opportunities[0]["impact_unit"] == "percent"


def test_endpoint_no_signals_returns_conflict(phase25_environment) -> None:
    client, _session_factory, _model_root, app, create_company = phase25_environment
    tenant = create_company("Company Empty")
    _set_tenant(app, tenant)

    response = client.post("/api/v1/portfolio-opportunities", json={"module_code": "retail"})
    assert response.status_code == 409


def test_endpoint_tenant_isolation_between_companies(phase25_environment) -> None:
    client, _session_factory, _model_root, app, create_company = phase25_environment

    company_high_churn = create_company("Company High Churn")
    company_low_churn = create_company("Company Low Churn")

    _set_tenant(app, company_high_churn)
    client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("customers.csv", _churn_segmentation_csv(company_bias=0), "text/csv")},
    )
    high_churn_response = client.post("/api/v1/portfolio-opportunities", json={"module_code": "retail"})
    assert high_churn_response.status_code == 200
    assert high_churn_response.json()["company_id"] == str(company_high_churn.company_id)

    # company_low_churn n'a jamais rien importé : jamais les opportunités de
    # l'autre entreprise, réponse 409 propre.
    _set_tenant(app, company_low_churn)
    low_churn_response = client.post("/api/v1/portfolio-opportunities", json={"module_code": "retail"})
    assert low_churn_response.status_code == 409

    upload = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("customers.csv", _churn_segmentation_csv(company_bias=1), "text/csv")},
    )
    assert upload.status_code == 201
    low_churn_response = client.post("/api/v1/portfolio-opportunities", json={"module_code": "retail"})
    assert low_churn_response.status_code == 200
    assert low_churn_response.json()["company_id"] == str(company_low_churn.company_id)
    assert low_churn_response.json()["company_id"] != high_churn_response.json()["company_id"]


def test_endpoint_never_accepts_client_supplied_company_id(phase25_environment) -> None:
    """Le tenant est toujours résolu côté serveur : un `company_id` fourni

    par le client (même s'il existe dans le payload) est purement et
    simplement ignoré — le schéma de requête ne l'accepte même pas."""

    client, _session_factory, _model_root, app, create_company = phase25_environment
    tenant = create_company("Company Server Enforced")
    _set_tenant(app, tenant)

    client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("orders.csv", _demand_growth_price_flat_csv(), "text/csv")},
    )
    response = client.post(
        "/api/v1/portfolio-opportunities",
        json={"module_code": "retail", "company_id": str(uuid4())},
    )
    assert response.status_code == 200
    assert response.json()["company_id"] == str(tenant.company_id)


def test_endpoint_critical_and_high_counts_are_consistent(phase25_environment) -> None:
    client, _session_factory, _model_root, app, create_company = phase25_environment
    tenant = create_company("Company Counts")
    _set_tenant(app, tenant)

    client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("customers.csv", _churn_segmentation_csv(company_bias=0), "text/csv")},
    )
    response = client.post("/api/v1/portfolio-opportunities", json={"module_code": "retail"})
    body = response.json()

    critical = sum(1 for o in body["opportunities"] if o["priority"] == "critical")
    high = sum(1 for o in body["opportunities"] if o["priority"] == "high")
    assert body["critical_count"] == critical
    assert body["high_count"] == high


def test_endpoint_response_never_exposes_raw_metadata_field(phase25_environment) -> None:
    client, _session_factory, _model_root, app, create_company = phase25_environment
    tenant = create_company("Company No Metadata Leak")
    _set_tenant(app, tenant)

    client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("orders.csv", _demand_growth_price_flat_csv(), "text/csv")},
    )
    response = client.post("/api/v1/portfolio-opportunities", json={"module_code": "retail"})
    body = response.json()
    for opportunity in body["opportunities"]:
        assert "metadata" not in opportunity
        assert set(opportunity.keys()) == {
            "id",
            "capability",
            "title",
            "summary",
            "direction",
            "priority",
            "severity",
            "confidence",
            "estimated_impact",
            "impact_unit",
            "recommended_action",
            "status",
            "created_at",
        }
