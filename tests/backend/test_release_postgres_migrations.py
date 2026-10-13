"""Release rehearsal on a newly created, isolated PostgreSQL database only."""
import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url


@pytest.mark.skipif(not os.getenv("AVENQO_TEST_POSTGRES_URL"), reason="Isolated PostgreSQL required")
def test_postgres_0048_to_0050_preserves_data_and_accepts_long_revision_ids(monkeypatch):
    admin_url = make_url(os.environ["AVENQO_TEST_POSTGRES_URL"])
    assert admin_url.host in {"127.0.0.1", "localhost"}, "Never target a deployed database"
    name = "avenqo_release_rehearsal_" + uuid4().hex[:12]
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text('CREATE DATABASE "' + name + '"'))
    target = admin_url.set(database=name)
    monkeypatch.setenv("ALEMBIC_DATABASE_URL", target.render_as_string(hide_password=False))
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    engine = create_engine(target)
    # Reproduce Alembic's default PostgreSQL version table before applying code.
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
    command.upgrade(config, "0048_billing_test_documents")
    with engine.begin() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0048_billing_test_documents"
        connection.execute(text("CREATE TABLE release_preservation_probe (id integer PRIMARY KEY, value text)"))
        connection.execute(text("INSERT INTO release_preservation_probe VALUES (1, 'test-only-preserve')"))
    command.upgrade(config, "0050_mfa_recovery_and_lockout")
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0050_mfa_recovery_and_lockout"
        assert connection.execute(text("SELECT value FROM release_preservation_probe")).scalar_one() == "test-only-preserve"
        columns = {item["name"] for item in inspect(connection).get_columns("users")}
        assert {"mfa_secret_encrypted", "mfa_recovery_hashes", "failed_login_count", "locked_until"} <= columns
        assert inspect(connection).get_columns("alembic_version")[0]["type"].length >= 64
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0055_voice_call_policy"
        assert connection.execute(text("SELECT value FROM release_preservation_probe")).scalar_one() == "test-only-preserve"
        assert inspect(connection).has_table("company_locale_profiles")
        assert inspect(connection).has_table("voice_module_permissions")
        assert inspect(connection).has_table("voice_provisioning_orders")
        assert inspect(connection).has_table("voice_provisioning_claims")
        for table in ("voice_provisioning_orders", "voice_provisioning_claims", "voice_telecom_costs"):
            protected = connection.execute(text("SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE relname=:table"), {"table": table}).scalar_one()
            assert protected
    # Exercise the real PostgreSQL policies as a non-superuser, not just SQLite filters.
    from datetime import datetime, timezone
    from sqlalchemy.orm import Session
    from backend.app.models import Company, User
    from backend.app.models.voice_provisioning import VoiceProvisioningOrder, VoiceProvisioningClaim
    with Session(engine) as db:
        tenants=[]
        for suffix in ("alpha", "beta"):
            company=Company(name="Fixture "+suffix,slug=suffix,email=suffix+"@example.test",country="CA",timezone="America/Montreal",industry="Garage",subscription_plan="base")
            db.add(company);db.flush()
            import secrets
            user=User(company_id=company.id,first_name="Fixture",last_name=suffix,email="owner-"+suffix+"@example.test",password_hash=secrets.token_hex(32))
            db.add(user);db.flush()
            at=datetime.now(timezone.utc)
            order=VoiceProvisioningOrder(company_id=company.id,actor_id=user.id,phone_number="fixture-"+suffix,snapshot={},expires_at=at,available_at=at,stripe_customer_id="fixture",stripe_subscription_id="fixture")
            db.add(order);db.flush()
            db.add(VoiceProvisioningClaim(phone_number=order.phone_number,order_id=order.id,company_id=company.id))
            tenants.append(company.id)
        db.commit()
    role="voice_rls_rehearsal_"+uuid4().hex[:12]
    with engine.begin() as connection:
        connection.execute(text('CREATE ROLE "'+role+'" NOLOGIN NOSUPERUSER NOBYPASSRLS'))
        connection.execute(text('GRANT USAGE ON SCHEMA public TO "'+role+'"'))
        connection.execute(text('GRANT SELECT,UPDATE ON voice_provisioning_orders,voice_provisioning_claims,voice_telecom_costs TO "'+role+'"'))
    for tenant in tenants:
        with engine.begin() as connection:
            connection.execute(text('SET LOCAL ROLE "'+role+'"'))
            connection.execute(text("SELECT set_config('app.bypass_rls','off',true),set_config('app.current_company_id',:tenant,true)"),{"tenant":str(tenant)})
            for table in ("voice_provisioning_orders", "voice_provisioning_claims"):
                assert connection.execute(text('SELECT company_id FROM '+table)).scalars().all()==[tenant]
            assert connection.execute(text("UPDATE voice_provisioning_orders SET status='FOREIGN' WHERE company_id=:other"),{"other":str(next(x for x in tenants if x!=tenant))}).rowcount==0
    with engine.begin() as connection:
        connection.execute(text('SET LOCAL ROLE "'+role+'"'))
        connection.execute(text("SELECT set_config('app.bypass_rls','off',true),set_config('app.current_company_id','',true)"))
        assert connection.execute(text("SELECT count(*) FROM voice_provisioning_orders")).scalar_one()==0
    engine.dispose()
    admin.dispose()
    # Keep the isolated rehearsal database for inspection; no active DB is deleted.
