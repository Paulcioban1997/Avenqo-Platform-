"""Durable Voice saga. Payment is verified; ambiguous provider writes are never repeated."""
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID
from urllib.parse import urlsplit
from sqlalchemy import select, text, or_
from sqlalchemy.exc import IntegrityError
from backend.app.models import BillingAccount, CompanyMembership, User, VoiceBusinessConfig, VoicePhoneNumber
from backend.app.models.voice_provisioning import VoiceNumberTariff, VoiceProvisioningOrder as Order, VoiceProvisioningClaim as Claim
from backend.app.core.permissions import permissions_for
from backend.app.services.module_entitlement_service import ModuleEntitlementService
from backend.app.services.voice_number_service import VoiceNumberManagementService, PhoneNumberSearch
from backend.app.services.voice_billing_gateway import line_price
from backend.app.voice.service import ensure_voice_business_config
from backend.app.voice.quotes import valid_cost
from shared.ai_engine.contracts import TenantContext
logger = logging.getLogger("avenqo.voice.provisioning")

def now(): return datetime.now(timezone.utc)
def aware(value): return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value

class VoiceProvisioningError(ValueError): pass

class VoiceProvisioningService:
    def __init__(self, db, settings, telecom, billing, audio=None):
        self.db, self.settings, self.telecom, self.billing = db, settings, telecom, billing
        from backend.app.services.voice_realtime_readiness import VoiceRealtimeReadiness
        self.audio=audio or VoiceRealtimeReadiness(settings)

    def audit(self,order,action,actor=None):
        from backend.app.services.audit_log_service import AuditLogService
        AuditLogService(self.db).record(actor_user_id=actor,action=action,target_type="voice_provisioning_order",
            target_id=str(order.id),company_id=order.company_id,metadata={"status":order.status},commit=False)

    def authorize(self, tenant, *, active=True):
        member = self.db.scalar(select(CompanyMembership).where(CompanyMembership.company_id == tenant.company_id,
            CompanyMembership.user_id == tenant.user_id, CompanyMembership.is_active.is_(True)))
        user = self.db.get(User, tenant.user_id)
        if not member or not user or not user.is_active or not {"modules:manage", "billing:manage"} <= set(permissions_for(member.role)):
            raise PermissionError("An active tenant manager is required")
        account = self.db.scalar(select(BillingAccount).where(BillingAccount.company_id == tenant.company_id))
        if active and (not account or account.status not in {"active", "trialing"} or not ModuleEntitlementService(self.db).can_use_module(tenant, "voice")):
            raise PermissionError("Active subscription and Voice module required")
        return account

    def owned(self, tenant, order_id):
        self.authorize(tenant, active=False)
        order = self.db.scalar(select(Order).where(Order.id == order_id, Order.company_id == tenant.company_id).with_for_update())
        if not order: raise LookupError("Voice order not found")
        return order

    def gate(self):
        if not self.settings.voice_commercial_enabled:
            raise VoiceProvisioningError("VOICE_COMMERCIAL_DISABLED")

    async def quote(self, tenant, phone, country, kind, currency):
        self.gate(); account = self.authorize(tenant)
        config=self.db.scalar(select(VoiceBusinessConfig).where(VoiceBusinessConfig.company_id==tenant.company_id))
        if config is None:config=ensure_voice_business_config(self.db,tenant.company_id)
        if (not config or not self.settings.telnyx_media_enabled or not self.settings.telnyx_media_inbound_enabled
            or config.preferred_language not in self.settings.voice_certified_realtime_locales
            or self.settings.voice_realtime_model not in self.settings.voice_approved_realtime_models
            or not await self.audio.validate_model()):
            raise VoiceProvisioningError("VOICE_AUDIO_NOT_APPROVED")
        if not account.stripe_customer_id or not account.stripe_subscription_id:
            raise VoiceProvisioningError("A linked subscription is required; no second subscription is created")
        existing = self.db.scalar(select(VoicePhoneNumber).where(VoicePhoneNumber.company_id == tenant.company_id, VoicePhoneNumber.status != "RELEASED"))
        if existing: raise VoiceProvisioningError("Manage the existing tenant number before ordering another")
        tariff = self.db.scalar(select(VoiceNumberTariff).where(VoiceNumberTariff.country == country.upper(),
            VoiceNumberTariff.number_type == kind, VoiceNumberTariff.currency == currency.upper(), VoiceNumberTariff.approved.is_(True)))
        if not tariff or not tariff.stripe_price_id: raise VoiceProvisioningError("MARKET_PRICE_NOT_APPROVED")
        offers = await VoiceNumberManagementService(self.telecom).search(PhoneNumberSearch(country, number_type=kind, limit=100,prefix=phone.removeprefix("+")))
        offer = next((x for x in offers["offers"] if x["phone_number"] == phone), None)
        if not offer or not offer.get("is_orderable") or not offer.get("voice_capability") or offer.get("country_code")!=country.upper() or offer.get("number_type")!=kind:
            raise VoiceProvisioningError("NUMBER_UNAVAILABLE")
        self.check_cost(offer, tariff.provider_cost_limits)
        regulatory = await self.telecom.number_requirements(phone, country.upper(), kind)
        if regulatory["status"] != "verified_no_requirements": raise VoiceProvisioningError("REGULATORY_REVIEW_REQUIRED")
        preview = self.billing.preview(account.stripe_customer_id, account.stripe_subscription_id, tariff.stripe_price_id, int(now().timestamp()))
        if preview["currency"] != currency.upper() or preview["number_monthly_amount"] != tariff.monthly_amount:
            raise VoiceProvisioningError("STRIPE_PRICE_MISMATCH")
        if self.settings.environment == "sandbox" and preview["livemode"]:
            raise VoiceProvisioningError("LIVE_PAYMENT_FORBIDDEN_IN_SANDBOX")
        order = Order(company_id=tenant.company_id, actor_id=tenant.user_id, phone_number=phone,
            stripe_customer_id=account.stripe_customer_id, stripe_subscription_id=account.stripe_subscription_id,
            snapshot={"offer": offer, "regulatory": regulatory, "billing": preview, "cost_limits": tariff.provider_cost_limits,
                      "connection_id": self.settings.telnyx_voice_connection_id, "setup_amount": 0},
            status="QUOTED", expires_at=now()+timedelta(minutes=5), available_at=now())
        self.db.add(order);self.db.commit()
        return order

    @staticmethod
    def check_cost(offer, limits):
        costs = offer.get("cost_information") or {}
        currency = str(costs.get("currency") or "").upper()
        monthly=limits.get("monthly",limits)
        upfront=limits.get("upfront",{})
        if currency not in monthly or Decimal(valid_cost(costs.get("monthly_cost"))) > Decimal(valid_cost(monthly[currency])):
            raise VoiceProvisioningError("PROVIDER_MARGIN_REVIEW_REQUIRED")
        if Decimal(valid_cost(costs.get("upfront_cost"))) > Decimal(valid_cost(upfront.get(currency,"0"))):
            raise VoiceProvisioningError("UPFRONT_COST_REQUIRES_NEW_TARIFF")

    def confirm(self, tenant, order_id, *, consent, max_initial_amount, monthly_total, allow_crm_bookings=False):
        self.gate(); self.authorize(tenant)
        if not self.settings.voice_commercial_payments_enabled:raise VoiceProvisioningError("COMMERCIAL_PAYMENTS_DISABLED")
        order = self.owned(tenant, order_id)
        if order.actor_id != tenant.user_id: raise PermissionError("The quote belongs to another actor")
        if order.status != "QUOTED": return order
        if not consent or now() >= aware(order.expires_at): raise VoiceProvisioningError("Current explicit consent is required")
        quoted = order.snapshot["billing"]
        if allow_crm_bookings and not ModuleEntitlementService(self.db).can_use_module(tenant,"crm"):
            raise VoiceProvisioningError("CRM module and explicit booking permission required")
        order.snapshot={**order.snapshot,"crm_booking_consent":allow_crm_bookings}
        if max_initial_amount != quoted["initial_amount_due"] or monthly_total != quoted["monthly_total_before_tax"]:
            raise VoiceProvisioningError("The displayed payment amounts changed")
        fresh = self.billing.preview(order.stripe_customer_id, order.stripe_subscription_id, quoted["price_id"], quoted["proration_date"])
        for key in ("currency", "initial_amount_due", "initial_invoice_total", "initial_tax", "monthly_total_before_tax", "monthly_invoice_total", "monthly_tax", "tax_status"):
            if fresh.get(key) != quoted.get(key): raise VoiceProvisioningError("Confirm a new quote; subscription or tax changed")
        if self.db.scalar(select(VoicePhoneNumber).where(VoicePhoneNumber.phone_number == order.phone_number)):
            raise VoiceProvisioningError("The number is already assigned")
        self.db.add(Claim(phone_number=order.phone_number, order_id=order.id,company_id=order.company_id))
        order.consent_at=now(); order.status="BILLING_CREATING"
        self.audit(order,"voice_number_purchase_consented",tenant.user_id)
        try: self.db.commit()
        except IntegrityError:
            self.db.rollback(); raise VoiceProvisioningError("Another confirmed order already claims this number") from None
        # Durable state precedes the write. A timeout goes to read-only reconciliation,
        # never another uncontrolled payment or telecom order.
        try:
            invoice=self.billing.add_number(order)
            self.validate_invoice(order,invoice)
            self.db.refresh(order)
            order.stripe_invoice_id=invoice["id"]; order.invoice_url=invoice.get("hosted_invoice_url")
            if order.status=="BILLING_CREATING":order.status="AWAITING_PAYMENT"
        except Exception:
            order.status="BILLING_RECONCILE";order.error_code="BILLING_OUTCOME_UNKNOWN"
        self.db.commit()
        return order

    def validate_invoice(self, order, invoice):
        subscription = invoice.get("subscription") or (invoice.get("parent") or {}).get("subscription_details", {}).get("subscription")
        if (invoice.get("customer") != order.stripe_customer_id or subscription != order.stripe_subscription_id
            or str(invoice.get("currency", "")).upper() != order.snapshot["billing"]["currency"]
            or bool(invoice.get("livemode")) != order.snapshot["billing"]["livemode"]
            or invoice.get("total") != order.snapshot["billing"]["initial_invoice_total"]):
            raise VoiceProvisioningError("INVOICE_OWNERSHIP_OR_AMOUNT_MISMATCH")
        if order.snapshot["billing"]["price_id"] not in {line_price(x) for x in invoice.get("lines", {}).get("data", [])}:
            raise VoiceProvisioningError("VOICE_INVOICE_LINE_REQUIRED")

    def handle_verified_event(self, event):
        """Called only by BillingService after Stripe signature verification."""
        data=event["data"]["object"]
        if hasattr(data,"to_dict"):data=data.to_dict()
        kind=event["type"]
        subscription=data.get("subscription") or (data.get("parent") or {}).get("subscription_details",{}).get("subscription")
        if kind.startswith("customer.subscription."):subscription=data.get("id")
        orders=list(self.db.scalars(select(Order).where(Order.stripe_subscription_id==subscription))) if subscription else []
        for order in orders:
            if data.get("customer") != order.stripe_customer_id: raise VoiceProvisioningError("Foreign Stripe customer")
            if kind=="invoice.paid":
                # Renewal invoices have different totals; match the specific recurring item.
                relevant=order.snapshot["billing"]["price_id"] in {line_price(x) for x in data.get("lines",{}).get("data",[])}
                if not relevant:continue
                if order.status in {"CANCELED","STOP_REQUESTED","COMPENSATE","REFUNDED","REVIEW_REQUIRED"}:continue
                if order.paid_at is None:
                    metadata=(data.get("parent") or {}).get("subscription_details",{}).get("metadata") or data.get("metadata") or {}
                    if order.stripe_invoice_id != data.get("id") and metadata.get("avenqo_voice_order_id") != str(order.id):continue
                    self.validate_invoice(order,data)
                    if data.get("status")!="paid" or data.get("amount_remaining",0)!=0:continue
                    order.stripe_invoice_id=data["id"];order.invoice_url=data.get("hosted_invoice_url");order.paid_at=now()
                    order.status="QUEUED";order.available_at=now()
                    self.audit(order,"voice_number_payment_verified")
                elif order.status=="SUSPENDED_PAYMENT":
                    order.status="VERIFYING";order.available_at=now()
            elif kind in {"invoice.payment_failed","invoice.marked_uncollectible"}:
                if order.paid_at and order.snapshot["billing"]["price_id"] in {line_price(x) for x in data.get("lines",{}).get("data",[])}:
                    self.suspend(order,"SUSPENDED_PAYMENT")
            elif kind=="customer.subscription.deleted":
                self.suspend(order,"STOP_REQUESTED");order.available_at=now()
            elif kind=="customer.subscription.pending_update_expired" and order.paid_at is None:
                self.suspend(order,"STOP_REQUESTED");order.available_at=now()
            elif kind=="customer.subscription.updated" and order.paid_at:
                prices={x["price"]["id"] for x in data.get("items",{}).get("data",[])}
                if order.snapshot["billing"]["price_id"] not in prices:
                    self.suspend(order,"STOP_REQUESTED");order.available_at=now()
        self.db.flush()

    def suspend(self, order, status):
        if status=="STOP_REQUESTED":order.snapshot={**order.snapshot,"stopped_from":order.status}
        order.status=status
        number=self.db.get(VoicePhoneNumber,order.number_id) if order.number_id else None
        config=self.db.get(VoiceBusinessConfig,order.config_id) if order.config_id else None
        if number and number.company_id==order.company_id:number.status="SUSPENDED"
        if config and config.company_id==order.company_id:config.enabled=False

    def owner_action(self, tenant, order_id, action):
        self.gate();order=self.owned(tenant,order_id)
        if action=="suspend":order.suspended_by_owner=True;self.suspend(order,"SUSPENDED_OWNER")
        elif action=="resume":
            self.authorize(tenant);order.suspended_by_owner=False
            if order.paid_at and order.status=="SUSPENDED_OWNER":order.status="VERIFYING";order.available_at=now()
        elif action=="cancel":self.suspend(order,"STOP_REQUESTED");order.available_at=now()
        else:raise VoiceProvisioningError("Unknown lifecycle action")
        self.db.commit();return order

    async def application_ready(self, order):
        connection=order.snapshot["connection_id"]
        if not connection or connection!=self.settings.telnyx_voice_connection_id:raise VoiceProvisioningError("CONNECTION_CHANGED")
        app=await self.telecom.voice_application(connection)
        stream=urlsplit(self.settings.telnyx_media_stream_base_url or "")
        if stream.scheme!="wss" or not stream.hostname or app.get("id")!=connection or not app.get("active") or app.get("webhook_api_version")!="2" or app.get("webhook_event_url")!=f"https://{stream.netloc}/api/v1/voice/telnyx/webhook":
            raise VoiceProvisioningError("WEBHOOK_CONFIGURATION_REQUIRED")

    async def run_one(self):
        self.gate()
        states=("QUEUED","ORDERING","RECONCILING","VERIFYING","READY_FOR_AUDIO","STOP_REQUESTED","COMPENSATE","BILLING_RECONCILE")
        order=self.db.scalar(select(Order).where(Order.status.in_(states),Order.available_at<=now(),or_(Order.lease_until.is_(None),Order.lease_until<=now())).order_by(Order.available_at).with_for_update(skip_locked=True))
        if not order or order.lease_until and aware(order.lease_until)>now():return False
        order.lease_until=now()+timedelta(minutes=2);order.attempts+=1;self.db.commit()
        try:
            await self.advance(order)
        except Exception as exc:
            self.db.rollback();self.db.refresh(order)
            order.error_code=type(exc).__name__[:64]
            if order.attempts>=5:order.status="REVIEW_REQUIRED"
            logger.warning("Voice provisioning step failed; order_id=%s state=%s error_class=%s",order.id,order.status,type(exc).__name__)
        finally:
            order.lease_until=None;order.available_at=now()+timedelta(seconds=300 if order.status=="READY_FOR_AUDIO" else min(300,10*2**min(order.attempts,5)))
            self.db.commit()
        return True

    async def advance(self, order):
        if order.status=="BILLING_RECONCILE":
            sub=self.billing.subscription(order.stripe_subscription_id)
            invoice=sub.get("latest_invoice")
            if sub.get("customer")!=order.stripe_customer_id or (sub.get("metadata") or {}).get("avenqo_voice_order_id")!=str(order.id):return
            if isinstance(invoice,str):invoice=self.billing.invoice(invoice)
            self.validate_invoice(order,invoice);order.stripe_invoice_id=invoice["id"];order.invoice_url=invoice.get("hosted_invoice_url");order.status="AWAITING_PAYMENT"
            return
        if order.status=="COMPENSATE":
            self.billing.compensate(order);order.status="REFUNDED"
            claim=self.db.get(Claim,order.phone_number)
            if claim and claim.order_id==order.id:self.db.delete(claim)
            self.audit(order,"voice_number_compensated");return
        if order.status=="STOP_REQUESTED":
            if order.snapshot.get("stopped_from") in {"BILLING_CREATING","BILLING_RECONCILE"} and not order.stripe_invoice_id:
                sub=self.billing.subscription(order.stripe_subscription_id)
                if sub.get("customer")!=order.stripe_customer_id or (sub.get("metadata") or {}).get("avenqo_voice_order_id")!=str(order.id):
                    if order.attempts>=5:order.status="REVIEW_REQUIRED"
                    return
                invoice=sub.get("latest_invoice")
                if isinstance(invoice,str):invoice=self.billing.invoice(invoice)
                self.validate_invoice(order,invoice)
                order.stripe_invoice_id=invoice["id"]
                self.db.commit()
            from backend.app.models import VoiceCall
            if order.config_id:
                active_calls=list(self.db.scalars(select(VoiceCall).where(VoiceCall.company_id==order.company_id,
                    VoiceCall.config_id==order.config_id,VoiceCall.ended_at.is_(None))))
                if active_calls:
                    for call in active_calls:
                        if call.telnyx_call_control_id:await self.telecom.hangup(call.telnyx_call_control_id)
                    return  # Wait for signed hangup confirmation before releasing the number.
            if order.snapshot.get("stopped_from") in {"ORDERING","RECONCILING","VERIFYING","READY_FOR_AUDIO","ACTIVE"} and not order.provider_number_id:
                data=await self.telecom.find_number_order(str(order.id))
                if not data:return
                if data.get("status")=="pending":return
                if data.get("status")=="success":
                    owned=await self.telecom.get_owned_number(order.phone_number)
                    if owned.get("connection_id")!=order.snapshot["connection_id"]:raise VoiceProvisioningError("FOREIGN_PROVIDER_NUMBER")
                    order.provider_number_id=owned["id"]
            if order.provider_number_id:
                await self.telecom.release_phone_number(order.provider_number_id)
                if order.number_id:
                    number=self.db.get(VoicePhoneNumber,order.number_id);number.status="RELEASED";number.released_at=now()
                    config=self.db.get(VoiceBusinessConfig,order.config_id)
                    if config and config.company_id==order.company_id:config.telnyx_phone_number=None
            if order.consent_at:self.billing.compensate(order,refund=order.number_id is None)
            order.status="CANCELED"
            claim=self.db.get(Claim,order.phone_number)
            if claim and claim.order_id==order.id:self.db.delete(claim)
            self.audit(order,"voice_number_canceled");return
        if not order.paid_at or not order.consent_at:raise VoiceProvisioningError("Verified payment and consent required")
        account=self.db.scalar(select(BillingAccount).where(BillingAccount.company_id==order.company_id))
        if not account or account.status not in {"active","trialing"} or account.stripe_subscription_id!=order.stripe_subscription_id or not ModuleEntitlementService(self.db).can_use_module(TenantContext(order.company_id),"voice"):
            self.suspend(order,"STOP_REQUESTED");return
        claim=self.db.get(Claim,order.phone_number)
        if not claim or claim.order_id!=order.id:raise VoiceProvisioningError("NUMBER_CLAIM_MISMATCH")
        await self.application_ready(order)
        if order.status=="QUEUED":
            if not self.settings.voice_telecom_purchases_enabled:order.error_code="TELECOM_PURCHASES_DISABLED";return
            offer=order.snapshot["offer"]
            regulatory=await self.telecom.number_requirements(order.phone_number,offer["country_code"],offer["number_type"])
            if regulatory["status"]!="verified_no_requirements":order.status="REGULATORY_REVIEW";return
            search=await VoiceNumberManagementService(self.telecom).search(PhoneNumberSearch(offer["country_code"],number_type=offer["number_type"],limit=100,prefix=order.phone_number.removeprefix("+")))
            fresh=next((x for x in search["offers"] if x["phone_number"]==order.phone_number),None)
            if not fresh:order.status="COMPENSATE";return
            self.check_cost(fresh,order.snapshot["cost_limits"])
            if fresh["cost_information"]!=offer["cost_information"]:order.status="COMPENSATE";return
            self.db.refresh(order)
            if order.status!="QUEUED":return
            order.status="ORDERING";self.db.commit()
            response=await self.telecom.order_phone_number(phone_number=order.phone_number,connection_id=order.snapshot["connection_id"],
                        idempotency_key=f"voice-order:{order.id}",customer_reference=str(order.id))
            data=response.get("data") or {}
            self.db.refresh(order)
            if not data.get("id"):
                if order.status!="STOP_REQUESTED":order.status="RECONCILING"
                return
            order.provider_order_id=data["id"]
            if order.status=="STOP_REQUESTED":self.db.commit();return
            order.status="VERIFYING";self.db.commit()
        if order.status in {"ORDERING","RECONCILING"}:
            # A crashed/ambiguous write is reconciled by the persisted customer reference.
            data=await self.telecom.find_number_order(str(order.id))
            if not data:return
            if data.get("customer_reference")!=str(order.id):raise VoiceProvisioningError("FOREIGN_PROVIDER_ORDER")
            order.provider_order_id=data["id"];order.status="VERIFYING"
            self.db.commit()
        if order.status in {"VERIFYING","READY_FOR_AUDIO"}:
            record=await self.telecom.get_number_order(order.provider_order_id)
            if record.get("customer_reference")!=str(order.id) or record.get("connection_id")!=order.snapshot["connection_id"]:
                raise VoiceProvisioningError("FOREIGN_PROVIDER_ORDER")
            if record.get("status")=="failure":order.status="COMPENSATE";return
            if record.get("status")!="success":return
            if not any(x.get("phone_number")==order.phone_number and x.get("status")=="success" for x in record.get("phone_numbers",[])):return
            owned=await self.telecom.get_owned_number(order.phone_number)
            if owned.get("status")!="active" or owned.get("connection_id")!=order.snapshot["connection_id"]:return
            self.db.refresh(order,with_for_update=True)
            if order.status not in {"VERIFYING","READY_FOR_AUDIO"}:return
            config=ensure_voice_business_config(self.db,order.company_id,order.phone_number)
            self.authorize(TenantContext(order.company_id,order.actor_id))
            if order.snapshot.get("crm_booking_consent") and order.config_id is None:
                from backend.app.services.voice_module_permission_service import VoiceModulePermissionService
                from backend.app.models import CRMService
                grant=VoiceModulePermissionService(self.db)
                for action in ("read_availability","list_slots","create_appointment"):
                    grant.grant(TenantContext(order.company_id,order.actor_id),"crm",action,granted_by=order.actor_id)
                services=list(self.db.scalars(select(CRMService).where(CRMService.company_id==order.company_id,CRMService.is_active.is_(True))))
                config.services=[{"name":x.name,"duration_minutes":x.duration_minutes,"crm_service_id":str(x.id)} for x in services]
                # Use existing tenant schedules/services; never invent a real client's availability.
            number=self.db.scalar(select(VoicePhoneNumber).where(VoicePhoneNumber.phone_number==order.phone_number))
            if number and number.company_id!=order.company_id:raise VoiceProvisioningError("FOREIGN_NUMBER_BINDING")
            if not number:
                offer=order.snapshot["offer"]
                number=VoicePhoneNumber(company_id=order.company_id,config_id=config.id,phone_number=order.phone_number,country_code=offer["country_code"],
                    number_type=offer["number_type"],provider="telnyx",provider_number_id=owned["id"],provider_order_id=order.provider_order_id,
                    provider_connection_id=order.snapshot["connection_id"],capabilities=["voice"],regulatory_status="verified_no_requirements",
                    regulatory_requirements=[],monthly_cost=offer["monthly_cost"],monthly_cost_currency=offer["monthly_cost_currency"],purchased_at=now(),status="SUSPENDED")
                self.db.add(number);self.db.flush()
            order.number_id=number.id;order.config_id=config.id;order.provider_number_id=owned["id"]
            ready=(self.settings.telnyx_media_enabled and self.settings.telnyx_media_inbound_enabled and self.settings.openai_api_key
                and self.settings.voice_realtime_model in self.settings.voice_approved_realtime_models
                and config.preferred_language in self.settings.voice_certified_realtime_locales and not order.suspended_by_owner)
            if ready:ready=await self.audio.validate_model()
            config.enabled=bool(ready);number.status="ACTIVE" if ready else "SUSPENDED"
            order.status="ACTIVE" if ready else "READY_FOR_AUDIO"
            self.audit(order,"voice_number_provider_confirmed")
            if not ready:order.attempts=0;order.available_at=now()+timedelta(minutes=5)
            self.db.commit()

    def public(self,order):
        return {"id":str(order.id),"status":order.status,"phone_number":order.phone_number,"billing":{k:v for k,v in order.snapshot["billing"].items() if k not in {"subscription_metadata","price_id"}},
                "provider_cost":order.snapshot["offer"]["cost_information"],"setup_amount":0,"invoice_url":order.invoice_url,
                "paid":order.paid_at is not None,"error_code":order.error_code,"agent_config_id":str(order.config_id) if order.config_id else None,
                "phone_assigned":bool(order.provider_number_id),"audio_ready":order.status=="ACTIVE" and self.settings.voice_commercial_enabled and self.settings.telnyx_media_enabled and self.settings.telnyx_media_inbound_enabled,"usage_charged_automatically":False}
