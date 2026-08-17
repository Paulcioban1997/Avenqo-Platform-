"""Erreurs métier exposées par les frontières de l'AI Engine."""


class AIEngineError(Exception):
    """Erreur de base pour les échecs de l'AI Engine."""


class ConnectorNotRegisteredError(AIEngineError):
    """Signale qu'aucun connecteur ne prend en charge la source demandée."""


class TaskNotRegisteredError(AIEngineError):
    """Signale qu'une tâche de module est inconnue."""


class TenantScopeError(AIEngineError):
    """Signale qu'un artefact n'appartient pas à l'entreprise active."""


class ModelNotFoundError(AIEngineError):
    """Signale qu'aucun modèle ne peut être trouvé pour l'entreprise."""


class UnsupportedExecutionDomainError(AIEngineError):
    """Signale qu'aucune stratégie n'est enregistrée pour ce domaine interne."""
