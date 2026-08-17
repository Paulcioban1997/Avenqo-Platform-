from typing import Any

from shared.ai_engine.ingestion.base import DelegatingLoader


class ExcelLoader(DelegatingLoader[Any]):
    """Charge des données Excel avec un lecteur injecté."""
