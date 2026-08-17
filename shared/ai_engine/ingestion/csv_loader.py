from typing import Any

from shared.ai_engine.ingestion.base import DelegatingLoader


class CSVLoader(DelegatingLoader[Any]):
    """Charge des données CSV avec un lecteur injecté."""
