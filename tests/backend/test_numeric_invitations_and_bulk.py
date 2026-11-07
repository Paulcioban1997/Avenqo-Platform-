from datetime import datetime, timedelta, timezone
from uuid import uuid4
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.models.base import Base
from backend.app.models.company import Company
from backend.app.models.user import User, UserRole
from backend.app.models.workspace import EmployeeInvitation
from backend.app.services.workspace_service import WorkspaceError, WorkspaceService

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()

def test_numeric_invitation_code_and_bulk(db_session: Session):
    company = Company(
        id=uuid4(),
        name="Test Corp",
        slug="test-corp",
        email="contact@testcorp.com",
        country="Canada",
        timezone="America/Toronto",
        industry="Retail",
        subscription_plan="professional",
        preferred_language="fr",
    )
    db_session.add(company)
    db_session.flush()

    owner = User(
        id=uuid4(),
        company_id=company.id,
        email="owner@testcorp.com",
        password_hash="argon2_fake",
        first_name="Alice",
        last_name="Owner",
        role=UserRole.OWNER,
        is_active=True,
    )
    db_session.add(owner)
    db_session.commit()

    service = WorkspaceService(db_session)

    # 1. Single invite generates 8-digit CSPRNG code
    inv = service.invite(owner, "bob@testcorp.com", UserRole.USER, "Analyst", "Finance")
    assert hasattr(inv, "_raw_code")
    code = inv._raw_code
    assert len(code) == 8
    assert code.isdigit()
    exp = inv.expires_at if inv.expires_at.tzinfo is not None else inv.expires_at.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    assert exp <= now + timedelta(hours=24, minutes=5)
    assert exp >= now + timedelta(hours=23, minutes=50)

    # 2. Max 5 failed attempts locks the invitation
    for attempt in range(4):
        with pytest.raises(WorkspaceError, match="Code d'invitation incorrect"):
            service.accept_invitation(None, "Bob", "Smith", "password12345", code="99999999", email="bob@testcorp.com")
        db_session.refresh(inv)
        assert inv.failed_attempts == attempt + 1
        assert inv.revoked_at is None

    # 5th failed attempt revokes the invitation
    with pytest.raises(WorkspaceError, match="tentative"):
        service.accept_invitation(None, "Bob", "Smith", "password12345", code="99999999", email="bob@testcorp.com")
    db_session.refresh(inv)
    assert inv.revoked_at is not None

    # 6th attempt is blocked
    with pytest.raises(WorkspaceError, match="dépassé|Aucune invitation active"):
        service.accept_invitation(None, "Bob", "Smith", "password12345", code=code, email="bob@testcorp.com")

    # 3. Successful invite and acceptance with valid code
    inv2 = service.invite(owner, "charlie@testcorp.com", UserRole.ADMIN, "Manager", "Ops")
    code2 = inv2._raw_code
    new_user = service.accept_invitation(None, "Charlie", "Brown", "strongpassword123", code=code2, email="charlie@testcorp.com")
    assert new_user.email == "charlie@testcorp.com"
    assert new_user.first_name == "Charlie"
    assert new_user.role == UserRole.ADMIN
    db_session.refresh(inv2)
    assert inv2.accepted_at is not None

    # 4. Bulk invite
    bulk_invs = service.invite_bulk(
        owner,
        ["dev1@testcorp.com", "dev2@testcorp.com"],
        UserRole.USER,
        "Developer",
        "R&D",
    )
    assert len(bulk_invs) == 2
    for b in bulk_invs:
        assert len(b._raw_code) == 8
        assert b._raw_code.isdigit()
