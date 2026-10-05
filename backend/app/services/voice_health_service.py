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
    CommerceConnection,
    CommerceConnectionStatus,
    Dataset,
    DatasetStatus,
    RetailActiveSource,
    RetailSourceState,
    TenantAIProviderAttempt,
    VoiceBusinessConfig,
    VoiceCall,
    VoiceCentralSession,
)
from backend.app.services.data_freshness_service import DataFreshnessService


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
        companies = {
            company.id: company
            for company in self._session.scalars(
                select(Company).where(Company.id.in_({item.company_id for item in configs}))
            ).all()
        } if configs else {}
        tenants = [
            self._tenant_health(config, companies.get(config.company_id))
            for config in configs
        ]
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

    def _tenant_health(self, config: VoiceBusinessConfig, company: Company | None) -> dict[str, Any]:
        calls = self._session.scalars(
            select(VoiceCall)
            .where(VoiceCall.config_id == config.id)
            .order_by(VoiceCall.started_at.desc())
            .limit(500)
        ).all()
        calls_count = int(self._session.scalar(
            select(func.count(VoiceCall.id)).where(VoiceCall.config_id == config.id)
        ) or 0)
        central_sessions = self._session.scalars(
            select(VoiceCentralSession).where(VoiceCentralSession.company_id == config.company_id)
        ).all()
        conversation_ids = {item.conversation_id for item in central_sessions}
        attempts = self._session.scalars(
            select(TenantAIProviderAttempt).where(
                TenantAIProviderAttempt.company_id == config.company_id,
                TenantAIProviderAttempt.conversation_id.in_(conversation_ids),
            )
        ).all() if conversation_ids else []

        last_call = max((self._utc(item.started_at) for item in calls if item.started_at), default=None)
        last_success = max(
            (
                self._utc(item.ended_at or item.started_at)
                for item in calls
                if item.status in {"ended", "appointment_booked", "appointment_cancelled", "transferred"}
                and (item.ended_at or item.started_at)
            ),
            default=None,
        )
        last_failure = max(
            (self._utc(item.ended_at or item.started_at) for item in calls if item.status in {"failed", "rejected"} and (item.ended_at or item.started_at)),
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
        freshness = self._tenant_freshness(config.company_id)

        return {
            "company_id": str(config.company_id),
            "company_name": company.name if company else "Unavailable tenant",
            "voice_status": "ENABLED" if config.enabled else "DISABLED",
            "phone_number": config.telnyx_phone_number,
            "country": company.country if company else None,
            "region": company.region if company else None,
            "provider": "telnyx",
            "telnyx_webhook_status": "CONFIGURED" if self._settings.telnyx_public_key else "NOT_CONFIGURED",
            "retell_status": "CONFIGURED" if self._settings.retell_api_key else "NOT_CONFIGURED",
            "stt_provider": config and ("CONFIGURED" if self._settings.voice_stt_provider and self._settings.openai_api_key else "NOT_CONFIGURED"),
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