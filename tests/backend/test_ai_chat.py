from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.ai.chat.conversation_service import ConversationService
from backend.app.ai.chat.exceptions import ConversationNotFoundError
from backend.app.ai.chat.retrieval_service import RetrievalService
from backend.app.ai.llm.factory import LLMProviderFactory
from backend.app.ai.llm.openai_provider import OpenAIProvider
from backend.app.config.settings import Settings
from backend.app.models import Base, Company, CompanyMembership, Dataset, DatasetStatus, Mapping, User, UserRole


@pytest.fixture
def chat_session(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'chat.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        company_a = Company(name="Company A", slug="company-a", email="a@example.com", country="CA", timezone="America/Toronto", industry="Retail", subscription_plan="demo")
        company_b = Company(name="Company B", slug="company-b", email="b@example.com", country="CA", timezone="America/Toronto", industry="Retail", subscription_plan="demo")
        session.add_all([company_a, company_b]); session.flush()
        user_a = User(company_id=company_a.id, first_name="User", last_name="A", email="user-a@example.com", password_hash="hash")
        user_b = User(company_id=company_b.id, first_name="User", last_name="B", email="user-b@example.com", password_hash="hash")
        session.add_all([user_a, user_b])
        session.add_all([
            Dataset(company_id=company_a.id, name="Sales A", type="csv", source="a.csv", rows_count=10, columns_count=2, status=DatasetStatus.READY),
            Dataset(company_id=company_b.id, name="Secret B", type="csv", source="b.csv", rows_count=20, columns_count=3, status=DatasetStatus.READY),
        ])
        session.flush()
        user_a.role = UserRole.OWNER
        session.add(CompanyMembership(company_id=company_a.id, user_id=user_a.id, role=UserRole.OWNER, is_active=True))
        dataset_a = session.scalar(select(Dataset).where(Dataset.company_id == company_a.id))
        dataset_a.mapping = Mapping(mapping_json={"accepted": {}}, confidence=1, approved=True)
        session.flush()
        from backend.app.services.retail_source_service import RetailSourceService
        from shared.ai_engine.contracts import TenantContext
        RetailSourceService(session).set_workspace_selection(TenantContext(company_a.id), mode="SINGLE", selected_source_ids=[dataset_a.id])
        session.commit()
        yield session, company_a, company_b, user_a, user_b


def test_conversation_cannot_be_read_by_another_tenant(chat_session) -> None:
    session, company_a, company_b, user_a, user_b = chat_session
    service = ConversationService(session)
    conversation = service.create(company_b.id, user_b.id, "Private B")

    with pytest.raises(ConversationNotFoundError):
        service.get(company_a.id, user_a.id, conversation.id)


def test_retrieval_excludes_other_tenant_datasets(chat_session) -> None:
    session, company_a, _, user_a, _ = chat_session
    results = RetrievalService(session).retrieve_context(company_a.id, "sales", user_id=user_a.id)

    assert [result.name for result in results] == ["Sales A"]
    assert all(result.metadata["dataset_id"] != "Secret B" for result in results)


def test_retrieval_excludes_tenant_datasets_that_are_not_ready(chat_session) -> None:
    session, company_a, _, user_a, _ = chat_session
    session.add(
        Dataset(
            company_id=company_a.id,
            name="Still cleaning",
            type="csv",
            source="cleaning.csv",
            rows_count=10,
            columns_count=2,
            status=DatasetStatus.CLEANING,
        )
    )
    session.commit()

    results = RetrievalService(session).retrieve_context(company_a.id, "sales", user_id=user_a.id)

    assert [result.name for result in results] == ["Sales A"]


def test_llm_factory_selects_configured_provider() -> None:
    provider = LLMProviderFactory.create(Settings(LLM_PROVIDER="openai"))

    assert isinstance(provider, OpenAIProvider)