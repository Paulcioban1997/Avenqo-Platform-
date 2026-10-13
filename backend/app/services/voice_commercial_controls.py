"""Scoped termination and signed provider-cost receipts; no strict spend-cap claim."""
import asyncio,hashlib
from datetime import datetime,timezone
from decimal import Decimal
from sqlalchemy import select
from backend.app.models import VoiceCall,VoicePhoneNumber
from backend.app.models.voice_provisioning import VoiceProvisioningOrder,VoiceTelecomCost
from backend.app.voice.quotes import valid_cost
_tasks=set()

def utc(value):return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
def managed_order(db,call):
    return db.scalar(select(VoiceProvisioningOrder).where(VoiceProvisioningOrder.company_id==call.company_id,
        VoiceProvisioningOrder.config_id==call.config_id,VoiceProvisioningOrder.paid_at.is_not(None))
        .order_by(VoiceProvisioningOrder.created_at.desc()).limit(1))

def remaining(call,settings):
    if not call.started_at:return 0.0
    return max(0.0,settings.voice_commercial_max_call_seconds-max(0.0,(datetime.now(timezone.utc)-utc(call.started_at)).total_seconds()))

async def stop_expired(db,settings,client):
    if not settings.voice_commercial_enabled:return 0
    stopped=0
    calls=db.scalars(select(VoiceCall).where(VoiceCall.ended_at.is_(None))).all()
    for call in calls:
        order=managed_order(db,call)
        if not order or remaining(call,settings)>0:continue
        number=db.get(VoicePhoneNumber,order.number_id)
        if not number or number.company_id!=call.company_id or number.config_id!=call.config_id or number.provider_connection_id!=settings.telnyx_voice_connection_id:continue
        if call.telnyx_call_control_id:
            await asyncio.wait_for(client.hangup(call.telnyx_call_control_id),timeout=5)
            stopped+=1  # Provider accepted command; signed hangup still confirms actual termination.
    return stopped

def schedule(db,settings,call):
    if not settings.voice_commercial_enabled or settings.environment not in {"sandbox","production","prod"} or not managed_order(db,call):return
    from backend.app.database import SessionLocal
    from backend.app.services.tenant_rls import apply_tenant_rls
    from backend.app.voice.providers import TelnyxClient
    delay=remaining(call,settings);company_id=call.company_id
    async def timer():
        await asyncio.sleep(delay)
        with SessionLocal() as fresh:
            apply_tenant_rls(fresh,company_id)
            await stop_expired(fresh,settings,TelnyxClient(settings))
    task=asyncio.create_task(timer());_tasks.add(task);task.add_done_callback(_tasks.discard)

def cost_receipt(db,settings,data,payload):
    """Caller must verify Ed25519 first. Resolve solely by stored provider call ID."""
    if str(payload.get("connection_id"))!=settings.telnyx_voice_connection_id:return False
    call=db.scalar(select(VoiceCall).where(VoiceCall.telnyx_call_control_id==payload.get("call_control_id")))
    if not call:return False
    order=managed_order(db,call)
    if not order or order.snapshot["connection_id"]!=settings.telnyx_voice_connection_id:return False
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
