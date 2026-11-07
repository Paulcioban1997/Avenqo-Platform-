#!/usr/bin/env python3
"""CRM Services Read-Only Migration Inventory Tool (P10.2).

Performs a strict READ-ONLY pre-flight audit of all tenant services and historical
appointments prior to or following Alembic migration 0069.

Guarantees:
- Pure SELECT queries (zero database mutation).
- Auditable inventory of services that require explicit OWNER approval via the UI.
- Proof that historical records (services and appointments) are preserved.
- Tenant isolation and breakdown per company.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any
import sqlalchemy as sa


def run_inventory(db_url: str, company_id_filter: str | None = None) -> dict[str, Any]:
    """Execute a read-only inventory of CRM services and appointments."""
    engine = sa.create_engine(db_url)
    inspector = sa.inspect(engine)

    has_companies = inspector.has_table("companies")
    has_services = inspector.has_table("crm_services")
    has_appointments = inspector.has_table("crm_appointments")

    if not has_services:
        return {
            "status": "NO_CRM_SERVICES_TABLE",
            "db_url_masked": _mask_url(db_url),
            "total_companies": 0,
            "total_services": 0,
            "companies": [],
        }

    cols = {c["name"] for c in inspector.get_columns("crm_services")}
    has_approval_cols = "is_approved_by_owner" in cols and "is_published" in cols

    inventory: dict[str, Any] = {
        "status": "AUDIT_COMPLETE",
        "db_url_masked": _mask_url(db_url),
        "has_approval_columns": has_approval_cols,
        "migration_0069_applied": has_approval_cols,
        "total_companies": 0,
        "total_services": 0,
        "services_with_historical_appointments": 0,
        "services_requiring_owner_review": 0,
        "companies": [],
    }

    with engine.connect() as conn:
        # 1. Fetch companies
        companies_query = "SELECT id, name, slug, email, status FROM companies"
        if company_id_filter:
            companies_query += f" WHERE id = '{company_id_filter}'"
        companies_query += " ORDER BY name"

        try:
            company_rows = conn.execute(sa.text(companies_query)).fetchall()
        except Exception:
            company_rows = []

        company_map: dict[str, dict[str, Any]] = {}
        for r in company_rows:
            cid = str(r[0])
            company_map[cid] = {
                "id": cid,
                "name": r[1],
                "slug": r[2],
                "email": r[3],
                "status": r[4],
                "services": [],
            }

        # 2. Fetch services
        select_cols = "id, company_id, name, category, price, duration_minutes, is_active"
        if has_approval_cols:
            select_cols += ", is_approved_by_owner, is_published"

        svc_query = f"SELECT {select_cols} FROM crm_services"
        if company_id_filter:
            svc_query += f" WHERE company_id = '{company_id_filter}'"
        svc_query += " ORDER BY company_id, name"

        services_rows = conn.execute(sa.text(svc_query)).fetchall()

        # 3. Fetch appointment stats per service if table exists
        appt_stats: dict[str, dict[str, int]] = {}
        if has_appointments:
            appt_query = """
                SELECT service_id, 
                       COUNT(*) as total_appts,
                       SUM(CASE WHEN status IN ('confirmed', 'completed') THEN 1 ELSE 0 END) as confirmed_appts
                FROM crm_appointments
                WHERE service_id IS NOT NULL
                GROUP BY service_id
            """
            for row in conn.execute(sa.text(appt_query)).fetchall():
                sid = str(row[0])
                appt_stats[sid] = {
                    "total_appointments": int(row[1] or 0),
                    "confirmed_or_completed": int(row[2] or 0),
                }

        # 4. Collate services into companies
        for row in services_rows:
            sid = str(row[0])
            cid = str(row[1])
            name = row[2]
            category = row[3]
            price = float(row[4] or 0.0)
            duration = int(row[5] or 0)
            is_active = bool(row[6])

            if has_approval_cols:
                is_approved = bool(row[7])
                is_published = bool(row[8])
            else:
                # Pre-migration: all services are unapproved by default in the upcoming 0069
                is_approved = False
                is_published = False

            stats = appt_stats.get(sid, {"total_appointments": 0, "confirmed_or_completed": 0})
            has_appts = stats["total_appointments"] > 0
            has_confirmed = stats["confirmed_or_completed"] > 0

            # Classification
            if not is_approved or not is_published:
                if has_confirmed:
                    status_flag = "REQUIRES_OWNER_UI_VALIDATION"
                    guidance = "Service a des rendez-vous historiques confirmés mais reste non publié jusqu'à approbation explicite OWNER."
                else:
                    status_flag = "UNPUBLISHED_INACTIVE_OR_DRAFT"
                    guidance = "Service non publié (brouillon, démo ou sans rendez-vous confirmé)."
            else:
                status_flag = "EXPLICITLY_APPROVED_AND_PUBLISHED"
                guidance = "Service commercialement actif et approuvé par le propriétaire."

            svc_info = {
                "id": sid,
                "name": name,
                "category": category,
                "price": price,
                "duration_minutes": duration,
                "is_active": is_active,
                "is_approved_by_owner": is_approved,
                "is_published": is_published,
                "total_appointments": stats["total_appointments"],
                "confirmed_appointments": stats["confirmed_or_completed"],
                "status_flag": status_flag,
                "guidance": guidance,
            }

            inventory["total_services"] += 1
            if has_appts:
                inventory["services_with_historical_appointments"] += 1
            if status_flag == "REQUIRES_OWNER_UI_VALIDATION":
                inventory["services_requiring_owner_review"] += 1

            if cid in company_map:
                company_map[cid]["services"].append(svc_info)
            else:
                if cid not in company_map:
                    company_map[cid] = {
                        "id": cid,
                        "name": f"Unknown Company ({cid})",
                        "slug": "",
                        "email": "",
                        "status": "UNKNOWN",
                        "services": [svc_info],
                    }

        inventory["total_companies"] = len(company_map)
        inventory["companies"] = list(company_map.values())

    return inventory


def format_markdown_report(inventory: dict[str, Any]) -> str:
    """Format the inventory results as a clean, auditable Markdown report."""
    md = []
    md.append("# 📊 Inventaire Pré-Migration CRM 0069 — Validation des Prestations (P10.2)")
    md.append("")
    md.append(f"- **Statut DB**: `{inventory['status']}`")
    md.append(f"- **URL Cible**: `{inventory['db_url_masked']}`")
    md.append(f"- **Migration 0069 Appliquée**: `{inventory['migration_0069_applied']}`")
    md.append(f"- **Nombre d'entreprises**: `{inventory['total_companies']}`")
    md.append(f"- **Nombre total de prestations**: `{inventory['total_services']}`")
    md.append(f"- **Prestations avec historique de rendez-vous**: `{inventory['services_with_historical_appointments']}`")
    md.append(f"- **Prestations nécessitant une validation OWNER via l'UI**: `{inventory['services_requiring_owner_review']}`")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 🛡️ Stratégie Fail-Closed et Conservation Explicite")
    md.append("")
    md.append("1. **Zéro inférence automatique** : Un rendez-vous historique (même confirmé ou complété) ne constitue pas une approbation commerciale du propriétaire.")
    md.append("2. **Préservation stricte** : Aucun rendez-vous ni aucune prestation n'est supprimé.")
    md.append("3. **Procédure d'approbation auditable** :")
    md.append("   - Le propriétaire (`role = OWNER`) se connecte à la console Avenqo.")
    md.append("   - Accède à `Paramètres CRM` > `Prestations`.")
    md.append("   - Examine chaque prestation et clique sur **Approuver et publier**.")
    md.append("   - Un journal d'audit immuable (`AuditLogEntry`, action: `crm_service_approval_toggled`) consigne l'acteur, la date et le statut.")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 🏢 Détail par Entreprise")
    md.append("")

    for c in inventory["companies"]:
        md.append(f"### Entreprise : {c['name']} (`{c['id']}`)")
        md.append(f"- **Statut**: `{c.get('status', 'N/A')}` | **Slug**: `{c.get('slug', 'N/A')}`")
        services = c.get("services", [])
        if not services:
            md.append("- *Aucune prestation enregistrée.*")
            md.append("")
            continue

        md.append("")
        md.append("| Prestation | Catégorie | Prix | Durée | Approuvé | Publié | Rdv Conf. | Statut / Action Requise |")
        md.append("|---|---|---|---|---|---|---|---|")
        for s in services:
            appr = "✅ Oui" if s["is_approved_by_owner"] else "❌ Non"
            pub = "✅ Oui" if s["is_published"] else "❌ Non"
            md.append(
                f"| **{s['name']}** | `{s['category'] or 'sans'}` | {s['price']} $ | {s['duration_minutes']}m | "
                f"{appr} | {pub} | {s['confirmed_appointments']} | `{s['status_flag']}` |"
            )
        md.append("")

    return "\n".join(md)


def _mask_url(url: str) -> str:
    """Mask credentials in database URLs for security."""
    if "@" in url:
        prefix, rest = url.split("@", 1)
        protocol = prefix.split("://")[0] if "://" in prefix else ""
        return f"{protocol}://***:***@{rest}"
    return url


def main() -> None:
    parser = argparse.ArgumentParser(description="CRM Services Read-Only Migration Inventory")
    parser.add_argument(
        "--db-url",
        dest="db_url",
        default=os.environ.get("ALEMBIC_DATABASE_URL") or os.environ.get("DATABASE_URL") or "sqlite:///./avenqo.db",
        help="Database URL (default: ALEMBIC_DATABASE_URL or DATABASE_URL)",
    )
    parser.add_argument(
        "--company-id",
        dest="company_id",
        default=None,
        help="Optional company UUID filter",
    )
    parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Output as raw JSON",
    )
    parser.add_argument(
        "--output",
        dest="output_file",
        default=None,
        help="Write report to file instead of stdout",
    )
    args = parser.parse_args()

    inventory = run_inventory(args.db_url, company_id_filter=args.company_id)

    if args.as_json:
        output = json.dumps(inventory, indent=2, ensure_ascii=False)
    else:
        output = format_markdown_report(inventory)

    if args.output_file:
        with open(args.output_file, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Rapport d'inventaire sauvegardé dans: {args.output_file}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
