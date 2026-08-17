"""Domaines d'exécution internes que l'AI Engine sait orchestrer."""

from enum import StrEnum


class ExecutionDomain(StrEnum):
    """Famille d'intelligence artificielle interne, jamais exposée aux API publiques.

    Chaque valeur correspond exactement à un dossier sous `shared/ai_engine/families/`,
    tous organisés selon la même architecture (strategy, trainer, optimizer, evaluator,
    candidates, registry, models/). Ajouter une future famille ne nécessite qu'un nouveau
    dossier de famille et une ligne d'enregistrement dans le registre par défaut : ni
    l'AIEngine, ni les familles existantes ne sont jamais modifiés.
    """

    MACHINE_LEARNING = "machine_learning"
    DEEP_LEARNING = "deep_learning"
    FORECASTING = "forecasting"
    NLP = "nlp"
    VISION = "vision"
    OCR = "ocr"
    RECOMMENDATION = "recommendation"
    ANOMALY_DETECTION = "anomaly"
    SYNTHETIC_DATA = "synthetic"
    LLM = "llm"
    RAG = "rag"
    AUDIO = "audio"
