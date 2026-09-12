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

    assert len(catalog) == 30
    assert len({item.provider for item in catalog}) == 30
    assert {item.provider for item in catalog if item.enabled} == {
        "shopify",
        "woocommerce",
    }
    assert {
        item.provider
        for item in catalog
        if item.implementation_status == ConnectorImplementationStatus.AVAILABLE
    } == {"shopify", "woocommerce"}


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