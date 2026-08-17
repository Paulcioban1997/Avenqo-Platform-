"""Recherche d'hyperparamètres Deep Learning : autorité unique basée sur Optuna.

`optuna` (pip, pur Python, léger — contrairement à `torch`/`torch_geometric`/`sdv`,
volontairement écartés ailleurs dans l'AI Engine pour éviter des installations fragiles
sous Windows) est la seule bibliothèque de recherche d'hyperparamètres Deep Learning
utilisée dans tout l'AI Engine. `KerasTuner` aurait été une alternative tout aussi
valable (voir `SearchMethod.KERAS_TUNER`, déjà présent dans `experiments/models.py` mais
non utilisé) ; Optuna a été retenu car il fonctionne indifféremment sur des modèles Keras
`Sequential`/`Functional` (LSTM, GRU, Transformer, MLP, CNN, AutoEncoder, VAE, GNN...) ET
sur une boucle d'entraînement manuelle (GAN), ce que KerasTuner ne permet pas nativement.

`ParamSource` est l'abstraction clé de ce module : elle permet à chaque modèle Deep
Learning d'écrire UNE SEULE fonction de construction d'architecture, utilisée à la fois
pendant la recherche (elle échantillonne via Optuna) et pendant le ré-entraînement final
sur l'intégralité du dataset (elle relit simplement les meilleurs hyperparamètres déjà
trouvés) — zéro duplication entre "essai de recherche" et "entraînement final".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Sequence


class ParamSource:
    """Fournit un hyperparamètre soit en l'échantillonnant (recherche Optuna), soit en le
    relisant (ré-entraînement final à partir de `best_trial.params`).
    """

    def __init__(self, trial: Any = None, params: dict[str, Any] | None = None):
        if (trial is None) == (params is None):
            raise ValueError("Fournir exactement un de `trial` ou `params`.")
        self._trial = trial
        self._params = params

    @property
    def is_search(self) -> bool:
        return self._trial is not None

    def int(self, name: str, low: int, high: int, log: bool = False) -> int:
        if self._trial is not None:
            return self._trial.suggest_int(name, low, high, log=log)
        return self._params[name]

    def float(self, name: str, low: float, high: float, log: bool = False) -> float:
        if self._trial is not None:
            return self._trial.suggest_float(name, low, high, log=log)
        return self._params[name]

    def categorical(self, name: str, choices: Sequence[Any]) -> Any:
        if self._trial is not None:
            return self._trial.suggest_categorical(name, list(choices))
        return self._params[name]


def run_keras_hyperparameter_search(
    objective: Callable[[Any], float],
    n_trials: int = 15,
    direction: str = "minimize",
    seed: int = 42,
) -> Any:
    """Exécute une étude Optuna et retourne le meilleur essai (`optuna.trial.FrozenTrial`)."""

    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    sampler = optuna.samplers.TPESampler(seed=seed)
    pruner = optuna.pruners.MedianPruner()
    study = optuna.create_study(direction=direction, sampler=sampler, pruner=pruner)
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
    return study.best_trial


@dataclass(frozen=True, slots=True)
class TrainingControls:
    """Nombre d'epochs, taille de batch, et rappels (early stopping) échantillonnés."""

    epochs: int
    batch_size: int
    steps_per_epoch: int
    callbacks: list[Any] = field(default_factory=list)


def suggest_training_controls(
    source: ParamSource, sample_count: int, with_validation: bool = True, prefix: str = ""
) -> TrainingControls:
    """Résout epochs/batch size, et un éventuel early stopping (patience=3)."""

    import tensorflow as tf

    epochs = source.categorical(f"{prefix}epochs", [10, 20, 30, 50])
    batch_size = min(source.categorical(f"{prefix}batch_size", [16, 32, 64]), max(1, sample_count))
    steps_per_epoch = max(1, sample_count // batch_size)

    callbacks: list[Any] = []
    if with_validation and source.categorical(f"{prefix}early_stopping", [True, False]):
        callbacks.append(
            tf.keras.callbacks.EarlyStopping(monitor="val_loss", patience=3, restore_best_weights=True)
        )
    return TrainingControls(
        epochs=epochs, batch_size=batch_size, steps_per_epoch=steps_per_epoch, callbacks=callbacks
    )


def suggest_optimizer(source: ParamSource, controls: TrainingControls, prefix: str = "") -> Any:
    """Résout learning rate (+ scheduler cosine decay optionnel), optimiseur, weight decay."""

    import tensorflow as tf

    base_learning_rate = source.float(f"{prefix}learning_rate", 1e-4, 1e-1, log=True)
    lr_schedule = source.categorical(f"{prefix}lr_schedule", ["constant", "cosine_decay"])
    if lr_schedule == "cosine_decay":
        learning_rate = tf.keras.optimizers.schedules.CosineDecay(
            base_learning_rate, decay_steps=max(1, controls.steps_per_epoch * controls.epochs)
        )
    else:
        learning_rate = base_learning_rate

    optimizer_name = source.categorical(f"{prefix}optimizer", ["adam", "rmsprop", "sgd"])
    weight_decay = source.float(f"{prefix}weight_decay", 1e-6, 1e-2, log=True)

    if optimizer_name == "adam":
        return tf.keras.optimizers.Adam(learning_rate=learning_rate, weight_decay=weight_decay)
    if optimizer_name == "rmsprop":
        return tf.keras.optimizers.RMSprop(learning_rate=learning_rate, weight_decay=weight_decay)
    return tf.keras.optimizers.SGD(learning_rate=learning_rate, momentum=0.9, weight_decay=weight_decay)


def add_dense_stack(
    inputs: Any,
    source: ParamSource,
    prefix: str = "",
    min_layers: int = 1,
    max_layers: int = 3,
    min_units: int = 16,
    max_units: int = 256,
) -> Any:
    """Empile un nombre variable de couches Dense (unités, dropout, activation résolus).

    Réutilisé par MLP, AutoEncoder, VAE, GAN — toutes des architectures denses dont seule
    la profondeur/largeur change ; centralise cette boucle pour éviter de la dupliquer.
    """

    import tensorflow as tf

    activation = source.categorical(f"{prefix}activation", ["relu", "tanh", "elu"])
    dropout_rate = source.float(f"{prefix}dropout", 0.0, 0.5)
    num_layers = source.int(f"{prefix}num_layers", min_layers, max_layers)

    hidden = inputs
    for layer_index in range(num_layers):
        units = source.int(f"{prefix}units_{layer_index}", min_units, max_units, log=True)
        hidden = tf.keras.layers.Dense(units, activation=activation)(hidden)
        if dropout_rate > 0:
            hidden = tf.keras.layers.Dropout(dropout_rate)(hidden)
    return hidden
