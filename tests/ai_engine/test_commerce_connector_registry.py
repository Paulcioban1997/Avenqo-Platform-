import pytest

from shared.ai_engine.connectors.commerce import (
    ConnectorCapability,
    ConnectorImplementationStatus,
)
from shared.ai_engine.connectors.registry import CommerceConnectorRegistry
from shared.ai_engine.exceptions import ConnectorNotRegisteredError


def test_catalog_lists_all_retail_providers_once() -> None:
    registry = CommerceConnectorRegistry()
    catalog = registry.catalog()

    from shared.ai_engine.connectors.catalog import CANONICAL_22_DEFINITIONS, CONNECTOR_ALIASES
    canonical = {item.provider for item in CANONICAL_22_DEFINITIONS}
    providers = {item.provider for item in catalog}
    assert len(canonical) == 22
    assert len(catalog) == len(providers) == 32
    assert all(CONNECTOR_ALIASES.get(alias) in canonical for alias in providers - canonical)
    assert {item.provider for item in catalog if item.enabled} == {
        "shopify",
        "woocommerce",
        "google_calendar", "outlook_calendar", "telnyx", "stripe",
    }
    assert {
        item.provider
        for item in catalog
        if item.implementation_status == ConnectorImplementationStatus.AVAILABLE
    } == {"shopify", "woocommerce", "google_calendar", "outlook_calendar", "telnyx", "stripe"}


def test_shopify_exposes_implemented_read_capabilities() -> None:
    definition = CommerceConnectorRegistry().definition("shopify")

    assert definition.configuration_requirements == ("shop_domain",)
    assert ConnectorCapability.ORDERS in definition.capabilities
    assert ConnectorCapability.INVENTORY in definition.capabilities
    assert ConnectorCapability.REFUNDS in definition.capabilities
    assert ConnectorCapability.PAYMENTS not in definition.capabilities


def test_coming_soon_provider_has_no_fake_implementation() -> None:
    with pytest.raises(ConnectorNotRegisteredError, match="not available"):
        CommerceConnectorRegistry().get("woocommerce")