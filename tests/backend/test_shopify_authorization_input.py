import pytest
from pydantic import ValidationError

from backend.app.schemas.commerce import ShopifyAuthorizationRequest


def test_shopify_domain_is_normalized():
    request = ShopifyAuthorizationRequest(shop_domain=" AVENQO-RETAIL-TEST.myshopify.com ")
    assert request.shop_domain == "avenqo-retail-test.myshopify.com"


@pytest.mark.parametrize("domain", [
    "", "shop", "https://shop.myshopify.com", "shop.myshopify.com.evil.test",
    "shop.myshopify.com/path", "shop.myshopify.com:443", "user@shop.myshopify.com",
    "-shop.myshopify.com", "shop\n.myshopify.com",
])
def test_shopify_domain_rejects_non_shop_hosts(domain):
    with pytest.raises(ValidationError):
        ShopifyAuthorizationRequest(shop_domain=domain)
