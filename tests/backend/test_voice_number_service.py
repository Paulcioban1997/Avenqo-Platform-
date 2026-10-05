import pytest
import httpx

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
    }
    assert result["status"] == "READY_FOR_OWNER_ACTION"
    assert result["offers"][0] == {
        "phone_number": "+14165550123",
        "country_code": "CA",
        "region": "ON",
        "locality": "Toronto",
        "provider": "telnyx",
        "provider_number_id": "provider-number-1",
        "number_type": "local",
        "voice_capability": True,
        "sms_capability": True,
        "monthly_cost": 1.0,
        "monthly_cost_currency": "USD",
        "regulatory_status": "requirements_required",
        "regulatory_requirements": ["proof_of_address"],
        "status": "AVAILABLE",
        "provisioning_state": "READY_FOR_OWNER_ACTION",
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