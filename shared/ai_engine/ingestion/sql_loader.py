from typing import Any, Callable


class SQLLoader:
    """Charge des données SQL avec un adaptateur de connexion injecté."""

    def __init__(self, reader: Callable[..., Any]) -> None:
        self._reader = reader

    def load(self, connection: str, query: str, **options: Any) -> Any:
        return self._reader(connection, query=query, **options)
