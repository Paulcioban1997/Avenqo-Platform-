"""Commercial saga tests: real registration/database/CRM, mocked provider money and telecom."""
import hashlib,hmac,json,secrets,time
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
from uuid import uuid4
import pytest,stripe
from sqlalchemy import create_engine,select,func
from sqlalchemy.orm import Session
from backend.app.models import Base,BillingAccount,BillingInvoice,CRMAppointment,CRMService,VoiceBusinessConfig,VoicePhoneNumber,VoiceCall
from backend.app.models.voice_provisioning import VoiceNumberTariff,VoiceProvisioningOrder
from backend.app.services.auth_service import AuthService
from backend.app.schemas.auth import RegisterRequest
from backend.app.services.voice_provisioning_service import VoiceProvisioningService,VoiceProvisioningError,now
from backend.app.services.billing_service import BillingService
from backend.app.config.settings import Settings
from shared.ai_engine.contracts import TenantContext

class Telecom:
 def __init__(self):self.orders={};self.writes=[];self.lost=False;self.unavailable=False;self.requirements=False
 async def search_available_numbers(self,**kw):
  if self.unavailable:return []
  return [{'phone_number':p,'phone_number_type':'local','country_code':'CA','features':[{'name':'voice'}],
           'cost_information':{'monthly_cost':'0.50','upfront_cost':'0','currency':'USD'}} for p in ('+15145550001','+15145550002')]
 async def number_requirements(self,*a):return {'status':'requirements_required' if self.requirements else 'verified_no_requirements','requirements':[]}
 async def voice_application(self,c):return {'id':c,'active':True,'webhook_api_version':'2','webhook_event_url':'https://voice.example.test/api/v1/voice/telnyx/webhook'}
 async def order_phone_number(self,**kw):
  self.writes.append(kw);data={'id':f'order_{len(self.writes)}','customer_reference':kw['customer_reference'],'connection_id':kw['connection_id'],'status':'success','phone_numbers':[{'phone_number':kw['phone_number'],'status':'success'}]};self.orders[data['id']]=data
  if self.lost: self.lost=False;raise TimeoutError('Synthetic lost response')
  return {'data':data}
 async def find_number_order(self,ref):return next((x for x in self.orders.values() if x['customer_reference']==ref),None)
 async def get_number_order(self,id):return self.orders[id]
 async def get_owned_number(self,phone):return {'id':'number_'+phone[-2:],'phone_number':phone,'status':'active','connection_id':'test-connection'}
 async def release_phone_number(self,id):return {'deleted':True}

class Billing:
 def __init__(self):self.updates=[];self.invoices={};self.compensations=[];self.metadata={}
 def preview(self,customer,sub,price,date):return {'currency':'CAD','number_monthly_amount':499,'subscription_monthly_before_tax':2999,'monthly_total_before_tax':3498,'initial_invoice_total':574,'initial_amount_due':574,'initial_tax':75,'tax_status':'calculated','price_id':price,'proration_date':date,'subscription_metadata':{'avenqo_company_id':customer.split('_',1)[1]},'livemode':False}
 def add_number(self,o):
  self.updates.append(o.id)
  invoice={'id':'in_'+str(o.id),'customer':o.stripe_customer_id,'subscription':o.stripe_subscription_id,'currency':'cad','livemode':False,'total':574,'amount_due':574,'amount_paid':574,'amount_remaining':0,'subtotal':499,'created':int(time.time()),'status':'paid','lines':{'data':[{'id':'il_voice','price':{'id':o.snapshot['billing']['price_id']},'amount':499,'quantity':1}]},'metadata':{'avenqo_voice_order_id':str(o.id),'avenqo_company_id':str(o.company_id)},'hosted_invoice_url':'https://invoice.stripe.com/i/test'}
  self.invoices[invoice['id']]=invoice;self.metadata[o.stripe_subscription_id]=invoice;return invoice
 def invoice(self,id):return self.invoices[id]
 def subscription(self,id):return {'id':id,'customer':self.metadata[id]['customer'],'metadata':self.metadata[id]['metadata'],'latest_invoice':self.metadata[id]}
 def compensate(self,o,**kwargs):self.compensations.append(o.id)

@pytest.fixture
def setup(tmp_path):
 engine=create_engine(f"sqlite:///{tmp_path/'provisioning.db'}");Base.metadata.create_all(engine);db=Session(engine,expire_on_commit=False)
 settings=Settings();settings.voice_commercial_enabled=True;settings.voice_commercial_payments_enabled=True;settings.voice_telecom_purchases_enabled=True
 settings.telnyx_voice_connection_id='test-connection';settings.telnyx_media_stream_base_url='wss://voice.example.test/api/v1/voice/telnyx/media'
 settings.voice_approved_realtime_models=['gpt-realtime-2.1'];settings.voice_certified_realtime_locales=['fr'];settings.openai_api_key='explicitly-nonsensitive-fixture';settings.telnyx_media_enabled=True;settings.telnyx_media_inbound_enabled=True
 settings.stripe_webhook_secret=secrets.token_urlsafe(32)
 notifier=SimpleNamespace(email_delivery_configured=False,send_new_company=lambda *a,**k:None,send_invoice_paid=lambda *a,**k:None)
 tenants=[]
 for n in ('alpha','beta'):
  company,user,_=AuthService(db,notifier).register(RegisterRequest(company_name='Fixture '+n,company_email=n+'-company@example.com',first_name='Fixture',last_name=n,email=n+'@example.com',password=secrets.token_urlsafe(24)+'Aa1!',country='CA',industry='Garage',selected_modules=['crm','voice'],preferred_language='fr',plan_code='base'))
  company.business_hours={'weekly':{day:[{'open':'09:00','close':'17:00'}] for day in ('monday','tuesday','wednesday','thursday','friday')}}
  acc=db.scalar(select(BillingAccount).where(BillingAccount.company_id==company.id));acc.status='active';acc.stripe_customer_id='cus_'+str(company.id);acc.stripe_subscription_id='sub_'+str(company.id)
  db.add(CRMService(company_id=company.id,name='Test appointment',duration_minutes=30,price=0,currency='CAD',is_active=True))
  tenants.append(TenantContext(company.id,user.id))
 db.add(VoiceNumberTariff(country='CA',number_type='local',currency='CAD',monthly_amount=499,stripe_price_id='price_voice',provider_cost_limits={'USD':'1.00'},approved=True));db.commit()
 from unittest.mock import AsyncMock
 tel=Telecom();bill=Billing();svc=VoiceProvisioningService(db,settings,tel,bill,audio=SimpleNamespace(validate_model=AsyncMock(return_value=True)))
 yield SimpleNamespace(db=db,settings=settings,tenants=tenants,tel=tel,bill=bill,svc=svc,notifier=notifier)
 db.close();engine.dispose()

async def paid_order(env,index=0,*,disable_sales_during_callback=False):
 t=env.tenants[index];o=await env.svc.quote(t,'+1514555000'+str(index+1),'CA','local','CAD')
 env.svc.confirm(t,o.id,consent=True,max_initial_amount=574,monthly_total=3498,allow_crm_bookings=True)
 assert not env.tel.writes
 event={'id':'evt_'+str(o.id),'type':'invoice.paid','data':{'object':env.bill.invoice(o.stripe_invoice_id)}}
 class SignedProvider:
  def construct_event(self,payload,signature,secret):return stripe.Webhook.construct_event(payload,signature,secret).to_dict()
 payload=json.dumps(event).encode();stamp=str(int(time.time()));signature=hmac.new(env.settings.stripe_webhook_secret.encode(),stamp.encode()+b'.'+payload,hashlib.sha256).hexdigest()
 billing=BillingService(env.db,SignedProvider(),env.settings,None,env.notifier)
 if disable_sales_during_callback:env.settings.voice_commercial_enabled=False
 assert billing.process_webhook(payload,'t='+stamp+',v1='+signature)
 assert not billing.process_webhook(payload,'t='+stamp+',v1='+signature)
 assert o.status=='QUEUED'
 return o

@pytest.mark.asyncio
async def test_signed_payment_is_not_lost_when_sales_are_disabled(setup):
 e=setup;o=await paid_order(e,disable_sales_during_callback=True)
 assert o.status=='QUEUED' and o.paid_at is not None
 with pytest.raises(VoiceProvisioningError):await e.svc.run_one()
 assert not e.tel.writes
 e.settings.voice_commercial_enabled=True
 await e.svc.run_one()
 assert o.status=='ACTIVE' and len(e.tel.writes)==1

@pytest.mark.asyncio
async def test_cancel_reconciles_ambiguous_billing_before_releasing_claim(setup):
 e=setup
 o=await e.svc.quote(e.tenants[0],'+15145550001','CA','local','CAD')
 original=e.bill.add_number
 def lost(order):original(order);raise TimeoutError('Synthetic lost response')
 e.bill.add_number=lost
 e.svc.confirm(e.tenants[0],o.id,consent=True,max_initial_amount=574,monthly_total=3498)
 assert o.status=='BILLING_RECONCILE' and o.stripe_invoice_id is None
 e.svc.owner_action(e.tenants[0],o.id,'cancel')
 await e.svc.run_one()
 assert o.status=='CANCELED' and o.stripe_invoice_id
 assert e.bill.compensations==[o.id] and not e.tel.writes

@pytest.mark.asyncio
async def test_registration_payment_two_tenants_provision_agent_invoice_isolation(setup):
 e=setup;a=await paid_order(e);b=await paid_order(e,1)
 assert e.db.scalar(select(func.count()).select_from(BillingInvoice))==2
 for _ in range(2):assert await e.svc.run_one()
 assert a.status==b.status=='ACTIVE' and len(e.tel.writes)==2
 for o in (a,b):
  number=e.db.get(VoicePhoneNumber,o.number_id);config=e.db.get(VoiceBusinessConfig,o.config_id)
  assert number.company_id==config.company_id==o.company_id and config.preferred_language=='fr'
  assert config.enabled and number.provider_number_id
 with pytest.raises(LookupError):e.svc.owned(e.tenants[1],a.id)
 assert e.svc.confirm(e.tenants[0],a.id,consent=True,max_initial_amount=574,monthly_total=3498).id==a.id
 assert len(e.bill.updates)==2 and not await e.svc.run_one()

@pytest.mark.asyncio
async def test_lost_telnyx_response_reconciles_without_second_purchase(setup):
 e=setup;o=await paid_order(e);e.tel.lost=True
 assert await e.svc.run_one();assert o.status=='ORDERING'
 o.available_at=now()-timedelta(seconds=1);e.db.commit()
 assert await e.svc.run_one();assert o.status=='ACTIVE' and len(e.tel.writes)==1

@pytest.mark.asyncio
async def test_payment_failed_never_provisions_and_foreign_invoice_rejected(setup):
 e=setup;o=await e.svc.quote(e.tenants[0],'+15145550001','CA','local','CAD')
 e.svc.confirm(e.tenants[0],o.id,consent=True,max_initial_amount=574,monthly_total=3498)
 assert not await e.svc.run_one() and e.tel.writes==[]
 wrong=dict(e.bill.invoice(o.stripe_invoice_id),customer='foreign_customer')
 with pytest.raises(VoiceProvisioningError):e.svc.handle_verified_event({'type':'invoice.paid','data':{'object':wrong}})
 assert o.status=='AWAITING_PAYMENT'

@pytest.mark.asyncio
@pytest.mark.parametrize('reason',['consent','regulatory','unavailable','margin','disabled','payments'])
async def test_commercial_failure_gates_never_charge_or_order(setup,reason):
 e=setup
 if reason=='regulatory':e.tel.requirements=True
 if reason=='unavailable':e.tel.unavailable=True
 if reason=='margin':e.db.scalar(select(VoiceNumberTariff)).provider_cost_limits={'USD':'0.10'};e.db.commit()
 if reason=='disabled':e.settings.voice_commercial_enabled=False
 if reason in {'consent','payments'}:
  o=await e.svc.quote(e.tenants[0],'+15145550001','CA','local','CAD')
  if reason=='payments':e.settings.voice_commercial_payments_enabled=False
  with pytest.raises(VoiceProvisioningError):e.svc.confirm(e.tenants[0],o.id,consent=reason!='consent',max_initial_amount=574,monthly_total=3498)
 else:
  with pytest.raises(VoiceProvisioningError):await e.svc.quote(e.tenants[0],'+15145550001','CA','local','CAD')
 assert e.bill.updates==[] and e.tel.writes==[]

@pytest.mark.asyncio
async def test_unavailable_after_payment_compensates_only_own_order(setup):
 e=setup;o=await paid_order(e);e.tel.unavailable=True
 await e.svc.run_one();assert o.status=='COMPENSATE' and e.tel.writes==[]
 o.available_at=now()-timedelta(seconds=1);e.db.commit();await e.svc.run_one()
 assert o.status=='REFUNDED' and e.bill.compensations==[o.id]

@pytest.mark.asyncio
async def test_global_purchase_and_audio_gates_stay_off_until_approved(setup):
 e=setup;o=await paid_order(e);e.settings.voice_telecom_purchases_enabled=False
 await e.svc.run_one();assert e.tel.writes==[] and o.status=='QUEUED'
 e.settings.voice_telecom_purchases_enabled=True;e.settings.telnyx_media_inbound_enabled=False
 o.available_at=now()-timedelta(seconds=1);e.db.commit();await e.svc.run_one()
 assert o.status=='READY_FOR_AUDIO' and not e.db.get(VoiceBusinessConfig,o.config_id).enabled

@pytest.mark.asyncio
async def test_owner_suspend_cancel_and_renewal_failure_are_tenant_scoped(setup):
 e=setup;o=await paid_order(e);await e.svc.run_one()
 e.svc.owner_action(e.tenants[0],o.id,'suspend');assert o.status=='SUSPENDED_OWNER'
 assert not e.db.get(VoiceBusinessConfig,o.config_id).enabled
 e.svc.owner_action(e.tenants[0],o.id,'resume');await e.svc.run_one()
 data=dict(e.bill.invoice(o.stripe_invoice_id),status='open')
 e.svc.handle_verified_event({'type':'invoice.payment_failed','data':{'object':data}});e.db.commit()
 assert o.status=='SUSPENDED_PAYMENT'
 e.svc.owner_action(e.tenants[0],o.id,'cancel');await e.svc.run_one()
 assert o.status=='CANCELED' and e.db.get(VoicePhoneNumber,o.number_id).status=='RELEASED'

@pytest.mark.asyncio
async def test_registered_paid_agent_signed_inbound_books_only_own_crm(setup,monkeypatch):
 from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
 from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat
 from fastapi import FastAPI
 from fastapi.testclient import TestClient
 import base64
 from backend.app.routers import voice as vr
 from backend.app.database import get_db
 from backend.app.config.settings import get_settings
 from backend.app.voice.service import VoiceOrchestrator
 e=setup;o=await paid_order(e);await e.svc.run_one()
 cfg=e.db.get(VoiceBusinessConfig,o.config_id)
 cfg.opening_hours={day:{'open':'09:00','close':'17:00'} for day in ('monday','tuesday','wednesday','thursday','friday')};e.db.commit()
 key=Ed25519PrivateKey.generate();e.settings.telnyx_public_key=base64.b64encode(key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)).decode();e.settings.rate_limit_enabled=False
 commands=[]
 class Calls:
  async def answer_call(self,*a,**kw):commands.append('answer')
  async def start_media_stream(self,*a,**kw):commands.append('stream')
 provider=Calls();svc=VoiceOrchestrator(e.db,e.settings,SimpleNamespace(),provider)
 monkeypatch.setattr(vr,'_orchestrator',lambda *a:svc)
 app=FastAPI();app.include_router(vr.router,prefix='/api/v1');app.dependency_overrides[get_db]=lambda:e.db;app.dependency_overrides[get_settings]=lambda:e.settings
 with TestClient(app) as c:
  for kind in ('call.initiated','call.answered'):
   body=json.dumps({'data':{'id':str(uuid4()),'event_type':kind,'payload':{'call_control_id':'synthetic-control','connection_id':'test-connection','direction':'incoming','from':'+15145550999','to':o.phone_number,'tenant_id':str(e.tenants[1].company_id)}}}).encode();stamp=str(int(time.time()))
   response=c.post('/api/v1/voice/telnyx/webhook',content=body,headers={'content-type':'application/json','telnyx-timestamp':stamp,'telnyx-signature-ed25519':base64.b64encode(key.sign(stamp.encode()+b'|'+body)).decode()})
   assert response.status_code==200
 assert commands==['answer','stream']
 call=e.db.scalar(select(VoiceCall).where(VoiceCall.telnyx_call_control_id=='synthetic-control'));assert call.company_id==e.tenants[0].company_id
 from backend.app.voice.auth import VoiceCallerAuth
 auth=VoiceCallerAuth(e.db,e.settings);pin=''.join(str(secrets.randbelow(10)) for _ in range(6))
 # Validate the chosen owner PIN rather than bypassing caller verification.
 auth.set_pin(e.tenants[0],'USER',e.tenants[0].user_id,pin,phone_number='+15145550999')
 e.db.commit();auth.challenge(call)
 assert auth.verify_gather(call,pin)['authenticated'];e.db.commit()
 start=(now()+timedelta(days=3)).replace(hour=18,minute=0,second=0,microsecond=0)
 while start.weekday()>4:start+=timedelta(days=1)
 result=await svc.execute_tool(cfg,'synthetic-control','book-fixture','book_appointment',{'service_name':'Test appointment','starts_at':start.isoformat(),'caller_name':'Fixture caller','caller_phone':'+15145550999','confirmed':True})
 assert result.get('success'),result
 replay=await svc.execute_tool(cfg,'synthetic-control','book-fixture','book_appointment',{'service_name':'Test appointment','starts_at':start.isoformat(),'caller_name':'Fixture caller','caller_phone':'+15145550999','confirmed':True})
 assert replay==result
 rows=e.db.scalars(select(CRMAppointment)).all();assert len(rows)==1 and rows[0].company_id==e.tenants[0].company_id
 foreign=e.db.get(VoiceBusinessConfig,o.config_id)
 assert e.db.scalar(select(func.count()).select_from(CRMAppointment).where(CRMAppointment.company_id==e.tenants[1].company_id))==0

@pytest.mark.asyncio
async def test_number_claim_prevents_two_payments_for_same_tenant_or_number(setup):
 e=setup
 a=await e.svc.quote(e.tenants[0],'+15145550001','CA','local','CAD')
 b=await e.svc.quote(e.tenants[1],'+15145550001','CA','local','CAD')
 c=await e.svc.quote(e.tenants[0],'+15145550002','CA','local','CAD')
 e.svc.confirm(e.tenants[0],a.id,consent=True,max_initial_amount=574,monthly_total=3498)
 for tenant,order in ((e.tenants[1],b),(e.tenants[0],c)):
  with pytest.raises(VoiceProvisioningError):e.svc.confirm(tenant,order.id,consent=True,max_initial_amount=574,monthly_total=3498)
 assert e.bill.updates==[a.id] and e.tel.writes==[]

@pytest.mark.asyncio
async def test_signed_cost_receipt_and_duration_stop_do_not_bill_or_touch_other_tenant(setup):
 from backend.app.services.voice_commercial_controls import cost_receipt,stop_expired
 from backend.app.models.voice_provisioning import VoiceTelecomCost
 from unittest.mock import AsyncMock
 e=setup;o=await paid_order(e);await e.svc.run_one()
 call=VoiceCall(company_id=o.company_id,config_id=o.config_id,telnyx_call_control_id='cost-control',caller_phone='synthetic',status='in_progress',started_at=now()-timedelta(seconds=91))
 e.db.add(call);e.db.commit()
 data={'id':str(uuid4()),'occurred_at':now().isoformat()}
 payload={'call_control_id':'cost-control','connection_id':'test-connection','status':'success','total_cost':'0.02','billed_duration_secs':90,'cost_parts':[{'currency':'USD','cost':'0.02'}]}
 assert cost_receipt(e.db,e.settings,data,payload)
 assert cost_receipt(e.db,e.settings,data,payload)
 assert e.db.scalar(select(func.count()).select_from(VoiceTelecomCost))==1
 assert not cost_receipt(e.db,e.settings,data,dict(payload,connection_id='foreign'))
 client=SimpleNamespace(hangup=AsyncMock())
 assert await stop_expired(e.db,e.settings,client)==1
 client.hangup.assert_awaited_once_with('cost-control')
 assert call.ended_at is None  # Provider callback still needed, never fabricate success.
