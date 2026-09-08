"""Central catalog metadata for commerce connector plugins."""

from shared.ai_engine.connectors.commerce import (
    ConnectorAuthMethod,
    ConnectorCapability,
    ConnectorCategory,
    ConnectorDefinition,
    ConnectorImplementationStatus,
)

_AVAILABLE = ConnectorImplementationStatus.AVAILABLE
_COMING_SOON = ConnectorImplementationStatus.COMING_SOON
_OAUTH = ConnectorAuthMethod.OAUTH2
_API_KEY = ConnectorAuthMethod.API_KEY

_COMMERCE = frozenset(
    {
        ConnectorCapability.ORDERS,
        ConnectorCapability.CUSTOMERS,
        ConnectorCapability.PRODUCTS,
        ConnectorCapability.INVENTORY,
        ConnectorCapability.REFUNDS,
        ConnectorCapability.DISCOUNTS,
    }
)
_MARKETPLACE = frozenset(
    {
        ConnectorCapability.ORDERS,
        ConnectorCapability.PRODUCTS,
        ConnectorCapability.INVENTORY,
        ConnectorCapability.REFUNDS,
    }
)
_PAYMENTS = frozenset(
    {
        ConnectorCapability.CUSTOMERS,
        ConnectorCapability.REFUNDS,
        ConnectorCapability.PAYMENTS,
    }
)


def _definition(
    provider: str,
    display_name: str,
    category: ConnectorCategory,
    *,
    status: ConnectorImplementationStatus = _COMING_SOON,
    auth_method: ConnectorAuthMethod = _OAUTH,
    capabilities: frozenset[ConnectorCapability] = frozenset(),
    configuration_requirements: tuple[str, ...] = (),
) -> ConnectorDefinition:
    return ConnectorDefinition(
        provider=provider,
        display_name=display_name,
        category=category,
        implementation_status=status,
        auth_method=auth_method,
        capabilities=capabilities,
        description_key=f"connector.{provider}.description",
        icon_key=provider,
        configuration_requirements=configuration_requirements,
    )


COMMERCE_CONNECTOR_CATALOG: tuple[ConnectorDefinition, ...] = (
    _definition(
        "shopify",
        "Shopify",
        ConnectorCategory.ECOMMERCE,
        status=_AVAILABLE,
        capabilities=_COMMERCE,
        configuration_requirements=("shop_domain",),
    ),
    _definition("woocommerce", "WooCommerce", ConnectorCategory.ECOMMERCE, auth_method=_API_KEY, capabilities=_COMMERCE),
    _definition("bigcommerce", "BigCommerce", ConnectorCategory.ECOMMERCE, capabilities=_COMMERCE),
    _definition("adobe-commerce", "Adobe Commerce / Magento", ConnectorCategory.ECOMMERCE, capabilities=_COMMERCE),
    _definition("prestashop", "PrestaShop", ConnectorCategory.ECOMMERCE, auth_method=_API_KEY, capabilities=_COMMERCE),
    _definition("wix-ecommerce", "Wix eCommerce", ConnectorCategory.ECOMMERCE, capabilities=_COMMERCE),
    _definition("squarespace-commerce", "Squarespace Commerce", ConnectorCategory.ECOMMERCE, capabilities=_COMMERCE),
    _definition("ecwid", "Ecwid", ConnectorCategory.ECOMMERCE, capabilities=_COMMERCE),
    _definition("shopware", "Shopware", ConnectorCategory.ECOMMERCE, capabilities=_COMMERCE),
    _definition("vtex", "VTEX", ConnectorCategory.ECOMMERCE, capabilities=_COMMERCE),
    _definition("amazon-seller-central", "Amazon Seller Central", ConnectorCategory.MARKETPLACE, capabilities=_MARKETPLACE),
    _definition("ebay", "eBay", ConnectorCategory.MARKETPLACE, capabilities=_MARKETPLACE),
    _definition("etsy", "Etsy", ConnectorCategory.MARKETPLACE, capabilities=_MARKETPLACE),
    _definition("walmart-marketplace", "Walmart Marketplace", ConnectorCategory.MARKETPLACE, capabilities=_MARKETPLACE),
    _definition("mercado-libre", "Mercado Libre", ConnectorCategory.MARKETPLACE, capabilities=_MARKETPLACE),
    _definition("tiktok-shop", "TikTok Shop", ConnectorCategory.MARKETPLACE, capabilities=_MARKETPLACE),
    _definition("mirakl", "Mirakl", ConnectorCategory.MARKETPLACE, capabilities=_MARKETPLACE),
    _definition("faire", "Faire", ConnectorCategory.MARKETPLACE, capabilities=_MARKETPLACE),
    _definition("wayfair-marketplace", "Wayfair Marketplace", ConnectorCategory.MARKETPLACE, capabilities=_MARKETPLACE),
    _definition("target-plus", "Target Plus", ConnectorCategory.MARKETPLACE, capabilities=_MARKETPLACE),
    _definition("stripe-commerce", "Stripe Commerce Payments", ConnectorCategory.PAYMENTS, capabilities=_PAYMENTS),
    _definition("paypal", "PayPal", ConnectorCategory.PAYMENTS, capabilities=_PAYMENTS),
    _definition("square", "Square", ConnectorCategory.PAYMENTS, capabilities=_PAYMENTS),
    _definition("adyen", "Adyen", ConnectorCategory.PAYMENTS, capabilities=_PAYMENTS),
    _definition("klaviyo", "Klaviyo", ConnectorCategory.MARKETING, capabilities=frozenset({ConnectorCapability.CUSTOMERS})),
    _definition("mailchimp", "Mailchimp", ConnectorCategory.MARKETING, capabilities=frozenset({ConnectorCapability.CUSTOMERS})),
    _definition("gorgias", "Gorgias", ConnectorCategory.MARKETING, capabilities=frozenset({ConnectorCapability.CUSTOMERS})),
    _definition("shipstation", "ShipStation", ConnectorCategory.FULFILLMENT, capabilities=frozenset({ConnectorCapability.ORDERS, ConnectorCapability.INVENTORY})),
    _definition("shipbob", "ShipBob", ConnectorCategory.FULFILLMENT, capabilities=frozenset({ConnectorCapability.ORDERS, ConnectorCapability.INVENTORY})),
    _definition("google-analytics-4", "Google Analytics 4", ConnectorCategory.ANALYTICS),
)