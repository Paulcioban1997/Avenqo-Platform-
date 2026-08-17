from typing import Any, Callable, Mapping


class APILoader:
    """Charge des données REST avec un adaptateur HTTP injecté."""

    def __init__(self, client: Callable[..., Any]) -> None:
        self._client = client

    def load(self, url: str, **options: Any) -> Any:
        return self._client(url, **options)
