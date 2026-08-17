"""Contrats et registre des connecteurs de sources de données."""

from shared.ai_engine.connectors.registry import (
	ConnectorRegistry,
	build_default_connector_registry,
)

__all__ = ["ConnectorRegistry", "build_default_connector_registry"]
