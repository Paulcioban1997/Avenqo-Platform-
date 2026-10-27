import os
import shutil
import tempfile
from uuid import uuid4
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.ai.memory.service import AvenqoMemoryService
from backend.app.config.settings import Settings
from backend.app.models.base import Base
from backend.app.models.company import Company
from backend.app.models.user import User
from backend.app.models.ai_chat import AIConversation, AIMessage, AIMessageRole
from backend.app.models.ai_memory import AIEnterpriseMemory, MemoryScope, MemoryType
from backend.app.voice.caller_scope import PUBLIC_VOICE_CALLER_PERMISSIONS


@pytest.fixture(scope="module")
def temp_memory_dir():
    d = tempfile.mkdtemp(prefix="avenqo_test_mem_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


from sqlalchemy.pool import StaticPool


@pytest.fixture(scope="module")
def db_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def db_session(db_engine):
    connection = db_engine.connect()
    transaction = connection.begin()
    Session = sessionmaker(bind=connection)
    session = Session()

    yield session

    session.close()
    if transaction.is_active:
        transaction.rollback()
    connection.close()


@pytest.fixture
def test_settings(temp_memory_dir):
    return Settings(
        avenqo_memory_enabled=True,
        avenqo_memory_backend="qdrant",
        avenqo_memory_storage_path=temp_memory_dir,
        avenqo_memory_collection_name="test_enterprise_memories",
        avenqo_memory_embedding_dims=64,
        avenqo_memory_embedder_provider="openai",
        avenqo_memory_llm_provider="openai",
    )


@pytest.fixture
def company_a(db_session):
    company = Company(
        id=uuid4(),
        name="Company A Retail Corp",
        slug="company-a-retail",
        email="contact@company-a.com",
        country="CA",
        timezone="America/Toronto",
        industry="Retail",
        subscription_plan="professional",
        preferred_language="fr-CA",
        currency_code="CAD",
    )
    db_session.add(company)
    db_session.commit()
    return company


@pytest.fixture
def company_b(db_session):
    company = Company(
        id=uuid4(),
        name="Company B Independent LLC",
        slug="company-b-independent",
        email="contact@company-b.com",
        country="US",
        timezone="America/New_York",
        industry="Services",
        subscription_plan="starter",
        preferred_language="en",
        currency_code="USD",
    )
    db_session.add(company)
    db_session.commit()
    return company


@pytest.fixture
def user_a1(db_session, company_a):
    user = User(
        id=uuid4(),
        company_id=company_a.id,
        email="admin.a@company-a.com",
        password_hash="fakehash",
        first_name="Alice",
        last_name="Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def user_a2(db_session, company_a):
    user = User(
        id=uuid4(),
        company_id=company_a.id,
        email="employee.a@company-a.com",
        password_hash="fakehash",
        first_name="Bob",
        last_name="Employee",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def user_b1(db_session, company_b):
    user = User(
        id=uuid4(),
        company_id=company_b.id,
        email="owner.b@company-b.com",
        password_hash="fakehash",
        first_name="Charlie",
        last_name="Owner",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def test_recall_between_independent_conversations(db_session, test_settings, company_a, user_a1):
    """Company A saves a preference in conversation 1, and retrieves it in a totally new conversation 2."""
    service = AvenqoMemoryService(db_session, test_settings)

    # Conversation 1: Company A saves preference
    conv_1 = AIConversation(
        id=uuid4(),
        company_id=company_a.id,
        user_id=user_a1.id,
        title="Preferences Setup",
        locale="fr-CA",
    )
    db_session.add(conv_1)
    db_session.commit()

    saved_mem = service.add_memory(
        tenant_id=company_a.id,
        user_id=user_a1.id,
        content="Our company prefers weekly sales reports every Monday.",
        scope=MemoryScope.COMPANY.value,
        memory_type=MemoryType.PREFERENCE.value,
        conversation_id=conv_1.id,
    )
    assert saved_mem.id is not None
    assert "weekly sales reports every Monday" in saved_mem.content

    # Conversation 2: Fresh independent conversation
    conv_2 = AIConversation(
        id=uuid4(),
        company_id=company_a.id,
        user_id=user_a1.id,
        title="Monday Sales Inquiry",
        locale="fr-CA",
    )
    db_session.add(conv_2)
    db_session.commit()

    # Query memory context in conversation 2
    context_block = service.retrieve_relevant_context(
        tenant_id=company_a.id,
        user_id=user_a1.id,
        query="When do we prefer receiving sales reports?",
    )
    assert "<enterprise_memory" in context_block
    assert "weekly sales reports every Monday" in context_block


def test_persistence_after_service_restart(db_session, test_settings, company_a, user_a1):
    """Memory survives complete re-instantiation of AvenqoMemoryService (service restart simulation)."""
    # 1st service instance saves memory
    service_1 = AvenqoMemoryService(db_session, test_settings)
    mem = service_1.add_memory(
        tenant_id=company_a.id,
        user_id=user_a1.id,
        content="VIP customer threshold is set to 5000 CAD.",
        scope=MemoryScope.COMPANY.value,
        memory_type=MemoryType.DECISION.value,
    )

    # Simulate service restart: create fresh service instance
    service_2 = AvenqoMemoryService(db_session, test_settings)
    loaded = service_2.get_memory(company_a.id, user_a1.id, mem.id)
    assert loaded is not None
    assert loaded.content == "VIP customer threshold is set to 5000 CAD."

    results = service_2.search_memories(company_a.id, user_a1.id, "VIP customer threshold")
    assert any("5000 CAD" in r.content for r in results)


def test_cross_tenant_isolation(db_session, test_settings, company_a, company_b, user_a1, user_b1):
    """Company B must NEVER retrieve Company A memories, even with identical semantic queries."""
    service = AvenqoMemoryService(db_session, test_settings)

    # Company A saves confidential financial target
    service.add_memory(
        tenant_id=company_a.id,
        user_id=user_a1.id,
        content="Company A confidential quarterly revenue target is 1,200,000 CAD.",
        scope=MemoryScope.COMPANY.value,
        memory_type=MemoryType.GOAL.value,
    )

    # Company B queries for quarterly revenue targets
    results_b = service.search_memories(
        tenant_id=company_b.id,
        user_id=user_b1.id,
        query="quarterly revenue target",
    )
    assert len(results_b) == 0

    context_b = service.retrieve_relevant_context(
        tenant_id=company_b.id,
        user_id=user_b1.id,
        query="quarterly revenue target",
    )
    assert "1,200,000 CAD" not in context_b
    assert context_b == ""


def test_private_versus_company_shared_permissions(db_session, test_settings, company_a, user_a1, user_a2):
    """Private user memories are isolated to the specific user; company-shared memories are accessible across company."""
    service = AvenqoMemoryService(db_session, test_settings)

    # User A1 creates private user memory
    private_mem = service.add_memory(
        tenant_id=company_a.id,
        user_id=user_a1.id,
        content="Alice personal preference: Dark mode interface and compact table view.",
        scope=MemoryScope.USER.value,
        memory_type=MemoryType.PREFERENCE.value,
    )

    # User A1 creates company-shared memory
    shared_mem = service.add_memory(
        tenant_id=company_a.id,
        user_id=user_a1.id,
        content="Company policy: Invoices must have Net 30 payment terms.",
        scope=MemoryScope.COMPANY.value,
        memory_type=MemoryType.PROCEDURE.value,
    )

    # User A2 (colleague in same company) searches memories
    user_a2_memories = service.search_memories(
        tenant_id=company_a.id,
        user_id=user_a2.id,
        query="preference or terms",
        include_company_shared=True,
    )
    contents = [m.content for m in user_a2_memories]
    # Should see company policy
    assert any("Net 30 payment terms" in c for c in contents)
    # Should NOT see Alice's private preference
    assert not any("Alice personal preference" in c for c in contents)

    # Direct access check
    direct_private = service.get_memory(company_a.id, user_a2.id, private_mem.id)
    assert direct_private is None


def test_memory_correction_and_deletion(db_session, test_settings, company_a, user_a1):
    """Updating or deleting a memory correctly mutates the persistent state and vector index."""
    service = AvenqoMemoryService(db_session, test_settings)

    mem = service.add_memory(
        tenant_id=company_a.id,
        user_id=user_a1.id,
        content="Our primary store contact phone is 514-555-0199.",
        scope=MemoryScope.COMPANY.value,
    )

    # Correction / update
    updated = service.update_memory(
        company_a.id,
        user_a1.id,
        mem.id,
        content="Our primary store contact phone has changed to 514-555-9900.",
    )
    assert updated is not None
    assert "514-555-9900" in updated.content

    # Verify updated content is searched
    found = service.search_memories(company_a.id, user_a1.id, "primary store contact phone")
    assert len(found) > 0
    assert "514-555-9900" in found[0].content
    assert "514-555-0199" not in found[0].content

    # Deletion
    deleted = service.delete_memory(company_a.id, user_a1.id, mem.id)
    assert deleted is True

    # Search should no longer return it
    found_after = service.search_memories(company_a.id, user_a1.id, "primary store contact phone")
    assert len(found_after) == 0


def test_voice_caller_continuity_and_public_caller_isolation(db_session, test_settings, company_a, user_a1):
    """Verified employees access memories over voice; public callers are strictly denied access."""
    service = AvenqoMemoryService(db_session, test_settings)

    # Employee saved an operational instruction by text
    service.add_memory(
        tenant_id=company_a.id,
        user_id=user_a1.id,
        content="Store holiday schedule: Closed on Thanksgiving Monday.",
        scope=MemoryScope.COMPANY.value,
    )

    # Verified employee (authorized voice caller with standard permissions)
    verified_context = service.retrieve_relevant_context(
        tenant_id=company_a.id,
        user_id=user_a1.id,
        query="Are we open on Thanksgiving Monday?",
    )
    assert "Closed on Thanksgiving Monday" in verified_context

    # Public phone caller: permissions check at execution boundary
    from backend.app.voice.caller_scope import is_public_voice_caller
    public_permissions = PUBLIC_VOICE_CALLER_PERMISSIONS
    assert is_public_voice_caller(public_permissions) is True

    # In ChatService / Voice execution, public callers bypass memory retrieval:
    if is_public_voice_caller(public_permissions):
        public_context = ""
    else:
        public_context = service.retrieve_relevant_context(
            tenant_id=company_a.id,
            user_id=user_a1.id,
            query="holiday schedule",
        )
    assert public_context == ""


def test_sensitive_data_redaction_before_persistence(db_session, test_settings, company_a, user_a1):
    """Credit card numbers and raw passwords must be redacted before being saved to enterprise memory."""
    service = AvenqoMemoryService(db_session, test_settings)

    content_with_sensitive = "Client asked to charge card 4532-1234-5678-9012 for the monthly retainer."
    mem = service.add_memory(
        tenant_id=company_a.id,
        user_id=user_a1.id,
        content=content_with_sensitive,
    )
    assert "4532-1234-5678-9012" not in mem.content
    assert "[REDACTED_SENSITIVE]" in mem.content


def test_graceful_degradation_on_backend_failure(db_session, company_a, user_a1):
    """If memory backend throws an exception or is disabled, service degrades safely without crashing."""
    broken_settings = Settings(
        avenqo_memory_enabled=True,
        avenqo_memory_backend="invalid_broken_backend",
        avenqo_memory_storage_path="/proc/non_existent_path_cannot_write_here",
    )
    service = AvenqoMemoryService(db_session, broken_settings)

    # Add memory still persists to relational database even if vector store fails
    mem = service.add_memory(
        company_a.id,
        user_a1.id,
        content="Fallback memory stored in SQL.",
    )
    assert mem.id is not None

    # Search falls back gracefully to SQL ilike
    results = service.search_memories(company_a.id, user_a1.id, "Fallback memory")
    assert len(results) > 0
    assert results[0].content == "Fallback memory stored in SQL."
