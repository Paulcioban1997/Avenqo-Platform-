"""Erreurs contrôlées du Tool Calling (Phase 30).

Le LLM peut recevoir une représentation sûre de ces erreurs (message
métier), jamais une stack trace ni un détail d'implémentation.
"""

from __future__ import annotations


class ToolError(Exception):
    """Base commune de toutes les erreurs de tool calling."""


class ToolNotFoundError(ToolError):
    """L'outil demandé n'existe pas ou n'est pas enregistré."""


class ToolValidationError(ToolError):
    """Les arguments fournis par le LLM ne respectent pas le schéma attendu."""


class ToolAuthorizationError(ToolError):
    """Le tenant/utilisateur courant n'a pas le droit d'exécuter cet outil."""


class ToolExecutionError(ToolError):
    """L'outil a levé une erreur inattendue pendant son exécution."""


class ToolTimeoutError(ToolError):
    """L'outil n'a pas répondu dans le délai imparti."""


class ToolUnavailableError(ToolError):
    """L'outil existe mais la capacité/donnée requise n'est pas disponible pour ce tenant."""


# --- Phase 31 : Predictive Intelligence -------------------------------------
# Hiérarchie dédiée aux outils prédictifs (`PredictiveAITool`). Chacune de ces
# erreurs hérite d'une erreur Phase 30 déjà gérée par `ToolExecutor`/
# `ToolOrchestrator` (jamais de stack trace ni de détail fournisseur/modèle
# exposé au LLM — uniquement le message métier porté par l'exception).


class ModelNotFoundError(ToolUnavailableError):
    """Aucun modèle actif n'existe pour ce tenant/tâche prédictive."""


class ModelUnavailableError(ToolUnavailableError):
    """Le modèle existe mais n'est pas utilisable actuellement (ex. supprimé/désactivé)."""


class ModelNotReadyError(ToolUnavailableError):
    """Le modèle est encore en cours d'entraînement, pas encore prêt pour l'inférence."""


class ModelInputIncompatibleError(ToolUnavailableError):
    """Les données du tenant ne contiennent pas les colonnes attendues par le modèle."""


class InferenceError(ToolExecutionError):
    """L'inférence a échoué de façon inattendue (jamais de détail technique exposé)."""


class PredictionUnavailableError(ToolUnavailableError):
    """Aucune prédiction exploitable n'a pu être produite (ex. aucune ligne, résultat vide)."""


class StalePredictionError(ToolUnavailableError):
    """Le modèle/la prédiction est considéré(e) comme périmé(e)."""
