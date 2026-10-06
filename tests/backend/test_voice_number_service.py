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
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from backend.app.models import Base, Company, User, CompanyMembership, BillingAccount, VoicePhoneNumber, VoiceBusinessConfig
from backend.app.models.accounting import AccountingTransaction
from backend.app.services.module_entitlement_service import ModuleEntitlementService, ModuleLimitReached
from shared.ai_engine.contracts import TenantContext


@pytest.fixture
def owned_binding_db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'owned-binding.db'}")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        tenants = []
        for slug in ('target-binding', 'other-binding'):
            company = Company(name=slug, slug=slug, email=f'{slug}@example.com', country='CA',
                timezone='America/Toronto', industry='Retail', subscription_plan='base')
            db.add(company); db.flush()
            owner = User(company_id=company.id, first_name='Owner', last_name='Test', email=f'owner-{slug}@example.com',
                password_hash='test', role=UserRole.OWNER, is_active=True)
            db.add(owner); db.flush()
            db.add_all([BillingAccount(company_id=company.id, plan_code='base', status='active'),
                CompanyMembership(company_id=company.id, user_id=owner.id, role=UserRole.OWNER, is_active=True)])
            db.flush()
            tenant = TenantContext(company.id, owner.id)
            entitlements = ModuleEntitlementService(db)
            for key in ('retail', 'crm', 'accounting'):
                entitlements.activate_module(tenant, key)
            tenants.append(tenant)
        entry = AccountingTransaction(company_id=tenants[0].company_id, transaction_date=datetime.now(timezone.utc),
            transaction_type='revenue', category='sales', description='preserve existing accounting', amount=123, currency='CAD')
        db.add(entry); db.commit()
        yield db, tenants[0], tenants[1], entry.id
    engine.dispose()


class OwnedProvider:
    def __init__(self):
        self.reads = 0

    async def get_owned_number(self, phone_number):
        self.reads += 1
        return {'id': 'provider-owned-id', 'phone_number': phone_number, 'status': 'active',
            'country_iso_alpha2': 'CA', 'phone_number_type': 'local', 'connection_id': 'verified-connection'}


@pytest.mark.asyncio
@pytest.mark.parametrize('scenario', ['unconfirmed', 'missing_quote', 'expired', 'wrong_actor', 'wrong_tenant', 'price_changed', 'unknown_requirements', 'requirements_changed', 'pending', 'ambiguous', 'verified'])
async def test_number_purchase_requires_current_actor_quote_and_truthful_provider_verification(owned_binding_db, monkeypatch, scenario):
    import jwt
    from backend.app.schemas.voice import VoiceNumberProvisionRequest
    from backend.app.voice.quotes import signed_number_quote

    db, tenant, other, _entry_id = owned_binding_db
    entitlements = ModuleEntitlementService(db)
    entitlements.deactivate_module(tenant, 'accounting'); entitlements.activate_module(tenant, 'voice')
    db.commit()
    user = db.get(User, tenant.user_id)
    membership = db.scalar(select(CompanyMembership).where(CompanyMembership.user_id == tenant.user_id))
    identity = SimpleNamespace(user=user)
    settings = Settings(AUTH_JWT_SECRET='quote-test-secret-at-least-32-characters', TELNYX_VOICE_CONNECTION_ID='verified-connection')
    offer = {'phone_number': '+14385550123', 'country_code': 'CA', 'number_type': 'local',
        'is_orderable': True, 'cost_information': {'upfront_cost': '1.00', 'monthly_cost': '1.00', 'currency': 'USD'},
        'monthly_cost': 1.0, 'monthly_cost_currency': 'USD', 'voice_capability': True,
        'regulatory_status': 'unknown' if scenario == 'unknown_requirements' else 'verified_no_requirements', 'regulatory_requirements': []}
    token = signed_number_quote(settings, other.company_id if scenario == 'wrong_tenant' else tenant.company_id,
        uuid4() if scenario == 'wrong_actor' else tenant.user_id, offer)
    if scenario == 'expired':
        claims = jwt.decode(token, settings.auth_jwt_secret, algorithms=[settings.auth_jwt_algorithm], audience=settings.auth_jwt_audience)
        claims['exp'] = 1
        token = jwt.encode(claims, settings.auth_jwt_secret, algorithm=settings.auth_jwt_algorithm)
    orders = []

    async def search(_filters):
        refreshed = dict(offer)
        if scenario == 'price_changed': refreshed['cost_information'] = dict(offer['cost_information'], monthly_cost='2.00')
        return {'offers': [refreshed]}

    async def provision(**kwargs):
        orders.append(kwargs)
        if scenario == 'ambiguous': raise TimeoutError('provider-secret-must-not-leak')
        return {'data': {'id': 'order-test-id', 'status': 'pending' if scenario == 'pending' else 'success'}}

    class Telecom:
        async def number_requirements(self, *args):
            return {'status': 'unknown' if scenario == 'requirements_changed' else 'verified_no_requirements', 'requirements': []}

        async def get_owned_number(self, number):
            return {'id': 'verified-owned-id', 'phone_number': number, 'status': 'active', 'connection_id': 'verified-connection'}

    monkeypatch.setattr(voice_router, '_voice_number_service', lambda _: SimpleNamespace(search=search, provision=provision))
    monkeypatch.setattr(voice_router, 'TelnyxClient', lambda _: Telecom())
    request = VoiceNumberProvisionRequest(phone_number=offer['phone_number'], country_code='CA',
        confirmed=scenario != 'unconfirmed', quote_token=None if scenario == 'missing_quote' else token)
    blocked = scenario in {'missing_quote', 'expired', 'wrong_actor', 'wrong_tenant', 'price_changed'}
    if blocked:
        with pytest.raises(HTTPException) as failure:
            await voice_router.provision_voice_number(request, identity, db, settings, membership)
        assert failure.value.status_code == 409
    else:
        result = await voice_router.provision_voice_number(request, identity, db, settings, membership)
        assert result['status'] == {'pending': 'PENDING', 'verified': 'ACTIVE'}.get(scenario, 'READY_FOR_OWNER_ACTION')
        assert 'provider-secret-must-not-leak' not in str(result)
    paid_path = scenario in {'pending', 'ambiguous', 'verified'}
    assert len(orders) == int(paid_path)
    binding = db.scalar(select(VoicePhoneNumber).where(VoicePhoneNumber.phone_number == offer['phone_number']))
    if paid_path:
        assert binding.status == {'pending': 'PENDING', 'ambiguous': 'OUTCOME_UNKNOWN', 'verified': 'ACTIVE'}[scenario]
        if scenario != 'ambiguous': assert binding.provider_order_id == 'order-test-id'
        replay = await voice_router.provision_voice_number(request, identity, db, settings, membership)
        assert replay['number']['id'] == str(binding.id)
        assert len(orders) == 1
    else:
        assert binding is None


@pytest.mark.asyncio
async def test_atomic_accounting_voice_swap_and_owned_binding_preserves_data_and_tenants(owned_binding_db):
    db, tenant, other, entry_id = owned_binding_db
    provider = OwnedProvider()
    manager = VoiceNumberManagementService(provider)
    with db.begin():
        entitlements = ModuleEntitlementService(db)
        with pytest.raises(ModuleLimitReached):
            entitlements.activate_module(tenant, 'voice')
        entitlements.deactivate_module(tenant, 'accounting')
        state = entitlements.activate_module(tenant, 'voice')
        assert set(state.active_modules) == {'retail', 'crm', 'voice'} and state.module_limit == 3
        number = await manager.register_owned_number(db, tenant, '+14385550123', confirmed=True)
        number_id = number.id
    with db.begin():
        replay = await manager.register_owned_number(db, tenant, '+14385550123', confirmed=True)
        assert replay.id == number_id
        assert replay.company_id == tenant.company_id and replay.config_id is None
        assert replay.provider_connection_id == "verified-connection"
        assert db.scalar(select(func.count(VoicePhoneNumber.id))) == 1
        assert db.get(AccountingTransaction, entry_id).amount == 123
        assert set(ModuleEntitlementService(db).get_active_modules(other)) == {'retail', 'crm', 'accounting'}
        assert db.scalar(select(func.count(VoiceBusinessConfig.id))) == 0
        assert db.scalar(select(BillingAccount.plan_code).where(BillingAccount.company_id == tenant.company_id)) == 'base'


@pytest.mark.asyncio
async def test_owned_number_conflict_rolls_back_whole_module_swap(owned_binding_db):
    db, tenant, other, _entry_id = owned_binding_db
    db.add(VoicePhoneNumber(company_id=other.company_id, phone_number='+14385550123', country_code='CA',
        provider='telnyx', provider_number_id='provider-owned-id', number_type='local', status='ACTIVE', capabilities=['voice']))
    db.commit()
    with pytest.raises(PermissionError):
        with db.begin():
            service = ModuleEntitlementService(db)
            service.deactivate_module(tenant, 'accounting'); service.activate_module(tenant, 'voice')
            await VoiceNumberManagementService(OwnedProvider()).register_owned_number(db, tenant, '+14385550123', confirmed=True)
    assert set(ModuleEntitlementService(db).get_active_modules(tenant)) == {'retail', 'crm', 'accounting'}
    number = db.scalar(select(VoicePhoneNumber))
    assert number.company_id == other.company_id


@pytest.mark.asyncio
@pytest.mark.parametrize('denial', ['unconfirmed', 'no_entitlement', 'inactive_subscription', 'wrong_actor', 'insufficient_role'])
async def test_owned_import_denied_before_provider_read(owned_binding_db, denial):
    db, tenant, _other, _entry_id = owned_binding_db
    if denial != 'no_entitlement':
        service = ModuleEntitlementService(db)
        service.deactivate_module(tenant, 'accounting'); service.activate_module(tenant, 'voice')
    if denial == 'inactive_subscription':
        db.scalar(select(BillingAccount).where(BillingAccount.company_id == tenant.company_id)).status = 'past_due'
    if denial == 'wrong_actor': tenant = TenantContext(tenant.company_id, uuid4())
    if denial == 'insufficient_role':
        db.scalar(select(CompanyMembership).where(CompanyMembership.company_id == tenant.company_id)).role = UserRole.VIEWER
    db.commit()
    provider = OwnedProvider()
    with pytest.raises((ValueError, PermissionError)):
        await VoiceNumberManagementService(provider).register_owned_number(db, tenant, '+14385550123', confirmed=denial != 'unconfirmed')
    assert provider.reads == 0
    assert db.scalar(select(func.count(VoicePhoneNumber.id))) == 0


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
async def test_owned_number_read_is_exact_get_only_and_never_returns_porting_pin():
    captured = []

    def handler(request):
        captured.append(request)
        return httpx.Response(200, json={"data": [{
            "id": "owned-id", "phone_number": "+14386075438", "status": "active",
            "connection_id": "configured-connection", "country_iso_alpha2": "CA", "phone_number_type": "local",
            "external_pin": "porting-secret-not-to-return",
        }]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = TelnyxClient(Settings(TELNYX_API_KEY="test-key", TELNYX_VOICE_CONNECTION_ID="configured-connection"), client)
        record = await provider.get_owned_number("+14386075438")
    assert len(captured) == 1 and captured[0].method == "GET"
    assert captured[0].url.params["filter[phone_number]"] == "14386075438"
    assert record["phone_number"] == "+14386075438"
    assert "external_pin" not in record and "porting-secret-not-to-return" not in str(record)


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
async def test_telnyx_call_control_command_paths_and_ids_use_mock_transport_only():
    captured = []

    def handler(request):
        captured.append(request)
        return httpx.Response(200, json={"data": {"result": "ok"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = TelnyxClient(Settings(TELNYX_API_KEY="test-key-only"), client=client)
        await provider.answer_call("control-test", command_id="answer-command")
        await provider.transfer_call("control-test", "sip:agent@sip.retell.example", "+15145550100", command_id="transfer-command", call_reference="internal-call-uuid")
    import json
    assert [item.method for item in captured] == ["POST", "POST"]
    assert [item.url.path for item in captured] == ["/v2/calls/control-test/actions/answer", "/v2/calls/control-test/actions/transfer"]
    assert json.loads(captured[0].content) == {"command_id": "answer-command"}
    assert json.loads(captured[1].content) == {"to": "sip:agent@sip.retell.example", "from": "+15145550100", "timeout_secs": 30, "command_id": "transfer-command", "custom_headers": [{"name": "X-Avenqo-Call-ID", "value": "internal-call-uuid"}], "mute_dtmf": "both"}


@pytest.mark.asyncio
async def test_telnyx_gather_and_regulatory_lookup_are_scoped_and_whitelisted():
    captured = []

    def handler(request):
        captured.append(request)
        if request.url.path.endswith("/regulatory_requirements"):
            return httpx.Response(200, json={"data": [{"country_code": "CA", "phone_number_type": "local", "action": "ordering",
                "regulatory_requirements": [{"id": "proof-of-address", "name": "Address", "description": "Provide address", "field_type": "address", "acceptance_criteria": ["residential"], "secret": "must-not-leak"}]}]})
        return httpx.Response(200, json={"data": {"result": "ok"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = TelnyxClient(Settings(TELNYX_API_KEY="test-key-only"), client=client)
        await provider.gather_pin("control-test", command_id="gather-command", client_state="opaque-challenge")
        result = await provider.number_requirements("+14165550123", "CA", "local")
    import json
    gather = json.loads(captured[0].content)
    assert captured[0].method == "POST" and captured[0].url.path.endswith("/actions/gather")
    assert "digits" not in gather and "pin" not in str(gather).lower()
    assert gather["maximum_digits"] == 12 and gather["maximum_tries"] == 1
    assert captured[1].url.params["filter[phone_number]"] == "+14165550123"
    assert captured[1].url.params["filter[action]"] == "ordering"
    assert result["status"] == "requirements_required"
    assert "secret" not in str(result)


@pytest.mark.asyncio
async def test_telnyx_regulatory_lookup_unknown_is_not_treated_as_empty_requirements():
    def handler(_request):
        return httpx.Response(200, json={"data": [{"country_code": "US", "phone_number_type": "local", "action": "ordering", "regulatory_requirements": []}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = TelnyxClient(Settings(TELNYX_API_KEY="test-key-only"), client=client)
        result = await provider.number_requirements("+14165550123", "CA", "local")
    assert result == {"status": "unknown", "requirements": []}


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