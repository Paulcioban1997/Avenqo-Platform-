from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.config.settings import Settings
from backend.app.models import (
    AIConversation,
    Company,
    CompanyModule,
    CompanyModuleStatus,
    CommerceConnection,
    CommerceConnectionStatus,
    Dataset,
    DatasetStatus,
    RetailActiveSource,
    RetailSourceState,
    TenantAIProviderAttempt,
    Module,
    VoiceBusinessConfig,
    VoiceCall,
    VoiceCentralSession,
    VoicePhoneNumber,
)
from backend.app.services.data_freshness_service import DataFreshnessService
from backend.app.services.module_entitlement_service import ModuleEntitlementService
from shared.ai_engine.contracts import TenantContext


class VoiceHealthService:
    """Safe platform-admin voice operations inventory; never performs provider probes."""

    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._freshness = DataFreshnessService()

    def list_tenants(self) -> dict[str, Any]:
        configs = self._session.scalars(
            select(VoiceBusinessConfig).order_by(VoiceBusinessConfig.created_at.desc())
        ).all()
        numbers = self._session.scalars(select(VoicePhoneNumber).where(VoicePhoneNumber.status == "ACTIVE")).all()
        entitled_ids = set(self._session.scalars(
            select(CompanyModule.company_id).join(Module, Module.id == CompanyModule.module_id).where(
                Module.code == "voice", CompanyModule.status == CompanyModuleStatus.ACTIVE,
            )
        ).all())
        tenant_ids = {item.company_id for item in configs} | {item.company_id for item in numbers} | entitled_ids
        companies = {company.id: company for company in self._session.scalars(
            select(Company).where(Company.id.in_(tenant_ids))
        ).all()} if tenant_ids else {}
        config_by_company = {item.company_id: item for item in configs}
        number_by_company = {}
        for number in numbers:
            number_by_company.setdefault(number.company_id, number)
        tenants = []
        for company_id in tenant_ids:
            company = companies.get(company_id)
            if company is None:
                continue
            entitlement = ModuleEntitlementService(self._session).summary(TenantContext(company_id))
            config = config_by_company.get(company_id)
            number = number_by_company.get(company_id)
            tenants.append(self._tenant_health(config, company, number, entitlement.plan_code,
                entitlement.subscription_status, entitlement.active_modules))
        tenants.sort(key=lambda item: (item["company_name"].casefold(), item["company_id"]))
        return {
            "provider_configuration": {
                "telnyx": "CONFIGURED" if self._settings.telnyx_api_key and self._settings.telnyx_public_key else "NOT_CONFIGURED",
                "retell": "CONFIGURED" if self._settings.retell_api_key else "NOT_CONFIGURED",
                "stt": "CONFIGURED" if self._settings.voice_stt_provider and self._settings.openai_api_key else "NOT_CONFIGURED",
                "tts": "CONFIGURED" if self._settings.voice_tts_provider and self._settings.openai_api_key else "NOT_CONFIGURED",
                "realtime": "CONFIGURED" if self._settings.voice_realtime_provider and self._settings.voice_realtime_model and self._settings.openai_api_key and self._settings.voice_realtime_supported_locales else "NOT_CONFIGURED",
                "health_probe": "NOT_CHECKED",
            },
            "tenants": tenants,
            "generated_at": datetime.now(timezone.utc),
        }

    def _tenant_health(self, config: VoiceBusinessConfig | None, company: Company,
                       number: VoicePhoneNumber | None, plan_code: str, subscription_status: str,
                       active_modules: tuple[str, ...]) -> dict[str, Any]:
        company_id = company.id
        voice_entitled = "voice" in active_modules
        calls = self._session.scalars(
            select(VoiceCall)
            .where(VoiceCall.config_id == config.id)
            .order_by(VoiceCall.started_at.desc())
            .limit(500)
        ).all() if config is not None else []
        calls_count = int(self._session.scalar(
            select(func.count(VoiceCall.id)).where(VoiceCall.config_id == config.id)
        ) or 0) if config is not None else 0
        central_sessions = self._session.scalars(
            select(VoiceCentralSession).where(VoiceCentralSession.company_id == config.company_id)
        ).all() if config is not None else self._session.scalars(
            select(VoiceCentralSession).where(VoiceCentralSession.company_id == company.id)
        ).all()
        conversation_ids = {item.conversation_id for item in central_sessions}
        conversation_ids.update(item.central_conversation_id for item in calls if item.central_conversation_id is not None)
        attempts = self._session.scalars(
            select(TenantAIProviderAttempt).where(
                TenantAIProviderAttempt.company_id == company_id,
                TenantAIProviderAttempt.conversation_id.in_(conversation_ids),
            )
        ).all() if conversation_ids else []

        last_call = max((self._utc(item.started_at) for item in calls if item.started_at is not None), default=None)
        last_success = max(
            (
                self._utc(ts)
                for item in calls
                if item.status in {"ended", "appointment_booked", "appointment_cancelled", "transferred"}
                for ts in [item.ended_at or item.started_at]
                if ts is not None
            ),
            default=None,
        )
        last_failure = max(
            (
                self._utc(ts)
                for item in calls
                if item.status in {"failed", "rejected"}
                for ts in [item.ended_at or item.started_at]
                if ts is not None
            ),
            default=None,
        )
        duration_seconds = sum(
            max(0, int((self._utc(item.ended_at) - self._utc(item.started_at)).total_seconds()))
            for item in calls
            if item.started_at is not None and item.ended_at is not None
        )
        speech_seconds = sum(float(item.stt_input_seconds or 0) + float(item.tts_output_seconds or 0) for item in central_sessions)
        credits = sum(int(item.avenqo_credits_charged or 0) for item in attempts)
        cost = sum((Decimal(item.provider_cost_usd or 0) for item in attempts), Decimal("0"))
        freshness = self._tenant_freshness(company_id)

        return {
            "company_id": str(company_id),
            "company_name": company.name,
            "voice_status": "ENABLED" if config is not None and config.enabled else "DISABLED" if config is not None else "AUDIO_CONFIGURATION_REQUIRED" if voice_entitled and number is not None else "NO_NUMBER_ASSIGNED" if voice_entitled else "MODULE_INACTIVE",
            "plan_code": plan_code,
            "subscription_status": subscription_status,
            "active_modules": list(active_modules),
            "voice_entitled": voice_entitled,
            "number_status": number.status if number is not None else "NOT_CONFIGURED",
            "configuration_status": "AUDIO_READY" if config is not None and config.enabled else "MODULE_INACTIVE" if not voice_entitled else "AUDIO_CONFIGURATION_REQUIRED" if config is not None or number is not None else "NOT_CONFIGURED",
            "phone_number": number.phone_number if number is not None else config.telnyx_phone_number if config is not None else None,
            "country": company.country,
            "region": company.region,
            "provider": "telnyx",
            "telnyx_webhook_status": "CONFIGURED" if self._settings.telnyx_public_key else "NOT_CONFIGURED",
            "retell_status": "CONFIGURED" if self._settings.retell_api_key else "NOT_CONFIGURED",
            "stt_provider": "CONFIGURED" if self._settings.voice_stt_provider and self._settings.openai_api_key else "NOT_CONFIGURED",
            "tts_provider": "CONFIGURED" if self._settings.voice_tts_provider and self._settings.openai_api_key else "NOT_CONFIGURED",
            "realtime_status": "CONFIGURED" if self._settings.voice_realtime_provider and self._settings.voice_realtime_model and self._settings.openai_api_key and self._settings.voice_realtime_supported_locales else "NOT_CONFIGURED",
            "realtime_supported_locales": sorted(self._settings.voice_realtime_supported_locales),
            "last_interaction_at": last_call,
            "last_successful_interaction_at": last_success,
            "last_failure_category": "call_failed" if last_failure else None,
            "last_failure_at": last_failure,
            "calls_count": calls_count,
            "failed_calls_count": sum(1 for item in calls if item.status in {"failed", "rejected"}),
            "call_minutes": round(duration_seconds / 60, 2),
            "browser_voice_seconds": round(speech_seconds, 2),
            "ai_credits_charged": credits,
            "provider_cost_usd": str(cost),
            "average_latency_ms": self._average_latency(attempts),
            "fallback_count": sum(1 for item in central_sessions if item.stt_provider == "browser_speech" or item.tts_provider is None),
            "data_freshness": freshness.as_dict(),
            "business_metrics_status": "AVAILABLE" if freshness.freshness_status not in {"UNAVAILABLE"} else "UNAVAILABLE",
        }

    def _tenant_freshness(self, company_id) -> Any:
        source_states = self._session.scalars(select(RetailSourceState).where(
            RetailSourceState.company_id == company_id,
            RetailSourceState.enabled.is_(True),
        )).all()
        timestamps = []
        providers = set()
        if source_states:
            for state in source_states:
                if state.connection_id is not None:
                    connection = self._session.scalar(select(CommerceConnection).where(
                        CommerceConnection.id == state.connection_id,
                        CommerceConnection.company_id == company_id,
                        CommerceConnection.status == CommerceConnectionStatus.READY.value,
                    ))
                    if connection is not None:
                        providers.add(connection.provider)
                        timestamps.append(connection.last_successful_sync)
                elif state.dataset_id is not None:
                    dataset = self._session.scalar(select(Dataset).where(
                        Dataset.id == state.dataset_id,
                        Dataset.company_id == company_id,
                        Dataset.status == DatasetStatus.READY,
                    ))
                    if dataset is not None:
                        providers.add("dataset")
                        timestamps.append(dataset.uploaded_at)
        else:
            legacy = self._session.scalar(select(RetailActiveSource).where(
                RetailActiveSource.company_id == company_id
            ))
            if legacy is not None and legacy.source_type == "all":
                connections = self._session.scalars(select(CommerceConnection).where(
                    CommerceConnection.company_id == company_id,
                    CommerceConnection.status == CommerceConnectionStatus.READY.value,
                )).all()
                datasets = self._session.scalars(select(Dataset).where(
                    Dataset.company_id == company_id,
                    Dataset.status == DatasetStatus.READY,
                )).all()
                providers.update(item.provider for item in connections)
                timestamps.extend(item.last_successful_sync for item in connections)
                providers.update("dataset" for _ in datasets)
                timestamps.extend(item.uploaded_at for item in datasets)
            elif legacy is not None and legacy.source_type == "connector":
                connection = self._session.scalar(select(CommerceConnection).where(
                    CommerceConnection.company_id == company_id,
                    CommerceConnection.id == legacy.connection_id,
                    CommerceConnection.status == CommerceConnectionStatus.READY.value,
                ))
                if connection is not None:
                    providers.add(connection.provider)
                    timestamps.append(connection.last_successful_sync)
            elif legacy is not None and legacy.source_type == "dataset":
                dataset = self._session.scalar(select(Dataset).where(
                    Dataset.company_id == company_id,
                    Dataset.id == legacy.dataset_id,
                    Dataset.status == DatasetStatus.READY,
                ))
                if dataset is not None:
                    providers.add("dataset")
                    timestamps.append(dataset.uploaded_at)
        complete = bool(timestamps) and all(value is not None for value in timestamps)
        updated_at = min(timestamps) if complete else None
        name = ",".join(sorted(providers)) or None
        return self._freshness.evaluate(
            source=name,
            last_updated_at=updated_at,
            source_available=complete,
        )

    @staticmethod
    def _average_latency(attempts) -> float | None:
        values = [int(item.latency_ms) for item in attempts if item.latency_ms is not None and item.latency_ms > 0]
        return round(sum(values) / len(values), 2) if values else None

    @staticmethod
    def _utc(value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)