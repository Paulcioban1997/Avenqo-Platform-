"""Opt-in background queue worker; purchases and billing have separate default-off gates."""
import asyncio,logging
from uuid import UUID
from backend.app.database import SessionLocal
from backend.app.services.tenant_rls import apply_tenant_rls
from backend.app.services.voice_provisioning_service import VoiceProvisioningService
from backend.app.services.voice_billing_gateway import VoiceBillingGateway
from backend.app.voice.providers import TelnyxClient
logger=logging.getLogger("avenqo.voice.worker")

def run_once(settings):
    with SessionLocal() as db:
        # Trusted internal worker only; never receives caller-supplied tenant IDs.
        apply_tenant_rls(db,UUID(int=0),bypass=True)
        from backend.app.services.voice_commercial_controls import stop_expired
        asyncio.run(stop_expired(db,settings,TelnyxClient(settings)))
        return asyncio.run(VoiceProvisioningService(db,settings,TelnyxClient(settings),VoiceBillingGateway(settings)).run_one())

async def loop(settings,stop):
    while not stop.is_set():
        try:await asyncio.to_thread(run_once,settings)
        except Exception as exc:logger.warning("Voice worker failed; error_class=%s",type(exc).__name__)
        try:await asyncio.wait_for(stop.wait(),timeout=10)
        except asyncio.TimeoutError:pass
