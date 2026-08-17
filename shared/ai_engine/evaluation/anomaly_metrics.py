"""Métriques adaptées à la détection d'anomalies non supervisée (IsolationForest).

Autorité unique d'évaluation de cette famille, utilisée par le pipeline officiel
de `shared.ai_engine.training`. Non supervisé : aucune vérité terrain n'existe,
donc aucune accuracy/précision/rappel/F1 n'est jamais calculée ou fabriquée ici
(voir `shared/ai_engine/hyperparameters/anomaly.py`). La qualité d'un candidat
se mesure uniquement par la séparation interne de ses propres scores de
décision entre observations jugées normales et observations jugées anormales.
"""

from typing import Mapping, Sequence

import numpy as np


def evaluate_anomalies(scores: np.ndarray, labels: np.ndarray) -> Mapping[str, float]:
    """Calcule la séparation interne des scores de décision IsolationForest.

    `labels` suit la convention sklearn (``1`` = normal, ``-1`` = anomalie).
    `separation_score` est l'écart moyen entre les scores des observations
    normales et ceux des anomalies (plus l'écart est grand, plus la frontière
    détectée est nette) ; il vaut ``0.0`` si le candidat n'isole aucune
    anomalie ou si tout est classé anomalie (rien de comparable).
    """

    scores = np.asarray(scores)
    labels = np.asarray(labels)
    is_anomaly = labels == -1
    anomaly_ratio = float(np.mean(is_anomaly))
    if not is_anomaly.any() or is_anomaly.all():
        return {
            "anomaly_ratio": anomaly_ratio,
            "separation_score": 0.0,
            "mean_score": float(np.mean(scores)),
        }

    return {
        "anomaly_ratio": anomaly_ratio,
        "separation_score": float(np.mean(scores[~is_anomaly]) - np.mean(scores[is_anomaly])),
        "mean_score": float(np.mean(scores)),
    }


def rank_anomaly_candidates(candidates: Sequence[Mapping[str, float]]) -> list[float]:
    """Classe les candidats (combinaisons d'hyperparamètres) par séparation interne.

    Plus haut = mieux. Un candidat qui n'isole aucune anomalie (`anomaly_ratio`
    nul) est systématiquement écarté (score le plus bas) : il ne détecte rien,
    donc ne peut jamais être la meilleure configuration.
    """

    return [
        candidate["separation_score"] if candidate["anomaly_ratio"] > 0 else -1.0
        for candidate in candidates
    ]
