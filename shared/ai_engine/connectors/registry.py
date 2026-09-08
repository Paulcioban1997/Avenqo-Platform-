"""Registries selecting data-source and commerce connector plugins."""

from collections.abc import Iterable

from shared.ai_engine.contracts import DataConnector, SourceKind
from shared.ai_engine.connectors.catalog import COMMERCE_CONNECTOR_CATALOG
from shared.ai_engine.connectors.commerce import CommerceConnector, ConnectorDefinition
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


class CommerceConnectorRegistry:
    """Single source of truth for provider metadata and implementations."""

    def __init__(
        self,
        definitions: Iterable[ConnectorDefinition] = COMMERCE_CONNECTOR_CATALOG,
    ) -> None:
        self._definitions = {item.provider: item for item in definitions}
        self._connectors: dict[str, CommerceConnector] = {}

    def register(self, connector: CommerceConnector) -> None:
        provider = connector.definition.provider
        if provider not in self._definitions:
            raise ConnectorNotRegisteredError(
                f"Provider '{provider}' is not present in the connector catalog"
            )
        self._connectors[provider] = connector

    def catalog(self) -> tuple[ConnectorDefinition, ...]:
        return tuple(self._definitions.values())

    def definition(self, provider: str) -> ConnectorDefinition:
        try:
            return self._definitions[provider]
        except KeyError as exc:
            raise ConnectorNotRegisteredError(
                f"Provider '{provider}' is not present in the connector catalog"
            ) from exc

    def get(self, provider: str) -> CommerceConnector:
        definition = self.definition(provider)
        try:
            return self._connectors[provider]
        except KeyError as exc:
            raise ConnectorNotRegisteredError(
                f"Provider '{definition.display_name}' is not available"
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
