"""Owner-scoped commercial consent and lifecycle endpoints."""
from typing import Literal
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend.app.config.settings import Settings,get_settings
from backend.app.database import get_db
from backend.app.dependencies.auth import CurrentIdentity,require_permission,require_platform_admin
from backend.app.models import Company
from backend.app.models.voice_provisioning import VoiceNumberTariff,VoiceProvisioningOrder
from backend.app.services.voice_provisioning_service import VoiceProvisioningService,VoiceProvisioningError
from backend.app.services.voice_billing_gateway import VoiceBillingGateway
from backend.app.voice.providers import TelnyxClient
from shared.ai_engine.contracts import TenantContext
router=APIRouter(prefix="/voice/provisioning",tags=["Voice provisioning"])
owner=require_permission("billing:manage")

def service(db,settings):return VoiceProvisioningService(db,settings,TelnyxClient(settings),VoiceBillingGateway(settings))
def tenant(identity):return TenantContext(identity.user.company_id,identity.user.id)
def error(exc):
    if isinstance(exc,PermissionError):return HTTPException(403,"Voice provisioning is not authorized")
    if isinstance(exc,LookupError):return HTTPException(404,"Voice order not found")
    if isinstance(exc,VoiceProvisioningError):return HTTPException(409,str(exc))
    return HTTPException(502,"Voice provider is temporarily unavailable")

class QuoteRequest(BaseModel):
    phone_number:str=Field(pattern=r"^\+[1-9]\d{7,14}$")
    country:str=Field(pattern=r"^[A-Z]{2}$")
    number_type:Literal["local","mobile","national","toll_free","shared_cost"]="local"
    currency:str=Field(default="CAD",pattern=r"^[A-Z]{3}$")

class ConsentRequest(BaseModel):
    consent:bool
    max_initial_amount:int=Field(ge=0)
    monthly_total:int=Field(ge=0)
    allow_crm_bookings:bool=False

class ActionRequest(BaseModel):
    action:Literal["suspend","resume","cancel"]
    confirmed:bool

class TariffRequest(BaseModel):
    country:str=Field(pattern=r"^[A-Z]{2}$")
    number_type:Literal["local","mobile","national","toll_free","shared_cost"]
    currency:str=Field(pattern=r"^[A-Z]{3}$")
    monthly_amount:int=Field(gt=0)
    stripe_price_id:str|None=None
    provider_cost_limits:dict=Field(default_factory=dict)
    approved:bool=False

@router.get("/catalog")
def catalog(identity:CurrentIdentity=Depends(owner),db:Session=Depends(get_db),settings:Settings=Depends(get_settings)):
    rows=db.scalars(select(VoiceNumberTariff)).all()
    return {"commercial_enabled":settings.voice_commercial_enabled,"payments_enabled":settings.voice_commercial_payments_enabled,"purchases_enabled":settings.voice_telecom_purchases_enabled,"standard_provisional":{"amount":499,"currency":"CAD","interval":"month","setup_amount":0,"approved":False},
            "tariffs":[{"id":str(x.id),"country":x.country,"number_type":x.number_type,"currency":x.currency,"monthly_amount":x.monthly_amount,"approved":x.approved} for x in rows],
            "usage_included":False,"automatic_overage_billing":False}

@router.post("/tariffs")
def tariff(request:TariffRequest,identity:CurrentIdentity=Depends(require_platform_admin),db:Session=Depends(get_db)):
    from backend.app.voice.quotes import valid_cost
    if request.approved and (not request.stripe_price_id or not request.provider_cost_limits):raise HTTPException(422,"Approval requires a Stripe price and reviewed provider cost limits")
    for entries in (request.provider_cost_limits.get("monthly",request.provider_cost_limits),request.provider_cost_limits.get("upfront",{})):
        if not isinstance(entries,dict):raise HTTPException(422,"Invalid provider cost limits")
        for currency,cost in entries.items():
            if len(currency)!=3:raise HTTPException(422,"Invalid provider cost currency")
            try:valid_cost(cost)
            except ValueError:raise HTTPException(422,"Invalid provider cost limit") from None
    row=db.scalar(select(VoiceNumberTariff).where(VoiceNumberTariff.country==request.country,VoiceNumberTariff.number_type==request.number_type,VoiceNumberTariff.currency==request.currency))
    if not row:row=VoiceNumberTariff(**request.model_dump());db.add(row)
    else:
        for key,value in request.model_dump().items():setattr(row,key,value)
    db.commit();return {"id":str(row.id),"approved":row.approved}

@router.get("/tariffs")
def admin_tariffs(identity:CurrentIdentity=Depends(require_platform_admin),db:Session=Depends(get_db)):
    return [{"id":str(x.id),"country":x.country,"number_type":x.number_type,"currency":x.currency,"monthly_amount":x.monthly_amount,
             "stripe_price_id":x.stripe_price_id,"provider_cost_limits":x.provider_cost_limits,"approved":x.approved} for x in db.scalars(select(VoiceNumberTariff))]

@router.post("/quote")
async def quote(request:QuoteRequest,identity:CurrentIdentity=Depends(owner),db:Session=Depends(get_db),settings:Settings=Depends(get_settings)):
    try:
        svc=service(db,settings);return svc.public(await svc.quote(tenant(identity),request.phone_number,request.country,request.number_type,request.currency))
    except Exception as exc:db.rollback();raise error(exc) from None

@router.get("/orders")
def orders(identity:CurrentIdentity=Depends(owner),db:Session=Depends(get_db),settings:Settings=Depends(get_settings)):
    svc=service(db,settings)
    try:svc.authorize(tenant(identity),active=False)
    except Exception as exc:raise error(exc) from None
    return [svc.public(x) for x in db.scalars(select(VoiceProvisioningOrder).where(VoiceProvisioningOrder.company_id==identity.user.company_id).order_by(VoiceProvisioningOrder.created_at.desc()).limit(50))]

@router.get("/costs")
def costs(identity:CurrentIdentity=Depends(owner),db:Session=Depends(get_db),settings:Settings=Depends(get_settings)):
    from decimal import Decimal
    from sqlalchemy import func
    from backend.app.models import TenantAIProviderAttempt
    from backend.app.models.voice_provisioning import VoiceTelecomCost
    svc=service(db,settings);svc.authorize(tenant(identity),active=False)
    rows=db.scalars(select(VoiceTelecomCost).where(VoiceTelecomCost.company_id==identity.user.company_id)).all()
    sums={}
    for row in rows:
        for currency,amount in row.costs_by_currency.items():sums[currency]=sums.get(currency,Decimal(0))+Decimal(amount)
    ai=db.scalar(select(func.sum(TenantAIProviderAttempt.provider_cost_usd)).where(TenantAIProviderAttempt.company_id==identity.user.company_id,TenantAIProviderAttempt.module_id.like("voice%"))) or Decimal(0)
    return {"telecom_reported_by_currency":{k:str(v) for k,v in sums.items()},"voice_ai_recorded_usd":str(ai),"telecom_receipts":len(rows),
            "coverage":"reported_telecom_and_voice_audio_only_central_ai_and_late_provider_costs_excluded","strict_combined_spend_cap":False}

@router.post("/orders/{order_id}/confirm")
def confirm(order_id:UUID,request:ConsentRequest,identity:CurrentIdentity=Depends(owner),db:Session=Depends(get_db),settings:Settings=Depends(get_settings)):
    try:
        svc=service(db,settings);return svc.public(svc.confirm(tenant(identity),order_id,**request.model_dump()))
    except Exception as exc:db.rollback();raise error(exc) from None

@router.post("/orders/{order_id}/action")
def action(order_id:UUID,request:ActionRequest,identity:CurrentIdentity=Depends(owner),db:Session=Depends(get_db),settings:Settings=Depends(get_settings)):
    if not request.confirmed:raise HTTPException(422,"Explicit lifecycle confirmation is required")
    try:
        svc=service(db,settings);return svc.public(svc.owner_action(tenant(identity),order_id,request.action))
    except Exception as exc:db.rollback();raise error(exc) from None
