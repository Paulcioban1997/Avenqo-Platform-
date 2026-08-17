"""Candidat CNN, entraîné avec keras.layers.Conv2D.

En l'absence d'un pipeline d'ingestion d'images dans `DatasetArtifact` (voir
`shared/ai_engine/core/tabular_dataset.py`), les colonnes numériques du dataset sont
réorganisées en une grille 2D carrée (complétée par des zéros) pour permettre un
entraînement Conv2D réellement exécuté de bout en bout. Le jour où l'ingestion d'images
sera disponible, remplacer cette mise en forme fera de ce fichier un point d'extension
naturel, sans toucher à l'architecture (strategy, trainer, optimizer, evaluator, registry).

Recherche d'hyperparamètres : Optuna (voir
`shared.ai_engine.architectures.deep_learning.keras_hyperparameter_search`) sur le nombre
de blocs convolutifs, les filtres par bloc, l'activation, le dropout, la tête dense finale
(réutilise `add_dense_stack`), l'optimiseur, le weight decay, le learning rate (+
scheduler), le nombre d'epochs et la taille de batch. `_build_model` est appelée à
l'identique pendant la recherche et pendant le ré-entraînement final (`ParamSource`).
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

from shared.ai_engine.architectures.deep_learning.keras_hyperparameter_search import (
    ParamSource,
    add_dense_stack,
    run_keras_hyperparameter_search,
    suggest_optimizer,
    suggest_training_controls,
)
from shared.ai_engine.contracts import DatasetArtifact
from shared.ai_engine.core.model_stub import UntrainedModel
from shared.ai_engine.core.tabular_dataset import (
    detect_target_column,
    load_dataframe,
    numeric_feature_matrix,
)


class CNNModel(UntrainedModel):
    candidate_id = "cnn"
    n_trials = 12

    def train(self, dataset: DatasetArtifact) -> Any:
        frame = load_dataframe(dataset)
        target_column = detect_target_column(frame)
        features = numeric_feature_matrix(frame, exclude=(target_column,))
        target = frame[target_column]

        side = max(2, math.ceil(math.sqrt(features.shape[1])))
        padded = np.zeros((features.shape[0], side * side), dtype="float32")
        padded[:, : features.shape[1]] = features
        images = padded.reshape(-1, side, side, 1)

        if pd.api.types.is_numeric_dtype(target) and target.nunique() > 20:
            task_type = "regression"
            output_size = 1
            y = target.astype("float64").to_numpy()
            stratify = None
        else:
            task_type = "classification"
            encoded, uniques = pd.factorize(target)
            output_size = max(2, len(uniques))
            y = encoded
            stratify = y if pd.Series(y).value_counts().min() >= 2 else None

        train_x, val_x, train_y, val_y = train_test_split(
            images, y, test_size=0.2, random_state=42, stratify=stratify
        )

        def objective(trial: Any) -> float:
            source = ParamSource(trial=trial)
            model, controls = self._build_model(source, side, task_type, output_size, len(train_x))
            history = model.fit(
                train_x,
                train_y,
                validation_data=(val_x, val_y),
                epochs=controls.epochs,
                batch_size=controls.batch_size,
                callbacks=controls.callbacks,
                verbose=0,
            )
            return float(min(history.history["val_loss"]))

        best_trial = run_keras_hyperparameter_search(objective, n_trials=self.n_trials)
        source = ParamSource(params=best_trial.params)
        model, controls = self._build_model(source, side, task_type, output_size, len(images))
        model.fit(images, y, epochs=controls.epochs, batch_size=controls.batch_size, verbose=0)
        return model

    def _build_model(
        self,
        source: ParamSource,
        side: int,
        task_type: str,
        output_size: int,
        sample_count: int,
    ) -> tuple[Any, Any]:
        import tensorflow as tf

        controls = suggest_training_controls(source, sample_count)
        optimizer = suggest_optimizer(source, controls)

        num_conv_blocks = source.int("num_conv_blocks", 1, 2)
        conv_activation = source.categorical("conv_activation", ["relu", "tanh", "elu"])
        conv_dropout = source.float("conv_dropout", 0.0, 0.4)

        inputs = tf.keras.layers.Input(shape=(side, side, 1))
        hidden = inputs
        for block_index in range(num_conv_blocks):
            filters = source.int(f"filters_{block_index}", 8, 64, log=True)
            hidden = tf.keras.layers.Conv2D(filters, 3, padding="same", activation=conv_activation)(hidden)
            hidden = tf.keras.layers.MaxPooling2D(pool_size=2, padding="same")(hidden)
            if conv_dropout > 0:
                hidden = tf.keras.layers.Dropout(conv_dropout)(hidden)
        hidden = tf.keras.layers.GlobalAveragePooling2D()(hidden)
        hidden = add_dense_stack(hidden, source, prefix="dense_", min_layers=1, max_layers=2, min_units=16, max_units=128)

        if task_type == "regression":
            outputs = tf.keras.layers.Dense(1)(hidden)
            loss = "mse"
            metrics = ["mae"]
        elif output_size == 2:
            outputs = tf.keras.layers.Dense(1, activation="sigmoid")(hidden)
            loss = "binary_crossentropy"
            metrics = ["accuracy"]
        else:
            outputs = tf.keras.layers.Dense(output_size, activation="softmax")(hidden)
            loss = "sparse_categorical_crossentropy"
            metrics = ["accuracy"]

        model = tf.keras.Model(inputs, outputs)
        model.compile(optimizer=optimizer, loss=loss, metrics=metrics)
        return model, controls
