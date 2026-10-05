from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.config.settings import Settings
from backend.app.models import Base, Company, VoiceBusinessConfig, VoiceCall
from backend.app.services.voice_health_service import VoiceHealthService


def test_voice_health_reports_safe_config_and_call_metadata_without_provider_probes(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'voice-health.db'}")
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    with Session(engine, expire_on_commit=False) as session:
        company = Company(
            name="Health Tenant",
            slug="health-tenant",
            email="health@example.com",
            country="Canada",
            timezone="America/Toronto",
            industry="Retail",
            subscription_plan="professional",
            currency_code="CAD",
        )
        session.add(company)
        session.flush()
        config = VoiceBusinessConfig(
            company_id=company.id,
            business_name=company.name,
            timezone_name=company.timezone,
            opening_hours={},
            services=[],
            telnyx_phone_number="+14165550123",
            preferred_language="fr",
            greeting_message="Bonjour",
            retell_agent_id="agent-safe-id",
            retell_sip_uri="sip:agent@sip.retell.example",
            voice_api_key_hash="a" * 64,
            voice_api_key_last4="1234",
            enabled=True,
        )
        session.add(config)
        session.flush()
        session.add(VoiceCall(
            company_id=company.id,
            config_id=config.id,
            telnyx_call_control_id="call-1",
            caller_phone="+14165550999",
            status="ended",
            started_at=now - timedelta(minutes=3),
            ended_at=now,
        ))
        session.commit()

        result = VoiceHealthService(session, Settings()).list_tenants()

    assert result["provider_configuration"]["health_probe"] == "NOT_CHECKED"
    assert result["tenants"][0]["voice_status"] == "ENABLED"
    assert result["tenants"][0]["calls_count"] == 1
    assert result["tenants"][0]["call_minutes"] == 3
    assert result["tenants"][0]["last_successful_interaction_at"] is not None
    serialized = str(result)
    assert "voice_api_key_hash" not in serialized
    assert "retell_sip_uri" not in serialized
    assert "agent-safe-id" not in serialized
    engine.dispose()