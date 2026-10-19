from types import SimpleNamespace
from zoneinfo import ZoneInfo
from datetime import datetime,timedelta
import pytest
from sqlalchemy import create_engine,select
from sqlalchemy.orm import Session
from backend.app.models import Base, VoiceBusinessConfig, UserRole
from backend.app.core.permissions import permissions_for
from backend.app.services.tenant_locale_service import get_profile
from backend.app.services.crm_service import CRMService
from backend.app.models.crm import CRMService as CRMServiceRecord
from backend.app.services.crm_availability_service import CRMAvailabilityService
from backend.app.voice.tool_guard import VoiceToolGuard,VoiceToolDenied
from backend.app.voice.sandbox_preflight import first_call_preflight,MEDIA_BASE_URL
from scripts.voice_sandbox_scenarios import prepare_scenarios
from shared.ai_engine.contracts import TenantContext


def settings(**changes):
    values=dict(environment="sandbox",telnyx_api_key=None,telnyx_public_key=None,telnyx_voice_connection_id=None,telnyx_media_stream_base_url=None,telnyx_media_enabled=False,telnyx_media_inbound_enabled=False,openai_api_key=None,voice_realtime_provider="openai",voice_realtime_model="gpt-realtime-2.1",voice_realtime_supported_locales=["fr","en"],google_calendar_client_id=None,google_calendar_client_secret=None,google_calendar_redirect_uri=None)
    values.update(changes);return SimpleNamespace(**values)


@pytest.mark.parametrize("url",["wss://api.avenqo.ca/api/v1/voice/telnyx/media","ws://avenqo-platform-sandbox.up.railway.app/api/v1/voice/telnyx/media",MEDIA_BASE_URL+"?key=fixture",MEDIA_BASE_URL+"/wrong","wss://avenqo-platform-sandbox.up.railway.app:bad/"])
def test_reject_wrong_media_targets_without_echoing_values(url):
    report=first_call_preflight(settings(telnyx_media_stream_base_url=url))
    assert not report["checks"]["sandbox_wss_url"]
    assert url not in str(report)


def test_presence_does_not_authorize_spend_or_certify_audio():
    report=first_call_preflight(settings(telnyx_api_key=object(),telnyx_public_key=object(),telnyx_voice_connection_id=object(),telnyx_media_stream_base_url=MEDIA_BASE_URL,telnyx_media_enabled=True,telnyx_media_inbound_enabled=True,openai_api_key=object()))
    assert report["configuration_status"]=="PASS"
    assert report["call_status"]=="BLOCKED"
    assert "aggregate_2_cad_ceiling_enforced_and_verified" in report["remaining_gates"]
    assert not report["calendar_sync_configured"]


@pytest.fixture
def scenarios(tmp_path):
    engine=create_engine(f"sqlite:///{tmp_path/'first-call.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        companies=prepare_scenarios(db,environment="test");db.commit()
        # Booking fixtures must declare actual tenant-owned services. Module
        # activation alone is deliberately insufficient to offer appointments.
        for key, name in (("garage-montreal", "Entretien vehicule QA"), ("empresa-espanola", "Reunion QA")):
            company, _ = companies[key]
            service = CRMServiceRecord(company_id=company.id, name=name, duration_minutes=60, currency=company.currency_code, price=0, is_active=True)
            db.add(service); db.flush()
            config = db.scalar(select(VoiceBusinessConfig).where(VoiceBusinessConfig.company_id == company.id))
            config.services = [{"name": name, "crm_service_id": str(service.id)}]
        db.commit()
        yield db,companies
    engine.dispose()


def test_three_logical_agents_languages_permissions_and_isolation(scenarios):
    db,companies=scenarios
    assert len(db.scalars(select(VoiceBusinessConfig)).all())==3
    guard=VoiceToolGuard(db);perms=permissions_for(UserRole.OWNER)
    allowed={"garage-montreal":("check_availability","create_appointment"),"ecommerce-english":("get_product_detail","get_inventory_summary"),"empresa-espanola":("check_availability",)}
    denied={"garage-montreal":("get_product_detail","get_financial_overview"),"ecommerce-english":("create_appointment","get_sales_summary","get_financial_overview"),"empresa-espanola":("create_appointment","get_product_detail","get_financial_overview")}
    for (key,(company,owner)),locale in zip(companies.items(),("fr","en","es")):
        tenant=TenantContext(company.id,owner.id)
        profile=get_profile(db,company.id)
        assert profile.primary_locale==locale and profile.authorized_locales==[locale]
        for tool in allowed[key]:guard.authorize(tenant,tool,perms,user_id=owner.id)
        for tool in denied[key]:
            with pytest.raises(VoiceToolDenied):guard.authorize(tenant,tool,perms,user_id=owner.id)
        other=next(u for c,u in companies.values() if c.id!=company.id)
        with pytest.raises(VoiceToolDenied):guard.authorize(tenant,allowed[key][0],perms,user_id=other.id)


@pytest.mark.asyncio
async def test_garage_tomorrow_1400_booking_without_external_calendar(scenarios):
    db,companies=scenarios;company,owner=companies["garage-montreal"]
    start=(datetime.now(ZoneInfo("America/Montreal"))+timedelta(days=1)).replace(hour=14,minute=0,second=0,microsecond=0)
    availability=CRMAvailabilityService(db)
    assert (await availability.check_availability(company.id,start,duration_minutes=60))["available"]
    crm=CRMService(db)
    client=crm.create_client(company.id,{"first_name":"Synthetic","last_name":"Vehicle QA","email":"vehicle-qa@example.com"})
    appointment,error=await crm.create_appointment(company.id,{"client_id":client.id,"title":"Vehicle QA","start_time":start,"duration_minutes":60,"price":0.0})
    assert error is None and appointment.company_id==company.id
    assert not (await availability.check_availability(company.id,start,duration_minutes=60))["available"]


def test_fixture_writer_refuses_production(scenarios):
    db,_=scenarios
    with pytest.raises(ValueError):prepare_scenarios(db,environment="production")
