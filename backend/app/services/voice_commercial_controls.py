"""Scoped termination and signed provider-cost receipts; no strict spend-cap claim."""
import asyncio,hashlib,logging
from datetime import datetime,timezone
from decimal import Decimal
from sqlalchemy import select
from backend.app.models import VoiceCall,VoicePhoneNumber
from backend.app.models.voice_provisioning import VoiceProvisioningOrder,VoiceTelecomCost
from backend.app.voice.quotes import valid_cost
_tasks=set()
_scheduled=set()
logger=logging.getLogger("avenqo.voice.limits")

def utc(value):return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
def managed_order(db,call):
    return db.scalar(select(VoiceProvisioningOrder).where(VoiceProvisioningOrder.company_id==call.company_id,
        VoiceProvisioningOrder.config_id==call.config_id,VoiceProvisioningOrder.paid_at.is_not(None))
        .order_by(VoiceProvisioningOrder.created_at.desc()).limit(1))

def remaining(call,settings):
    if getattr(settings, "voice_long_calls_enabled", False):
        from backend.app.voice.call_policy import remaining as policy_remaining
        return policy_remaining(call) or 0.0
    if not call.started_at:return 0.0
    return max(0.0,settings.voice_commercial_max_call_seconds-max(0.0,(datetime.now(timezone.utc)-utc(call.started_at)).total_seconds()))

async def stop_expired(db,settings,client):
    if not settings.voice_commercial_enabled and not getattr(settings, "voice_long_calls_enabled", False):return 0
    from uuid import UUID
    from backend.app.services.tenant_rls import apply_tenant_rls
    apply_tenant_rls(db, UUID(int=0), bypass=True)
    stopped=0
    calls=db.scalars(select(VoiceCall).where(VoiceCall.ended_at.is_(None))).all()
    for call in calls:
        order=managed_order(db,call)
        long_mode=getattr(settings, "voice_long_calls_enabled", False)
        expired=remaining(call,settings)<=0
        if long_mode and (call.source_context or {}).get("runtime_policy"):
            from backend.app.voice.call_policy import check
            try:check(db,settings,call)
            except PermissionError:expired=True
        if (not order and not long_mode) or not expired:continue
        if getattr(settings, "voice_long_calls_enabled", False) and not (call.source_context or {}).get("runtime_policy"):continue
        number=db.scalar(select(VoicePhoneNumber).where(VoicePhoneNumber.company_id==call.company_id,
            VoicePhoneNumber.config_id==call.config_id,VoicePhoneNumber.provider=="telnyx",VoicePhoneNumber.status=="ACTIVE"))
        if not number or number.company_id!=call.company_id or number.config_id!=call.config_id or number.provider_connection_id!=settings.telnyx_voice_connection_id:continue
        if call.telnyx_call_control_id:
            await asyncio.wait_for(client.hangup(call.telnyx_call_control_id),timeout=5)
            stopped+=1  # Provider accepted command; signed hangup still confirms actual termination.
    return stopped

def schedule(db,settings,call):
    if settings.environment not in {"sandbox","production","prod"}:return
    if not getattr(settings, "voice_long_calls_enabled", False) and (not settings.voice_commercial_enabled or not managed_order(db,call)):return
    if call.ended_at is not None or call.id in _scheduled:return
    from backend.app.database import SessionLocal
    from backend.app.services.tenant_rls import apply_tenant_rls
    from backend.app.voice.providers import TelnyxClient
    delay=remaining(call,settings);company_id=call.company_id;call_id=call.id
    _scheduled.add(call_id)
    async def timer():
        try:
            await asyncio.sleep(delay)
            for attempt in range(3):
                try:
                    with SessionLocal() as fresh:
                        apply_tenant_rls(fresh,company_id)
                        await stop_expired(fresh,settings,TelnyxClient(settings))
                    return
                except Exception as exc:
                    logger.warning("Voice stop pending; call_id=%s attempt=%s error_class=%s",call_id,attempt+1,type(exc).__name__)
                    if attempt<2:await asyncio.sleep(0.25*2**attempt)
            logger.error("Voice independent manual stop required; call_id=%s",call_id)
        finally:_scheduled.discard(call_id)
    task=asyncio.create_task(timer());_tasks.add(task);task.add_done_callback(_tasks.discard)

def cost_receipt(db,settings,data,payload):
    """Caller must verify Ed25519 first. Resolve solely by stored provider call ID."""
    if str(payload.get("connection_id"))!=settings.telnyx_voice_connection_id:return False
    from uuid import UUID
    from backend.app.services.tenant_rls import apply_tenant_rls
    apply_tenant_rls(db, UUID(int=0), bypass=True)
    call=db.scalar(select(VoiceCall).where(VoiceCall.telnyx_call_control_id==payload.get("call_control_id")))
    if not call:return False
    apply_tenant_rls(db, call.company_id)
    order=managed_order(db,call)
    binding=db.scalar(select(VoicePhoneNumber).where(VoicePhoneNumber.company_id==call.company_id,
        VoicePhoneNumber.config_id==call.config_id,VoicePhoneNumber.provider_connection_id==settings.telnyx_voice_connection_id))
    if not binding or (order and order.snapshot["connection_id"]!=settings.telnyx_voice_connection_id):return False
    event_id=str(data.get("id") or "")
    if not event_id or len(event_id)>255:raise ValueError("Invalid cost event")
    at=datetime.fromisoformat(str(data.get("occurred_at") or payload.get("occurred_at")).replace("Z","+00:00"))
    row=db.get(VoiceTelecomCost,call.id)
    if row and (row.event_id==event_id or utc(row.occurred_at)>=utc(at)):return True
    totals={}
    parts=payload.get("cost_parts") or []
    if not isinstance(parts,list) or len(parts)>50:raise ValueError("Invalid cost parts")
    for part in parts:
        currency=str(part.get("currency") or "").upper()
        if len(currency)!=3 or not currency.isalpha():raise ValueError("Cost currency required")
        totals[currency]=totals.get(currency,Decimal(0))+Decimal(valid_cost(part.get("cost")))
    status="REPORTED" if payload.get("status")=="success" and totals else "UNAVAILABLE"
    if len(totals)==1 and sum(totals.values())!=Decimal(valid_cost(payload.get("total_cost"))):raise ValueError("Provider cost total mismatch")
    values={"company_id":call.company_id,"event_id":event_id,"occurred_at":at,"status":status,
            "costs_by_currency":{k:str(v) for k,v in totals.items()},"billed_seconds":max(0,int(payload.get("billed_duration_secs") or 0))}
    if row:
        for key,value in values.items():setattr(row,key,value)
    else:db.add(VoiceTelecomCost(call_id=call.id,**values))
    db.commit();return True
