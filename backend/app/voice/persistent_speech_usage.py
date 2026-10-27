"""Persistent call/task attribution through the existing Avenqo credit ledger.

No new billing database, conversion rate or public settlement endpoint. Used by
server-trusted orchestration only. HF phone traffic stays disabled. Synthetic
nonbillable events record measured allocation estimates but debit zero credits.
"""
import hashlib
from decimal import Decimal
from uuid import UUID
from sqlalchemy import select
from backend.app.models import VoiceCall, TenantAIProviderAttempt, TenantAICreditReservation
from backend.app.ai.llm.schemas import LLMUsage, LLMProviderAttempt
from backend.app.voice.open_speech_catalog import PARAKEET, KOKORO


class PersistentSpeechUsage:
    def __init__(self, db, usage_service, tenant, *, call_id, session_id, plan_code, nonbillable=True, pricing=None, tts_artifact=KOKORO):
        self.db, self.usage, self.tenant = db, usage_service, tenant
        self.call_id, self.session_id, self.plan_code = call_id, str(session_id), plan_code
        self.nonbillable = nonbillable
        self.pricing = pricing or {}
        self.tts_artifact = tts_artifact

    def register_inference(self, job_id, role):
        rate = self.pricing.get(role) or {}
        if not self.register(job_id, role, rate_usd_per_compute_second=rate.get("rate"),
                             pricing_source=rate.get("source"), pricing_version=rate.get("version")):
            raise ValueError("Inference already accepted; reconcile without replay")

    def _call(self):
        call = self.db.scalar(select(VoiceCall).where(VoiceCall.id == self.call_id,
            VoiceCall.company_id == self.tenant.company_id).with_for_update().execution_options(populate_existing=True))
        if call is None:
            raise PermissionError("Call does not belong to this tenant")
        return call

    def _store(self, call, job_id, job):
        jobs = dict((call.source_context or {}).get("speech_inference_jobs") or {})
        jobs[job_id] = job
        call.source_context = {**(call.source_context or {}), "speech_inference_jobs": jobs}
        self.db.commit()

    def register(self, job_id, role, *, rate_usd_per_compute_second, pricing_source, pricing_version):
        if str(UUID(job_id)) != job_id or role not in {"asr", "tts"}:
            raise ValueError("Canonical inference job and reviewed role required")
        if rate_usd_per_compute_second is None or not pricing_source or not pricing_version:
            raise ValueError("Unknown pricing: inference admission denied")
        rate = Decimal(str(rate_usd_per_compute_second))
        if not rate.is_finite() or rate < 0 or (rate == 0 and pricing_source != "existing-local-unpaid-lab"):
            raise ValueError("Explicit reviewed compute allocation rate required")
        call = self._call()
        jobs = (call.source_context or {}).get("speech_inference_jobs") or {}
        if job_id in jobs:
            return False  # Reconciliation only, never resubmit accepted inference.
        if call.ended_at is not None:
            raise ValueError("Call ended; new inference is not permitted")
        if len(jobs) >= 1000:
            raise ValueError("Call inference journal is full")
        self.usage.ensure_quota_available(self.tenant.company_id, self.plan_code)
        request_id = hashlib.sha256(f"speech:{self.tenant.company_id}:{self.call_id}:{self.session_id}:{job_id}".encode()).hexdigest()
        claim = self.usage.claim_credit_reservation(self.tenant.company_id, self.plan_code, request_id,
                                                   self.usage.estimate_credits(None))
        call = self._call()  # Reservation commits; reacquire the tenant call lock.
        jobs = (call.source_context or {}).get("speech_inference_jobs") or {}
        if job_id in jobs:
            return False
        artifact = PARAKEET if role == "asr" else self.tts_artifact
        self._store(call, job_id, {"session_id": self.session_id, "request_id": request_id,
            "role": role, "provider": "open_speech", "model": artifact.model_id, "revision": artifact.revision,
            "status": "pending" if claim.acquired else "unknown", "rate": str(rate),
            "pricing_source": pricing_source, "pricing_version": pricing_version, "nonbillable": self.nonbillable})
        return claim.acquired

    def reconcile(self, receipt):
        call = self._call()
        job_id = receipt.get("id")
        job = dict(((call.source_context or {}).get("speech_inference_jobs") or {}).get(job_id) or {})
        if not job or job.get("session_id") != self.session_id:
            raise PermissionError("Receipt not owned by this tenant/call/session")
        if any(receipt.get(k) != job[k] for k in ("role", "model", "revision")):
            raise ValueError("Receipt provenance mismatch")
        if receipt.get("status") not in {"completed", "failed"} or receipt.get("inference_seconds") is None:
            raise ValueError("Unknown work remains reserved and unresolved")
        seconds = Decimal(str(receipt["inference_seconds"]))
        if not seconds.is_finite() or seconds < 0 or seconds > 86400:
            raise ValueError("Invalid measured compute time")
        estimate = seconds * Decimal(job["rate"])
        cost = Decimal(0) if job["nonbillable"] else estimate
        if job.get("status") == "settled":
            if job.get("compute_seconds") != str(seconds) or job.get("estimated_cost_usd") != str(estimate):
                raise ValueError("Conflicting receipt after settlement")
            return job
        request_id = job["request_id"]
        reservation = self.db.scalar(select(TenantAICreditReservation).where(
            TenantAICreditReservation.company_id == self.tenant.company_id,
            TenantAICreditReservation.avenqo_request_id == request_id))
        if reservation is None:
            raise ValueError("Persistent credit reservation missing")
        attempt = self.db.scalar(select(TenantAIProviderAttempt).where(
            TenantAIProviderAttempt.company_id == self.tenant.company_id,
            TenantAIProviderAttempt.avenqo_request_id == request_id,
            TenantAIProviderAttempt.attempt_number == 1))
        if reservation.status != "reserved":
            # A crash may occur after ledger settlement but before call metadata.
            if attempt is None or attempt.provider_request_id != job_id or attempt.provider_cost_usd != cost:
                raise ValueError("Reservation requires manual reconciliation; never assume free work")
        else:
            usage = LLMUsage(provider="open_speech", model=job["model"], provider_request_id=job_id,
                avenqo_request_id=request_id, tenant_id=str(self.tenant.company_id),
                conversation_id=str(call.central_conversation_id) if call.central_conversation_id else None,
                idempotency_key=f"speech:{self.call_id}:{self.session_id}:{job_id}")
            provider_attempt = LLMProviderAttempt(provider="open_speech", model=job["model"],
                operation="voice_compute_" + job["role"], attempt_number=1,
                success=receipt["status"] == "completed", request_status=receipt["status"],
                latency_ms=round(float(seconds) * 1000), usage=usage, provider_cost_usd=cost,
                pricing_version=job["pricing_version"], pricing_source=job["pricing_source"])
            self.usage.settle_reservation(self.tenant.company_id, self.plan_code, request_id,
                                          attempts=(provider_attempt,), count_request=False)
        call = self._call()
        job.update(status="settled", compute_seconds=str(seconds), estimated_cost_usd=str(estimate),
                   ledger_cost_usd=str(cost), receipt_status=receipt["status"])
        self._store(call, job_id, job)
        return job

    def terminate(self):
        call = self._call()
        jobs = {key: dict(value) for key, value in ((call.source_context or {}).get("speech_inference_jobs") or {}).items()}
        for job in jobs.values():
            if job.get("session_id") == self.session_id and job.get("status") != "settled":
                job["status"] = "unknown"
        call.source_context = {**(call.source_context or {}), "speech_inference_jobs": jobs}
        self.db.commit()  # Never release unknown compute as zero-cost on close.
