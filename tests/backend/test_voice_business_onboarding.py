"""Business configuration and persistent synthetic credits; isolated databases only."""
from decimal import Decimal
from uuid import uuid4
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.backend.test_voice_module_permissions import _engine, _company, _activate, _grant, BOOKING, RETAIL
from backend.app.models import VoiceBusinessConfig, VoiceCall, TenantAIProviderAttempt, TenantAICreditReservation, TenantAICreditLedgerEntry
from backend.app.models.crm import CRMService
from backend.app.schemas.voice_onboarding import VoiceBusinessProfileRequest
from backend.app.services.voice_onboarding_service import VoiceOnboardingService, VoiceProfileConflict
from backend.app.services.company_intelligence_service import CompanyIntelligenceService
from backend.app.voice.tool_guard import VoiceToolGuard, VoiceToolDenied
from backend.app.voice.caller_scope import PUBLIC_VOICE_CALLER_PERMISSIONS
from backend.app.voice.persistent_speech_usage import PersistentSpeechUsage
from backend.app.voice.open_speech_catalog import PARAKEET
from backend.app.ai.usage.service import AIUsageService
from backend.app.ai.usage.policy import AIQuotaPolicy
from backend.app.config.settings import Settings
from shared.ai_engine.contracts import TenantContext


def request(company, **changes):
    return VoiceBusinessProfileRequest(business_name=company.name, industry="Custom mixed demonstration",
        **changes)


@pytest.mark.parametrize("modules", [("voice","retail"), ("voice","crm"), ("voice","retail","crm")])
def test_extensible_business_profile_and_canonical_catalog(tmp_path, modules):
    with Session(_engine(tmp_path, "profile.db")) as db:
        c, owner = _company(db, "business"); tenant = _activate(db,c,*modules)
        svc = db.scalar(select(CRMService).where(CRMService.company_id==c.id))
        ids=[svc.id] if "crm" in modules else []
        result=VoiceOnboardingService(db).save(tenant,owner.id,request(c,bookable_service_ids=ids,
            allowed_actions=[f"{m}:{a}" for m,a in BOOKING+RETAIL]))
        assert result["profile"]["industry"]=="Custom mixed demonstration"
        assert result["readiness"]["booking_configured"] == ("crm" in modules)
        assert result["readiness"]["telephone_verified"] is False
        if ids:
            assert CompanyIntelligenceService(db).get_profile(c.id).configured_crm_services[0]["id"]==str(svc.id)
        assert not result["readiness"]["booking_authorized"]  # Selecting UI capabilities grants nothing.


def test_stale_update_foreign_service_and_foreign_owner_rejected(tmp_path):
    with Session(_engine(tmp_path,"scope.db")) as db:
        c, owner=_company(db,"one"); tenant=_activate(db,c,"voice","crm")
        other, stranger=_company(db,"two");_activate(db,other,"voice","crm")
        foreign=db.scalar(select(CRMService).where(CRMService.company_id==other.id))
        service=VoiceOnboardingService(db)
        with pytest.raises(PermissionError): service.save(tenant,stranger.id,request(c))
        with pytest.raises(ValueError): service.save(tenant,owner.id,request(c,bookable_service_ids=[foreign.id]))
        old=CompanyIntelligenceService(db).get_profile(c.id).context_version
        result=service.save(tenant,owner.id,request(c,description="Actual company products"))
        assert result["context_version"]!=old
        with pytest.raises(VoiceProfileConflict): service.save(tenant,owner.id,request(c))


def test_selected_actions_only_restrict_existing_grants_and_public_stays_denied(tmp_path):
    with Session(_engine(tmp_path,"capability.db")) as db:
        c, owner=_company(db,"capability");tenant=_activate(db,c,"voice","retail")
        _grant(db,c,RETAIL,owner.id)
        service=VoiceOnboardingService(db)
        service.save(tenant,owner.id,request(c,allowed_actions=["retail:read_products"]))
        guard=VoiceToolGuard(db)
        guard.authorize(tenant,"get_product_detail",{"ai:use","data:read"},user_id=owner.id)
        with pytest.raises(VoiceToolDenied): guard.authorize(tenant,"get_sales_summary",{"ai:use","data:read"},user_id=owner.id)
        with pytest.raises(VoiceToolDenied): guard.authorize(tenant,"get_product_detail",PUBLIC_VOICE_CALLER_PERMISSIONS,user_id=owner.id)


def test_persistent_receipt_survives_session_close_and_settles_once(tmp_path):
    engine=_engine(tmp_path,"ledger.db")
    session_id,job_id=uuid4(),str(uuid4())
    with Session(engine) as db:
        c,owner=_company(db,"ledger");tenant=_activate(db,c,"voice","crm")
        cfg=db.scalar(select(VoiceBusinessConfig).where(VoiceBusinessConfig.company_id==c.id))
        call=VoiceCall(company_id=c.id,config_id=cfg.id,caller_phone="+15555550111",status="in_progress")
        db.add(call);db.commit();cid,callid=c.id,call.id
        usage=AIUsageService(db,AIQuotaPolicy(Settings(_env_file=None,ENVIRONMENT="test")))
        ledger=PersistentSpeechUsage(db,usage,tenant,call_id=call.id,session_id=session_id,plan_code="professional")
        assert ledger.register(job_id,"asr",rate_usd_per_compute_second="0.01",pricing_source="synthetic-allocation",pricing_version="fixture-v1")
        ledger.terminate()
    with Session(engine) as db:
        usage=AIUsageService(db,AIQuotaPolicy(Settings(_env_file=None,ENVIRONMENT="test")))
        ledger=PersistentSpeechUsage(db,usage,TenantContext(cid),call_id=callid,session_id=session_id,plan_code="professional")
        receipt={"id":job_id,"role":"asr","model":PARAKEET.model_id,"revision":PARAKEET.revision,"status":"completed","inference_seconds":2.5}
        result=ledger.reconcile(receipt)
        assert result["estimated_cost_usd"]=="0.025" and result["ledger_cost_usd"]=="0"
        ledger.reconcile(receipt)
        assert len(db.scalars(select(TenantAIProviderAttempt).where(TenantAIProviderAttempt.company_id==cid)).all())==1
        reservation=db.scalar(select(TenantAICreditReservation).where(TenantAICreditReservation.company_id==cid))
        assert reservation.actual_credits==0 and reservation.status=="released"
        assert db.scalar(select(TenantAICreditLedgerEntry).where(TenantAICreditLedgerEntry.company_id==cid)) is not None
        with pytest.raises(ValueError): ledger.reconcile({**receipt,"inference_seconds":3})
        other, _=_company(db,"foreign-ledger");db.commit()
        wrong=PersistentSpeechUsage(db,usage,TenantContext(other.id),call_id=callid,session_id=session_id,plan_code="professional")
        with pytest.raises(PermissionError): wrong.reconcile(receipt)


def test_unknown_pricing_never_reserves_or_debits(tmp_path):
    with Session(_engine(tmp_path,"unknown.db")) as db:
        c,owner=_company(db,"unknown");_activate(db,c,"voice","crm")
        usage=AIUsageService(db,AIQuotaPolicy(Settings(_env_file=None,ENVIRONMENT="test")))
        ledger=PersistentSpeechUsage(db,usage,TenantContext(c.id),call_id=uuid4(),session_id=uuid4(),plan_code="professional")
        with pytest.raises(ValueError): ledger.register(str(uuid4()),"asr",rate_usd_per_compute_second=None,pricing_source="",pricing_version="")
        assert not db.scalars(select(TenantAICreditReservation)).all()


def test_crash_after_credit_commit_recovers_without_duplicate_usage(tmp_path, monkeypatch):
    with Session(_engine(tmp_path,"crash.db")) as db:
        c,owner=_company(db,"crash");tenant=_activate(db,c,"voice","crm")
        cfg=db.scalar(select(VoiceBusinessConfig).where(VoiceBusinessConfig.company_id==c.id))
        call=VoiceCall(company_id=c.id,config_id=cfg.id,caller_phone="+15555550112",status="in_progress")
        db.add(call);db.commit()
        usage=AIUsageService(db,AIQuotaPolicy(Settings(_env_file=None,ENVIRONMENT="test")))
        sid,job=uuid4(),str(uuid4())
        ledger=PersistentSpeechUsage(db,usage,tenant,call_id=call.id,session_id=sid,plan_code="professional")
        ledger.register(job,"asr",rate_usd_per_compute_second=0,pricing_source="existing-local-unpaid-lab",pricing_version="fixture")
        real_store=ledger._store
        monkeypatch.setattr(ledger,"_store",lambda *args: (_ for _ in ()).throw(RuntimeError("fixture process failure")))
        receipt={"id":job,"role":"asr","model":PARAKEET.model_id,"revision":PARAKEET.revision,"status":"failed","inference_seconds":1}
        with pytest.raises(RuntimeError): ledger.reconcile(receipt)
        monkeypatch.setattr(ledger,"_store",real_store)
        assert ledger.reconcile(receipt)["status"]=="settled"
        assert len(db.scalars(select(TenantAIProviderAttempt).where(TenantAIProviderAttempt.company_id==c.id)).all())==1


def test_context_refresh_uses_canonical_service_after_crm_rename(tmp_path):
    engine=_engine(tmp_path,"refresh.db")
    with Session(engine) as first:
        c,owner=_company(first,"rename");tenant=_activate(first,c,"voice","crm")
        svc=first.scalar(select(CRMService).where(CRMService.company_id==c.id))
        sid,cid=svc.id,c.id
        service=VoiceOnboardingService(first)
        service.save(tenant,owner.id,request(c,bookable_service_ids=[sid]))
        before=CompanyIntelligenceService(first).get_profile(cid)
        with Session(engine) as second:
            row=second.get(CRMService,sid);row.name="Real product consultation";row.duration_minutes=45;second.commit()
        after=CompanyIntelligenceService(first).get_profile(cid)
        assert after.context_version!=before.context_version
        assert after.configured_crm_services[0]["duration_minutes"]==45
        assert after.configured_crm_services[0]["id"]==str(sid)


@pytest.mark.asyncio
async def test_canonical_service_id_refuses_foreign_service_before_any_booking(tmp_path):
    from backend.app.ai.tools.business.crm_tools import CreateAppointmentTool, CreateAppointmentArgs
    from backend.app.ai.tools.contracts import ToolExecutionContext
    with Session(_engine(tmp_path,"canonical.db")) as db:
        c,owner=_company(db,"canonical");tenant=_activate(db,c,"voice","crm")
        other,_=_company(db,"canonical-other");_activate(db,other,"voice","crm")
        foreign=db.scalar(select(CRMService).where(CRMService.company_id==other.id))
        context=ToolExecutionContext(tenant=tenant,user_id=owner.id,request_id=str(uuid4()),
            permissions=frozenset({"ai:use","crm:appointments:write"}),voice_path=True)
        result=await CreateAppointmentTool(db).run(context,CreateAppointmentArgs(client_name_or_id="Fixture",start_time="2030-01-07T14:00:00-05:00",
            title="Fixture",service_id=foreign.id,confirmed=True))
        assert not result.success and result.data["state"]=="UNSUPPORTED_SERVICE"


@pytest.mark.asyncio
async def test_cancelled_client_close_reconciles_existing_credit_ledger(tmp_path):
    import asyncio
    import secrets
    import httpx
    from backend.app.voice.open_speech import OpenSpeechClient, OpenSpeechConfig
    with Session(_engine(tmp_path,"client-ledger.db")) as db:
        c,owner=_company(db,"client-ledger");tenant=_activate(db,c,"voice","crm")
        cfg=db.scalar(select(VoiceBusinessConfig).where(VoiceBusinessConfig.company_id==c.id))
        call=VoiceCall(company_id=c.id,config_id=cfg.id,caller_phone="+15555550113",status="in_progress")
        db.add(call);db.commit()
        usage=AIUsageService(db,AIQuotaPolicy(Settings(_env_file=None,ENVIRONMENT="test")))
        ledger=PersistentSpeechUsage(db,usage,tenant,call_id=call.id,session_id=uuid4(),plan_code="professional",
            pricing={"asr":{"rate":0,"source":"existing-local-unpaid-lab","version":"fixture"}})
        seen=[]
        async def handler(req):
            seen.append(req.method)
            if req.method=="POST": raise asyncio.CancelledError()
            return httpx.Response(200,json={"id":req.url.path.rsplit("/",1)[-1],"model":PARAKEET.model_id,
                "revision":PARAKEET.revision,"role":"asr","status":"completed","inference_seconds":1})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client=OpenSpeechClient(OpenSpeechConfig("http://localhost:1","http://localhost:2",secrets.token_urlsafe(32)),
                                    client=http,usage_ledger=ledger)
            with pytest.raises(asyncio.CancelledError): await client.transcribe(b"\0\0"*2400)
            await client.close()
        assert seen==["POST","GET"]
        assert db.scalar(select(TenantAIProviderAttempt).where(TenantAIProviderAttempt.company_id==c.id)) is not None
        assert all(job["status"]=="settled" for job in db.get(VoiceCall,call.id,populate_existing=True).source_context["speech_inference_jobs"].values())
