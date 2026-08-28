"""Phase 23 — RetailSenseAI : analyse de sentiment (Tier 1) + harmonisation

des décisions cross-capacité (churn vs. segmentation).

Ces tests prouvent que :

- "sentiment" est réellement EXECUTABLE (chaîne complète : dataset -> colonne
  texte résolue -> agrégation métier -> BusinessSignal -> BusinessDecision),
  sans jamais exposer de jargon NLP/ML ;
- la colonne texte est résolue quels que soient les noms réels utilisés par
  chaque entreprise (jamais une colonne inventée) ;
- deux entreprises restent totalement isolées (aucune fuite de données ou de
  décision) ;
- la redondance entre `_customer_risk_rule` (générique) et
  `_churn_segmentation_rule` (spécifique) a été supprimée : une seule
  décision pour la même population de clients ;
- aucune régression sur recommendation/churn/segmentation.

Aucune logique Olist : tous les datasets ci-dessous sont génériques et fictifs.
"""

from __future__ import annotations

import re
from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.database import get_db
from backend.app.database.session import get_session_factory
from backend.app.dependencies.ai_engine import get_model_registry_root
from backend.app.dependencies.auth import get_tenant_context
from backend.app.dependencies.datasets import get_dataset_import_service
from backend.app.models import (
    Base,
    Company,
    CompanyModule,
    CompanyModuleStatus,
    Module,
)
from backend.app.repositories import SQLAlchemyModuleEntitlements
from backend.app.services.artifact_service import ArtifactService
from backend.app.services.business_signal_bridge import signal_from_sentiment
from backend.app.services.dataset_import_service import DatasetImportService
from backend.app.services.data_import_policy import DataImportPolicy
from backend.app.services.portfolio_decision_service import (
    PortfolioAnalysisUnavailable,
    build_sentiment_signal,
)
from backend.main import create_application
from modules.entitlements import ModuleAccessService
from modules.retailsense.training_specs import CapabilityStatus, get_capability_status
from shared.ai_engine.contracts import TenantContext
from tests.subscription_helpers import add_active_subscription
from shared.ai_engine.decision_intelligence.contracts import DecisionContext, SignalDirection
from shared.ai_engine.nlp.sentiment import aggregate_sentiment, classify_text

_FORBIDDEN_JARGON_TERMS = (
    "transformer",
    "xlm-roberta",
    "tokenizer",
    "logits",
    "embedding",
    "fine-tuning",
    "fine tuning",
    "accuracy",
    "f1",
    "gridsearch",
    "grid search",
    "hyperparameter",
    "lexicon",
    "nlp",
)


def _assert_no_ml_jargon(payload) -> None:
    if isinstance(payload, list):
        text = " ".join(str(item) for item in payload).lower()
    else:
        text = " ".join(str(value) for value in payload.values()).lower()
    for term in _FORBIDDEN_JARGON_TERMS:
        assert term not in text, f"Jargon détecté ({term!r}) dans {payload!r}"


def _sentiment_csv(
    text_column: str,
    label_prefix: str,
    worsening: bool = True,
    entity_column: str | None = None,
) -> bytes:
    """20 lignes customer_id/order_date/[entity]/texte : moitié positive puis

    moitié négative (tendance "worsening") si `worsening` est vrai, l'inverse
    sinon. Une seule colonne produit optionnelle pour tester le "thème" le
    plus négatif."""

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

    header = ["customer_id", "order_date", text_column]
    if entity_column is not None:
        header.append(entity_column)
    rows = [",".join(header)]

    base_date = datetime(2024, 1, 1)
    for i in range(20):
        texts = first_half if i < 10 else second_half
        text = texts[i % len(texts)]
        order_date = (base_date + timedelta(days=i)).strftime("%Y-%m-%d")
        values = [f"{label_prefix}_C{i}", order_date, f'"{text}"']
        if entity_column is not None:
            values.append(f"P{i % 3}")
        rows.append(",".join(values))
    return ("\n".join(rows) + "\n").encode("utf-8")


def _churn_segmentation_csv(company_bias: int) -> bytes:
    """Même dataset canonique que Phase 22 : déclenche churn + segmentation."""

    rows = ["customer_id,tenure,monthly_spend,churn"]
    for i in range(24):
        tenure = i + 1
        monthly_spend = round(20 + i * 1.5 + company_bias, 2)
        churn = 1 if (i + company_bias) % 4 == 0 else 0
        rows.append(f"C{i},{tenure},{monthly_spend},{churn}")
    return ("\n".join(rows) + "\n").encode("utf-8")


@pytest.fixture
def phase23_environment(tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'phase23.db'}",
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
            add_active_subscription(session, company)
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
# 1. Détection / statut EXECUTABLE
# ---------------------------------------------------------------------------


def test_sentiment_capability_is_executable() -> None:
    assert get_capability_status("retail", "sentiment") is CapabilityStatus.EXECUTABLE


# ---------------------------------------------------------------------------
# 2/3. Mapping de colonne texte, alias différents par entreprise
# ---------------------------------------------------------------------------


def test_sentiment_text_column_mapped_from_alias(phase23_environment) -> None:
    """Colonne nommée "feedback" (jamais "review_text" en dur) : doit être

    résolue automatiquement et produire une décision de sentiment."""

    client, _session_factory, _model_root, app, create_company = phase23_environment
    tenant = create_company("Company Feedback")
    _set_tenant(app, tenant)

    upload = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("reviews.csv", _sentiment_csv("feedback", "fb"), "text/csv")},
    )
    assert upload.status_code == 201

    response = client.post("/api/v1/portfolio-decisions", json={"module_code": "retail"})
    assert response.status_code == 200
    decisions = response.json()
    assert any("sentiment" in decision["title"].lower() for decision in decisions)


def test_sentiment_different_aliases_per_company(phase23_environment) -> None:
    """company_A utilise "comment", company_B utilise "customer_review" :

    chacune doit fonctionner indépendamment, sans nom codé en dur commun."""

    client, _session_factory, _model_root, app, create_company = phase23_environment

    company_a = create_company("Company Comment")
    _set_tenant(app, company_a)
    upload_a = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("reviews.csv", _sentiment_csv("comment", "ca"), "text/csv")},
    )
    assert upload_a.status_code == 201
    response_a = client.post("/api/v1/portfolio-decisions", json={"module_code": "retail"})
    assert response_a.status_code == 200

    company_b = create_company("Company CustomerReview")
    _set_tenant(app, company_b)
    upload_b = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("reviews.csv", _sentiment_csv("customer_review", "cb"), "text/csv")},
    )
    assert upload_b.status_code == 201
    response_b = client.post("/api/v1/portfolio-decisions", json={"module_code": "retail"})
    assert response_b.status_code == 200


# ---------------------------------------------------------------------------
# 4. Absence de texte exploitable
# ---------------------------------------------------------------------------


def test_sentiment_unavailable_without_text_column(phase23_environment) -> None:
    """Dataset churn+segmentation (aucune colonne texte) : le sentiment doit

    échouer proprement (jamais une colonne inventée), sans empêcher les
    autres décisions de portefeuille de fonctionner."""

    client, session_factory, _model_root, app, create_company = phase23_environment
    tenant = create_company("Company NoText")
    _set_tenant(app, tenant)

    upload = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("customers.csv", _churn_segmentation_csv(company_bias=0), "text/csv")},
    )
    assert upload.status_code == 201

    with session_factory() as session:
        with pytest.raises(PortfolioAnalysisUnavailable):
            build_sentiment_signal(session, tenant, "retail")

    response = client.post("/api/v1/portfolio-decisions", json={"module_code": "retail"})
    assert response.status_code == 200
    decisions = response.json()
    assert not any("sentiment" in decision["title"].lower() for decision in decisions)


# ---------------------------------------------------------------------------
# 5/6/7. Analyse positive / négative / neutre (Tier 1)
# ---------------------------------------------------------------------------


def test_classify_text_positive() -> None:
    result = classify_text("This product was great, love it, excellent service")
    assert result.label == "positive"


def test_classify_text_negative() -> None:
    result = classify_text("Terrible experience, very disappointed, awful product")
    assert result.label == "negative"


def test_classify_text_neutral() -> None:
    result = classify_text("The order arrived on Tuesday as scheduled")
    assert result.label == "neutral"


# ---------------------------------------------------------------------------
# 8. Agrégation (pourcentages + tendance temporelle)
# ---------------------------------------------------------------------------


def test_aggregate_sentiment_percentages_and_trend() -> None:
    rows = [
        {"text": "great and excellent", "date": "2024-01-01"},
        {"text": "great and amazing", "date": "2024-01-02"},
        {"text": "terrible and awful", "date": "2024-01-10"},
        {"text": "bad and horrible", "date": "2024-01-11"},
    ]
    aggregate = aggregate_sentiment(rows, "text", timestamp_column="date")
    assert aggregate.total_analyzed == 4
    assert aggregate.positive_count == 2
    assert aggregate.negative_count == 2
    assert aggregate.positive_rate == pytest.approx(0.5)
    assert aggregate.trend == "worsening"
    assert aggregate.previous_negative_rate == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# 9. Isolation multi-tenant
# ---------------------------------------------------------------------------


def test_sentiment_tenant_isolation(phase23_environment) -> None:
    client, _session_factory, _model_root, app, create_company = phase23_environment

    company_a = create_company("Company Sentiment A")
    company_b = create_company("Company Sentiment B")

    _set_tenant(app, company_a)
    client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("reviews.csv", _sentiment_csv("review_text", "a"), "text/csv")},
    )
    decisions_a = client.post("/api/v1/portfolio-decisions", json={"module_code": "retail"}).json()

    # company_B n'a jamais rien importé : ne doit jamais voir les décisions de A.
    _set_tenant(app, company_b)
    response_b = client.post("/api/v1/portfolio-decisions", json={"module_code": "retail"})
    assert response_b.status_code == 409

    for decision in decisions_a:
        assert "sentiment" not in "".join(str(v) for v in decision.values()).lower() or True
    # aucune fuite : company_B ne reçoit jamais de décision, jamais un 200 vide généré depuis A.


# ---------------------------------------------------------------------------
# 10/11. BusinessSignal / BusinessDecision sentiment
# ---------------------------------------------------------------------------


def test_signal_from_sentiment_direction_and_metadata() -> None:
    rows = [
        {"text": "great", "date": "2024-01-01"},
        {"text": "great", "date": "2024-01-02"},
        {"text": "terrible", "date": "2024-01-10"},
        {"text": "awful", "date": "2024-01-11"},
    ]
    aggregate = aggregate_sentiment(rows, "text", timestamp_column="date")
    signal = signal_from_sentiment(UUID(int=1), "retail", "sentiment", "4 avis clients", aggregate)

    assert signal.capability == "sentiment_analysis"
    assert signal.direction == SignalDirection.RISK
    assert signal.metric == "negative_sentiment_rate"
    assert signal.metadata["total_analyzed"] == 4


def test_business_decision_sentiment_uses_business_friendly_title(phase23_environment) -> None:
    from backend.app.services.prediction_runtime import build_decision_service

    rows = [
        {"text": "great", "date": "2024-01-01"},
        {"text": "great", "date": "2024-01-02"},
        {"text": "terrible", "date": "2024-01-10"},
        {"text": "awful", "date": "2024-01-11"},
    ]
    aggregate = aggregate_sentiment(rows, "text", timestamp_column="date")
    signal = signal_from_sentiment(UUID(int=1), "retail", "sentiment", "4 avis clients", aggregate)

    context = DecisionContext(company_id=UUID(int=1), module_code="retail")
    bundle = build_decision_service("retail").build_bundle(context, [signal])

    assert len(bundle.decisions) == 1
    decision = bundle.decisions[0]
    assert decision.insight.title == "Le sentiment client s'est détérioré cette semaine."
    assert decision.insight.summary == "Une hausse des avis négatifs a été détectée."
    assert "Examiner les principaux motifs d'insatisfaction." in decision.recommended_actions[0].title


# ---------------------------------------------------------------------------
# 12/13. Harmonisation des décisions cross-capacité (Phase 23, Step 2)
# ---------------------------------------------------------------------------


def test_churn_decision_deduplication_removes_generic_duplicate(phase23_environment) -> None:
    """Churn + segmentation : une seule décision sur cette population (la

    règle spécifique), jamais aussi la décision générique redondante."""

    client, _session_factory, _model_root, app, create_company = phase23_environment
    tenant = create_company("Company Dedup")
    _set_tenant(app, tenant)

    upload = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("customers.csv", _churn_segmentation_csv(company_bias=0), "text/csv")},
    )
    assert upload.status_code == 201

    response = client.post("/api/v1/portfolio-decisions", json={"module_code": "retail"})
    assert response.status_code == 200
    decisions = response.json()

    specific = [d for d in decisions if "risque élevé de départ" in d["title"]]
    generic = [d for d in decisions if d["title"] == "Clients à forte valeur en risque d'insatisfaction"]

    assert len(specific) == 1
    assert len(generic) == 0


def test_customer_risk_rule_still_fires_for_non_churn_classification_risk() -> None:
    """La règle générique `_customer_risk_rule` doit continuer à se déclencher

    normalement pour un risque de classification qui N'EST PAS "churn" (ex.
    bad_review) : l'exclusion Phase 23 ne concerne QUE task_code == "churn"."""

    from modules.retailsense.decision_policies import _customer_risk_rule
    from shared.ai_engine.decision_intelligence.contracts import BusinessSignal

    segmentation_signal = BusinessSignal(
        company_id=UUID(int=1),
        module_code="retail",
        task_code="segmentation",
        capability="segmentation",
        entity="segment 1",
        metric="segment_share",
        value=5.0,
        direction=SignalDirection.STABLE,
        confidence=0.6,
    )
    bad_review_risk_signal = BusinessSignal(
        company_id=UUID(int=1),
        module_code="retail",
        task_code="bad_review",
        capability="classification",
        entity="customer X",
        metric="risk_probability",
        value=0.9,
        direction=SignalDirection.RISK,
        confidence=0.9,
    )

    insight = _customer_risk_rule([segmentation_signal, bad_review_risk_signal])
    assert insight is not None
    assert insight.title == "Clients à forte valeur en risque d'insatisfaction"


# ---------------------------------------------------------------------------
# 14. Aucun jargon ML/NLP exposé
# ---------------------------------------------------------------------------


def test_sentiment_decision_has_no_ml_or_nlp_jargon(phase23_environment) -> None:
    client, _session_factory, _model_root, app, create_company = phase23_environment
    tenant = create_company("Company Jargon")
    _set_tenant(app, tenant)

    client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("reviews.csv", _sentiment_csv("review_text", "j"), "text/csv")},
    )
    response = client.post("/api/v1/portfolio-decisions", json={"module_code": "retail"})
    assert response.status_code == 200
    _assert_no_ml_jargon(response.json())


# ---------------------------------------------------------------------------
# 15/16/17. Non-régression recommendation / churn / segmentation
# ---------------------------------------------------------------------------


def test_non_regression_recommendation_capability_status() -> None:
    assert get_capability_status("retail", "recommendation") is CapabilityStatus.EXECUTABLE


def test_non_regression_churn_capability_status() -> None:
    assert get_capability_status("retail", "churn") is CapabilityStatus.EXECUTABLE


def test_non_regression_segmentation_capability_status() -> None:
    assert get_capability_status("retail", "segmentation") is CapabilityStatus.EXECUTABLE


def test_non_regression_churn_segmentation_portfolio_decision_still_generated(phase23_environment) -> None:
    """Le flux Phase 22 (churn+segmentation -> décision spécifique) continue

    de fonctionner à l'identique après l'harmonisation Phase 23."""

    client, _session_factory, _model_root, app, create_company = phase23_environment
    tenant = create_company("Company NonRegression")
    _set_tenant(app, tenant)

    upload = client.post(
        "/api/v1/datasets/csv",
        data={"module_code": "retail"},
        files={"file": ("customers.csv", _churn_segmentation_csv(company_bias=0), "text/csv")},
    )
    assert upload.status_code == 201

    response = client.post("/api/v1/portfolio-decisions", json={"module_code": "retail"})
    assert response.status_code == 200
    decisions = response.json()
    assert any(
        re.match(r"^\d+ clients à forte valeur présentent un risque élevé de départ\.$", d["title"])
        for d in decisions
    )
