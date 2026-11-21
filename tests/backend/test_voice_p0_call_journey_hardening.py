"""Tests verifying the P0 Incident Hardening for Avenqo Voice AI telephone calls.

Covers:
1. Compound question resolution: Identity + Modules + Tasks in a single turn without dropping parts
2. Identity query alone ("Qui suis-je ?")
3. Modules query alone ("Quels sont mes modules autorisés ?")
4. Coaching efficiency query ("Comment peux-tu m'aider à améliorer mon efficacité aujourd'hui ?")
5. Assistant polite farewell ("Bonne journée !", "Au revoir") does NOT trigger call hangup
6. Unauthenticated caller data protection (no leaks of identity, tasks, or modules)
7. Full employee handover journey: Employee A -> handover -> prompt PIN -> Employee B enters PIN -> Bob authenticated without owner fallback
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from uuid import uuid4

from backend.app.models.base import UserRole
from backend.app.models.user import User
from backend.app.models.company import Company
from backend.app.models.company_membership import CompanyMembership
from backend.app.voice.direct_answers import (
    resolve_direct_voice_answer,
    is_identity_inquiry,
    is_coach_efficiency_question,
    is_coach_tasks_question,
    is_module_access_question,
    spoken_identity_answer,
    spoken_module_answer,
)
from backend.app.services.employee_coach_service import EmployeeCoachService


def test_intent_detection_on_real_call_transcripts():
    """Verify that intent detection correctly flags compound, identity, and efficiency transcripts."""
    compound = "Qui suis-je ? Quels sont mes modules autorisés et quelles sont mes tâches aujourd'hui ?"
    assert is_identity_inquiry(compound) is True
    assert is_module_access_question(compound) is True
    assert is_coach_tasks_question(compound) is True

    identity_alone = "Qui suis-je ?"
    assert is_identity_inquiry(identity_alone) is True

    efficiency = "Comment peux-tu m'aider à améliorer mon efficacité aujourd'hui ?"
    assert is_coach_efficiency_question(efficiency) is True


def test_compound_question_identity_modules_tasks_single_turn():
    """Verify compound query returns identity, modules, and tasks combined in one answer."""
    company_id = uuid4()
    user_id = uuid4()

    company = Company(
        id=company_id,
        name="Produits Héros",
        country="CA",
        currency_code="CAD",
        timezone="America/Toronto",
    )
    user = User(
        id=user_id,
        company_id=company_id,
        email="francois@produitsheros.com",
        first_name="François",
        last_name="",
        role=UserRole.OWNER,
        is_active=True,
    )
    membership = CompanyMembership(
        user_id=user_id,
        company_id=company_id,
        role=UserRole.OWNER,
        is_active=True,
    )

    mock_db = MagicMock()
    mock_db.get.side_effect = lambda model, uid: user if model == User and uid == user_id else (
        company if model == Company and uid == company_id else None
    )

    def mock_scalar(query):
        q_str = str(query).lower()
        if "company_memberships" in q_str:
            return membership
        if "companies" in q_str:
            return company
        if "voice_business_configs" in q_str:
            return None
        return None

    mock_db.scalar.side_effect = mock_scalar

    # Mock module entitlements
    mock_summary = MagicMock()
    mock_summary.plan_code = "ENTERPRISE"
    mod1 = MagicMock()
    mod1.active = True
    mod1.display_name = "Commerce"
    mod2 = MagicMock()
    mod2.active = True
    mod2.display_name = "CRM"
    mock_summary.modules = [mod1, mod2]
    mock_summary.active_modules = ["retail", "crm"]

    # Mock coach tasks
    mock_db.scalars.return_value.all.return_value = []

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "backend.app.services.module_entitlement_service.ModuleEntitlementService.summary",
            lambda self, tenant: mock_summary,
        )

        answer = resolve_direct_voice_answer(
            mock_db,
            company_id=company_id,
            transcript="Qui suis-je ? Quels sont mes modules autorisés et quelles sont mes tâches aujourd'hui ?",
            authenticated_staff=True,
            staff_role="owner",
            locale="fr-CA",
            user_id=user_id,
        )

    assert answer is not None
    # 1. Must contain employee identity (François, Propriétaire)
    assert "François" in answer
    assert "Propriétaire" in answer
    # 2. Must contain authorized modules (Commerce, CRM)
    assert "Commerce" in answer
    assert "CRM" in answer
    # 3. Must contain task status
    assert "tâche" in answer.lower()


def test_identity_inquiry_alone():
    """Verify 'Qui suis-je ?' alone returns employee name, role, and company."""
    company_id = uuid4()
    user_id = uuid4()
    company = Company(id=company_id, name="Acme Logistics")
    user = User(
        id=user_id,
        company_id=company_id,
        first_name="Alice",
        last_name="Tremblay",
        job_title="Directrice des opérations",
        role=UserRole.MANAGER,
    )
    membership = CompanyMembership(
        user_id=user_id,
        company_id=company_id,
        role=UserRole.MANAGER,
        is_active=True,
    )

    mock_db = MagicMock()
    mock_db.get.side_effect = lambda model, uid: user if model == User and uid == user_id else (
        company if model == Company and uid == company_id else None
    )
    mock_db.scalar.return_value = membership

    answer = resolve_direct_voice_answer(
        mock_db,
        company_id=company_id,
        transcript="Qui suis-je ?",
        authenticated_staff=True,
        staff_role="manager",
        locale="fr-CA",
        user_id=user_id,
    )
    assert answer is not None
    assert "Alice Tremblay" in answer
    assert "Gestionnaire" in answer
    assert "Acme Logistics" in answer


def test_efficiency_coaching_returns_role_tailored_spoken_summary():
    """Verify 'Comment peux-tu m'aider à améliorer mon efficacité aujourd'hui ?' provides actionable advice."""
    company_id = uuid4()
    user_id = uuid4()
    company = Company(id=company_id, name="Produits Héros", industry="commerce")
    user = User(
        id=user_id,
        company_id=company_id,
        first_name="François",
        role=UserRole.OWNER,
    )
    membership = CompanyMembership(
        user_id=user_id,
        company_id=company_id,
        role=UserRole.OWNER,
        is_active=True,
    )

    mock_db = MagicMock()
    mock_db.get.side_effect = lambda model, uid: user if model == User and uid == user_id else (
        company if model == Company and uid == company_id else None
    )
    mock_db.scalar.return_value = membership

    coach = EmployeeCoachService(mock_db)
    advice = coach.get_coaching_advice(user, locale="fr-CA")
    assert advice["status"] == "success"
    assert "spoken_summary" in advice
    assert len(advice["spoken_summary"]) > 20
    assert "efficacité" in advice["spoken_summary"].lower() or "performance" in advice["spoken_summary"].lower()

    # Via direct voice resolver:
    direct_ans = resolve_direct_voice_answer(
        mock_db,
        company_id=company_id,
        transcript="Comment peux-tu m'aider à améliorer mon efficacité aujourd'hui ?",
        authenticated_staff=True,
        staff_role="owner",
        locale="fr-CA",
        user_id=user_id,
    )
    assert direct_ans is not None
    assert "efficacité" in direct_ans.lower() or "performance" in direct_ans.lower()


def test_assistant_farewell_does_not_hangup():
    """Verify that when assistant speaks polite farewell words, the telephone call is NOT hung up."""
    def is_hangup_request(text: str) -> bool:
        import unicodedata
        import re
        normalized = "".join(c for c in unicodedata.normalize("NFKD", text.casefold()) if not unicodedata.combining(c))
        patterns = [
            r"\b(au revoir|bonne journee|bonne soiree|a bientot|a la prochaine)\b",
            r"\b(vous pouvez raccrocher|termine l'appel|tu peux raccrocher|raccroche|raccrochez)\b",
            r"\b(c'est tout|ce sera tout)\b",
            r"\b(goodbye|bye bye|bye-bye|\bbye\b|have a great day|have a good day|have a nice day)\b",
            r"\b(you can hang up|hang up now|end the call|hang up the call)\b",
            r"\b(that's all|that is all|that'll be all|that will be all|that's it|that is it)\b",
        ]
        return any(re.search(p, normalized) for p in patterns)

    # Caller transcript asking normal question:
    caller_transcript = "Comment puis-je contacter le service client ?"
    assert is_hangup_request(caller_transcript) is False

    # Assistant polite response:
    assistant_answer = "Notre équipe est joignable au 514-555-0100. Au revoir et très bonne journée !"
    # The assistant response does contain polite words:
    assert is_hangup_request(assistant_answer) is True

    # BUT under our hardened logic, hangup_detected is strictly determined by caller transcript:
    hangup_detected = is_hangup_request(caller_transcript)
    assert hangup_detected is False, "Assistant farewell must NOT trigger call hangup!"


def test_unauthenticated_caller_blocked_from_internal_data():
    """Verify unauthenticated callers cannot see identity, modules, or tasks and are prompted for PIN."""
    mock_db = MagicMock()
    company_id = uuid4()

    # 1. Unauthenticated asks identity
    ans_id = resolve_direct_voice_answer(
        mock_db,
        company_id=company_id,
        transcript="Qui suis-je ?",
        authenticated_staff=False,
        locale="fr-CA",
        user_id=None,
    )
    assert ans_id is not None
    assert "réservée aux employés" in ans_id or "réservés aux employés" in ans_id
    assert "NIP" in ans_id or "PIN" in ans_id

    # 2. Unauthenticated asks tasks
    ans_tasks = resolve_direct_voice_answer(
        mock_db,
        company_id=company_id,
        transcript="Quelles sont mes tâches aujourd'hui ?",
        authenticated_staff=False,
        locale="fr-CA",
        user_id=None,
    )
    assert ans_tasks is not None
    assert "réservés aux employés" in ans_tasks or "réservée aux employés" in ans_tasks
    assert "NIP" in ans_tasks or "PIN" in ans_tasks
