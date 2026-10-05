import pytest
import httpx
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.app.config.settings import get_settings
from backend.app.core.rate_limit import reset_rate_limiter
from backend.app.database import get_db
from backend.app.dependencies.auth import get_current_identity
from backend.app.dependencies.subscription import require_active_subscription
from backend.app.models import UserRole
import backend.app.routers.voice as voice_router

from backend.app.services.voice_number_service import (
    PhoneNumberSearch,
    VoiceNumberManagementService,
    VoiceNumberOwnerActionRequired,
)
from backend.app.config.settings import Settings
from backend.app.voice.providers import TelnyxClient


class _FakeTelecomProvider:
    def __init__(self):
        self.search_kwargs = None
        self.orders = []
        self.releases = []

    async def search_available_numbers(self, **kwargs):
        self.search_kwargs = kwargs
        return [{
            "id": "provider-number-1",
            "phone_number": "+14165550123",
            "phone_number_type": "local",
            "country_code": "CA",
            "features": ["voice", "sms"],
            "region_information": [{"region": "ON", "locality": "Toronto"}],
            "cost_information": {"monthly_cost": "1.00", "currency": "USD"},
            "regulatory_requirements": ["proof_of_address"],
        }]

    async def order_phone_number(self, **kwargs):
        self.orders.append(kwargs)
        return {"status": "pending"}

    async def release_phone_number(self, provider_number_id):
        self.releases.append(provider_number_id)
        return {"status": "released"}


@pytest.mark.asyncio
async def test_telnyx_search_uses_v2_read_only_country_filter():
    captured = []

    def handler(request):
        captured.append(request)
        return httpx.Response(200, json={"data": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = TelnyxClient(Settings(TELNYX_API_KEY="test-key"), client=client)
        assert await provider.search_available_numbers(country_code="FR", limit=3) == []
    assert len(captured) == 1
    assert captured[0].method == "GET"
    assert captured[0].url.path == "/v2/available_phone_numbers"
    assert captured[0].url.params["filter[country_code]"] == "FR"
    assert captured[0].url.params["filter[limit]"] == "3"


@pytest.mark.asyncio
async def test_international_number_search_preserves_only_provider_returned_fields():
    provider = _FakeTelecomProvider()
    service = VoiceNumberManagementService(provider)

    result = await service.search(PhoneNumberSearch("ca", region="ON", locality="Toronto"))

    assert provider.search_kwargs == {
        "country_code": "CA",
        "region": "ON",
        "locality": "Toronto",
        "number_type": None,
        "limit": 20,
        "area_code": None,
        "prefix": None,
        "capabilities": ("voice",),
    }
    assert result["status"] == "READY_FOR_OWNER_ACTION"
    assert result["offers"][0] == {
        "phone_number": "+14165550123",
        "country_code": "CA",
        "region": "ON",
        "locality": "Toronto",
        "region_information": [{"region": "ON", "locality": "Toronto"}],
        "provider": "telnyx",
        "provider_number_id": "provider-number-1",
        "number_type": "local",
        "voice_capability": True,
        "sms_capability": True,
        "mms_capability": False,
        "capabilities": ["sms", "voice"],
        "cost_information": {"monthly_cost": "1.00", "currency": "USD"},
        "monthly_cost": 1.0,
        "monthly_cost_currency": "USD",
        "regulatory_status": "requirements_required",
        "regulatory_requirements": ["proof_of_address"],
        "status": "AVAILABLE",
        "provisioning_state": "READY_FOR_OWNER_ACTION",
        "is_orderable": True,
    }


@pytest.mark.asyncio
async def test_number_provision_and_release_require_explicit_confirmation():
    provider = _FakeTelecomProvider()
    service = VoiceNumberManagementService(provider)
    offer = {"phone_number": "+14165550123", "provider_number_id": "provider-number-1"}

    not_confirmed = await service.provision(
        offer=offer, confirmed=False, connection_id="tenant-voice-connection"
    )
    release_not_confirmed = await service.release(
        provider_number_id="provider-number-1", confirmed=False
    )
    assert not_confirmed["status"] == "READY_FOR_OWNER_ACTION"
    assert release_not_confirmed["status"] == "READY_FOR_OWNER_ACTION"
    assert provider.orders == [] and provider.releases == []

    with pytest.raises(VoiceNumberOwnerActionRequired):
        await service.provision(offer=offer, confirmed=True, connection_id=None)
    assert provider.orders == []

    await service.provision(offer=offer, confirmed=True, connection_id="configured-connection")
    await service.release(provider_number_id="provider-number-1", confirmed=True)
    assert provider.orders == [{
        "phone_number": "+14165550123",
        "connection_id": "configured-connection",
        "messaging_profile_id": None,
    }]
    assert provider.releases == ["provider-number-1"]


@pytest.mark.asyncio
async def test_number_search_rejects_non_iso_country_and_invalid_provider_numbers():
    provider = _FakeTelecomProvider()
    service = VoiceNumberManagementService(provider)

    with pytest.raises(ValueError, match="ISO country code"):
        await service.search(PhoneNumberSearch("Canada"))
    assert provider.search_kwargs is None

    assert service._offer("CA", {"phone_number": "4165550123"}) == {}


@pytest.mark.asyncio
async def test_telnyx_release_accepts_successful_no_content_response():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(204)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        telnyx = TelnyxClient(Settings(TELNYX_API_KEY="test-api-key"), client=client)
        result = await telnyx.release_phone_number("telnyx-number-123")

    assert result == {}
    assert requests[0].method == "DELETE"
    assert requests[0].url.path.endswith("/phone_numbers/telnyx-number-123")


@pytest.mark.asyncio
@pytest.mark.parametrize("country,region,city,area", [
    ("CA", "QC", "Montreal", "514"),
    ("CA", "QC", "Montreal", "438"),
    ("FR", None, "Paris", "1"),
])
async def test_read_only_search_generic_filters_and_real_provider_metadata(country, region, city, area):
    captured = []
    payload = {
        "phone_number": "+14386------",
        "phone_number_type": "local",
        "region_information": [{"region_type": "country_code", "region_name": country}],
        "features": [{"name": "voice"}, {"name": "sms"}, {"name": "mms"}],
        "cost_information": {"monthly_cost": "1.00000", "upfront_cost": "1.00000", "currency": "USD"},
        "regulatory_requirements": [{"requirement_type": "address"}],
    }

    def handler(request):
        captured.append(request)
        return httpx.Response(200, json={"data": [payload]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = VoiceNumberManagementService(TelnyxClient(Settings(TELNYX_API_KEY="secret-test-key"), client))
        result = await service.search(PhoneNumberSearch(
            country, region, city, "local", 3, area, "6", ("voice", "sms"),
        ))
    params = captured[0].url.params
    assert [request.method for request in captured] == ["GET"]
    assert params["filter[country_code]"] == country
    assert params["filter[national_destination_code]"] == area
    assert params["filter[phone_number][starts_with]"] == "6"
    assert params.get_list("filter[features]") == ["voice", "sms"]
    assert params["filter[locality]"] == city
    if region:
        assert params["filter[administrative_area]"] == region
    offer = result["offers"][0]
    assert offer["voice_capability"] is True and offer["sms_capability"] is True
    assert offer["mms_capability"] is True
    assert offer["region"] is None and offer["locality"] is None
    assert offer["is_orderable"] is False
    assert offer["cost_information"] == payload["cost_information"]
    assert offer["regulatory_requirements"] == payload["regulatory_requirements"]
    assert "secret-test-key" not in str(result)


@pytest.mark.asyncio
async def test_exact_inventory_empty_error_is_not_silently_relaxed():
    captured = []

    def handler(request):
        captured.append(request)
        return httpx.Response(400, json={"errors": [{
            "code": "10031", "detail": "No numbers found for the given filters. Please try again with best_effort=true.",
        }]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = VoiceNumberManagementService(TelnyxClient(Settings(TELNYX_API_KEY="test-key"), client))
        result = await service.search(PhoneNumberSearch("CA", area_code="514", limit=3))
    assert result["status"] == "NO_NUMBERS_AVAILABLE"
    assert result["offers"] == []
    assert len(captured) == 1 and captured[0].url.params["filter[best_effort]"] == "false"


@pytest.mark.asyncio
@pytest.mark.parametrize("search_request", [
    PhoneNumberSearch("Canada"), PhoneNumberSearch("CA", area_code="+514"),
    PhoneNumberSearch("CA", number_type="invalid"), PhoneNumberSearch("CA", limit=101),
    PhoneNumberSearch("CA", limit=2, offset=99), PhoneNumberSearch("CA", capabilities=("invalid",)),
])
async def test_bad_search_input_never_contacts_provider(search_request):
    provider = _FakeTelecomProvider()
    with pytest.raises(ValueError):
        await VoiceNumberManagementService(provider).search(search_request)
    assert provider.search_kwargs is None and provider.orders == [] and provider.releases == []


@pytest.mark.asyncio
async def test_bounded_window_and_absent_fields_are_honest():
    provider = _FakeTelecomProvider()

    async def inventory(**kwargs):
        provider.search_kwargs = kwargs
        return [{"phone_number": "+33123456789"}, {"phone_number": "+33123456790"}]

    provider.search_available_numbers = inventory
    result = await VoiceNumberManagementService(provider).search(PhoneNumberSearch("FR", limit=1, offset=1))
    assert provider.search_kwargs["limit"] == 2
    assert result["offers"][0]["phone_number"] == "+33123456790"
    assert result["offers"][0]["country_code"] is None
    assert result["offers"][0]["voice_capability"] is None
    assert result["offers"][0]["monthly_cost"] is None
    assert result["pagination"]["provider_pagination_supported"] is False
    assert result["pagination"]["total_available"] is None


@pytest.fixture
def search_api(monkeypatch):
    reset_rate_limiter()
    provider = _FakeTelecomProvider()
    company_id = uuid4()
    identity = SimpleNamespace(user=SimpleNamespace(id=uuid4(), company_id=company_id, role=UserRole.OWNER))
    checked = []

    def entitlement(_db, tenant_id):
        checked.append(tenant_id)
        if tenant_id != company_id:
            raise HTTPException(403, "Voice access denied")

    monkeypatch.setattr(voice_router, "_ensure_voice_access", entitlement)
    monkeypatch.setattr(voice_router, "_voice_number_service", lambda _settings: VoiceNumberManagementService(provider))
    app = FastAPI()
    app.include_router(voice_router.router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: SimpleNamespace()
    app.dependency_overrides[require_active_subscription] = lambda: None
    app.dependency_overrides[get_current_identity] = lambda: identity
    app.dependency_overrides[get_settings] = lambda: Settings(
        RATE_LIMIT_ENABLED=True, RATE_LIMIT_AI_PER_MINUTE=2, TELNYX_API_KEY="secret-test-key",
    )
    with TestClient(app) as client:
        yield client, app, provider, identity, checked, company_id
    reset_rate_limiter()


def test_search_endpoint_binds_server_tenant_and_never_orders(search_api):
    client, _app, provider, _identity, checked, company_id = search_api
    response = client.get("/api/v1/voice/numbers/search", params={
        "country_code": "CA", "area_code": "514", "organization_id": str(uuid4()), "company_id": str(uuid4()),
    })
    assert response.status_code == 200
    assert checked == [company_id]
    assert "organization_id" not in provider.search_kwargs and "company_id" not in provider.search_kwargs
    assert provider.orders == [] and provider.releases == []


def test_search_endpoint_missing_auth_never_contacts_provider(search_api):
    client, app, provider, *_rest = search_api
    app.dependency_overrides.pop(get_current_identity)
    response = client.get("/api/v1/voice/numbers/search?country_code=CA")
    assert response.status_code == 401
    assert provider.search_kwargs is None


def test_search_endpoint_wrong_tenant_is_denied(search_api):
    client, _app, provider, identity, *_rest = search_api
    identity.user.company_id = uuid4()
    response = client.get("/api/v1/voice/numbers/search?country_code=CA")
    assert response.status_code == 403
    assert provider.search_kwargs is None


def test_search_endpoint_rate_limit_precedes_provider(search_api):
    client, _app, provider, *_rest = search_api
    for _attempt in range(2):
        assert client.get("/api/v1/voice/numbers/search?country_code=CA").status_code == 200
    provider.search_kwargs = None
    assert client.get("/api/v1/voice/numbers/search?country_code=CA").status_code == 429
    assert provider.search_kwargs is None


@pytest.mark.parametrize("failure,expected", [("timeout", 504), ("provider", 502), ("country", 422)])
def test_search_endpoint_errors_never_expose_secret(search_api, caplog, failure, expected):
    client, _app, provider, *_rest = search_api

    async def fail(**kwargs):
        request = httpx.Request("GET", "https://api.telnyx.com/v2/available_phone_numbers")
        if failure == "timeout":
            raise httpx.ReadTimeout("secret-test-key", request=request)
        response = httpx.Response(422 if failure == "country" else 500, request=request)
        raise httpx.HTTPStatusError("secret-test-key", request=request, response=response)

    provider.search_available_numbers = fail
    response = client.get("/api/v1/voice/numbers/search?country_code=ZZ")
    assert response.status_code == expected
    assert "secret-test-key" not in response.text + caplog.text
    assert provider.orders == [] and provider.releases == []