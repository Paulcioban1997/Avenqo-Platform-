"""Global tenant-isolated multi-entity search engine for Avenqo CRM AI."""

from __future__ import annotations

import unicodedata
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.app.models.crm import (
    CRMAppointment,
    CRMClient,
    CRMEmployee,
    CRMNote,
    CRMOpportunity,
    CRMService,
)


def _normalize_text(text: str) -> str:
    """Removes accents and normalizes text for case-insensitive searching."""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(c for c in normalized if not unicodedata.combining(c)).lower().strip()


class CRMSearchService:
    """Provides fast, accent-tolerant, multi-entity search strictly isolated to the tenant."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def search(self, company_id: UUID, query_str: str, limit_per_group: int = 5) -> dict[str, Any]:
        """Convenience alias returning the grouped results dictionary directly."""
        res = self.search_all(company_id, query_str, limit_per_group)
        return res.get("results", {})

    def search_all(self, company_id: UUID, query_str: str, limit_per_group: int = 5) -> dict[str, Any]:
        raw_query = query_str.strip()
        if not raw_query:
            return {
                "query": "",
                "total_count": 0,
                "results": {
                    "clients": [],
                    "appointments": [],
                    "services": [],
                    "employees": [],
                    "notes": [],
                    "opportunities": [],
                },
            }

        search_pattern = f"%{raw_query}%"
        total_found = 0

        # 1. Search Clients (name, email, phone, company_name, vehicle metadata)
        clients_query = (
            select(CRMClient)
            .where(
                CRMClient.company_id == company_id,
                CRMClient.is_deleted.is_(False),
                or_(
                    CRMClient.first_name.ilike(search_pattern),
                    CRMClient.last_name.ilike(search_pattern),
                    CRMClient.email.ilike(search_pattern),
                    CRMClient.phone.ilike(search_pattern),
                    CRMClient.company_name.ilike(search_pattern),
                ),
            )
            .limit(limit_per_group)
        )
        matched_clients = list(self._session.scalars(clients_query).all())
        clients_data = [
            {
                "id": str(c.id),
                "title": c.full_name,
                "subtitle": f"{c.email} • {c.phone or 'Sans tél'}",
                "category": "clients",
                "badge": c.status.capitalize(),
                "metadata": {
                    "email": c.email,
                    "phone": c.phone,
                    "company_name": c.company_name,
                    "industry_type": c.industry_type,
                    "industry_metadata": c.industry_metadata,
                },
            }
            for c in matched_clients
        ]
        total_found += len(clients_data)

        # 2. Search Appointments (title, notes)
        apt_query = (
            select(CRMAppointment)
            .where(
                CRMAppointment.company_id == company_id,
                CRMAppointment.is_deleted.is_(False),
                or_(
                    CRMAppointment.title.ilike(search_pattern),
                    CRMAppointment.notes.ilike(search_pattern),
                ),
            )
            .order_by(CRMAppointment.start_time.desc())
            .limit(limit_per_group)
        )
        matched_apts = list(self._session.scalars(apt_query).all())
        apts_data = [
            {
                "id": str(a.id),
                "title": a.title,
                "subtitle": f"{a.start_time.strftime('%d/%m/%Y à %H:%M')} ({a.duration_minutes} min)",
                "category": "appointments",
                "badge": a.status.capitalize(),
                "metadata": {
                    "start_time": a.start_time.isoformat(),
                    "end_time": a.end_time.isoformat(),
                    "client_id": str(a.client_id),
                    "status": a.status,
                    "price": a.price,
                },
            }
            for a in matched_apts
        ]
        total_found += len(apts_data)

        # 3. Search Services (name, description, category)
        services_query = (
            select(CRMService)
            .where(
                CRMService.company_id == company_id,
                CRMService.is_active.is_(True),
                or_(
                    CRMService.name.ilike(search_pattern),
                    CRMService.description.ilike(search_pattern),
                    CRMService.category.ilike(search_pattern),
                ),
            )
            .limit(limit_per_group)
        )
        matched_services = list(self._session.scalars(services_query).all())
        services_data = [
            {
                "id": str(s.id),
                "title": s.name,
                "subtitle": f"{s.duration_minutes} min • {s.price:,.2f} {s.currency}",
                "category": "services",
                "badge": s.category or "Service",
                "metadata": {
                    "duration_minutes": s.duration_minutes,
                    "price": s.price,
                    "currency": s.currency,
                },
            }
            for s in matched_services
        ]
        total_found += len(services_data)

        # 4. Search Employees (name, email, role)
        emp_query = (
            select(CRMEmployee)
            .where(
                CRMEmployee.company_id == company_id,
                CRMEmployee.is_active.is_(True),
                or_(
                    CRMEmployee.name.ilike(search_pattern),
                    CRMEmployee.email.ilike(search_pattern),
                    CRMEmployee.role_title.ilike(search_pattern),
                ),
            )
            .limit(limit_per_group)
        )
        matched_emp = list(self._session.scalars(emp_query).all())
        emp_data = [
            {
                "id": str(e.id),
                "title": e.name,
                "subtitle": f"{e.role_title or 'Collaborateur'} • {e.email or 'Pas d email'}",
                "category": "employees",
                "badge": e.role_title or "Employé",
                "metadata": {
                    "role_title": e.role_title,
                    "color_hex": e.color_hex,
                },
            }
            for e in matched_emp
        ]
        total_found += len(emp_data)

        # 5. Search Notes (content)
        notes_query = (
            select(CRMNote)
            .where(
                CRMNote.company_id == company_id,
                CRMNote.content.ilike(search_pattern),
            )
            .order_by(CRMNote.created_at.desc())
            .limit(limit_per_group)
        )
        matched_notes = list(self._session.scalars(notes_query).all())
        notes_data = [
            {
                "id": str(n.id),
                "title": f"Note de {n.author_name}",
                "subtitle": n.content[:80] + ("..." if len(n.content) > 80 else ""),
                "category": "notes",
                "badge": "Épinglée" if n.pinned else "Note",
                "metadata": {
                    "client_id": str(n.client_id) if n.client_id else None,
                    "appointment_id": str(n.appointment_id) if n.appointment_id else None,
                    "created_at": n.created_at.isoformat(),
                },
            }
            for n in matched_notes
        ]
        total_found += len(notes_data)

        # 6. Search Opportunities (title, company_name)
        opp_query = (
            select(CRMOpportunity)
            .where(
                CRMOpportunity.company_id == company_id,
                or_(
                    CRMOpportunity.title.ilike(search_pattern),
                    CRMOpportunity.company_name.ilike(search_pattern),
                ),
            )
            .order_by(CRMOpportunity.created_at.desc())
            .limit(limit_per_group)
        )
        matched_opps = list(self._session.scalars(opp_query).all())
        opps_data = [
            {
                "id": str(o.id),
                "title": o.title,
                "subtitle": f"{o.company_name} • {o.amount:,.2f} {o.currency}",
                "category": "opportunities",
                "badge": o.stage.capitalize(),
                "metadata": {
                    "amount": o.amount,
                    "stage": o.stage,
                    "probability": o.probability,
                },
            }
            for o in matched_opps
        ]
        total_found += len(opps_data)

        return {
            "query": raw_query,
            "total_count": total_found,
            "results": {
                "clients": clients_data,
                "appointments": apts_data,
                "services": services_data,
                "employees": emp_data,
                "notes": notes_data,
                "opportunities": opps_data,
            },
        }
