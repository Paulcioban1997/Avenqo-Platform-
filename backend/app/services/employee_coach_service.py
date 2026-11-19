"""Avenqo AI Employee Performance Coach Service (Avenqo Performance Coach AI).

Provides personalized daily briefings, role-based professional coaching,
task management, and revenue optimization for authenticated employees over the phone.
Strictly tenant-isolated, role-scoped, and grounded in real database records.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from backend.app.core.locale_catalog import resolve_locale
from backend.app.models.user import User, UserRole
from backend.app.services.workspace_service import WorkspaceService

logger = logging.getLogger("avenqo.voice.employee_coach")


class EmployeeCoachService:
    """Core business intelligence engine for Avenqo Performance Coach AI."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._workspace = WorkspaceService(session)

    def get_daily_briefing(self, actor: User, locale: str = "fr-CA") -> dict[str, Any]:
        """Generate a personalized daily briefing for the authenticated employee."""
        if not actor or not actor.id or not actor.company_id:
            return {
                "status": "error",
                "error": "unauthenticated",
                "message": "Authentification requise pour accéder au coaching employé.",
            }

        briefing = self._workspace.personal_briefing(actor)
        loc = resolve_locale(locale)
        first_name = actor.first_name or ("Collègue" if loc.startswith("fr") else "Colleague")
        job_title = actor.job_title or ("Employé" if loc.startswith("fr") else "Employee")
        department = actor.department or ""
        role = actor.role.value if hasattr(actor.role, "value") else str(actor.role)

        overdue_tasks = briefing.get("overdue_tasks", [])
        today_tasks = briefing.get("today_tasks", [])
        all_open_tasks = briefing.get("open_tasks", [])
        responsibilities = briefing.get("responsibilities", [])

        # Fetch verified appointments for today if CRM module active
        appointments: list[dict[str, Any]] = []
        if "crm" in briefing.get("modules", []):
            try:
                appointments = self._workspace._today_appointments(actor)
            except Exception as exc:
                logger.debug("Failed to fetch today appointments for coach briefing: %s", exc)

        # Build Top 3 Priorities
        top_priorities: list[str] = []
        if overdue_tasks:
            top_priorities.append(
                f"Traiter la tâche prioritaire en retard : '{overdue_tasks[0]['title']}'"
                if loc.startswith("fr")
                else f"Address overdue high-priority task: '{overdue_tasks[0]['title']}'"
            )
        if today_tasks:
            top_priorities.append(
                f"Finaliser l'échéance du jour : '{today_tasks[0]['title']}'"
                if loc.startswith("fr")
                else f"Complete today's deadline: '{today_tasks[0]['title']}'"
            )
        elif len(all_open_tasks) > len(overdue_tasks):
            remaining = [t for t in all_open_tasks if t not in overdue_tasks]
            top_priorities.append(
                f"Avancer sur la tâche : '{remaining[0]['title']}'"
                if loc.startswith("fr")
                else f"Advance on task: '{remaining[0]['title']}'"
            )

        if appointments:
            top_priorities.append(
                f"Préparer et honorer vos {len(appointments)} rendez-vous clients prévus aujourd'hui."
                if loc.startswith("fr")
                else f"Prepare and attend your {len(appointments)} scheduled client appointments today."
            )

        # Role-based recommendation
        role_key = self._classify_role(job_title, department, role)
        role_action, role_tips = self._get_role_advice(role_key, loc)

        if len(top_priorities) < 3 and role_action:
            top_priorities.append(role_action)

        # Fallback if no specific tasks configured
        if not top_priorities:
            if loc.startswith("fr"):
                top_priorities = [
                    "Vérifier vos suivis et communications clients en attente.",
                    "Faire le point avec votre responsable sur vos priorités de la semaine.",
                    "Consulter les disponibilités et offres du jour.",
                ]
            else:
                top_priorities = [
                    "Check your pending client follow-ups and inquiries.",
                    "Align with your manager on top weekly priorities.",
                    "Review today's schedule and available offerings.",
                ]

        execution_order = [f"Étape {i+1} : {p}" if loc.startswith("fr") else f"Step {i+1}: {p}" for i, p in enumerate(top_priorities)]

        # Motivational encouragement
        motivation = self._get_motivation(first_name, role_key, loc)

        # Construct concise spoken summary
        if loc.startswith("fr"):
            spoken_summary = (
                f"Bonjour {first_name} ! Ravi de te retrouver pour ton shift. "
                f"Voici tes trois priorités du jour : premièrement, {top_priorities[0].lower()} ; "
                f"deuxièmement, {top_priorities[1].lower() if len(top_priorities) > 1 else 'suivre vos dossiers'} ; "
                f"et troisièmement, {top_priorities[2].lower() if len(top_priorities) > 2 else 'garder un excellent contact client'}. "
                f"{motivation}"
            )
        elif loc.startswith("es"):
            spoken_summary = (
                f"¡Hola {first_name}! Me alegro de saludarte para tu turno. "
                f"Aquí tienes tus tres prioridades de hoy: primero, {top_priorities[0]} ; "
                f"segundo, {top_priorities[1] if len(top_priorities) > 1 else 'seguimiento'} ; "
                f"y tercero, {top_priorities[2] if len(top_priorities) > 2 else 'calidad de servicio'}. "
                f"{motivation}"
            )
        elif loc.startswith("ro"):
            spoken_summary = (
                f"Salut {first_name}! Mă bucur să te aud la început de tură. "
                f"Iată cele trei priorități ale tale pentru astăzi: în primul rând, {top_priorities[0]} ; "
                f"în al doilea rând, {top_priorities[1] if len(top_priorities) > 1 else 'urmărirea clienților'} ; "
                f"iar în al treilea rând, {top_priorities[2] if len(top_priorities) > 2 else 'atenția la detalii'}. "
                f"{motivation}"
            )
        else:
            spoken_summary = (
                f"Hello {first_name}! Great to connect with you for your shift. "
                f"Here are your three priorities today: first, {top_priorities[0].lower()} ; "
                f"second, {top_priorities[1].lower() if len(top_priorities) > 1 else 'follow-up on active work'} ; "
                f"and third, {top_priorities[2].lower() if len(top_priorities) > 2 else 'maintain high customer service'}. "
                f"{motivation}"
            )

        return {
            "status": "success",
            "spoken_summary": spoken_summary,
            "employee": {
                "id": str(actor.id),
                "first_name": first_name,
                "job_title": job_title,
                "department": department,
                "role": role,
            },
            "top_priorities": top_priorities,
            "execution_order": execution_order,
            "role_recommendations": role_tips,
            "motivation": motivation,
            "tasks_summary": {
                "open_count": len(all_open_tasks),
                "overdue_count": len(overdue_tasks),
                "today_count": len(today_tasks),
            },
            "appointments_today": len(appointments),
            "responsibilities": [r.get("title") for r in responsibilities if isinstance(r, dict)],
        }

    def get_my_tasks(self, actor: User, *, status: str | None = None) -> list[dict[str, Any]]:
        """List tasks assigned to the employee."""
        if not actor or not actor.id or not actor.company_id:
            return []
        tasks = self._workspace.list_tasks(actor, mine=True)
        results = []
        for t in tasks:
            if status and t.status != status:
                continue
            results.append({
                "id": str(t.id),
                "title": t.title,
                "description": t.description,
                "priority": t.priority,
                "status": t.status,
                "due_at": t.due_at.isoformat() if t.due_at else None,
                "completed_at": t.completed_at.isoformat() if t.completed_at else None,
            })
        return results

    def complete_task(self, actor: User, task_identifier: str) -> dict[str, Any]:
        """Mark a task completed by UUID or title keyword matching."""
        if not actor or not actor.id or not actor.company_id:
            return {"status": "error", "error": "unauthenticated"}

        ident = (task_identifier or "").strip()
        if not ident:
            return {"status": "error", "error": "missing_identifier", "message": "Veuillez spécifier la tâche à compléter."}

        tasks = self._workspace.list_tasks(actor, mine=True)
        matched_task = None

        # Check if UUID
        try:
            target_uuid = UUID(ident)
            for t in tasks:
                if t.id == target_uuid:
                    matched_task = t
                    break
        except ValueError:
            pass

        # If not UUID, match by title substring
        if matched_task is None:
            norm_ident = ident.lower()
            open_tasks = [t for t in tasks if t.status != "done"]
            for t in open_tasks:
                if norm_ident in t.title.lower():
                    matched_task = t
                    break

        if matched_task is None:
            return {
                "status": "error",
                "error": "not_found",
                "message": f"Aucune tâche ouverte correspondant à '{ident}' n'a été trouvée pour votre compte.",
            }

        completed = self._workspace.complete_task(actor, matched_task.id)
        return {
            "status": "success",
            "task_id": str(completed.id),
            "title": completed.title,
            "status_after": completed.status,
            "message": f"La tâche '{completed.title}' a été marquée comme terminée avec succès.",
        }

    def get_coaching_advice(
        self,
        actor: User,
        topic: str | None = None,
        locale: str = "fr-CA",
    ) -> dict[str, Any]:
        """Provide structured, role-adapted professional coaching advice."""
        if not actor or not actor.id or not actor.company_id:
            return {"status": "error", "error": "unauthenticated"}

        loc = resolve_locale(locale)
        job_title = actor.job_title or ""
        department = actor.department or ""
        role = actor.role.value if hasattr(actor.role, "value") else str(actor.role)
        role_key = self._classify_role(job_title, department, role)

        advice_map = {
            "sales": {
                "fr": [
                    "Écoutez activement les besoins spécifiques exprimés par le client avant de présenter une solution.",
                    "Proposez de manière éthique les produits ou services complémentaires qui apportent une réelle valeur ajoutée.",
                    "Effectuez un suivi proactif des devis envoyés dans les 48 heures pour lever d'éventuels freins.",
                ],
                "en": [
                    "Actively listen to the client's specific needs before proposing a solution.",
                    "Ethically recommend complementary products or services that provide genuine value.",
                    "Follow up proactively within 48 hours on pending quotes to address any questions.",
                ],
            },
            "receptionist": {
                "fr": [
                    "Accueillez chaque appelant avec chaleur, clarté et bienveillance dès les premières secondes.",
                    "Confirmez systématiquement l'orthographe du nom, le numéro de rappel et l'objet de l'appel.",
                    "Si un transfert est nécessaire, prévenez le destinataire avant de basculer pour un passage fluide.",
                ],
                "en": [
                    "Greet every caller warmly, clearly, and attentively right from the first seconds.",
                    "Systematically confirm caller name spelling, callback number, and the purpose of call.",
                    "When transferring, warm-transfer by introducing the caller to avoid customer repetition.",
                ],
            },
            "retail": {
                "fr": [
                    "Vérifiez l'état des stocks sur les articles les plus demandés avant le pic d'affluence.",
                    "Assurez-vous que l'espace de vente est ordonné et accueillant pour faciliter le parcours client.",
                    "Suggérez aux clients les offres du moment ou les accessoires directement liés à leurs achats.",
                ],
                "en": [
                    "Check stock levels on top-selling items before peak customer traffic hours.",
                    "Keep the sales floor organized and welcoming to make shopping seamless.",
                    "Suggest relevant promotions or complementary accessories directly linked to customer choices.",
                ],
            },
            "manager": {
                "fr": [
                    "Passez en revue les éventuels goulots d'étranglement de l'équipe dès le début de journée.",
                    "Clarifiez les priorités avec chaque collaborateur et rééquilibrez la charge si nécessaire.",
                    "Soulignez les réussites récentes pour maintenir une dynamique positive et engagée.",
                ],
                "en": [
                    "Review potential operational bottlenecks with your team early in the shift.",
                    "Clarify priorities with team members and rebalance workloads as needed.",
                    "Acknowledge recent achievements to foster a positive, motivated team environment.",
                ],
            },
            "technician": {
                "fr": [
                    "Vérifiez la liste du matériel et des pièces nécessaires avant d'entamer une intervention.",
                    "Suivez rigoureusement les protocoles de conformité et de sécurité pour éviter toute reprise de travail.",
                    "Documentez avec précision les interventions réalisées pour assurer une traçabilité exemplaire.",
                ],
                "en": [
                    "Inspect the required parts and diagnostic checklist before starting any service work.",
                    "Strictly adhere to safety and quality protocols to eliminate rework.",
                    "Document all performed service steps accurately for transparent records.",
                ],
            },
            "support": {
                "fr": [
                    "Faites preuve d'empathie face à la préoccupation du client avant d'exposer la démarche technique.",
                    "Expliquez les étapes de résolution de manière simple, sans jargon inutile.",
                    "Vérifiez la satisfaction du client avant de clôturer le ticket ou l'appel.",
                ],
                "en": [
                    "Demonstrate genuine empathy for the client's concern before detailing the technical steps.",
                    "Explain resolution steps clearly and simply without unnecessary technical jargon.",
                    "Verify total customer satisfaction before marking the inquiry resolved.",
                ],
            },
        }

        lang_key = "fr" if loc.startswith("fr") else "en"
        role_tips = advice_map.get(role_key, advice_map["support"]).get(lang_key, advice_map["support"]["fr"])

        title = (
            f"Conseils de performance pour votre rôle : {job_title or role_key.capitalize()}"
            if loc.startswith("fr")
            else f"Performance coaching tips for your role: {job_title or role_key.capitalize()}"
        )

        return {
            "status": "success",
            "title": title,
            "role": role_key,
            "tips": role_tips,
            "actionable_steps": [f"1. {role_tips[0]}", f"2. {role_tips[1]}", f"3. {role_tips[2]}"],
            "topic": topic or "general_performance",
        }

    @staticmethod
    def _classify_role(job_title: str, department: str, role: str) -> str:
        text = f"{job_title} {department} {role}".lower()
        if any(w in text for w in ("vend", "sale", "représentant", "commercial", "account", "bizdev")):
            return "sales"
        if any(w in text for w in ("récept", "recept", "accueil", "standard", "secrét", "secret")):
            return "receptionist"
        if any(w in text for w in ("retail", "boutique", "magasin", "caiss", "store", "commerce")):
            return "retail"
        if any(w in text for w in ("manag", "gestio", "direct", "superv", "chef", "owner", "admin")):
            return "manager"
        if any(w in text for w in ("tech", "mécani", "ingén", "engin", "répar", "atelier")):
            return "technician"
        return "support"

    @staticmethod
    def _get_role_advice(role_key: str, loc: str) -> tuple[str, list[str]]:
        if role_key == "sales":
            action = (
                "Effectuer les relances clients et proposer les solutions complémentaires appropriées."
                if loc.startswith("fr")
                else "Execute pending client follow-ups and present relevant complementary offerings."
            )
            tips = ["Active listening", "Ethical upselling", "Timely follow-ups"]
        elif role_key == "receptionist":
            action = (
                "Confirmer les créneaux de rendez-vous de l'après-midi et fluidifier l'accueil téléphonique."
                if loc.startswith("fr")
                else "Confirm afternoon appointment slots and maintain high telephone responsiveness."
            )
            tips = ["Warm greetings", "Precise intake", "Reduced hold times"]
        elif role_key == "retail":
            action = (
                "Vérifier la disponibilité des stocks et soigner la mise en valeur des produits phares."
                if loc.startswith("fr")
                else "Verify stock levels and ensure premium presentation of flagship items."
            )
            tips = ["Stock awareness", "Merchandising", "Customer assistance"]
        elif role_key == "manager":
            action = (
                "Analyser les goulots d'étranglement de l'équipe et valider les priorités de la journée."
                if loc.startswith("fr")
                else "Analyze team bottlenecks and confirm daily departmental priorities."
            )
            tips = ["Workload balance", "Bottleneck resolution", "Team encouragement"]
        elif role_key == "technician":
            action = (
                "Inspecter la file des interventions prioritaires et respecter les protocoles de qualité."
                if loc.startswith("fr")
                else "Review priority work orders and execute standard quality procedures."
            )
            tips = ["SOP compliance", "Safety first", "Zero rework"]
        else:
            action = (
                "Prendre en charge les demandes clients ouvertes et veiller à une résolution rapide."
                if loc.startswith("fr")
                else "Handle open customer requests and ensure swift, high-satisfaction resolution."
            )
            tips = ["Customer empathy", "Accurate resolution", "Prompt response"]
        return action, tips

    @staticmethod
    def _get_motivation(first_name: str, role_key: str, loc: str) -> str:
        if loc.startswith("fr"):
            return f"Tu as toutes les compétences pour faire une excellente journée et apporter une vraie valeur à tes clients ! 🚀"
        elif loc.startswith("es"):
            return f"¡Tienes todo lo necesario para tener un día excelente y brindar un gran valor a los clientes! 🚀"
        elif loc.startswith("ro"):
            return f"Ai toate abilitățile necesare pentru a avea o zi excelentă și a oferi o experiență de top clienților! 🚀"
        else:
            return f"You have everything it takes to deliver an outstanding day and great value to customers! 🚀"


__all__ = ["EmployeeCoachService"]
