import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, select, func

from backend.app.models import Base, CompanyMembership
from tests.backend.test_master_security_and_billing import sec_env, _register_and_login


def test_deployed_enterprise_revision_has_one_upgrade_path():
    scripts = ScriptDirectory(str(Path(__file__).resolve().parents[2] / "alembic"))
    assert scripts.get_heads() == ["0019_company_memberships"]
    revisions = list(scripts.iterate_revisions("heads", "0019_enterprise_quotes"))
    assert [revision.revision for revision in revisions] == ["0019_company_memberships"]


def migrate(connection):
    path = Path(__file__).resolve().parents[2] / "alembic/versions/0019_company_memberships.py"
    spec = importlib.util.spec_from_file_location("membership_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.op = Operations(MigrationContext.configure(connection))
    module.upgrade()


def test_membership_migration_creates_empty_table_and_is_repeatable():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    CompanyMembership.__table__.drop(engine)
    with engine.begin() as connection:
        migrate(connection)
        migrate(connection)
        assert inspect(connection).has_table("company_memberships")
        assert connection.scalar(select(func.count()).select_from(CompanyMembership)) == 0
        assert {i["name"] for i in inspect(connection).get_indexes("company_memberships")} == {
            "ix_company_memberships_user_id", "ix_company_memberships_company_id",
        }


def test_me_after_missing_membership_table_is_migrated(sec_env):
    client, factory, notifier = sec_env
    token = _register_and_login(client, notifier, "Migration", "migration@example.com", "Migration tenant")
    with factory() as session:
        engine = session.get_bind()
    CompanyMembership.__table__.drop(engine)
    with engine.begin() as connection:
        migrate(connection)
    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert [org["name"] for org in response.json()["organizations"]] == ["Migration tenant"]
