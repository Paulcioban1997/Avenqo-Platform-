"""Construction de réseaux neuronaux denses TensorFlow/Keras.

Autorité unique de construction des réseaux denses génériques, utilisée par
le pipeline officiel de `shared.ai_engine.training` (`train_neural_network`).
"""

from typing import Any, Literal


def build_dense_network(
    input_size: int,
    task_type: Literal["classification", "regression"],
    output_size: int,
    hidden_units: tuple[int, ...],
    learning_rate: float,
    activation: str = "relu",
    dropout: float = 0.5,
    optimizer: Any | None = None,
) -> Any:
    """Construit et compile un réseau dense adapté à la cible.

    TensorFlow est importé seulement lors d'un entraînement deep learning. Les
    entraînements sklearn restent ainsi légers et utilisables sans charger Keras.

    `activation`/`dropout`/`optimizer` sont optionnels (défauts identiques au
    comportement historique) : ils permettent à `MLPModel` (recherche d'hyperparamètres
    Optuna) de réutiliser cette même autorité de construction sans dupliquer la boucle
    de couches, tout en gardant `train_neural_network` (qui n'utilise que les valeurs
    par défaut) strictement inchangé.
    """

    import tensorflow as tf

    layers: list[Any] = [tf.keras.layers.Input(shape=(input_size,))]
    for units in hidden_units:
        layers.append(tf.keras.layers.Dense(units, activation=activation))
        if dropout > 0:
            layers.append(tf.keras.layers.Dropout(dropout))

    if task_type == "regression":
        layers.append(tf.keras.layers.Dense(1))
        loss = "mean_squared_error"
        metrics = ["mean_absolute_error"]
    elif output_size == 2:
        layers.append(tf.keras.layers.Dense(1, activation="sigmoid"))
        loss = "binary_crossentropy"
        metrics = ["accuracy"]
    else:
        layers.append(tf.keras.layers.Dense(output_size, activation="softmax"))
        loss = "sparse_categorical_crossentropy"
        metrics = ["accuracy"]

    model = tf.keras.Sequential(layers)
    model.compile(
        optimizer=optimizer or tf.keras.optimizers.Adam(learning_rate=learning_rate),
        loss=loss,
        metrics=metrics,
    )
    return model
