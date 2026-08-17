"""Orchestration d'un entraînement supervisé TensorFlow/Keras."""

import logging
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Literal, Sequence

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

from shared.ai_engine.architectures.deep_learning.keras_dense_builder import build_dense_network
from shared.ai_engine.contracts import DatasetArtifact
from shared.ai_engine.drift.service import capture_reference_baseline
from shared.ai_engine.evaluation.neural_metrics import decode_neural_predictions, evaluate_neural_network
from shared.ai_engine.explainability.service import explain_neural_network
from shared.ai_engine.preprocessing.imbalance import analyze_class_balance, build_resampler
from shared.ai_engine.preprocessing.tabular import (
    FeatureColumns,
    build_preprocessor,
    detect_feature_columns,
)
from shared.ai_engine.training.deep_learning_result import DeepLearningTrainingResult
from shared.ai_engine.training.deep_model_saver import save_deep_model
from shared.ai_engine.training.experiment_logger import ExperimentLogger
from shared.ai_engine.training.run_context import TrainingRunContext

logger = logging.getLogger(__name__)

NeuralModelBuilder = Callable[[int, int], Any]


def train_neural_network(
    data: pd.DataFrame,
    target_column: str,
    task_type: Literal["classification", "regression"],
    dataset: DatasetArtifact,
    version: str,
    run_context: TrainingRunContext,
    destination: Path,
    experiment_logger: ExperimentLogger,
    hidden_units: tuple[int, ...] = (64, 32),
    learning_rate: float = 0.001,
    epochs: int = 20,
    batch_size: int = 32,
    test_size: float = 0.2,
    random_seed: int = 42,
    model_builder: NeuralModelBuilder | None = None,
    callbacks: Sequence[Any] = (),
) -> DeepLearningTrainingResult:
    """Prétraite, entraîne, évalue, sauvegarde et journalise un réseau."""

    import tensorflow as tf

    run = experiment_logger.start(dataset, version, run_context)
    started = perf_counter()
    try:
        tf.keras.utils.set_random_seed(random_seed)
        features, raw_target = _split_target(data, target_column)
        target, output_size = _encode_target(raw_target, task_type)
        columns = detect_feature_columns(features)
        train_x, test_x, train_y, test_y = train_test_split(
            features,
            target,
            test_size=test_size,
            random_state=random_seed,
            stratify=target if task_type == "classification" else None,
        )
        preprocessor = build_preprocessor(columns)
        transformed_train = np.asarray(preprocessor.fit_transform(train_x))
        transformed_test = np.asarray(preprocessor.transform(test_x))
        if task_type == "classification":
            transformed_train, train_y = _resample_if_imbalanced(
                transformed_train, train_y, random_seed
            )
        builder = model_builder or (
            lambda input_size, outputs: build_dense_network(
                input_size,
                task_type,
                outputs,
                hidden_units,
                learning_rate,
            )
        )
        model = builder(transformed_train.shape[1], output_size)
        history = model.fit(
            transformed_train,
            train_y,
            validation_data=(transformed_test, test_y),
            epochs=epochs,
            batch_size=batch_size,
            callbacks=list(callbacks),
            verbose=0,
        )
        metrics = evaluate_neural_network(model, transformed_test, test_y, task_type)
        explanation = explain_neural_network(
            model,
            transformed_test,
            test_y,
            preprocessor.get_feature_names_out(),
            "dense_neural_network",
            task_type,
            random_seed,
        )
        raw_test_predictions = np.asarray(model.predict(transformed_test, verbose=0))
        reference_baseline = capture_reference_baseline(
            test_x,
            decode_neural_predictions(raw_test_predictions, task_type),
            pd.Series(test_y),
            metrics,
            "dense_neural_network",
            task_type,
            columns,
            random_seed,
        )
        paths = save_deep_model(model, preprocessor, destination)
        parameters = {
            "hidden_units": hidden_units,
            "learning_rate": learning_rate,
            "epochs": epochs,
            "batch_size": batch_size,
        }
        experiment_logger.complete(
            run,
            run_context,
            "dense_neural_network",
            parameters,
            parameters,
            metrics,
            paths.model,
            paths.preprocessor,
            perf_counter() - started,
            columns.numerical,
            columns.categorical,
        )
        return DeepLearningTrainingResult(
            model=model,
            metrics=metrics,
            history={key: list(values) for key, values in history.history.items()},
            numerical_columns=columns.numerical,
            categorical_columns=columns.categorical,
            model_path=paths.model,
            preprocessor_path=paths.preprocessor,
            explanation=explanation,
            reference_baseline=reference_baseline,
        )
    except Exception:
        experiment_logger.fail(run, perf_counter() - started)
        raise


def _split_target(data: pd.DataFrame, target_column: str) -> tuple[pd.DataFrame, pd.Series]:
    if target_column not in data:
        raise ValueError(f"Colonne cible absente: {target_column}")
    return data.drop(columns=[target_column]), data[target_column]


def _encode_target(
    target: pd.Series,
    task_type: Literal["classification", "regression"],
) -> tuple[np.ndarray, int]:
    if task_type == "regression":
        return target.to_numpy(dtype=float), 1
    encoder = LabelEncoder()
    encoded = encoder.fit_transform(target)
    return encoded, len(encoder.classes_)


def _resample_if_imbalanced(
    transformed_train: np.ndarray,
    train_y: np.ndarray,
    random_seed: int,
) -> tuple[np.ndarray, np.ndarray]:
    """SMOTE sur les features déjà encodées/mises à l'échelle (classification uniquement).

    Appliqué uniquement au split d'entraînement (jamais au split de test/validation).
    Toujours SMOTE (jamais SMOTENC/SMOTEN) : à ce stade les catégories ont déjà été
    encodées en one-hot par `build_preprocessor`, donc plus aucune colonne n'est
    catégorielle au sens propre — la distinction numérique/catégoriel qui justifie
    SMOTENC n'a de sens qu'avant cet encodage (voir `train_classifier.py`, où le
    ré-échantillonnage s'intercale entre imputation et encodage).
    """

    imbalance = analyze_class_balance(pd.Series(train_y))
    resampler = build_resampler(
        FeatureColumns(numerical=tuple(range(transformed_train.shape[1])), categorical=()),
        imbalance,
        random_seed,
    )
    if resampler is None:
        return transformed_train, train_y
    logger.info(
        "Déséquilibre détecté (ratio=%.2f) : SMOTE appliqué sur le split d'entraînement.",
        imbalance.ratio,
    )
    resampled_x, resampled_y = resampler.fit_resample(transformed_train, train_y)
    return np.asarray(resampled_x), np.asarray(resampled_y)