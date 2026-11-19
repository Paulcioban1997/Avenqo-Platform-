"""Tests unitaires et d'intégration pour le module Ressources Humaines (HR AI)."""

import pytest
from datetime import datetime, timezone, timedelta
from uuid import uuid4

from backend.app.models.base import UserRole, CompanyStatus
from backend.app.models.company import Company
from backend.app.models.company_membership import CompanyMembership
from backend.app.models.user import User
from backend.app.models.voice import VoiceCallerCredential
from backend.app.models.workspace import EmployeeTask, EmployeeLeave, EmployeePerformanceReview
from backend.app.services.hr_service import HRService


@pytest.fixture
def hr_db_session(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from backend.app.models.base import Base

    db_path = tmp_path / "test_hr_module.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    company = Company(
        id=uuid4(),
        name="Produits Ero Test",
        slug=f"produits-ero-{uuid4().hex[:6]}",
        email=f"contact-{uuid4().hex[:6]}@eroproduits.com",
        country="Canada",
        timezone="America/Toronto",
        subscription_plan="enterprise",
        industry="Automobile / Pièces",
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
    manager = User(
        id=uuid4(),
        company_id=company.id,
        email="chef@eroproduits.com",
        first_name="Alain",
        last_name="Chef",
        job_title="Chef d'Atelier",
        department="Atelier Mécanique",
        role=UserRole.ADMIN,
        password_hash="fakehash",
        is_active=True,
    )
    technician = User(
        id=uuid4(),
        company_id=company.id,
        email="marc@eroproduits.com",
        first_name="Marc",
        last_name="Technicien",
        job_title="Technicien de Maintenance",
        department="Atelier Mécanique",
        role=UserRole.USER,
        password_hash="fakehash",
        is_active=True,
    )
    session.add_all([owner, manager, technician])
    session.commit()

    # Credential pour Francis
    cred = VoiceCallerCredential(
        company_id=company.id,
        principal_type="USER",
        principal_id=owner.id,
        phone_number="+15142955720",
        pin_hash="fakehash",
    )
    session.add(cred)

    # Tâches
    task = EmployeeTask(
        id=uuid4(),
        company_id=company.id,
        assignee_user_id=technician.id,
        created_by_user_id=manager.id,
        title="Contrôle circuit de freinage",
        priority="high",
        status="open",
        due_at=datetime.now(timezone.utc) + timedelta(days=2),
    )
    session.add(task)
    session.commit()

    yield session, company, owner, manager, technician
    session.close()
    engine.dispose()


def test_hr_overview(hr_db_session):
    session, company, owner, manager, technician = hr_db_session
    service = HRService(session)

    overview = service.get_overview(company.id)
    assert overview.total_employees == 3
    assert overview.active_employees == 3
    assert "Direction" in overview.departments
    assert "Atelier Mécanique" in overview.departments
    assert overview.hierarchy_breakdown["executive"] == 1
    assert overview.hierarchy_breakdown["management"] == 1
    assert overview.hierarchy_breakdown["operational"] == 1
    assert overview.tasks_metrics["total"] == 1
    assert overview.tasks_metrics["open"] == 1
    assert overview.company_industry == "Automobile / Pièces"


def test_hr_employees_list_and_hierarchy(hr_db_session):
    session, company, owner, manager, technician = hr_db_session
    service = HRService(session)

    employees = service.list_employees(company.id)
    assert len(employees) == 3

    # Vérifier l'owner
    owner_item = next(e for e in employees if e.id == owner.id)
    assert owner_item.hierarchy_level == "executive"
    assert owner_item.has_voice_pin is True

    # Vérifier le chef d'atelier
    mgr_item = next(e for e in employees if e.id == manager.id)
    assert mgr_item.hierarchy_level == "management"

    # Vérifier le technicien
    tech_item = next(e for e in employees if e.id == technician.id)
    assert tech_item.hierarchy_level == "operational"
    assert tech_item.open_tasks_count == 1


def test_hr_job_descriptions_and_sops(hr_db_session):
    session, company, owner, manager, technician = hr_db_session
    service = HRService(session)

    # SOPs Automobile
    sops_auto = service.get_job_descriptions(company.id, sector="automobile")
    assert sops_auto.sector == "automobile"
    assert "Automobile" in sops_auto.sector_name
    assert len(sops_auto.job_descriptions) >= 2
    assert any("clé dynamométrique" in " ".join(r.standard_operating_procedure).lower() for r in sops_auto.job_descriptions)

    # SOPs Construction
    sops_const = service.get_job_descriptions(company.id, sector="construction")
    assert sops_const.sector == "construction"
    assert any("RBQ" in " ".join(r.safety_and_compliance) for r in sops_const.job_descriptions)


def test_hr_skills_matrix(hr_db_session):
    session, company, owner, manager, technician = hr_db_session
    service = HRService(session)

    skills = service.get_skills_matrix(company.id)
    assert len(skills) >= 6
    tech_skills = [s for s in skills if s.employee_id == technician.id]
    assert any("OBD" in s.name or "Freinage" in s.name for s in tech_skills)


def test_hr_leave_lifecycle(hr_db_session):
    session, company, owner, manager, technician = hr_db_session
    service = HRService(session)

    # 1. Création de demande de congé
    start = datetime.now(timezone.utc) + timedelta(days=7)
    end = start + timedelta(days=3)
    leave = service.create_leave(
        company_id=company.id,
        user_id=technician.id,
        leave_type="vacation",
        start_date=start,
        end_date=end,
        days_count=3.0,
        reason="Vacances d'hiver",
    )
    assert leave.status == "pending"
    assert leave.days_count == 3.0

    # 2. Lister les congés
    leaves = service.list_leaves(company.id)
    assert len(leaves) == 1
    assert leaves[0].id == leave.id

    # 3. Approbation par le Manager
    approved_leave = service.update_leave_status(
        company_id=company.id,
        leave_id=leave.id,
        approver_user_id=manager.id,
        new_status="approved",
    )
    assert approved_leave.status == "approved"
    assert approved_leave.approved_by == "Alain Chef"


def test_hr_performance_review(hr_db_session):
    session, company, owner, manager, technician = hr_db_session
    service = HRService(session)

    # 1. Données opérationnelles insuffisantes (< 2 tâches) : message véridique exigé
    rev_insufficient = service.create_review(
        company_id=company.id,
        user_id=technician.id,
        reviewer_user_id=manager.id,
        review_period="Q4 2026",
        rating=4.8,
        strengths="Excellente rapidité d'exécution sur le freinage.",
        growth_areas="Continuer à optimiser le temps de check-list.",
        goals="Obtenir la certification niveau 2 sur véhicules hybrides.",
    )
    assert rev_insufficient.rating == 4.8
    assert rev_insufficient.employee_name == "Marc Technicien"
    assert rev_insufficient.data_sufficient is False
    assert rev_insufficient.ai_coach_notes == "Données insuffisantes pour produire une évaluation personnalisée fiable."

    # 2. Données suffisantes (ajout de tâches réelles complétées)
    session.add(
        EmployeeTask(
            id=uuid4(),
            company_id=company.id,
            assignee_user_id=technician.id,
            created_by_user_id=manager.id,
            title="Purge circuit hydraulique",
            status="completed",
        )
    )
    session.commit()

    rev_sufficient = service.create_review(
        company_id=company.id,
        user_id=technician.id,
        reviewer_user_id=manager.id,
        review_period="Q4 2026",
        rating=4.9,
        strengths="Maîtrise complète de l'atelier.",
        growth_areas="Superviser les apprentis.",
        goals="Former 1 nouveau technicien.",
    )
    assert rev_sufficient.data_sufficient is True
    assert "Voice Coach" in rev_sufficient.ai_coach_notes
    assert "ne constitue pas une décision RH formelle" in rev_sufficient.ai_coach_notes

    # 3. Liste des revues
    reviews = service.list_reviews(company.id)
    assert len(reviews) == 2
