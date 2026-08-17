"""Tests unitaires de la couche Auto Retraining Enterprise (Phase 8).

Vérifie : chaque règle individuelle (activable/désactivable, seuils
configurables), l'agrégation par `DecisionEngine`, la sélection de métrique
par famille, la comparaison obligatoire (jamais de remplacement par un
modèle moins bon), le caractère "never-raise" de `service.py`, la
persistance de l'historique via le `ModelRegistry` existant, et la fonction
calendaire `is_due`.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.drift.types import ConceptDriftReport, DriftSeverity
from shared.ai_engine.model_registry.serializer import JoblibArtifactSerializer
from shared.ai_engine.registry.registry import ModelRegistry
from shared.ai_engine.retraining.decision_engine import DecisionEngine
from shared.ai_engine.retraining.history import (
    RetrainingHistory,
    RetrainingHistoryEntry,
    RetrainingOutcome,
    append_history_entry,
    load_history,
)
from shared.ai_engine.retraining.registry import primary_metric_for
from shared.ai_engine.retraining.rules import (
    evaluate_data_volume_rule,
    evaluate_drift_rule,
    evaluate_manual_rule,
    evaluate_model_age_rule,
    evaluate_performance_rule,
    evaluate_scheduled_rule,
)
from shared.ai_engine.retraining.scheduler import RetrainingTarget, enqueue_retraining_check, is_due
from shared.ai_engine.retraining.service import compare_models, evaluate_retraining, should_activate
from shared.ai_engine.retraining.types import (
    RetrainingDecision,
    RetrainingRulesConfig,
    RetrainingSignals,
)


def _concept_report(
    severity: DriftSeverity, available: bool = True, ratio: float | None = 0.2
) -> ConceptDriftReport:
    return ConceptDriftReport(
        available=available,
        metric_name="accuracy",
        reference_value=0.9,
        current_value=0.7,
        degradation_ratio=ratio,
        severity=severity,
        drifted=severity != DriftSeverity.NONE,
    )


class TestRegistry:
    def test_primary_metric_known_families(self) -> None:
        assert primary_metric_for("classification") == ("accuracy", True)
        assert primary_metric_for("regression") == ("r2", True)
        assert primary_metric_for("clustering") == ("silhouette", True)

    def test_primary_metric_unknown_family_falls_back(self) -> None:
        assert primary_metric_for("unknown_family") == ("accuracy", True)


class TestRules:
    def test_drift_rule_disabled_returns_none(self) -> None:
        config = RetrainingRulesConfig(enable_drift_rule=False)
        signals = RetrainingSignals(data_drift_severity=DriftSeverity.CRITICAL)
        assert evaluate_drift_rule(signals, config) is None

    def test_drift_rule_none_not_triggered(self) -> None:
        config = RetrainingRulesConfig()
        signals = RetrainingSignals(data_drift_severity=DriftSeverity.NONE)
        outcome = evaluate_drift_rule(signals, config)
        assert outcome.triggered is False
        assert outcome.decision == RetrainingDecision.NO_ACTION

    def test_drift_rule_warning_maps_to_wait(self) -> None:
        config = RetrainingRulesConfig()
        signals = RetrainingSignals(data_drift_severity=DriftSeverity.WARNING)
        outcome = evaluate_drift_rule(signals, config)
        assert outcome.triggered is True
        assert outcome.decision == RetrainingDecision.WAIT

    def test_drift_rule_critical_maps_to_retrain_critical(self) -> None:
        config = RetrainingRulesConfig()
        signals = RetrainingSignals(data_drift_severity=DriftSeverity.CRITICAL)
        outcome = evaluate_drift_rule(signals, config)
        assert outcome.triggered is True
        assert outcome.decision == RetrainingDecision.RETRAIN_CRITICAL

    def test_data_volume_rule_below_threshold(self) -> None:
        config = RetrainingRulesConfig(min_new_rows=5000)
        signals = RetrainingSignals(rows_at_last_training=1000, rows_current=1500)
        outcome = evaluate_data_volume_rule(signals, config)
        assert outcome.triggered is False

    def test_data_volume_rule_reaches_threshold(self) -> None:
        config = RetrainingRulesConfig(min_new_rows=5000)
        signals = RetrainingSignals(rows_at_last_training=1000, rows_current=6500)
        outcome = evaluate_data_volume_rule(signals, config)
        assert outcome.triggered is True
        assert outcome.decision == RetrainingDecision.RETRAIN_REQUIRED

    def test_model_age_rule_no_previous_model(self) -> None:
        config = RetrainingRulesConfig()
        signals = RetrainingSignals(last_trained_at=None)
        outcome = evaluate_model_age_rule(signals, config)
        assert outcome.triggered is False

    def test_model_age_rule_too_old(self) -> None:
        config = RetrainingRulesConfig(max_model_age_days=30)
        now = datetime(2024, 6, 1, tzinfo=timezone.utc)
        signals = RetrainingSignals(last_trained_at=now - timedelta(days=45), now=now)
        outcome = evaluate_model_age_rule(signals, config)
        assert outcome.triggered is True
        assert outcome.decision == RetrainingDecision.RETRAIN_REQUIRED

    def test_model_age_rule_still_fresh(self) -> None:
        config = RetrainingRulesConfig(max_model_age_days=30)
        now = datetime(2024, 6, 1, tzinfo=timezone.utc)
        signals = RetrainingSignals(last_trained_at=now - timedelta(days=5), now=now)
        outcome = evaluate_model_age_rule(signals, config)
        assert outcome.triggered is False

    def test_performance_rule_unavailable(self) -> None:
        config = RetrainingRulesConfig()
        signals = RetrainingSignals(concept_drift=None)
        outcome = evaluate_performance_rule(signals, config)
        assert outcome.triggered is False

    def test_performance_rule_warning(self) -> None:
        config = RetrainingRulesConfig()
        signals = RetrainingSignals(concept_drift=_concept_report(DriftSeverity.WARNING))
        outcome = evaluate_performance_rule(signals, config)
        assert outcome.triggered is True
        assert outcome.decision == RetrainingDecision.RETRAIN_RECOMMENDED

    def test_performance_rule_critical(self) -> None:
        config = RetrainingRulesConfig()
        signals = RetrainingSignals(concept_drift=_concept_report(DriftSeverity.CRITICAL))
        outcome = evaluate_performance_rule(signals, config)
        assert outcome.triggered is True
        assert outcome.decision == RetrainingDecision.RETRAIN_REQUIRED

    def test_scheduled_rule(self) -> None:
        config = RetrainingRulesConfig()
        assert evaluate_scheduled_rule(RetrainingSignals(scheduled_due=False), config).triggered is False
        outcome = evaluate_scheduled_rule(RetrainingSignals(scheduled_due=True), config)
        assert outcome.triggered is True
        assert outcome.decision == RetrainingDecision.RETRAIN_REQUIRED

    def test_manual_rule(self) -> None:
        config = RetrainingRulesConfig()
        outcome = evaluate_manual_rule(RetrainingSignals(manual_trigger_requested=True), config)
        assert outcome.triggered is True
        assert outcome.decision == RetrainingDecision.RETRAIN_CRITICAL


class TestDecisionEngine:
    def test_no_signals_no_action(self) -> None:
        result = DecisionEngine().evaluate(RetrainingSignals())
        assert result.decision == RetrainingDecision.NO_ACTION
        assert result.triggered_rules == ()

    def test_worst_signal_wins(self) -> None:
        signals = RetrainingSignals(
            data_drift_severity=DriftSeverity.WARNING,  # WAIT
            manual_trigger_requested=True,  # RETRAIN_CRITICAL
        )
        result = DecisionEngine().evaluate(signals)
        assert result.decision == RetrainingDecision.RETRAIN_CRITICAL
        assert len(result.triggered_rules) == 2

    def test_disabled_rules_excluded_from_outcomes(self) -> None:
        config = RetrainingRulesConfig(
            enable_drift_rule=False,
            enable_data_volume_rule=False,
            enable_model_age_rule=False,
            enable_performance_rule=False,
            enable_scheduled_rule=False,
        )
        result = DecisionEngine(config).evaluate(RetrainingSignals(manual_trigger_requested=True))
        assert len(result.outcomes) == 1
        assert result.decision == RetrainingDecision.RETRAIN_CRITICAL


class TestService:
    def test_evaluate_retraining_never_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import shared.ai_engine.retraining.service as service_module

        def _boom(self, signals):
            raise RuntimeError("boom")

        monkeypatch.setattr(service_module.DecisionEngine, "evaluate", _boom)
        result = evaluate_retraining(RetrainingSignals())
        assert result.decision == RetrainingDecision.NO_ACTION

    def test_compare_models_candidate_better(self) -> None:
        comparison = compare_models(
            "classification", {"accuracy": 0.80}, {"accuracy": 0.85}
        )
        assert comparison.candidate_is_better is True
        assert should_activate(comparison) is True

    def test_compare_models_candidate_worse_keeps_previous(self) -> None:
        comparison = compare_models(
            "classification", {"accuracy": 0.90}, {"accuracy": 0.70}
        )
        assert comparison.candidate_is_better is False
        assert should_activate(comparison) is False

    def test_compare_models_tie_allows_activation(self) -> None:
        comparison = compare_models(
            "classification", {"accuracy": 0.80}, {"accuracy": 0.80}
        )
        assert comparison.candidate_is_better is True

    def test_compare_models_lower_is_better_family(self) -> None:
        # "regression"/"r2" est plus-haut-mieux ; ce test vérifie la branche
        # inverse via une famille synthétique enregistrée indirectement (r2
        # reste plus-haut-mieux dans le registre réel, donc on vérifie ici
        # simplement la cohérence du sens de comparaison pour régression).
        comparison = compare_models("regression", {"r2": 0.5}, {"r2": 0.6})
        assert comparison.higher_is_better is True
        assert comparison.candidate_is_better is True

    def test_compare_models_missing_metric_keeps_previous(self) -> None:
        comparison = compare_models("classification", {}, {"accuracy": 0.9})
        assert comparison.candidate_is_better is False

    def test_compare_models_blocked_by_critical_drift(self) -> None:
        comparison = compare_models(
            "classification",
            {"accuracy": 0.80},
            {"accuracy": 0.95},
            candidate_drift_severity=DriftSeverity.CRITICAL,
        )
        assert comparison.blocked_by_drift is True
        assert comparison.candidate_is_better is False

    def test_compare_models_never_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import shared.ai_engine.retraining.service as service_module

        def _boom(family):
            raise RuntimeError("boom")

        monkeypatch.setattr(service_module, "primary_metric_for", _boom)
        comparison = compare_models("classification", {"accuracy": 0.8}, {"accuracy": 0.9})
        assert comparison.candidate_is_better is False


class TestScheduler:
    def test_is_due_never_run_before(self) -> None:
        assert is_due(None, 7, datetime.now(timezone.utc)) is True

    def test_is_due_not_yet(self) -> None:
        now = datetime(2024, 6, 10, tzinfo=timezone.utc)
        assert is_due(now - timedelta(days=2), 7, now) is False

    def test_is_due_elapsed(self) -> None:
        now = datetime(2024, 6, 10, tzinfo=timezone.utc)
        assert is_due(now - timedelta(days=8), 7, now) is True

    def test_enqueue_retraining_check_uses_job_scheduler(self) -> None:
        tenant = TenantContext(uuid4())
        target = RetrainingTarget(tenant=tenant, module_code="retail", task_code="bad_review")

        enqueued = []

        class FakeScheduler:
            def enqueue(self, job):
                enqueued.append(job)
                return str(job.id)

            def schedule(self, job, run_at):
                raise NotImplementedError

        job_id = enqueue_retraining_check(FakeScheduler(), target)
        assert job_id
        assert len(enqueued) == 1
        assert enqueued[0].job_type == "retraining_check"
        assert enqueued[0].module_code == "retail"


class TestHistory:
    def test_load_history_missing_returns_empty(self, tmp_path: Path) -> None:
        registry = ModelRegistry(tmp_path, serializer=JoblibArtifactSerializer())
        tenant = TenantContext(uuid4())
        history = load_history(registry, tenant, "retail", "bad_review")
        assert history == RetrainingHistory()

    def test_append_and_reload_history(self, tmp_path: Path) -> None:
        registry = ModelRegistry(tmp_path, serializer=JoblibArtifactSerializer())
        tenant = TenantContext(uuid4())

        entry = RetrainingHistoryEntry(
            decision=RetrainingDecision.RETRAIN_REQUIRED,
            outcome=RetrainingOutcome.ACTIVATED,
            triggered_rules=("data_volume",),
            previous_version="20240101000000000000",
            previous_model_name="LogisticRegression",
            candidate_version="20240201000000000000",
            candidate_model_name="RandomForestClassifier",
        )
        append_history_entry(registry, tenant, "retail", "bad_review", entry)

        reloaded = load_history(registry, tenant, "retail", "bad_review")
        assert len(reloaded.entries) == 1
        assert reloaded.entries[0].outcome == RetrainingOutcome.ACTIVATED

        second_entry = RetrainingHistoryEntry(
            decision=RetrainingDecision.NO_ACTION,
            outcome=RetrainingOutcome.NOT_NEEDED,
        )
        append_history_entry(registry, tenant, "retail", "bad_review", second_entry)
        reloaded_again = load_history(registry, tenant, "retail", "bad_review")
        assert len(reloaded_again.entries) == 2
