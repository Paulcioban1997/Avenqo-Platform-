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
