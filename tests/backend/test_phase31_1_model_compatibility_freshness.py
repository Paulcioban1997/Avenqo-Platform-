"""Phase 31.1 — Model input compatibility + freshness safety.

Complète EXACTEMENT les deux lacunes documentées à la fin de la Phase 31
(`docs/ai-predictive-copilot.md`, section "Limites connues") : jusqu'ici
`ModelInputIncompatibleError` était défini mais jamais levé, et aucune
notion de fraîcheur modèle/donnée n'existait. Phase 31 elle-même n'est PAS
retouchée ici — cette suite ne fait que couvrir les deux garanties
supplémentaires ajoutées dans `SklearnPredictionExecutor` et
`PredictiveAITool` (voir `backend/app/services/prediction_compatibility.py`
et `backend/app/services/prediction_freshness.py`).

Aucune valeur n'est jamais inventée pour "faire passer" un modèle : les
champs manquants/incompatibles sont détectés et refusés, jamais complétés
avec une donnée fictive.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.ai.tools.business import predictive_tools
from backend.app.ai.tools.business.predictive_tools import ChurnRiskArgs, GetChurnRiskTool
from backend.app.ai.tools.contracts import ToolExecutionContext
from backend.app.ai.tools.exceptions import ModelInputIncompatibleError, StalePredictionError
from backend.app.config.settings import Settings
from backend.app.models import Base, Company, Dataset, DatasetProfile, ModelRegistry
from backend.app.services.prediction_compatibility import (
    ModelInputIncompatible,
    required_columns_for,
    validate_input_compatibility,
)
from backend.app.services.prediction_freshness import (
    FreshnessPolicy,
    evaluate_freshness,
    policy_from_settings,
    resolve_freshness_inputs,
)
from backend.app.services.sklearn_prediction_executor import SklearnPredictionExecutor
from shared.ai_engine.contracts import ModelArtifact, TenantContext

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def db_session(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'phase31_1.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        yield session


def _company(session, slug: str = "acme") -> Company:
    company = Company(
        name="Acme", slug=slug, email=f"{slug}@example.com", country="CA",
        timezone="America/Toronto", industry="Retail", subscription_plan="demo",
    )
    session.add(company)
    session.flush()
    return company


def _model_registry_row(session, company: Company, *, task_code: str = "churn", created_at: datetime | None = None) -> ModelRegistry:
    row = ModelRegistry(
        company_id=company.id, training_job_id=uuid4(), module_code="retail", task_code=task_code,
        model_name="churn-classifier", model_type="classification", framework="sklearn", version="1",
        storage_path="unused-in-this-test", metric={"accuracy": 0.9}, dataset_rows_count=100, is_active=True,
    )
    session.add(row)
    session.flush()
    if created_at is not None:
        session.query(ModelRegistry).filter(ModelRegistry.id == row.id).update({"created_at": created_at})
        session.flush()
        session.refresh(row)
    return row


def _dataset_row(session, company: Company, *, uploaded_at: datetime | None = None) -> Dataset:
    dataset = Dataset(
        company_id=company.id, name="orders.csv", type="csv", source="upload",
        rows_count=100, columns_count=5,
    )
    session.add(dataset)
    session.flush()
    session.add(DatasetProfile(dataset_id=dataset.id, module_code="retail", schema_json={}, distribution_json={}))
    session.flush()
    if uploaded_at is not None:
        session.query(Dataset).filter(Dataset.id == dataset.id).update({"uploaded_at": uploaded_at})
        session.flush()
        session.refresh(dataset)
    return dataset


def _context(company_id) -> ToolExecutionContext:
    return ToolExecutionContext(
        tenant=TenantContext(company_id=company_id), user_id=uuid4(),
        permissions=frozenset({"ai:use"}), request_id="r1",
    )


def _fitted_pipeline() -> Pipeline:
    """A tiny real sklearn pipeline mirroring `build_preprocessor()`'s shape."""

    preprocessor = ColumnTransformer(
        transformers=[
            ("numerical", StandardScaler(), ["orders_last_30d"]),
            ("categorical", OneHotEncoder(handle_unknown="ignore"), ["region"]),
        ]
    )
    pipeline = Pipeline([("preprocessor", preprocessor), ("model", LogisticRegression())])
    frame = pd.DataFrame({"orders_last_30d": [1, 2, 3, 4], "region": ["east", "west", "east", "west"]})
    labels = np.array([0, 1, 0, 1])
    pipeline.fit(frame, labels)
    return pipeline


def _artifact(tmp_path: Path, pipeline: Pipeline) -> ModelArtifact:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    joblib.dump(pipeline, model_dir / "model.joblib")
    return ModelArtifact(
        tenant=TenantContext(company_id=uuid4()), module_code="retail", task_code="churn",
        version="1", path=model_dir, metrics={},
    )


# ---------------------------------------------------------------------------
# 1. Model input compatibility (`ModelInputIncompatibleError`)
# ---------------------------------------------------------------------------


def test_compatible_features_pass_through_without_error() -> None:
    pipeline = _fitted_pipeline()
    validate_input_compatibility(pipeline, {"orders_last_30d": 5, "region": "east"})  # no raise


def test_missing_required_feature_raises_model_input_incompatible() -> None:
    pipeline = _fitted_pipeline()
    with pytest.raises(ModelInputIncompatible):
        validate_input_compatibility(pipeline, {"orders_last_30d": 5})


def test_incompatible_feature_type_raises_model_input_incompatible() -> None:
    pipeline = _fitted_pipeline()
    with pytest.raises(ModelInputIncompatible):
        validate_input_compatibility(pipeline, {"orders_last_30d": "not-a-number", "region": "east"})


def test_required_columns_reuses_fitted_pipeline_metadata_no_second_registry() -> None:
    pipeline = _fitted_pipeline()
    assert set(required_columns_for(pipeline)) == {"orders_last_30d", "region"}


def test_pipeline_without_preprocessor_step_skips_validation_gracefully() -> None:
    bare_pipeline = Pipeline([("model", LogisticRegression())])
    bare_pipeline.fit([[0], [1], [0], [1]], [0, 1, 0, 1])
    validate_input_compatibility(bare_pipeline, {})  # no metadata to check -> no raise


def test_sklearn_executor_raises_model_input_incompatible_on_real_predict(tmp_path: Path) -> None:
    pipeline = _fitted_pipeline()
    artifact = _artifact(tmp_path, pipeline)
    executor = SklearnPredictionExecutor()

    with pytest.raises(ModelInputIncompatible):
        executor.predict(artifact, {"orders_last_30d": 3})  # missing "region"


def test_sklearn_executor_predicts_normally_with_compatible_features(tmp_path: Path) -> None:
    pipeline = _fitted_pipeline()
    artifact = _artifact(tmp_path, pipeline)
    executor = SklearnPredictionExecutor()

    result = executor.predict(artifact, {"orders_last_30d": 3, "region": "east"})

    assert "result" in result


async def test_tool_translates_model_input_incompatible_into_tool_error(monkeypatch, db_session) -> None:
    company = _company(db_session)

    def _raise(*args, **kwargs):
        raise ModelInputIncompatible("Required fields are missing for this prediction: region.")

    monkeypatch.setattr(predictive_tools, "build_churn_segmentation_signals", _raise)
    tool = GetChurnRiskTool(session=db_session, prediction_service=object())

    with pytest.raises(ModelInputIncompatibleError):
        await tool.run(_context(company.id), ChurnRiskArgs())


async def test_tenant_a_cannot_use_tenant_b_model_metadata(db_session) -> None:
    """Freshness/compatibility resolution is always scoped by `tenant.company_id`."""

    tenant_a = _company(db_session, slug="tenant-a")
    tenant_b = _company(db_session, slug="tenant-b")
    _model_registry_row(db_session, tenant_b)  # only tenant B has a trained model

    model_trained_at, _ = resolve_freshness_inputs(db_session, TenantContext(company_id=tenant_a.id), "retail", "churn")

    assert model_trained_at is None


# ---------------------------------------------------------------------------
# 2. Freshness detection (`FreshnessResult` / `StalePredictionError`)
# ---------------------------------------------------------------------------


def test_fresh_model_within_policy_window() -> None:
    now = datetime.now(timezone.utc)
    trained_at = now - timedelta(days=1)
    result = evaluate_freshness(trained_at, None, FreshnessPolicy(), now=now)
    assert result.status == "fresh"


def test_stale_model_past_stale_threshold() -> None:
    now = datetime.now(timezone.utc)
    trained_at = now - timedelta(days=10)
    result = evaluate_freshness(trained_at, None, FreshnessPolicy(), now=now)
    assert result.status == "stale"


def test_stale_when_dataset_reimported_after_training_even_if_recent() -> None:
    now = datetime.now(timezone.utc)
    trained_at = now - timedelta(hours=1)
    dataset_updated_at = now - timedelta(minutes=1)
    result = evaluate_freshness(trained_at, dataset_updated_at, FreshnessPolicy(), now=now)
    assert result.status == "stale"


def test_expired_model_past_expired_threshold() -> None:
    now = datetime.now(timezone.utc)
    trained_at = now - timedelta(days=60)
    result = evaluate_freshness(trained_at, None, FreshnessPolicy(), now=now)
    assert result.status == "expired"


def test_unknown_freshness_when_no_model_timestamp_available() -> None:
    result = evaluate_freshness(None, None, FreshnessPolicy())
    assert result.status == "unknown"


def test_freshness_result_safe_dict_never_exposes_storage_details() -> None:
    now = datetime.now(timezone.utc)
    result = evaluate_freshness(now - timedelta(days=1), None, FreshnessPolicy(), now=now)
    safe = result.to_safe_dict()
    assert set(safe.keys()) == {"status", "data_as_of", "model_trained_at"}
    assert "storage_path" not in safe and "model_name" not in safe


def test_policy_from_settings_reads_configurable_thresholds() -> None:
    settings = Settings(
        AUTH_JWT_SECRET="x" * 32, ENVIRONMENT="test",
        AI_FRESHNESS_STALE_AFTER_DAYS=1, AI_FRESHNESS_EXPIRED_AFTER_DAYS=2, AI_FRESHNESS_BLOCK_ON_EXPIRED=False,
    )
    policy = policy_from_settings(settings)
    assert policy.stale_after == timedelta(days=1)
    assert policy.expired_after == timedelta(days=2)
    assert policy.block_on_expired is False


async def test_tool_attaches_freshness_metadata_on_success(monkeypatch, db_session) -> None:
    from backend.app.ai.tools.business.predictive_tools import ChurnRiskArgs as Args
    from shared.ai_engine.decision_intelligence.contracts import BusinessSignal, SignalDirection

    company = _company(db_session)
    _model_registry_row(db_session, company, created_at=datetime.now(timezone.utc) - timedelta(hours=1))

    def _fake_signal():
        return BusinessSignal(
            company_id=company.id, module_code="retail", task_code="churn", capability="classification",
            entity="3 clients", metric="at_risk_customers_count", value=3.0,
            direction=SignalDirection.RISK, confidence=0.7, metadata={},
        )

    monkeypatch.setattr(predictive_tools, "build_churn_segmentation_signals", lambda *a, **k: (_fake_signal(), _fake_signal()))
    tool = GetChurnRiskTool(session=db_session, prediction_service=object())

    result = await tool.run(_context(company.id), Args())

    assert result.success is True
    assert result.data["freshness"]["status"] == "fresh"


async def test_expired_prediction_blocked_by_policy_raises_stale_prediction_error(monkeypatch, db_session) -> None:
    company = _company(db_session)
    _model_registry_row(db_session, company, created_at=datetime.now(timezone.utc) - timedelta(days=90))

    def _should_not_be_called(*args, **kwargs):
        raise AssertionError("inference must not run once a model is expired and blocked by policy")

    monkeypatch.setattr(predictive_tools, "build_churn_segmentation_signals", _should_not_be_called)
    tool = GetChurnRiskTool(session=db_session, prediction_service=object())

    with pytest.raises(StalePredictionError):
        await tool.run(_context(company.id), ChurnRiskArgs())


async def test_unknown_freshness_never_blocks_execution(monkeypatch, db_session) -> None:
    """No `ModelRegistry` row at all -> `unknown`, documented safe default, never blocks."""

    from shared.ai_engine.decision_intelligence.contracts import BusinessSignal, SignalDirection

    company = _company(db_session)

    def _fake_signal():
        return BusinessSignal(
            company_id=company.id, module_code="retail", task_code="churn", capability="classification",
            entity="3 clients", metric="at_risk_customers_count", value=3.0,
            direction=SignalDirection.RISK, confidence=0.7, metadata={},
        )

    monkeypatch.setattr(predictive_tools, "build_churn_segmentation_signals", lambda *a, **k: (_fake_signal(), _fake_signal()))
    tool = GetChurnRiskTool(session=db_session, prediction_service=object())

    result = await tool.run(_context(company.id), ChurnRiskArgs())

    assert result.success is True
    assert result.data["freshness"]["status"] == "unknown"


async def test_prediction_summary_tool_skips_freshness_evaluation(db_session) -> None:
    from backend.app.ai.tools.business.predictive_tools import GetPredictionSummaryTool, PredictionSummaryArgs

    company = _company(db_session)
    tool = GetPredictionSummaryTool(session=db_session)

    result = await tool.run(_context(company.id), PredictionSummaryArgs())

    assert result.success is True
    assert "freshness" not in result.data


# ---------------------------------------------------------------------------
# 3. No fake values are ever inserted to satisfy a model
# ---------------------------------------------------------------------------


def test_validate_input_compatibility_never_fills_in_a_default_value() -> None:
    pipeline = _fitted_pipeline()
    features = {"orders_last_30d": 5, "region": "east"}
    original = dict(features)

    validate_input_compatibility(pipeline, features)

    assert features == original  # untouched, nothing injected


# ---------------------------------------------------------------------------
# 4. SSE predictive flow with stale information (reuses Phase 30.1 pipeline)
# ---------------------------------------------------------------------------


async def test_sse_predictive_call_surfaces_stale_freshness_metadata(db_session, monkeypatch) -> None:
    from backend.app.ai.chat.chat_service import ChatService
    from backend.app.ai.chat.conversation_service import ConversationService
    from backend.app.ai.chat.retrieval_service import RetrievalService
    from backend.app.ai.llm.base import LLMProvider
    from backend.app.ai.llm.schemas import LLMGeneration, LLMToolResponse
    from backend.app.ai.tools.business.registry_factory import build_business_tool_registry
    from backend.app.ai.tools.contracts import ToolCall
    from backend.app.ai.tools.executor import ToolExecutor
    from backend.app.core.permissions import permissions_for
    from backend.app.models import User, UserRole
    from shared.ai_engine.decision_intelligence.contracts import BusinessSignal, SignalDirection

    class ScriptedProvider(LLMProvider):
        name = "fake-predictive"
        supports_tool_calling = True

        def __init__(self, tool_name: str, final_content: str) -> None:
            self._tool_name, self._final_content, self._call_count = tool_name, final_content, 0

        async def generate(self, *, system_instruction: str, prompt: str) -> LLMGeneration:
            return LLMGeneration(content=self._final_content, provider=self.name, model="fake-model")

        async def stream(self, *, system_instruction: str, prompt: str):
            yield self._final_content

        async def generate_with_tools(self, *, system_instruction, messages, tools) -> LLMToolResponse:
            self._call_count += 1
            if self._call_count == 1:
                call = ToolCall(id="call-1", name=self._tool_name, arguments={})
                return LLMToolResponse(content=None, tool_calls=(call,), provider=self.name, model="fake-model")
            return LLMToolResponse(content=self._final_content, tool_calls=(), provider=self.name, model="fake-model")

    class _EmptyIngestion:
        def get_prepared_dataset(self, tenant, dataset_id):  # pragma: no cover
            raise AssertionError("predictive tools must not need dataset ingestion directly")

    company = _company(db_session)
    user = User(
        company_id=company.id, first_name="Ana", last_name="Lyst",
        email="analyst@example.com", password_hash="hash", role=UserRole.ANALYST,
    )
    db_session.add(user)
    db_session.flush()

    # Model trained 60 days ago -> stale (past `stale_after`, within `expired_after` default) -
    # not blocked, but freshness must be surfaced to the caller instead of silently hidden.
    _model_registry_row(db_session, company, created_at=datetime.now(timezone.utc) - timedelta(days=10))

    def _fake_signal():
        return BusinessSignal(
            company_id=company.id, module_code="retail", task_code="churn", capability="classification",
            entity="7 clients", metric="at_risk_customers_count", value=7.0,
            direction=SignalDirection.RISK, confidence=0.7, metadata={},
        )

    monkeypatch.setattr(predictive_tools, "build_churn_segmentation_signals", lambda *a, **k: (_fake_signal(), _fake_signal()))

    conversations = ConversationService(db_session)
    retrieval = RetrievalService(db_session)
    provider = ScriptedProvider("get_churn_risk", "7 customers are at risk of churn.")
    registry = build_business_tool_registry(db_session, _EmptyIngestion(), prediction_service=object())
    executor = ToolExecutor(registry)
    service = ChatService(conversations, retrieval, provider, tool_registry=registry, tool_executor=executor)
    conversation = conversations.create(company.id, user.id, "Chat")
    permissions = frozenset(permissions_for(UserRole.ANALYST))

    events = [event async for event in service.stream(
        company.id, user.id, conversation.id, "Which customers are at risk of leaving?",
        permissions=permissions, plan_code="demo", capabilities=frozenset({"churn"}), request_id="req-pred-stale",
    )]

    kinds = [event.kind for event in events]
    assert kinds[-2:] == ["sources", "done"]

    # Never a stack trace / storage path / model id leaked in any status payload.
    status_payloads = [event.payload for event in events if event.kind == "status"]
    for payload in status_payloads:
        assert "storage_path" not in str(payload)
        assert str(company.id) not in str(payload)

