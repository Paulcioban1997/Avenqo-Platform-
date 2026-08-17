"""Tests unitaires et d'intégration de la couche Drift Detection (Phase 7).

Vérifie : chaque fonction statistique pure, la classification par variable
(numérique/catégorielle), l'agrégation data drift, la réutilisation du drift
par variable pour prediction drift et target drift, le concept drift (avec/
sans vérités terrain disponibles), l'orchestration complète `DriftDetector`,
la capture de baseline bornée, et la persistance dans le `ModelRegistry`
existant sans modification de celui-ci.
"""

from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal, assert_series_equal

from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.drift import statistics as stats
from shared.ai_engine.drift.concept_drift import detect_concept_drift
from shared.ai_engine.drift.data_drift import detect_data_drift, detect_feature_drift
from shared.ai_engine.drift.drift_detector import DriftDetector
from shared.ai_engine.drift.prediction_drift import detect_prediction_drift
from shared.ai_engine.drift.registry import select_statistical_tests
from shared.ai_engine.drift.serializer import (
    load_baseline,
    load_drift_report,
    save_baseline,
    save_drift_report,
)
from shared.ai_engine.drift.service import capture_reference_baseline, run_drift_check
from shared.ai_engine.drift.thresholds import (
    classify_js,
    classify_metric_degradation,
    classify_p_value,
    classify_psi,
)
from shared.ai_engine.drift.types import DriftSeverity, ReferenceBaseline
from shared.ai_engine.model_registry.serializer import JoblibArtifactSerializer
from shared.ai_engine.preprocessing.tabular import FeatureColumns
from shared.ai_engine.registry.registry import ModelRegistry


def _build_baseline(task_type: str = "classification") -> ReferenceBaseline:
    rng = np.random.RandomState(0)
    features = pd.DataFrame({"age": rng.normal(0, 1, size=200), "segment": ["A"] * 100 + ["B"] * 100})
    predictions = np.where(rng.random(200) > 0.5, "yes", "no")
    target = pd.Series(np.where(rng.random(200) > 0.5, "yes", "no"))
    return ReferenceBaseline(
        model_name="random_forest",
        task_type=task_type,
        features=features,
        predictions=predictions,
        target=target,
        metrics={"accuracy": 0.9},
        numerical_columns=("age",),
        categorical_columns=("segment",),
    )


class TestStatistics:
    def test_ks_detecte_deux_distributions_identiques(self) -> None:
        rng = np.random.RandomState(0)
        sample = rng.normal(0, 1, size=500)
        statistic, p_value = stats.kolmogorov_smirnov(sample, sample.copy())
        assert statistic == pytest.approx(0.0)
        assert p_value == pytest.approx(1.0)

    def test_ks_detecte_un_deplacement_de_distribution(self) -> None:
        rng = np.random.RandomState(0)
        reference = rng.normal(0, 1, size=500)
        current = rng.normal(5, 1, size=500)
        _, p_value = stats.kolmogorov_smirnov(reference, current)
        assert p_value < 0.01

    def test_psi_faible_pour_distributions_similaires(self) -> None:
        rng = np.random.RandomState(0)
        reference = rng.normal(0, 1, size=1000)
        current = rng.normal(0, 1, size=1000)
        assert stats.population_stability_index(reference, current) < 0.1

    def test_psi_eleve_pour_distributions_differentes(self) -> None:
        rng = np.random.RandomState(0)
        reference = rng.normal(0, 1, size=1000)
        current = rng.normal(3, 1, size=1000)
        assert stats.population_stability_index(reference, current) > 0.25

    def test_wasserstein_distance_croit_avec_le_deplacement(self) -> None:
        rng = np.random.RandomState(0)
        reference = rng.normal(0, 1, size=500)
        close = rng.normal(0.1, 1, size=500)
        far = rng.normal(5, 1, size=500)
        assert stats.wasserstein_distance(reference, close) < stats.wasserstein_distance(reference, far)

    def test_category_proportions_categorical_helpers(self) -> None:
        reference = ["A"] * 80 + ["B"] * 20
        current = ["A"] * 80 + ["B"] * 20
        reference_p, current_p = stats.category_proportions(reference, current)
        assert stats.population_stability_index_categorical(reference_p, current_p) == pytest.approx(0.0, abs=1e-6)
        chi_statistic, chi_p_value = stats.chi_square_test(
            (reference_p * 100).round(), (current_p * 100).round()
        )
        assert chi_p_value > 0.9
        assert stats.jensen_shannon_distance(reference_p, current_p) == pytest.approx(0.0, abs=1e-6)
        assert stats.kl_divergence(reference_p, current_p) == pytest.approx(0.0, abs=1e-6)

    def test_category_proportions_detecte_un_changement_fort(self) -> None:
        reference = ["A"] * 90 + ["B"] * 10
        current = ["A"] * 10 + ["B"] * 90
        reference_p, current_p = stats.category_proportions(reference, current)
        assert stats.population_stability_index_categorical(reference_p, current_p) > 0.25
        assert stats.jensen_shannon_distance(reference_p, current_p) > 0.2


class TestThresholds:
    def test_classify_psi(self) -> None:
        assert classify_psi(0.05) == DriftSeverity.NONE
        assert classify_psi(0.15) == DriftSeverity.WARNING
        assert classify_psi(0.30) == DriftSeverity.CRITICAL

    def test_classify_p_value_est_inverse(self) -> None:
        assert classify_p_value(0.5) == DriftSeverity.NONE
        assert classify_p_value(0.03) == DriftSeverity.WARNING
        assert classify_p_value(0.001) == DriftSeverity.CRITICAL

    def test_classify_js(self) -> None:
        assert classify_js(0.05) == DriftSeverity.NONE
        assert classify_js(0.15) == DriftSeverity.WARNING
        assert classify_js(0.25) == DriftSeverity.CRITICAL

    def test_classify_metric_degradation(self) -> None:
        assert classify_metric_degradation(0.0) == DriftSeverity.NONE
        assert classify_metric_degradation(0.10) == DriftSeverity.WARNING
        assert classify_metric_degradation(0.20) == DriftSeverity.CRITICAL


class TestRegistry:
    def test_tests_for_numerical(self) -> None:
        assert select_statistical_tests("numerical") == ("psi", "ks", "wasserstein")

    def test_tests_for_categorical_avec_kl_optionnelle(self) -> None:
        assert select_statistical_tests("categorical") == ("psi", "chi_square", "jensen_shannon")
        assert select_statistical_tests("categorical", include_kl_divergence=True) == (
            "psi",
            "chi_square",
            "jensen_shannon",
            "kl_divergence",
        )
        # KL divergence n'est jamais activée pour le numérique.
        assert select_statistical_tests("numerical", include_kl_divergence=True) == ("psi", "ks", "wasserstein")


class TestDataDrift:
    def test_detect_feature_drift_numerique_stable(self) -> None:
        rng = np.random.RandomState(0)
        reference = pd.Series(rng.normal(0, 1, size=500))
        current = pd.Series(rng.normal(0, 1, size=500))
        result = detect_feature_drift("age", reference, current, is_categorical=False)
        assert result.severity == DriftSeverity.NONE
        assert result.drifted is False
        assert set(result.tests) == {"psi", "ks_statistic", "ks_p_value", "wasserstein_distance"}

    def test_detect_feature_drift_numerique_derive(self) -> None:
        rng = np.random.RandomState(0)
        reference = pd.Series(rng.normal(0, 1, size=500))
        current = pd.Series(rng.normal(6, 1, size=500))
        result = detect_feature_drift("age", reference, current, is_categorical=False)
        assert result.severity == DriftSeverity.CRITICAL
        assert result.drifted is True

    def test_detect_feature_drift_categoriel_stable(self) -> None:
        reference = pd.Series(["A"] * 50 + ["B"] * 50)
        current = pd.Series(["A"] * 48 + ["B"] * 52)
        result = detect_feature_drift("segment", reference, current, is_categorical=True)
        assert result.severity == DriftSeverity.NONE
        assert "jensen_shannon_distance" in result.tests
        assert "kl_divergence" not in result.tests

    def test_detect_feature_drift_categoriel_avec_kl_optionnelle(self) -> None:
        reference = pd.Series(["A"] * 50 + ["B"] * 50)
        current = pd.Series(["A"] * 48 + ["B"] * 52)
        result = detect_feature_drift(
            "segment", reference, current, is_categorical=True, include_kl_divergence=True
        )
        assert "kl_divergence" in result.tests

    def test_detect_feature_drift_categoriel_derive(self) -> None:
        reference = pd.Series(["A"] * 90 + ["B"] * 10)
        current = pd.Series(["A"] * 10 + ["B"] * 90)
        result = detect_feature_drift("segment", reference, current, is_categorical=True)
        assert result.severity == DriftSeverity.CRITICAL
        assert result.drifted is True

    def test_detect_data_drift_agrege_toutes_les_variables(self) -> None:
        rng = np.random.RandomState(0)
        reference = pd.DataFrame(
            {
                "age": rng.normal(0, 1, size=300),
                "segment": ["A"] * 150 + ["B"] * 150,
            }
        )
        current = pd.DataFrame(
            {
                "age": rng.normal(6, 1, size=300),
                "segment": ["A"] * 150 + ["B"] * 150,
            }
        )
        report = detect_data_drift(reference, current, numerical_columns=("age",), categorical_columns=("segment",))
        assert len(report.features) == 2
        assert report.drifted_feature_ratio == pytest.approx(0.5)
        assert report.overall_severity == DriftSeverity.CRITICAL

    def test_detect_data_drift_ignore_colonnes_absentes(self) -> None:
        reference = pd.DataFrame({"age": [1, 2, 3]})
        current = pd.DataFrame({"age": [1, 2, 3]})
        report = detect_data_drift(
            reference, current, numerical_columns=("age", "missing"), categorical_columns=()
        )
        assert len(report.features) == 1


class TestPredictionDrift:
    def test_reutilise_detect_feature_drift_classification(self) -> None:
        reference = np.array(["yes"] * 50 + ["no"] * 50)
        current = np.array(["yes"] * 48 + ["no"] * 52)
        report = detect_prediction_drift(reference, current, "classification")
        assert report.severity == DriftSeverity.NONE
        assert "kl_divergence" in report.tests

    def test_reutilise_detect_feature_drift_regression(self) -> None:
        rng = np.random.RandomState(0)
        reference = rng.normal(0, 1, size=300)
        current = rng.normal(6, 1, size=300)
        report = detect_prediction_drift(reference, current, "regression")
        assert report.severity == DriftSeverity.CRITICAL
        assert "kl_divergence" not in report.tests


class TestConceptDrift:
    def test_non_disponible_sans_metriques_actuelles(self) -> None:
        report = detect_concept_drift({"accuracy": 0.9}, None, "classification")
        assert report.available is False
        assert report.drifted is False
        assert report.degradation_ratio is None

    def test_stable_quand_performance_similaire(self) -> None:
        report = detect_concept_drift({"accuracy": 0.9}, {"accuracy": 0.89}, "classification")
        assert report.available is True
        assert report.severity == DriftSeverity.NONE

    def test_detecte_une_degradation_forte(self) -> None:
        report = detect_concept_drift({"accuracy": 0.9}, {"accuracy": 0.5}, "classification")
        assert report.available is True
        assert report.severity == DriftSeverity.CRITICAL
        assert report.drifted is True

    def test_utilise_r2_en_regression(self) -> None:
        report = detect_concept_drift({"r2": 0.8}, {"r2": 0.79}, "regression")
        assert report.metric_name == "r2"
        assert report.severity == DriftSeverity.NONE


class TestDriftDetector:
    def _baseline(self, task_type: str = "classification") -> ReferenceBaseline:
        return _build_baseline(task_type)

    def test_run_sans_derive_reste_stable(self) -> None:
        baseline = self._baseline()
        rng = np.random.RandomState(1)
        current_features = pd.DataFrame(
            {"age": rng.normal(0, 1, size=200), "segment": ["A"] * 100 + ["B"] * 100}
        )
        current_predictions = np.where(rng.random(200) > 0.5, "yes", "no")
        current_target = pd.Series(np.where(rng.random(200) > 0.5, "yes", "no"))
        report = DriftDetector().run(
            baseline, current_features, current_predictions, current_target, {"accuracy": 0.89}
        )
        assert report.model_name == "random_forest"
        assert report.data_drift is not None
        assert report.prediction_drift is not None
        assert report.target_drift is not None
        assert report.concept_drift.available is True
        assert report.overall_severity == DriftSeverity.NONE

    def test_run_detecte_une_forte_derive(self) -> None:
        baseline = self._baseline()
        rng = np.random.RandomState(1)
        current_features = pd.DataFrame(
            {"age": rng.normal(8, 1, size=200), "segment": ["A"] * 100 + ["B"] * 100}
        )
        report = DriftDetector().run(baseline, current_features, None, None, None)
        assert report.data_drift.overall_severity == DriftSeverity.CRITICAL
        assert report.overall_severity == DriftSeverity.CRITICAL
        assert report.prediction_drift is None
        assert report.target_drift is None
        assert report.concept_drift.available is False

    def test_run_sans_predictions_ni_target_ignore_ces_volets(self) -> None:
        baseline = self._baseline()
        report = DriftDetector().run(baseline, baseline.features)
        assert report.prediction_drift is None
        assert report.target_drift is None


class TestService:
    def test_capture_reference_baseline_echantillonne_avec_une_borne(self) -> None:
        rng = np.random.RandomState(0)
        features = pd.DataFrame({"age": rng.normal(0, 1, size=5000)})
        predictions = rng.normal(0, 1, size=5000)
        target = pd.Series(rng.normal(0, 1, size=5000))
        baseline = capture_reference_baseline(
            features,
            predictions,
            target,
            {"r2": 0.8},
            "random_forest",
            "regression",
            FeatureColumns(numerical=("age",), categorical=()),
            max_samples=500,
        )
        assert len(baseline.features) == 500
        assert baseline.predictions is not None
        assert len(baseline.predictions) == 500
        assert baseline.target is not None
        assert len(baseline.target) == 500

    def test_capture_reference_baseline_sans_depassement(self) -> None:
        features = pd.DataFrame({"age": [1, 2, 3]})
        baseline = capture_reference_baseline(
            features,
            None,
            None,
            {"r2": 0.8},
            "random_forest",
            "regression",
            FeatureColumns(numerical=("age",), categorical=()),
            max_samples=500,
        )
        assert len(baseline.features) == 3
        assert baseline.predictions is None
        assert baseline.target is None

    def test_run_drift_check_jamais_ne_leve(self) -> None:
        baseline = _build_baseline()

        class _BrokenFeatures:
            def __getattr__(self, item):
                raise RuntimeError("boom")

        report = run_drift_check(baseline, _BrokenFeatures())
        assert report.overall_severity == DriftSeverity.NONE
        assert report.concept_drift.available is False


class TestSerializer:
    def _baseline(self) -> ReferenceBaseline:
        return ReferenceBaseline(
            model_name="random_forest",
            task_type="classification",
            features=pd.DataFrame({"age": [1, 2, 3]}),
            predictions=np.array(["yes", "no", "yes"]),
            target=pd.Series(["yes", "no", "yes"]),
            metrics={"accuracy": 0.9},
            numerical_columns=("age",),
            categorical_columns=(),
        )

    def test_enregistre_et_recharge_baseline(self, tmp_path: Path) -> None:
        registry = ModelRegistry(tmp_path, serializer=JoblibArtifactSerializer())
        tenant = TenantContext(uuid4())
        registry.save("fake-model", tenant, "retail", "bad_review", "v1", filename="model.bin")

        baseline = self._baseline()
        path = save_baseline(registry, baseline, tenant, "retail", "bad_review", "v1")
        assert path.is_file()

        reloaded = load_baseline(registry, tenant, "retail", "bad_review", "v1")
        # `ReferenceBaseline` contient un DataFrame/ndarray/Series : une comparaison
        # `==` directe entre deux instances est ambiguë (pandas), on compare donc
        # chaque champ explicitement.
        assert_frame_equal(reloaded.features, baseline.features)
        np.testing.assert_array_equal(reloaded.predictions, baseline.predictions)
        assert_series_equal(reloaded.target, baseline.target)
        assert reloaded.metrics == baseline.metrics
        assert reloaded.model_name == baseline.model_name
        assert reloaded.task_type == baseline.task_type

    def test_leve_si_aucune_baseline_enregistree(self, tmp_path: Path) -> None:
        registry = ModelRegistry(tmp_path, serializer=JoblibArtifactSerializer())
        tenant = TenantContext(uuid4())
        registry.save("fake-model", tenant, "retail", "bad_review", "v1", filename="model.bin")

        with pytest.raises(FileNotFoundError):
            load_baseline(registry, tenant, "retail", "bad_review", "v1")

    def test_enregistre_et_recharge_drift_report(self, tmp_path: Path) -> None:
        registry = ModelRegistry(tmp_path, serializer=JoblibArtifactSerializer())
        tenant = TenantContext(uuid4())
        registry.save("fake-model", tenant, "retail", "bad_review", "v2", filename="model.bin")

        baseline = self._baseline()
        report = run_drift_check(baseline, baseline.features, baseline.predictions, baseline.target, baseline.metrics)
        path = save_drift_report(registry, report, tenant, "retail", "bad_review", "v2")
        assert path.is_file()

        reloaded = load_drift_report(registry, tenant, "retail", "bad_review", "v2")
        assert reloaded.model_name == report.model_name
        assert reloaded.overall_severity == report.overall_severity
        assert reloaded.data_drift == report.data_drift
        assert reloaded.concept_drift == report.concept_drift

