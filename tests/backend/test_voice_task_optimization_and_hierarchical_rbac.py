import pytest
from uuid import uuid4
from unittest.mock import MagicMock

from backend.app.ai.tools.contracts import ToolExecutionContext
from backend.app.ai.tools.business.coach_tools import (
    OptimizeTaskExecutionTool,
    OptimizeTaskArgs,
    GetExecutiveBriefingTool,
    EmptyCoachArgs,
)
from backend.app.models.base import UserRole, CompanyStatus
from backend.app.models.company import Company
from backend.app.models.company_membership import CompanyMembership
from backend.app.models.user import User
from backend.app.models.workspace import EmployeeTask
from backend.app.services.employee_coach_service import EmployeeCoachService
from shared.ai_engine.contracts import TenantContext


@pytest.fixture
def coach_db_session(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from backend.app.models.base import Base

    db_path = tmp_path / "test_coach_rbac.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    company = Company(
        id=uuid4(),
        name="Produits Ero",
        slug=f"produits-ero-{uuid4().hex[:6]}",
        email=f"contact-{uuid4().hex[:6]}@eroproduits.com",
        country="Canada",
        timezone="America/Toronto",
        subscription_plan="enterprise",
        industry="Commerce & Détail",
        status=CompanyStatus.ACTIVE,
    )
    session.add(company)

    owner = User(
        id=uuid4(),
        company_id=company.id,
        email="francis@eroproduits.com",
        first_name="Francis",
        last_name="Queval",
        job_title="Propriétaire & CEO",
        department="Direction",
        role=UserRole.OWNER,
        password_hash="fakehash",
        is_active=True,
    )
    employee = User(
        id=uuid4(),
        company_id=company.id,
        email="technicien@eroproduits.com",
        first_name="Marc",
        last_name="Technicien",
        job_title="Technicien d'Atelier",
        department="Opérations",
        role=UserRole.USER,
        password_hash="fakehash",
        is_active=True,
    )
    session.add_all([owner, employee])
    session.commit()

    mem_owner = CompanyMembership(company_id=company.id, user_id=owner.id, role=UserRole.OWNER, is_active=True)
    mem_emp = CompanyMembership(company_id=company.id, user_id=employee.id, role=UserRole.USER, is_active=True)
    session.add_all([mem_owner, mem_emp])

    task1 = EmployeeTask(
        id=uuid4(),
        company_id=company.id,
        assignee_user_id=employee.id,
        created_by_user_id=owner.id,
        title="Vidange et contrôle des freins avant",
        priority="high",
        status="open",
    )
    session.add(task1)
    session.commit()

    yield session, company, owner, employee
    session.close()
    engine.dispose()


def test_optimize_task_execution_across_sectors(coach_db_session):
    session, company, owner, employee = coach_db_session
    coach = EmployeeCoachService(session)

    # 1. Tâche Mécanique / Automobile
    opt_auto = coach.optimize_task_execution(employee, "Changement des plaquettes de frein avant")
    assert opt_auto["status"] == "success"
    assert opt_auto["sector"] == "Automobile & Mécanique"
    assert len(opt_auto["methodology_steps"]) >= 4
    assert "clé dynamométrique" in opt_auto["methodology_steps"][1].lower() or "servante" in opt_auto["time_optimization_tip"].lower()
    assert "plaquettes de frein avant" in opt_auto["spoken_summary"]

    # 2. Tâche Construction / Rénovation
    opt_const = coach.optimize_task_execution(employee, "Pose de carrelage 60x60 dans la salle de bain")
    assert opt_const["status"] == "success"
    assert opt_const["sector"] == "Construction & Rénovation"
    assert "niveau" in opt_const["methodology_steps"][2].lower()
    assert "découpe" in opt_const["time_optimization_tip"].lower()

    # 3. Tâche Coiffure / Beauté
    opt_beauty = coach.optimize_task_execution(employee, "Balayage blond et patine pour cliente")
    assert opt_beauty["status"] == "success"
    assert opt_beauty["sector"] == "Coiffure & Esthétique"
    assert "diagnostic" in opt_beauty["methodology_steps"][0].lower()
    assert "panier moyen" in opt_beauty["revenue_booster"].lower()

    # 4. Tâche Commerce / Relance
    opt_sales = coach.optimize_task_execution(employee, "Relance des devis en attente")
    assert opt_sales["status"] == "success"
    assert opt_sales["sector"] == "Commerce & Relations Clients"


def test_executive_briefing_owner_vs_employee(coach_db_session):
    session, company, owner, employee = coach_db_session
    coach = EmployeeCoachService(session)

    # Propriétaire -> plein accès au point stratégique
    brief_owner = coach.get_executive_briefing(owner, locale="fr-CA")
    assert brief_owner["status"] == "success"
    assert brief_owner["company_name"] == "Produits Ero"
    assert brief_owner["tasks_metrics"]["total"] >= 1
    assert "point stratégique" in brief_owner["spoken_summary"].lower()
    assert len(brief_owner["strategic_priorities"]) == 3

    # Employé opérationnel -> refus poli de protection des données financières
    brief_emp = coach.get_executive_briefing(employee, locale="fr-CA")
    assert brief_emp["status"] == "restricted"
    assert "réservé à la direction" in brief_emp["spoken_summary"].lower()


def test_hierarchical_data_fencing(coach_db_session):
    session, company, owner, employee = coach_db_session
    coach = EmployeeCoachService(session)

    # Employé demande les chiffres financiers de l'entreprise
    allowed, msg = coach.check_hierarchical_data_access(employee, "Quel est notre chiffre d'affaires et la marge ce mois ?")
    assert allowed is False
    assert "strictement réservées à la direction" in msg
    assert "Technicien d'Atelier" in msg

    # Propriétaire demande les mêmes chiffres -> Autorisé
    allowed_owner, msg_owner = coach.check_hierarchical_data_access(owner, "Quel est le chiffre d'affaires ?")
    assert allowed_owner is True


@pytest.mark.asyncio
async def test_ai_tools_optimize_and_executive(coach_db_session):
    session, company, owner, employee = coach_db_session

    tenant_emp = TenantContext(company.id, employee.id)
    ctx_emp = ToolExecutionContext(
        tenant=tenant_emp,
        user_id=employee.id,
        permissions=frozenset({"ai:use"}),
        request_id="req-test-1",
        locale="fr-CA",
    )

    opt_tool = OptimizeTaskExecutionTool(session)
    res_opt = await opt_tool.run(ctx_emp, OptimizeTaskArgs(task_description="Pose de plomberie multicouche"))
    assert res_opt.success is True
    assert "Construction & Rénovation" in res_opt.data["sector"]

    exec_tool = GetExecutiveBriefingTool(session)
    # L'employé essaie d'appeler l'outil exécutif -> restricted
    res_exec_emp = await exec_tool.run(ctx_emp, EmptyCoachArgs())
    assert res_exec_emp.success is False
    assert res_exec_emp.error == "restricted"

    # L'owner appelle l'outil exécutif -> success
    tenant_owner = TenantContext(company.id, owner.id)
    ctx_owner = ToolExecutionContext(
        tenant=tenant_owner,
        user_id=owner.id,
        permissions=frozenset({"ai:use"}),
        request_id="req-test-2",
        locale="fr-CA",
    )
    res_exec_owner = await exec_tool.run(ctx_owner, EmptyCoachArgs())
    assert res_exec_owner.success is True
    assert res_exec_owner.data["status"] == "success"
