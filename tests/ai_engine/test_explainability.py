"""Tests unitaires et d'intégration de la couche d'explicabilité (Phase 6 — XAI).

Vérifie : l'importance native, la permutation importance (sklearn + Keras),
les explications SHAP (arbres/linéaires) et leur repli pour les modèles non
supportés, l'assemblage du `ExplanationArtifact`, et sa persistance dans le
`ModelRegistry` existant sans modification de celui-ci.
"""

from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd
import pytest
from sklearn.ensemble import AdaBoostClassifier, RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.svm import SVC

from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.explainability.feature_importance import (
    compute_native_importance,
    resolve_output_feature_names,
)
from shared.ai_engine.explainability.permutation_importance import (
    compute_neural_permutation_importance,
    compute_permutation_importance,
)
from shared.ai_engine.explainability.registry import explanation_family_for, is_shap_supported
from shared.ai_engine.explainability.serializer import load_explanation, save_explanation
from shared.ai_engine.explainability.service import explain_neural_network, explain_supervised
from shared.ai_engine.explainability.shap_explainer import build_shap_explanation
from shared.ai_engine.explainability.types import ExplanationArtifact, ExplanationMethod
from shared.ai_engine.model_registry.serializer import JoblibArtifactSerializer
from shared.ai_engine.preprocessing.tabular import (
    build_model_pipeline,
    build_preprocessor,
    detect_feature_columns,
)
from shared.ai_engine.registry.registry import ModelRegistry


def _build_data(rows: int = 60, seed: int = 0) -> pd.DataFrame:
    rng = np.random.RandomState(seed)
    age = rng.randint(18, 65, size=rows)
    tenure = rng.normal(3.0, 1.0, size=rows)
    segment = np.where(np.arange(rows) % 2 == 0, "A", "B")
    churn = ((age < 35).astype(int) + (segment == "B").astype(int) >= 1).astype(int)
    revenue = age * 2.0 + tenure * 5.0 + rng.normal(0, 1, size=rows)
    return pd.DataFrame(
        {
            "age": age,
            "tenure": tenure,
            "segment": segment,
            "churn": churn,
            "revenue": revenue,
        }
    )


def _fitted_pipeline(estimator, task_type: str) -> tuple[Pipeline, pd.DataFrame, pd.Series]:
    data = _build_data()
    target_column = "churn" if task_type == "classification" else "revenue"
    target = data[target_column]
    features = data.drop(columns=["churn", "revenue"])
    columns = detect_feature_columns(features)
    preprocessor = build_preprocessor(columns)
    pipeline = build_model_pipeline(preprocessor, estimator, task_type)
    pipeline.fit(features, target)
    return pipeline, features, target


class TestRegistryFamily:
    def test_arbres_reconnus(self) -> None:
        assert explanation_family_for(RandomForestClassifier()) == "tree"
        assert explanation_family_for(RandomForestRegressor()) == "tree"

    def test_lineaires_reconnus(self) -> None:
        assert explanation_family_for(LogisticRegression()) == "linear"
        assert explanation_family_for(LinearRegression()) == "linear"

    def test_adaboost_et_svm_non_supportes(self) -> None:
        # AdaBoost n'est volontairement pas un format d'arbres standard pour
        # `shap.TreeExplainer` : repli documenté sur la permutation importance.
        assert explanation_family_for(AdaBoostClassifier()) == "other"
        assert explanation_family_for(SVC()) == "other"
        assert is_shap_supported(SVC()) is False
        assert is_shap_supported(RandomForestClassifier()) is True


class TestNativeImportance:
    def test_importance_native_arbre(self) -> None:
        pipeline, _, _ = _fitted_pipeline(RandomForestClassifier(n_estimators=20, random_state=42), "classification")
        importance = compute_native_importance(pipeline)
        assert set(importance) == set(resolve_output_feature_names(pipeline))
        assert all(value >= 0 for value in importance.values())

    def test_importance_native_lineaire(self) -> None:
        pipeline, _, _ = _fitted_pipeline(LogisticRegression(max_iter=500), "classification")
        importance = compute_native_importance(pipeline)
        assert set(importance) == set(resolve_output_feature_names(pipeline))


class TestPermutationImportance:
    def test_permutation_importance_classification(self) -> None:
        pipeline, features, target = _fitted_pipeline(
            RandomForestClassifier(n_estimators=20, random_state=42), "classification"
        )
        importance = compute_permutation_importance(pipeline, features, target, "accuracy", random_seed=42)
        assert set(importance) == {"age", "tenure", "segment"}

    def test_permutation_importance_neuronale(self) -> None:
        class _FakeKerasModel:
            """Modèle Keras minimal : prédit 1 si la moyenne des variables > 0."""

            def predict(self, features: np.ndarray, verbose: int = 0) -> np.ndarray:
                return (features.mean(axis=1, keepdims=True) > 0).astype(float)

        rng = np.random.RandomState(0)
        features = rng.normal(size=(80, 3))
        target = (features.mean(axis=1) > 0).astype(int)
        importance = compute_neural_permutation_importance(
            _FakeKerasModel(), features, target, ["f0", "f1", "f2"], "classification", random_seed=0
        )
        assert set(importance) == {"f0", "f1", "f2"}


class TestShapExplainer:
    def test_shap_arbre_classification(self) -> None:
        pipeline, features, _ = _fitted_pipeline(
            RandomForestClassifier(n_estimators=20, random_state=42), "classification"
        )
        names = resolve_output_feature_names(pipeline)
        method, importance, samples = build_shap_explanation(pipeline, features, names, "classification")
        assert method == "shap_tree"
        assert importance is not None
        assert set(importance) == set(names)
        assert len(samples) == 5

    def test_shap_lineaire_regression(self) -> None:
        pipeline, features, _ = _fitted_pipeline(LinearRegression(), "regression")
        names = resolve_output_feature_names(pipeline)
        method, importance, samples = build_shap_explanation(pipeline, features, names, "regression")
        assert method == "shap_linear"
        assert importance is not None
        assert len(samples) == 5

    def test_shap_repli_modele_non_supporte(self) -> None:
        pipeline, features, _ = _fitted_pipeline(AdaBoostClassifier(n_estimators=10), "classification")
        names = resolve_output_feature_names(pipeline)
        method, importance, samples = build_shap_explanation(pipeline, features, names, "classification")
        assert method is None
        assert importance is None
        assert samples == ()


class TestExplainSupervised:
    def test_assemble_explication_arbre(self) -> None:
        pipeline, features, _ = _fitted_pipeline(
            RandomForestClassifier(n_estimators=20, random_state=42), "classification"
        )
        native = compute_native_importance(pipeline)
        permutation = {name: 0.1 for name in native}
        explanation = explain_supervised(
            pipeline, features, "random_forest", "classification", native, permutation
        )
        assert isinstance(explanation, ExplanationArtifact)
        assert explanation.method is ExplanationMethod.SHAP_TREE
        assert explanation.global_importance
        assert explanation.shap_importance is not None
        assert explanation.native_importance == native

    def test_repli_permutation_quand_shap_indisponible(self) -> None:
        pipeline, features, _ = _fitted_pipeline(AdaBoostClassifier(n_estimators=10), "classification")
        permutation = {"age": 0.2, "tenure": 0.1, "segment": 0.05}
        explanation = explain_supervised(
            pipeline, features, "adaboost", "classification", {}, permutation
        )
        assert explanation.method is ExplanationMethod.PERMUTATION
        assert explanation.shap_importance is None
        assert explanation.global_importance == permutation


class TestExplainNeuralNetwork:
    def test_assemble_explication_reseau_neuronal(self) -> None:
        class _FakeKerasModel:
            def predict(self, features: np.ndarray, verbose: int = 0) -> np.ndarray:
                return (features.mean(axis=1, keepdims=True) > 0).astype(float)

        rng = np.random.RandomState(0)
        features = rng.normal(size=(80, 3))
        target = (features.mean(axis=1) > 0).astype(int)
        explanation = explain_neural_network(
            _FakeKerasModel(), features, target, ["f0", "f1", "f2"], "dense_neural_network", "classification"
        )
        assert explanation.method is ExplanationMethod.PERMUTATION
        assert explanation.shap_importance is None
        assert set(explanation.global_importance) == {"f0", "f1", "f2"}


class TestSerializer:
    def test_enregistre_et_recharge_dans_le_model_registry(self, tmp_path: Path) -> None:
        registry = ModelRegistry(tmp_path, serializer=JoblibArtifactSerializer())
        tenant = TenantContext(uuid4())
        # Le répertoire versionné du modèle doit déjà exister (créé par `.save()`
        # du modèle lui-même en production) avant d'y ajouter l'explication.
        registry.save("fake-model", tenant, "retail", "bad_review", "v1", filename="model.bin")

        explanation = ExplanationArtifact(
            model_name="random_forest",
            task_type="classification",
            method=ExplanationMethod.SHAP_TREE,
            global_importance={"age": 0.5},
            native_importance={"age": 0.4},
            permutation_importance={"age": 0.3},
            shap_importance={"age": 0.5},
            sample_explanations=({"age": 0.5},),
        )
        path = save_explanation(registry, explanation, tenant, "retail", "bad_review", "v1")
        assert path.is_file()

        reloaded = load_explanation(registry, tenant, "retail", "bad_review", "v1")
        assert reloaded == explanation

    def test_leve_si_aucune_explication_enregistree(self, tmp_path: Path) -> None:
        registry = ModelRegistry(tmp_path, serializer=JoblibArtifactSerializer())
        tenant = TenantContext(uuid4())
        registry.save("fake-model", tenant, "retail", "bad_review", "v1", filename="model.bin")

        with pytest.raises(FileNotFoundError):
            load_explanation(registry, tenant, "retail", "bad_review", "v1")
