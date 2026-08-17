"""Registre extensible sélectionnant un connecteur selon la source."""

from shared.ai_engine.contracts import DataConnector, SourceKind
from shared.ai_engine.exceptions import ConnectorNotRegisteredError


class ConnectorRegistry:
    """Stocke les connecteurs sans coupler l'orchestration aux fournisseurs."""

    def __init__(self) -> None:
        self._connectors: dict[SourceKind, DataConnector] = {}

    def register(self, connector: DataConnector) -> None:
        self._connectors[connector.kind] = connector

    def get(self, kind: SourceKind) -> DataConnector:
        try:
            return self._connectors[kind]
        except KeyError as exc:
            raise ConnectorNotRegisteredError(
                f"No connector is registered for source kind '{kind.value}'"
            ) from exc


def build_default_connector_registry() -> ConnectorRegistry:
    """Construit le registre standard sans coupler services et adaptateurs."""
    from shared.ai_engine.connectors.api import RESTAPIConnector
    from shared.ai_engine.connectors.csv import CSVConnector
    from shared.ai_engine.connectors.excel import ExcelConnector
    from shared.ai_engine.connectors.mysql import MySQLConnector
    from shared.ai_engine.connectors.postgresql import PostgreSQLConnector
    from shared.ai_engine.connectors.sqlite import SQLiteConnector
    from shared.ai_engine.connectors.sqlserver import SQLServerConnector

    registry = ConnectorRegistry()
    for connector in (
        CSVConnector(),
        ExcelConnector(),
        SQLiteConnector(),
        PostgreSQLConnector(),
        MySQLConnector(),
        SQLServerConnector(),
        RESTAPIConnector(),
    ):
        registry.register(connector)
    return registry
