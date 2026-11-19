"""Service Métier pour le Module Ressources Humaines (HR AI) & Hiérarchie d'Entreprise.

Fournit la gestion complète des effectifs, l'organigramme hiérarchique, les
fiches de poste et standards opératoires (SOP) adaptés à toutes les industries,
la matrice de compétences, les congés et les revues de performance.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models.base import UserRole
from backend.app.models.company import Company
from backend.app.models.company_membership import CompanyMembership
from backend.app.models.user import User
from backend.app.models.voice import VoiceCallerCredential
from backend.app.models.workspace import (
    EmployeeLeave,
    EmployeePerformanceReview,
    EmployeeSkill,
    EmployeeTask,
)
from backend.app.schemas.hr import (
    HREmployeeItem,
    HRJobDescriptionSOP,
    HRLeaveItem,
    HROverviewResponse,
    HRPerformanceReviewItem,
    HRSectorSOPResponse,
    HRSkillItem,
)


# Standards Opératoires & Fiches de poste par secteur
SECTOR_SOPS_DATABASE: dict[str, dict[str, Any]] = {
    "automobile": {
        "sector_name": "Automobile & Mécanique",
        "overview": "Opérations de maintenance, diagnostic mécanique, gestion des pièces détachées et relation client atelier.",
        "roles": [
            {
                "role_title": "Chef d'Atelier / Maître Mécanicien",
                "department": "Atelier Mécanique",
                "hierarchy_level": "management",
                "key_responsibilities": [
                    "Supervision technique des réparations et contrôle qualité final",
                    "Planification des ponts élévateurs et attribution des ordres de réparation (OR)",
                    "Validation des devis complexes et communication avec les clients pour travaux imprévus",
                ],
                "standard_operating_procedure": [
                    "Réception du véhicule : tour du véhicule, relevé kilométrique et check-list visuelle",
                    "Vérification des codes défauts via outil OBD-II",
                    "Contrôle de conformité avant remise des clés (serrage au couple, niveaux, essai routier)",
                ],
                "safety_and_compliance": [
                    "Port des EPI obligatoires (chaussures de sécurité, lunettes, gants nitrile)",
                    "Procédure de calage sécurisé des ponts à double verrouillage mécanique",
                    "Recyclage conforme des huiles de vidange et filtres usagés",
                ],
                "time_optimization_tips": [
                    "Préparer la servante d'outils et les pièces requises avant d'installer le véhicule sur le pont (-25% temps d'intervention)",
                    "Utiliser l'assistant vocal pour dicter le compte-rendu d'intervention sans enlever ses gants",
                ],
                "revenue_booster_actions": [
                    "Contrôle systématique de l'état des balais d'essuie-glace, filtre habitacle et batterie (+15% de panier moyen)",
                    "Proposition d'un forfait préventif lors du changement des freins ou pneus",
                ],
            },
            {
                "role_title": "Technicien de Maintenance & Réparation",
                "department": "Opérations Atelier",
                "hierarchy_level": "operational",
                "key_responsibilities": [
                    "Exécution des vidanges, révisions périodiques, pneumatiques et freinage",
                    "Remplacement d'organes d'usure selon les préconisations constructeurs",
                    "Nettoyage et maintien de la propreté du poste de travail",
                ],
                "standard_operating_procedure": [
                    "Protection habitacle (housse de siège, volant, tapis de sol)",
                    "Levage du véhicule et purge des liquides dans bacs dédiés",
                    "Serrage des roues à la clé dynamométrique selon spécification constructeur",
                ],
                "safety_and_compliance": [
                    "Interdiction formelle de travailler sous un véhicule sur cric sans chandelles sécurisées",
                    "Aspiration immédiate des gaz d'échappement en atelier fermé",
                ],
                "time_optimization_tips": [
                    "Regrouper les opérations sous le véhicule avant de le redescendre pour les opérations sous capot",
                ],
                "revenue_booster_actions": [
                    "Signaler tout jeu de rotule ou usure asymétrique des pneus pour établir un devis immédiat",
                ],
            },
        ],
    },
    "construction": {
        "sector_name": "Construction & Rénovation",
        "overview": "Chantiers résidentiels et commerciaux, gros œuvre, second œuvre et respect strict des normes de sécurité.",
        "roles": [
            {
                "role_title": "Conducteur de Travaux / Chef de Chantier",
                "department": "Gestion de Projets",
                "hierarchy_level": "management",
                "key_responsibilities": [
                    "Coordination des corps de métier et planification du calendrier d'exécution",
                    "Approvisionnement en matériaux et contrôle des livraisons sur site",
                    "Respect des budgets d'heures et des jalons contractuels",
                ],
                "standard_operating_procedure": [
                    "Briefing de sécurité matinal (Quart d'heure sécurité) avec toutes les équipes",
                    "Vérification des plans d'exécution et relevé des cotes avant perçage/coulage",
                    "Rapport photo journalier de l'avancement transmis au client",
                ],
                "safety_and_compliance": [
                    "Port du casque de sécurité, gilet haute visibilité et bottes à embout d'acier",
                    "Vérification des garde-corps et harnais anti-chute pour tout travail en hauteur > 3m",
                    "Licence RBQ / CCQ et respect du Code de sécurité pour les travaux de construction",
                ],
                "time_optimization_tips": [
                    "Faire livrer les matériaux lourds directement à l'étage via grue plutôt que manutention manuelle",
                    "Validation des réservations électriques et plomberie avant fermeture des cloisons Placoplatre",
                ],
                "revenue_booster_actions": [
                    "Documenter immédiatement tout changement demandé par le client via un avenant signé avant réalisation",
                ],
            },
            {
                "role_title": "Ouvrier Spécialisé / Compagnon",
                "department": "Opérations Chantier",
                "hierarchy_level": "operational",
                "key_responsibilities": [
                    "Pose de matériaux, cloisons, plomberie ou raccordements selon plans",
                    "Manutention, découpe et mise en œuvre sécurisée des matériaux",
                    "Repli de chantier et sécurisation en fin de journée",
                ],
                "standard_operating_procedure": [
                    "Contrôle de l'outillage électroportatif et des câbles avant démarrage",
                    "Traçage au cordeau et niveau laser",
                    "Nettoyage continu des gravats pour maintenir les zones de passage dégagées",
                ],
                "safety_and_compliance": [
                    "Port de masque anti-poussière FFP3 lors des opérations de ponçage ou démolition",
                    "Coupure électrique consignée avant intervention sur tableau ou câblage",
                ],
                "time_optimization_tips": [
                    "Calibrer l'ensemble des coupes de plaques ou profilés par série de même dimension",
                ],
                "revenue_booster_actions": [
                    "Préserver les chutes réutilisables pour réduire le gaspillage de matériaux",
                ],
            },
        ],
    },
    "beaute": {
        "sector_name": "Salons de Coiffure & Esthétique",
        "overview": "Soins capillaires, prestations esthétiques, fidélisation de clientèle et vente de soins à domicile.",
        "roles": [
            {
                "role_title": "Styliste / Coiffeur Principal",
                "department": "Soins Capillaires",
                "hierarchy_level": "operational",
                "key_responsibilities": [
                    "Diagnostic cheveu et conseil personnalisé coupe, couleur et balayage",
                    "Réalisation technique des prestations dans le respect du timing fixé",
                    "Recommandation des produits d'entretien à domicile adaptés",
                ],
                "standard_operating_procedure": [
                    "Consultation initiale de 5 minutes avec écoute active des souhaits client",
                    "Pesée précise des formulations de coloration au gramme près",
                    "Fiche technique mise à jour dans le CRM avec formule exacte et temps de pause",
                ],
                "safety_and_compliance": [
                    "Test d'allergie cutanée pour tout nouveau client avant coloration",
                    "Stérilisation des ciseaux, peignes et tondeuses entre chaque client",
                ],
                "time_optimization_tips": [
                    "Appliquer le protocole de rinçage à double émulsion pour réduire le temps de séchage de 10 min",
                ],
                "revenue_booster_actions": [
                    "Proposer systématiquement un soin profond restructurant au bac (+20 à 35 $ par visite)",
                    "Planifier le rendez-vous d'entretien suivant avant le passage en caisse",
                ],
            },
        ],
    },
    "commerce": {
        "sector_name": "Commerce & Vente au Détail",
        "overview": "Boutiques, magasins spécialisés, gestion des stocks, accueil client et encaissement.",
        "roles": [
            {
                "role_title": "Conseiller de Vente / Responsable de Rayon",
                "department": "Vente en Magasin",
                "hierarchy_level": "operational",
                "key_responsibilities": [
                    "Accueil chaleureux et accompagnement conseil des clients",
                    "Maintien du merchandising, réassortiment et étiquetage des prix",
                    "Encaissement rapide et gestion sécurisée de la caisse",
                ],
                "standard_operating_procedure": [
                    "Saluer chaque client entrant dans les 10 secondes",
                    "Poser des questions ouvertes pour identifier le besoin précis",
                    "Vérification de l'adéquation stock physique et stock informatique",
                ],
                "safety_and_compliance": [
                    "Respect des règles de port de charges lourdes lors de la réception des colis",
                    "Conformité avec les règles de protection des données bancaires des clients",
                ],
                "time_optimization_tips": [
                    "Réassortir les têtes de gondole aux heures creuses pour être 100% disponible aux heures d'affluence",
                ],
                "revenue_booster_actions": [
                    "Vente complémentaire systématique (accessoires, entretien, garantie prolongée)",
                    "Collecte du courriel ou mobile pour le programme fidélité (+25% de fidélisation)",
                ],
            },
        ],
    },
    "general": {
        "sector_name": "Services & Entreprises Générales",
        "overview": "Standards universels d'efficacité opérationnelle, gestion de tâches et relation client d'excellence.",
        "roles": [
            {
                "role_title": "Responsable Opérationnel / Chef d'Équipe",
                "department": "Opérations",
                "hierarchy_level": "management",
                "key_responsibilities": [
                    "Répartition des tâches journalières selon les compétences des collaborateurs",
                    "Contrôle de la qualité d'exécution et déblocage des obstacles d'équipe",
                    "Remontée des indicateurs de performance à la direction",
                ],
                "standard_operating_procedure": [
                    "Point d'alignement rapide de 5 minutes chaque matin",
                    "Suivi de l'avancement des tâches prioritaires à mi-journée",
                    "Débriefing de fin de journée et planification du lendemain",
                ],
                "safety_and_compliance": [
                    "Respect de la confidentialité des données clients et des processus internes",
                ],
                "time_optimization_tips": [
                    "Traiter les tâches similaires par lots groupés pour éliminer le coût cognitif de changement de contexte",
                ],
                "revenue_booster_actions": [
                    "Identifier les goulots d'étranglement qui ralentissent le traitement des commandes ou dossiers",
                ],
            },
        ],
    },
}


class HRService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_overview(self, company_id: UUID) -> HROverviewResponse:
        company = self._session.get(Company, company_id)
        industry_name = getattr(company, "industry", "Services Généraux") or "Services Généraux"

        users = self._session.scalars(select(User).where(User.company_id == company_id)).all()
        total_employees = len(users)
        active_employees = sum(1 for u in users if getattr(u, "is_active", True))

        departments_set = {u.department for u in users if u.department}
        if not departments_set:
            departments_set = {"Direction", "Opérations"}

        hierarchy_breakdown = {"executive": 0, "management": 0, "operational": 0}
        for u in users:
            role_val = getattr(u, "role", None)
            job = str(getattr(u, "job_title", "")).lower()
            if role_val == UserRole.OWNER or "dirigeant" in job or "ceo" in job or "président" in job:
                hierarchy_breakdown["executive"] += 1
            elif role_val == UserRole.ADMIN or "manager" in job or "chef" in job or "responsable" in job or "lead" in job:
                hierarchy_breakdown["management"] += 1
            else:
                hierarchy_breakdown["operational"] += 1

        total_tasks = self._session.scalar(
            select(func.count(EmployeeTask.id)).where(EmployeeTask.company_id == company_id)
        ) or 0
        open_tasks = self._session.scalar(
            select(func.count(EmployeeTask.id)).where(
                EmployeeTask.company_id == company_id, EmployeeTask.status == "open"
            )
        ) or 0
        completed_tasks = self._session.scalar(
            select(func.count(EmployeeTask.id)).where(
                EmployeeTask.company_id == company_id, EmployeeTask.status == "completed"
            )
        ) or 0

        now = datetime.now(timezone.utc)
        overdue_tasks = self._session.scalar(
            select(func.count(EmployeeTask.id)).where(
                EmployeeTask.company_id == company_id,
                EmployeeTask.status == "open",
                EmployeeTask.due_at.is_not(None),
                EmployeeTask.due_at < now,
            )
        ) or 0

        # Pending leaves count
        try:
            pending_leaves = self._session.scalar(
                select(func.count(EmployeeLeave.id)).where(
                    EmployeeLeave.company_id == company_id, EmployeeLeave.status == "pending"
                )
            ) or 0
        except Exception:
            pending_leaves = 0

        return HROverviewResponse(
            total_employees=total_employees,
            active_employees=active_employees,
            departments_count=len(departments_set),
            departments=sorted(list(departments_set)),
            hierarchy_breakdown=hierarchy_breakdown,
            tasks_metrics={
                "total": total_tasks,
                "open": open_tasks,
                "completed": completed_tasks,
                "overdue": overdue_tasks,
            },
            pending_leaves_count=pending_leaves,
            company_industry=industry_name,
        )

    def list_employees(self, company_id: UUID) -> list[HREmployeeItem]:
        users = self._session.scalars(
            select(User).where(User.company_id == company_id).order_by(User.created_at.asc())
        ).all()

        results: list[HREmployeeItem] = []
        for u in users:
            cred = self._session.scalar(
                select(VoiceCallerCredential).where(
                    VoiceCallerCredential.principal_type == "USER",
                    VoiceCallerCredential.principal_id == u.id,
                    VoiceCallerCredential.company_id == company_id,
                )
            )
            has_voice_pin = cred is not None

            job = str(getattr(u, "job_title", "")).lower()
            role_val = getattr(u, "role", None)
            if role_val == UserRole.OWNER or "dirigeant" in job or "ceo" in job:
                hier = "executive"
            elif role_val == UserRole.ADMIN or "manager" in job or "chef" in job or "responsable" in job or "superviseur" in job:
                hier = "management"
            else:
                hier = "operational"

            open_tasks = self._session.scalar(
                select(func.count(EmployeeTask.id)).where(
                    EmployeeTask.company_id == company_id,
                    EmployeeTask.assignee_user_id == u.id,
                    EmployeeTask.status == "open",
                )
            ) or 0
            completed_tasks = self._session.scalar(
                select(func.count(EmployeeTask.id)).where(
                    EmployeeTask.company_id == company_id,
                    EmployeeTask.assignee_user_id == u.id,
                    EmployeeTask.status == "completed",
                )
            ) or 0

            results.append(
                HREmployeeItem(
                    id=u.id,
                    first_name=u.first_name or "",
                    last_name=u.last_name or "",
                    email=u.email,
                    phone=getattr(u, "phone", None),
                    role=str(getattr(u, "role", "user")).lower().replace("userrole.", ""),
                    job_title=u.job_title or "Collaborateur",
                    department=u.department or "Général",
                    hierarchy_level=hier,
                    is_active=getattr(u, "is_active", True),
                    has_voice_pin=has_voice_pin,
                    open_tasks_count=open_tasks,
                    completed_tasks_count=completed_tasks,
                )
            )
        return results

    def get_job_descriptions(self, company_id: UUID, sector: str | None = None) -> HRSectorSOPResponse:
        company = self._session.get(Company, company_id)
        industry = sector or (company.industry if company else "general")
        ind_lower = industry.lower()

        key = "general"
        if "auto" in ind_lower or "mécani" in ind_lower or "garage" in ind_lower:
            key = "automobile"
        elif "construct" in ind_lower or "bâtiment" in ind_lower or "rénov" in ind_lower:
            key = "construction"
        elif "beaut" in ind_lower or "coiff" in ind_lower or "esthét" in ind_lower or "spa" in ind_lower:
            key = "beaute"
        elif "retail" in ind_lower or "commerce" in ind_lower or "magasin" in ind_lower or "boutique" in ind_lower:
            key = "commerce"

        data = SECTOR_SOPS_DATABASE.get(key, SECTOR_SOPS_DATABASE["general"])
        roles = [
            HRJobDescriptionSOP(
                role_title=r["role_title"],
                department=r["department"],
                hierarchy_level=r["hierarchy_level"],
                key_responsibilities=r["key_responsibilities"],
                standard_operating_procedure=r["standard_operating_procedure"],
                safety_and_compliance=r["safety_and_compliance"],
                time_optimization_tips=r["time_optimization_tips"],
                revenue_booster_actions=r["revenue_booster_actions"],
            )
            for r in data["roles"]
        ]

        return HRSectorSOPResponse(
            sector=key,
            sector_name=data["sector_name"],
            overview=data["overview"],
            job_descriptions=roles,
        )

    def get_skills_matrix(
        self,
        company_id: UUID,
        user_id: UUID | None = None,
        department: str | None = None,
    ) -> list[HRSkillItem]:
        company = self._session.get(Company, company_id)
        ind_lower = str(getattr(company, "industry", "")).lower()
        employees = self.list_employees(company_id)
        if user_id is not None:
            employees = [e for e in employees if e.id == user_id]
        elif department is not None:
            employees = [e for e in employees if e.department == department]

        skills: list[HRSkillItem] = []

        # 1. Compétences réelles stockées en base (vérifiées ou auto-déclarées)
        query = select(EmployeeSkill).where(EmployeeSkill.company_id == company_id)
        if user_id is not None:
            query = query.where(EmployeeSkill.user_id == user_id)
        elif department is not None:
            query = query.join(User, EmployeeSkill.user_id == User.id).where(User.department == department)

        stored_skills = self._session.scalars(
            query.order_by(EmployeeSkill.created_at.desc())
        ).all()

        stored_by_user: dict[UUID, list[EmployeeSkill]] = {}
        for s in stored_skills:
            stored_by_user.setdefault(s.user_id, []).append(s)

        for emp in employees:
            emp_skills = stored_by_user.get(emp.id, [])
            emp_name = f"{emp.first_name} {emp.last_name}".strip() or emp.email

            if emp_skills:
                for s in emp_skills:
                    is_certified = (s.status == "verified" and s.verified_at is not None)
                    verifier_name = None
                    if s.verified_by_user_id:
                        verifier = self._session.get(User, s.verified_by_user_id)
                        verifier_name = f"{verifier.first_name} {verifier.last_name}".strip() if verifier else None

                    skills.append(
                        HRSkillItem(
                            id=str(s.id),
                            name=s.name,
                            category=s.category,
                            level=s.level,
                            certified=is_certified,
                            status=s.status,
                            evidence_url_or_note=s.evidence_url_or_note,
                            verified_at=s.verified_at,
                            verified_by=verifier_name,
                            employee_id=s.user_id,
                            employee_name=emp_name,
                        )
                    )
            else:
                # Aucune certification inventée sans preuve réelle.
                # Statut explicite 'not_assessed' (Non Évalué) avec niveau 1 et certified=False.
                job_lower = emp.job_title.lower()
                if "mécani" in job_lower or "auto" in job_lower or "maintenance" in job_lower or "auto" in ind_lower or "mécani" in ind_lower:
                    skills.append(HRSkillItem(id=f"{emp.id}-1", name="Diagnostic Électronique OBD", category="Technique", level=1, certified=False, status="not_assessed", employee_id=emp.id, employee_name=emp_name))
                    skills.append(HRSkillItem(id=f"{emp.id}-2", name="Freinage & Sécurité Active", category="Sécurité", level=1, certified=False, status="not_assessed", employee_id=emp.id, employee_name=emp_name))
                    skills.append(HRSkillItem(id=f"{emp.id}-3", name="Chiffrage & Devis Pièces", category="Commercial", level=1, certified=False, status="not_assessed", employee_id=emp.id, employee_name=emp_name))
                elif "chantier" in job_lower or "travaux" in job_lower or "construct" in job_lower:
                    skills.append(HRSkillItem(id=f"{emp.id}-1", name="Lecture de Plans & Cotes", category="Technique", level=1, certified=False, status="not_assessed", employee_id=emp.id, employee_name=emp_name))
                    skills.append(HRSkillItem(id=f"{emp.id}-2", name="Normes Sécurité CNESST / OSHA", category="Sécurité", level=1, certified=False, status="not_assessed", employee_id=emp.id, employee_name=emp_name))
                    skills.append(HRSkillItem(id=f"{emp.id}-3", name="Gestion des Matériaux & Stocks", category="Outils", level=1, certified=False, status="not_assessed", employee_id=emp.id, employee_name=emp_name))
                elif "coiff" in job_lower or "styliste" in job_lower or "esthét" in job_lower:
                    skills.append(HRSkillItem(id=f"{emp.id}-1", name="Techniques Coloration & Balayage", category="Technique", level=1, certified=False, status="not_assessed", employee_id=emp.id, employee_name=emp_name))
                    skills.append(HRSkillItem(id=f"{emp.id}-2", name="Conseil Vente Soins à Domicile", category="Commercial", level=1, certified=False, status="not_assessed", employee_id=emp.id, employee_name=emp_name))
                    skills.append(HRSkillItem(id=f"{emp.id}-3", name="Hygiène & Stérilisation Outils", category="Sécurité", level=1, certified=False, status="not_assessed", employee_id=emp.id, employee_name=emp_name))
                else:
                    skills.append(HRSkillItem(id=f"{emp.id}-1", name="Service & Relation Client", category="Commercial", level=1, certified=False, status="not_assessed", employee_id=emp.id, employee_name=emp_name))
                    skills.append(HRSkillItem(id=f"{emp.id}-2", name="Rigueur & Organisation des Tâches", category="Outils", level=1, certified=False, status="not_assessed", employee_id=emp.id, employee_name=emp_name))
                    skills.append(HRSkillItem(id=f"{emp.id}-3", name="Utilisation Voice AI Coach", category="Technique", level=1, certified=False, status="not_assessed", employee_id=emp.id, employee_name=emp_name))

        return skills

    def declare_skill(
        self,
        company_id: UUID,
        user_id: UUID,
        name: str,
        category: str = "Technique",
        level: int = 1,
        evidence_url_or_note: str | None = None,
    ) -> HRSkillItem:
        """Enregistre une compétence auto-déclarée par un collaborateur (non certifiée par défaut)."""
        skill = EmployeeSkill(
            id=uuid4(),
            company_id=company_id,
            user_id=user_id,
            name=name.strip(),
            category=category.strip(),
            level=max(1, min(level, 5)),
            status="self_declared",
            evidence_url_or_note=evidence_url_or_note,
            verified_at=None,
            verified_by_user_id=None,
        )
        self._session.add(skill)
        self._session.commit()
        self._session.refresh(skill)

        user = self._session.get(User, user_id)
        emp_name = f"{user.first_name} {user.last_name}".strip() if user else "Collaborateur"

        return HRSkillItem(
            id=str(skill.id),
            name=skill.name,
            category=skill.category,
            level=skill.level,
            certified=False,
            status="self_declared",
            evidence_url_or_note=skill.evidence_url_or_note,
            verified_at=None,
            verified_by=None,
            employee_id=skill.user_id,
            employee_name=emp_name,
        )

    def verify_skill(
        self,
        company_id: UUID,
        skill_id: UUID,
        verifier_user_id: UUID,
        level: int | None = None,
        evidence_url_or_note: str | None = None,
    ) -> HRSkillItem:
        """Valide et certifie formellement une compétence avec preuve et horodatage auditable."""
        skill = self._session.get(EmployeeSkill, skill_id)
        if skill is None or skill.company_id != company_id:
            raise ValueError("Compétence introuvable pour cette entreprise.")

        if skill.user_id == verifier_user_id:
            raise ValueError("Un collaborateur ne peut pas certifier ses propres compétences.")

        skill.status = "verified"
        skill.verified_at = datetime.now(timezone.utc)
        skill.verified_by_user_id = verifier_user_id
        if level is not None:
            skill.level = max(1, min(level, 5))
        if evidence_url_or_note:
            skill.evidence_url_or_note = evidence_url_or_note

        self._session.commit()
        self._session.refresh(skill)

        user = self._session.get(User, skill.user_id)
        emp_name = f"{user.first_name} {user.last_name}".strip() if user else "Collaborateur"
        verifier = self._session.get(User, verifier_user_id)
        verifier_name = f"{verifier.first_name} {verifier.last_name}".strip() if verifier else "Direction"

        return HRSkillItem(
            id=str(skill.id),
            name=skill.name,
            category=skill.category,
            level=skill.level,
            certified=True,
            status="verified",
            evidence_url_or_note=skill.evidence_url_or_note,
            verified_at=skill.verified_at,
            verified_by=verifier_name,
            employee_id=skill.user_id,
            employee_name=emp_name,
        )

    def list_leaves(
        self,
        company_id: UUID,
        user_id: UUID | None = None,
        department: str | None = None,
    ) -> list[HRLeaveItem]:
        query = select(EmployeeLeave).where(EmployeeLeave.company_id == company_id)
        if user_id is not None:
            query = query.where(EmployeeLeave.user_id == user_id)
        elif department is not None:
            query = query.join(User, EmployeeLeave.user_id == User.id).where(User.department == department)

        leaves = self._session.scalars(query.order_by(EmployeeLeave.created_at.desc())).all()

        results: list[HRLeaveItem] = []
        for l in leaves:
            user = self._session.get(User, l.user_id)
            user_name = f"{user.first_name} {user.last_name}".strip() if user else "Collaborateur"
            approver_name = None
            if l.approved_by_user_id:
                approver = self._session.get(User, l.approved_by_user_id)
                approver_name = f"{approver.first_name} {approver.last_name}".strip() if approver else None

            results.append(
                HRLeaveItem(
                    id=l.id,
                    user_id=l.user_id,
                    employee_name=user_name,
                    leave_type=l.leave_type,
                    start_date=l.start_date,
                    end_date=l.end_date,
                    days_count=l.days_count,
                    reason=l.reason,
                    status=l.status,
                    approved_by=approver_name,
                    created_at=l.created_at,
                )
            )
        return results

    def create_leave(
        self,
        company_id: UUID,
        user_id: UUID,
        leave_type: str,
        start_date: datetime,
        end_date: datetime,
        days_count: float,
        reason: str | None,
    ) -> HRLeaveItem:
        leave = EmployeeLeave(
            id=uuid4(),
            company_id=company_id,
            user_id=user_id,
            leave_type=leave_type,
            start_date=start_date,
            end_date=end_date,
            days_count=days_count,
            reason=reason,
            status="pending",
        )
        self._session.add(leave)
        self._session.commit()
        self._session.refresh(leave)

        user = self._session.get(User, user_id)
        user_name = f"{user.first_name} {user.last_name}".strip() if user else "Collaborateur"

        return HRLeaveItem(
            id=leave.id,
            user_id=leave.user_id,
            employee_name=user_name,
            leave_type=leave.leave_type,
            start_date=leave.start_date,
            end_date=leave.end_date,
            days_count=leave.days_count,
            reason=leave.reason,
            status=leave.status,
            approved_by=None,
            created_at=leave.created_at,
        )

    def update_leave_status(
        self, company_id: UUID, leave_id: UUID, approver_user_id: UUID, new_status: str
    ) -> HRLeaveItem:
        leave = self._session.get(EmployeeLeave, leave_id)
        if leave is None or leave.company_id != company_id:
            raise ValueError("Demande de congé introuvable pour cette entreprise.")

        if leave.user_id == approver_user_id:
            raise PermissionError("Vous ne pouvez pas approuver votre propre demande de congé.")

        leave.status = new_status
        leave.approved_by_user_id = approver_user_id
        self._session.commit()
        self._session.refresh(leave)

        user = self._session.get(User, leave.user_id)
        user_name = f"{user.first_name} {user.last_name}".strip() if user else "Collaborateur"
        approver = self._session.get(User, approver_user_id)
        approver_name = f"{approver.first_name} {approver.last_name}".strip() if approver else "Direction"

        return HRLeaveItem(
            id=leave.id,
            user_id=leave.user_id,
            employee_name=user_name,
            leave_type=leave.leave_type,
            start_date=leave.start_date,
            end_date=leave.end_date,
            days_count=leave.days_count,
            reason=leave.reason,
            status=leave.status,
            approved_by=approver_name,
            created_at=leave.created_at,
        )

    def list_reviews(
        self,
        company_id: UUID,
        user_id: UUID | None = None,
        department: str | None = None,
    ) -> list[HRPerformanceReviewItem]:
        query = select(EmployeePerformanceReview).where(EmployeePerformanceReview.company_id == company_id)
        if user_id is not None:
            query = query.where(EmployeePerformanceReview.user_id == user_id)
        elif department is not None:
            query = query.join(User, EmployeePerformanceReview.user_id == User.id).where(User.department == department)

        reviews = self._session.scalars(query.order_by(EmployeePerformanceReview.created_at.desc())).all()

        results: list[HRPerformanceReviewItem] = []
        for r in reviews:
            user = self._session.get(User, r.user_id)
            reviewer = self._session.get(User, r.reviewer_user_id)
            user_name = f"{user.first_name} {user.last_name}".strip() if user else "Collaborateur"
            rev_name = f"{reviewer.first_name} {reviewer.last_name}".strip() if reviewer else "Direction"

            results.append(
                HRPerformanceReviewItem(
                    id=r.id,
                    user_id=r.user_id,
                    employee_name=user_name,
                    reviewer_name=rev_name,
                    review_period=r.review_period,
                    rating=r.rating,
                    strengths=r.strengths,
                    growth_areas=r.growth_areas,
                    goals=r.goals,
                    ai_coach_notes=r.ai_coach_notes,
                    is_demo=getattr(r, "is_demo", False),
                    data_sufficient=getattr(r, "data_sufficient", True),
                    created_at=r.created_at,
                )
            )
        return results

    def create_review(
        self,
        company_id: UUID,
        user_id: UUID,
        reviewer_user_id: UUID,
        review_period: str,
        rating: float,
        strengths: str,
        growth_areas: str,
        goals: str,
        is_demo: bool = False,
    ) -> HRPerformanceReviewItem:
        if user_id == reviewer_user_id:
            raise ValueError("Un collaborateur ne peut pas s'évaluer lui-même.")

        target_user = self._session.get(User, user_id)
        if target_user is None or target_user.company_id != company_id:
            raise ValueError("Collaborateur introuvable dans cette entreprise.")

        # Vérification stricte des données opérationnelles réelles pour Voice Coach
        tasks_count = self._session.scalar(
            select(func.count(EmployeeTask.id)).where(
                EmployeeTask.company_id == company_id,
                EmployeeTask.assignee_user_id == user_id,
            )
        ) or 0
        completed_tasks = self._session.scalar(
            select(func.count(EmployeeTask.id)).where(
                EmployeeTask.company_id == company_id,
                EmployeeTask.assignee_user_id == user_id,
                EmployeeTask.status == "completed",
            )
        ) or 0

        if is_demo:
            data_sufficient = True
            ai_coach_notes = (
                f"[DÉMONSTRATION] Synthèse de performance simulée ({rating}/5). "
                "Recommandation consultative issue de l'analyse opérationnelle IA — "
                "ne constitue pas une décision RH formelle."
            )
        elif tasks_count < 2:
            data_sufficient = False
            ai_coach_notes = "Données insuffisantes pour produire une évaluation personnalisée fiable."
        else:
            data_sufficient = True
            completion_rate = round((completed_tasks / tasks_count) * 100) if tasks_count > 0 else 0
            ai_coach_notes = (
                f"Recommandation Voice Coach basée sur {completed_tasks}/{tasks_count} tâches validées ({completion_rate}% d'achèvement). "
                f"Rythme opérationnel conforme aux objectifs du département {target_user.department or 'Opérations'}. "
                "Recommandation consultative issue de l'analyse opérationnelle IA — "
                "ne constitue pas une décision RH formelle."
            )

        review = EmployeePerformanceReview(
            id=uuid4(),
            company_id=company_id,
            user_id=user_id,
            reviewer_user_id=reviewer_user_id,
            review_period=review_period,
            rating=rating,
            strengths=strengths,
            growth_areas=growth_areas,
            goals=goals,
            ai_coach_notes=ai_coach_notes,
            is_demo=is_demo,
            data_sufficient=data_sufficient,
        )
        self._session.add(review)
        self._session.commit()
        self._session.refresh(review)

        reviewer = self._session.get(User, reviewer_user_id)
        user_name = f"{target_user.first_name} {target_user.last_name}".strip() or target_user.email
        rev_name = f"{reviewer.first_name} {reviewer.last_name}".strip() if reviewer else "Direction"

        return HRPerformanceReviewItem(
            id=review.id,
            user_id=review.user_id,
            employee_name=user_name,
            reviewer_name=rev_name,
            review_period=review.review_period,
            rating=review.rating,
            strengths=review.strengths,
            growth_areas=review.growth_areas,
            goals=review.goals,
            ai_coach_notes=review.ai_coach_notes,
            is_demo=review.is_demo,
            data_sufficient=review.data_sufficient,
            created_at=review.created_at,
        )
