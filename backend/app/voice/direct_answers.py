"""Tenant-scoped spoken answers that must not depend on model routing.

Module discovery uses the authenticated employee's company entitlements.
Catalog answers use that same company's retail records. Nothing is invented,
and another tenant's rows are never readable from a different company id.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import Company, CompanyMembership, User, VoiceBusinessConfig


def _words(text: str) -> set[str]:
    normalized = unicodedata.normalize("NFKD", text.casefold())
    ascii_text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return set(re.findall(r"[a-z0-9]+", ascii_text))


def is_identity_inquiry(text: str) -> bool:
    norm = unicodedata.normalize("NFKD", text.casefold())
    norm = "".join(c for c in norm if not unicodedata.combining(c))
    phrase_match = bool(re.search(
        r"\b(qui\s+suis\s*je|qui\s+je\s+suis|quel\s+est\s+mon\s+(?:nom|role|compte|statut)|qui\s+parle|"
        r"who\s+am\s+i|what\s+is\s+my\s+(?:name|role|account|status)|"
        r"quien\s+soy|cual\s+es\s+mi\s+(?:nombre|rol|cuenta|estado)|"
        r"cine\s+sunt|cum\s+ma\s+cheama|care\s+este\s+rolul\s+meu)\b",
        norm,
    ))
    if phrase_match:
        return True
    words = _words(text)
    has_target = bool(words & {"qui", "nom", "role", "compte", "who", "name", "quien", "rol", "cine", "nume"})
    has_self = bool(words & {"suis", "mon", "mes", "am", "my", "soy", "mi", "sunt", "meu"})
    return has_target and has_self and bool(words & {"qui", "who", "quien", "cine"})


def is_coach_efficiency_question(text: str) -> bool:
    norm = unicodedata.normalize("NFKD", text.casefold())
    norm = "".join(c for c in norm if not unicodedata.combining(c))
    words = _words(text)

    # 1. Non-coaching business operations (CRM, appointments, reservations, orders, catalog, billing, hiring)
    # MUST NOT route to coaching even if phrased as "comment peux-tu m'aider à..."
    if words & {
        "rendez", "vous", "rdv", "reservation", "reserver", "booking", "appointment", "cita", "programare",
        "commande", "commandes", "order", "orders", "panier", "cart", "comanda", "pedido",
        "catalogue", "catalog", "catalogs", "catalogues", "prix", "price", "pret", "precio",
        "facture", "factures", "invoice", "invoices", "paiement", "payment",
        "recrutement", "embauche", "candidature", "cv", "job", "hiring", "fournisseur", "fournisseurs", "supplier",
    }:
        return False

    # 2. Strict regex targeting efficiency, productivity, and professional guidance
    phrase_match = bool(re.search(
        r"\b(ameliorer\s+(?:mon\s+)?efficacite|ameliorer\s+(?:mes\s+)?performances?|ameliorer\s+(?:ma\s+)?productivite|"
        r"conseils?\s+(?:pour\s+)?(?:aujourd['’\s]hui|la\s+journee|mon\s+travail)|"
        r"comment\s+(?:peux[- ]tu\s+m['’]aider\s+a\s+(?:ameliorer|optimiser|etre\s+plus\s+efficace|mieux\s+travailler)|mieux\s+travailler|etre\s+plus\s+efficace)|"
        r"improve\s+(?:my\s+)?efficiency|improve\s+(?:my\s+)?performance|improve\s+(?:my\s+)?productivity|"
        r"how\s+can\s+you\s+help\s+me\s+(?:improve|be\s+more\s+efficient|work\s+better)|"
        r"coaching\s+du\s+jour|conseil\s+du\s+jour)\b",
        norm,
    ))
    if phrase_match:
        return True

    # 3. Fallback: requires BOTH an explicit efficiency topic and guidance action
    efficiency = bool(words & {"efficacite", "productivite", "performance", "performances", "efficiency", "productivity"})
    guidance = bool(words & {"ameliorer", "optimiser", "conseil", "conseils", "mieux", "improve", "advice"})
    return efficiency and guidance


def is_module_access_question(text: str) -> bool:
    words = _words(text)
    if words & {"contrat", "contrats", "contract", "contracts", "clause", "clauses", "nda", "juridique", "avocat"}:
        return False
    modules = bool(words & {"module", "modules", "modulo", "modulos", "fonctionnalite", "fonctionnalites"})
    access = bool(words & {
        "accessible", "accessibles", "disponible", "disponibles", "actif", "actifs", "active", "actives", "activee", "activees",
        "inclus", "incluse", "incluses", "abonnement", "subscription", "entreprise", "avenqo",
        "souscrit", "souscrits", "souscrite", "souscrites", "avons", "avez", "notre", "nos", "disposons",
        "liste", "quels", "quelles", "quel", "quelle", "what", "which", "ce", "care", "activat", "activate",
        "activo", "activos", "activado", "activados", "cuales", "cuanto",
    })
    return (modules and access) or (modules and len(words) <= 6 and bool(words & {"quels", "quelles", "quel", "quelle", "what", "which", "nos", "notre", "liste"}))


def is_coach_briefing_question(text: str) -> bool:
    words = _words(text)
    is_briefing = bool(words & {
        "briefing", "shift", "priorite", "priorites", "priority", "priorities",
        "focus", "journee", "today", "programme", "matinee", "shift",
    })
    is_guidance = bool(words & {
        "faire", "ameliorer", "performance", "performances", "commencer", "commence",
        "start", "do", "improve", "conseil", "conseils", "guide", "guider",
    })
    return (is_briefing and is_guidance) or ("briefing" in words)


def is_coach_tasks_question(text: str) -> bool:
    words = _words(text)
    is_task = bool(words & {"tache", "taches", "task", "tasks", "a faire"})
    is_inquiry = bool(words & {"mes", "quelles", "quel", "liste", "my", "what", "which", "list", "combien"})
    return is_task and is_inquiry


def is_coach_optimize_task_question(text: str) -> bool:
    words = _words(text)
    optimize = bool(words & {
        "optimiser", "optimise", "comment", "conseille", "conseil", "conseils",
        "mieux", "vite", "efficace", "astuce", "recommandation", "recommandations",
        "ameliorer", "aide", "aider", "preparer", "dire", "appeler", "contacter", "joindre",
    })
    task_word = bool(words & {
        "tache", "travail", "intervention", "pose", "reparation", "coupe", "devis",
        "reclamation", "chantier", "client", "frein", "vidange", "carrelage",
        "transport", "transporteur", "livraison", "expedition", "colis", "fret",
        "marketing", "prospect", "prospects", "campagne", "vente",
    })
    return optimize and task_word


def is_executive_strategic_question(text: str) -> bool:
    words = _words(text)
    strategic = bool(words & {"strategique", "strategie", "executif", "direction", "situation", "bilan", "conversion", "chiffre", "affaires", "chiffre d'affaires"})
    point = bool(words & {"point", "briefing", "etat", "resume", "vue", "dashboard", "taux", "comment"})
    return strategic and point


def is_open_catalog_question(text: str) -> bool:
    words = _words(text)
    products = bool(words & {
        "produit", "produits", "product", "products", "article", "articles",
        "catalogue", "catalog", "catalogs", "catalogues", "item", "items",
        "planche", "planches", "snowboard", "snowboards",
    })
    if not products:
        return False
    listing = bool(words & {
        "quels", "quelles", "quel", "quelle", "liste", "what", "which",
        "catalogue", "catalog", "chacun", "chacune", "tous", "toutes", "all", "every", "each",
    })
    for_sale = bool(words & {"vente", "vendre", "sale", "sales"})
    prices = bool(words & {"prix", "price", "prices", "tarif", "tarifs", "combien", "cout"})
    stock_inquiry = bool(words & {
        "stock", "stocks", "inventaire", "inventory", "disponible", "disponibles",
        "disponibilite", "disponibilites", "restant", "restants",
    })
    return listing or for_sale or prices or stock_inquiry


def spoken_identity_answer(
    actor: Any,
    membership: Any,
    company_name: str | None,
    locale: str,
) -> str:
    loc = locale.lower()
    first_name = (getattr(actor, "first_name", "") or "").strip()
    last_name = (getattr(actor, "last_name", "") or "").strip()
    full_name = f"{first_name} {last_name}".strip() or first_name or "Collaborateur"
    raw_role = (
        membership.role.value
        if membership and hasattr(membership.role, "value")
        else str(getattr(membership, "role", "") or getattr(actor, "role", "") or "member")
    ).lower()

    role_map_fr = {
        "owner": "Propriétaire",
        "admin": "Administrateur",
        "manager": "Gestionnaire",
        "employee": "Employé",
        "staff": "Collaborateur",
        "member": "Membre de l'équipe",
        "viewer": "Consultant",
    }
    role_map_en = {
        "owner": "Owner",
        "admin": "Administrator",
        "manager": "Manager",
        "employee": "Employee",
        "staff": "Staff member",
        "member": "Team member",
        "viewer": "Viewer",
    }
    role_map_es = {
        "owner": "Propietario",
        "admin": "Administrador",
        "manager": "Gerente",
        "employee": "Empleado",
        "staff": "Colaborador",
        "member": "Miembro del equipo",
        "viewer": "Consultor",
    }
    role_map_ro = {
        "owner": "Proprietar",
        "admin": "Administrator",
        "manager": "Manager",
        "employee": "Angajat",
        "staff": "Colaborator",
        "member": "Membru al echipei",
        "viewer": "Vizitator",
    }
    c_name = company_name or ("votre entreprise" if loc.startswith("fr") else "your company")
    job = f" ({actor.job_title})" if getattr(actor, "job_title", None) else ""
    if loc.startswith("fr"):
        r_title = role_map_fr.get(raw_role, "Collaborateur")
        return f"Vous êtes {full_name}, {r_title}{job} chez {c_name}."
    elif loc.startswith("es"):
        r_title = role_map_es.get(raw_role, "Colaborador")
        return f"Usted es {full_name}, {r_title}{job} en {c_name}."
    elif loc.startswith("ro"):
        r_title = role_map_ro.get(raw_role, "Colaborator")
        return f"Sunteți {full_name}, {r_title}{job} la {c_name}."
    else:
        r_title = role_map_en.get(raw_role, "Staff member")
        return f"You are {full_name}, {r_title}{job} at {c_name}."


def spoken_module_answer(names: list[str], *, plan_code: str | None, locale: str) -> str:
    loc = locale.lower()
    french = loc.startswith("fr")
    romanian = loc.startswith("ro")
    spanish = loc.startswith("es")
    unique = []
    for name in names:
        cleaned = str(name).strip()
        if cleaned and cleaned not in unique:
            unique.append(cleaned)
    plan = (plan_code or "").strip()
    if spanish:
        if not unique:
            base = "Su empresa no tiene actualmente ningún módulo activo."
        else:
            base = "Su empresa cuenta actualmente con los siguientes módulos: " + ", ".join(unique) + "."
        if plan:
            return f"Su suscripción {plan} está activa. {base}"
        return base
    if romanian:
        if not unique:
            base = "Compania dumneavoastră nu are în prezent niciun modul activ."
        else:
            base = "Compania dumneavoastră dispune în prezent de următoarele module: " + ", ".join(unique) + "."
        if plan:
            return f"Abonamentul dumneavoastră {plan} este activ. {base}"
        return base
    if french:
        if not unique:
            base = "Votre entreprise n'a actuellement aucun module actif."
        else:
            base = "Votre entreprise dispose actuellement des modules suivants : " + ", ".join(unique) + "."
        if plan:
            return f"Votre abonnement {plan} est actif. {base}"
        return base
    if not unique:
        base = "Your company does not currently have any active modules."
    else:
        base = "Your company currently has these modules: " + ", ".join(unique) + "."
    if plan:
        return f"Your {plan} subscription is active. {base}"
    return base


def spoken_catalog_answer(
    products: Any,
    *,
    retail_enabled: bool,
    locale: str,
    currency: str | None = None,
) -> str:
    loc = locale.lower()
    french = loc.startswith("fr")
    romanian = loc.startswith("ro")
    spanish = loc.startswith("es")
    if not retail_enabled:
        if spanish:
            return "El catálogo de ventas no está disponible para su empresa."
        if romanian:
            return "Catalogul de vânzări nu este disponibil pentru compania dumneavoastră."
        return (
            "Le catalogue de vente n'est pas disponible pour votre entreprise."
            if french else
            "The sales catalog is not available for your company."
        )
    rows = [
        row for row in products
        if isinstance(row, dict) and str(row.get("name") or row.get("title") or row.get("product_name") or "").strip()
    ]
    if not rows:
        if spanish:
            return "El catálogo no contiene actualmente ningún producto a la venta."
        if romanian:
            return "Catalogul nu conține în prezent niciun produs de vânzare."
        return (
            "Le catalogue ne contient actuellement aucun produit en vente."
            if french else
            "The catalog does not currently list any products for sale."
        )
    spoken = []
    for row in rows[:3]:
        name = str(row.get("name") or row.get("title") or row.get("product_name") or "").strip()
        price = row.get("price")
        raw_unit = str(row.get("currency") or currency or "").strip().upper()
        if raw_unit in ("CAD", "USD", "$") or not raw_unit:
            unit = "$"
        elif raw_unit in ("EUR", "€"):
            unit = "€"
        elif raw_unit in ("GBP", "£"):
            unit = "£"
        else:
            unit = raw_unit
        is_live = row.get("is_live_stock") is True
        freshness = str(row.get("freshness_status") or "").upper()
        is_demo_row = row.get("is_demo") is True or freshness == "DEMO_SIMULATION"
        if price is None or price == "":
            price_text = "precio no especificado" if spanish else ("preț nespecificat" if romanian else ("prix non indiqué" if french else "price not listed"))
        else:
            price_text = f"{price} {unit}".strip()
            if is_demo_row:
                demo_tag = " (precio de demostración)" if spanish else (" (preț demonstrativ)" if romanian else (" (prix démonstration)" if french else " (demo price)"))
                price_text += demo_tag
            elif row.get("price_status") == "historical_catalog" or not is_live:
                hist_tag = " (precio de referencia)" if spanish else (" (preț de referință)" if romanian else (" (prix indicatif)" if french else " (reference price)"))
                price_text += hist_tag

        available = ""
        inventory = row.get("inventory_count")
        stock_avail = row.get("stock_availability")
        if is_demo_row:
            available = ", datos de demostración" if spanish else (", date demonstrative" if romanian else (", données de démonstration" if french else ", demo data"))
        elif is_live and (stock_avail == "IN_STOCK" or row.get("in_stock") is True):
            available = ", disponible" if spanish else (", disponibil" if romanian else (", disponible" if french else ", available"))
        elif is_live and (stock_avail == "OUT_OF_STOCK" or row.get("in_stock") is False):
            available = ", agotado" if spanish else (", stoc epuizat" if romanian else (", en rupture de stock" if french else ", out of stock"))
        elif freshness == "STALE":
            available = ", datos de stock no recientes" if spanish else (", date de stoc expirate" if romanian else (", données de stock non récentes" if french else ", stock data stale"))
        elif freshness == "UNAVAILABLE":
            available = ", stock no disponible" if spanish else (", stoc indisponibil" if romanian else (", stock indisponible" if french else ", stock unavailable"))
        elif freshness == "SYNCING":
            available = ", sincronización de stock en curso" if spanish else (", sincronizare stoc în curs" if romanian else (", synchronisation de stock en cours" if french else ", stock syncing in progress"))
        elif freshness == "UNCONFIRMED_HISTORICAL":
            available = ", stock en directo no confirmado" if spanish else (", stoc direct neconfirmat" if romanian else (", stock en direct non synchronisé" if french else ", live stock unconfirmed"))
        else:
            available = ", stock en directo no confirmado" if spanish else (", stoc direct neconfirmat" if romanian else (", stock direct non confirmé" if french else ", live stock unconfirmed"))
        spoken.append(f"{name}, {price_text}{available}")
    extra = ""
    if len(rows) > 3:
        remaining = len(rows) - 3
        if spanish:
            extra = f" Y {remaining} {'artículo' if remaining == 1 else 'artículos'} más en el catálogo."
        elif romanian:
            extra = f" Și încă {remaining} {'articol' if remaining == 1 else 'articole'} în catalog."
        elif french:
            extra = f" Et {remaining} autre{'s' if remaining > 1 else ''} article{'s' if remaining > 1 else ''} au catalogue."
        else:
            extra = f" And {remaining} more items in the catalog."
    if spanish:
        return "Tenemos en el catálogo: " + " ; ".join(spoken) + "." + extra
    if romanian:
        return "Avem în catalog: " + " ; ".join(spoken) + "." + extra
    if french:
        return "Nous avons au catalogue : " + " ; ".join(spoken) + "." + extra
    return "In our catalog, we have: " + "; ".join(spoken) + "." + extra


def is_language_inquiry(text: str) -> str | None:
    """Detect if caller is asking about language capabilities (Spanish, English, French, Romanian)."""
    normalized = unicodedata.normalize("NFKD", text.casefold())
    ascii_text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    if re.search(r"\b(habla|hablas|hablo|hablar|hablan)\b.{0,15}\b(espanol|spanish)\b|\b(parlez|parle|parlez-vous|tu parles|vous parlez)\b.{0,15}\b(espagnol|spanish)\b|\b(do you speak|can you speak)\b.{0,15}\b(spanish|espanol)\b|\b(en espanol|en espagnol)\b", ascii_text):
        return "es"
    if re.search(r"\b(do you speak|can you speak)\b.{0,15}\b(english)\b|\b(parlez|parle|parlez-vous|tu parles|vous parlez)\b.{0,15}\b(anglais|english)\b|\b(habla|hablas|hablo)\b.{0,15}\b(ingles|english)\b|\b(in english|en anglais)\b", ascii_text):
        return "en"
    if re.search(r"\b(parlez|parle|parlez-vous|tu parles|vous parlez)\b.{0,15}\b(francais|french)\b|\b(do you speak|can you speak)\b.{0,15}\b(french)\b|\b(habla|hablas|hablo)\b.{0,15}\b(frances|french)\b|\b(en francais|in french)\b", ascii_text):
        return "fr"
    if re.search(r"\b(vorbiti|vorbim|vorbesti)\b.{0,15}\b(romana)\b|\b(parlez|parlez-vous|do you speak)\b.{0,15}\b(roumain|romanian)\b", ascii_text):
        return "ro"
    return None


def is_language_authorized_for_company(db: Session, company_id: UUID, lang_code: str) -> bool:
    """Check if a language code (e.g. 'es', 'fr', 'en', 'ro') is authorized for the given tenant."""
    from backend.app.services.tenant_locale_service import get_stored_profile, authorized_locales

    lang_prefix = lang_code.casefold().split("-")[0]
    profile = get_stored_profile(db, company_id)
    if profile is not None:
        locales = authorized_locales(profile)
        for loc in locales:
            if loc.casefold().startswith(lang_prefix):
                return True
        return False

    cfg = db.scalar(select(VoiceBusinessConfig).where(VoiceBusinessConfig.company_id == company_id))
    if cfg and cfg.preferred_language:
        if cfg.preferred_language.casefold().startswith(lang_prefix):
            return True
        policy = getattr(cfg, "call_policy", None) or {}
        if isinstance(policy, dict):
            extra = policy.get("authorized_languages") or policy.get("secondary_languages") or []
            if isinstance(extra, list):
                for el in extra:
                    if str(el).casefold().startswith(lang_prefix):
                        return True

    comp = db.scalar(select(Company).where(Company.id == company_id))
    if comp and comp.preferred_language:
        if comp.preferred_language.casefold().startswith(lang_prefix):
            return True

    return lang_prefix == "fr"


def resolve_direct_voice_answer(
    db: Session | None,
    *,
    company_id: UUID,
    transcript: str,
    authenticated_staff: bool,
    staff_role: str | None = None,
    locale: str,
    user_id: UUID | None = None,
) -> str | None:
    """Return a spoken answer, or None when Central AI should handle the turn."""
    if db is None:
        return None

    # 1. Tenant-authorized language detection (Spanish, English, French, Romanian)
    lang_inquiry = is_language_inquiry(transcript)
    if lang_inquiry:
        cfg = db.scalar(select(VoiceBusinessConfig).where(VoiceBusinessConfig.company_id == company_id))
        comp = db.scalar(select(Company).where(Company.id == company_id)) if cfg is None else None

        # Clean tenant brand name: NO global fallback to "Produits Héros"!
        brand_name = None
        if cfg:
            brand_name = (
                getattr(cfg, "effective_voice_name", None)
                or getattr(cfg, "voice_display_name", None)
                or getattr(cfg, "business_name", None)
            )
        elif comp:
            brand_name = comp.name

        if brand_name:
            brand_name = str(brand_name).replace("_", " ").strip()

        # Check tenant language authorization
        if not is_language_authorized_for_company(db, company_id, lang_inquiry):
            if lang_inquiry == "es":
                if brand_name:
                    return f"Lo sentimos, la atención en español no está disponible para {brand_name}. Podemos atenderle en francés o inglés."
                return "Lo sentimos, la atención en español no está disponible para esta empresa. Podemos atenderle en francés o inglés."
            elif lang_inquiry == "en":
                if brand_name:
                    return f"Sorry, English assistance is not currently available for {brand_name}."
                return "Sorry, English assistance is not currently available for this business."
            elif lang_inquiry == "ro":
                if brand_name:
                    return f"Ne pare rău, asistența în limba română nu este disponibilă pentru {brand_name}."
                return "Ne pare rău, asistența în limba română nu este disponibilă pentru această companie."
            elif lang_inquiry == "fr":
                if brand_name:
                    return f"Désolé, l'assistance en français n'est pas disponible pour {brand_name}."
                return "Désolé, l'assistance en français n'est pas disponible pour cette entreprise."
            return None

        # Language confirmed authorized:
        if lang_inquiry == "es":
            return f"¡Hola! Sí, hablo español. ¿En qué puedo ayudarle hoy en {brand_name}?" if brand_name else "¡Hola! Sí, hablo español. ¿En qué puedo ayudarle hoy?"
        elif lang_inquiry == "en":
            return f"Hello! Yes, I speak English. How can I help you today at {brand_name}?" if brand_name else "Hello! Yes, I speak English. How can I help you today?"
        elif lang_inquiry == "ro":
            return f"Bună ziua! Da, vorbesc limba română. Cu ce vă pot ajuta astăzi la {brand_name}?" if brand_name else "Bună ziua! Da, vorbesc limba română. Cu ce vă pot ajuta astăzi?"
        elif lang_inquiry == "fr":
            return f"Bonjour ! Oui, je parle français. Comment puis-je vous aider aujourd'hui chez {brand_name} ?" if brand_name else "Bonjour ! Oui, je parle français. Comment puis-je vous aider aujourd'hui ?"

    # 2. Check for employee internal requests: identity, modules, coach tasks, coaching efficiency, briefing, optimize, executive
    has_identity = is_identity_inquiry(transcript)
    has_modules = is_module_access_question(transcript)
    has_tasks = is_coach_tasks_question(transcript)
    has_efficiency = is_coach_efficiency_question(transcript)
    has_briefing = is_coach_briefing_question(transcript)
    has_optimize = is_coach_optimize_task_question(transcript)
    has_exec = is_executive_strategic_question(transcript)

    is_internal_staff_request = (
        has_identity
        or has_modules
        or has_tasks
        or has_efficiency
        or has_briefing
        or has_optimize
        or has_exec
    )

    if is_internal_staff_request:
        if not authenticated_staff or user_id is None:
            # Only intercept if this is explicitly an internal employee inquiry,
            # avoiding blocking general public customer inquiries (e.g. "Comment fonctionne la livraison ?").
            is_explicit_internal_inquiry = (
                has_identity
                or has_modules
                or has_tasks
                or has_briefing
                or has_exec
                or bool(_words(transcript) & {"tache", "taches", "briefing", "quart", "shift", "priorite", "priorites", "employe", "employes", "collaborateur", "module", "modules", "qui"})
            )
            if not is_explicit_internal_inquiry:
                return None

            loc = locale.lower()
            if has_identity or has_modules:
                if loc.startswith("es"):
                    return "Esta información está reservada para empleados autenticados de su empresa. Por favor ingrese su código NIP en el teclado para identificarse."
                if loc.startswith("ro"):
                    return "Aceste informații sunt rezervate angajaților autentificați ai companiei dumneavoastră. Vă rugăm să introduceți codul PIN pe tastatura telefonului pentru a vă autentifica."
                if loc.startswith("fr"):
                    return "Cette information est réservée aux employés authentifiés de votre entreprise. Veuillez saisir votre code NIP sur le clavier de votre téléphone pour vous identifier."
                return "This information is reserved for authenticated employees of your company. Please enter your PIN on your phone keypad to authenticate."

            if loc.startswith("es"):
                return "El coaching de desempeño y las prioridades de trabajo están reservados para colaboradores autenticados con NIP. Por favor ingrese su código NIP en el teclado para identificarse."
            if loc.startswith("ro"):
                return "Coaching-ul de performanță și sarcinile de serviciu sunt rezervate angajaților autentificați prin PIN. Vă rugăm să introduceți codul PIN pe tastatura telefonului pentru a vă autentifica."
            if loc.startswith("fr"):
                return "Le coaching de performance et vos priorités professionnelles sont réservés aux employés authentifiés par NIP. Veuillez saisir votre code NIP sur le clavier de votre téléphone pour vous identifier."
            return "Performance coaching and internal shift priorities are reserved for employees authenticated with a PIN. Please enter your PIN on your phone keypad to authenticate."

        from backend.app.services.employee_coach_service import EmployeeCoachService
        from backend.app.services.module_entitlement_service import ModuleEntitlementService
        from shared.ai_engine.contracts import TenantContext

        actor = db.get(User, user_id)
        if actor is None or actor.company_id != company_id:
            return None

        membership = db.scalar(
            select(CompanyMembership).where(
                CompanyMembership.user_id == user_id,
                CompanyMembership.company_id == company_id,
                CompanyMembership.is_active.is_(True),
            )
        )
        comp = db.get(Company, company_id)
        coach = EmployeeCoachService(db)

        # Strict hierarchical access check for financial/executive topics
        if has_exec or (has_briefing and not has_identity and not has_modules and not has_tasks):
            allowed, denial_reason = coach.check_hierarchical_data_access(actor, transcript)
            if not allowed:
                return denial_reason

        # Assemble parts for compound inquiries (e.g. "Qui suis-je ? Quels sont mes modules autorisés et mes tâches ?")
        parts: list[str] = []

        # Part A: Identity
        if has_identity:
            identity_text = spoken_identity_answer(actor, membership, comp.name if comp else None, locale)
            if identity_text:
                parts.append(identity_text)

        # Part B: Modules
        if has_modules:
            summary = ModuleEntitlementService(db).summary(TenantContext(company_id))
            names = [item.display_name for item in summary.modules if item.active and item.display_name]
            if not names:
                names = list(summary.active_modules)
            mod_text = spoken_module_answer(names, plan_code=summary.plan_code, locale=locale)
            if mod_text:
                parts.append(mod_text)

        # Part C: Tasks
        if has_tasks:
            tasks = coach.get_my_tasks(actor, status="open")
            if not tasks:
                if locale.lower().startswith("fr"):
                    parts.append("Vous n'avez aucune tâche ouverte en attente dans votre espace de travail.")
                elif locale.lower().startswith("es"):
                    parts.append("No tiene tareas pendientes en su espacio de trabajo.")
                elif locale.lower().startswith("ro"):
                    parts.append("Nu aveți nicio sarcină deschisă în așteptare în spațiul dumneavoastră de lucru.")
                else:
                    parts.append("You have no open tasks pending in your workspace.")
            else:
                task_titles = [f"'{t['title']}'" for t in tasks[:3]]
                if locale.lower().startswith("fr"):
                    parts.append(f"Vous avez {len(tasks)} tâche(s) ouverte(s). Les principales sont : {', '.join(task_titles)}.")
                elif locale.lower().startswith("es"):
                    parts.append(f"Tiene {len(tasks)} tarea(s) abierta(s). Las principales son: {', '.join(task_titles)}.")
                elif locale.lower().startswith("ro"):
                    parts.append(f"Aveți {len(tasks)} sarcini deschise. Principalele sunt: {', '.join(task_titles)}.")
                else:
                    parts.append(f"You have {len(tasks)} open task(s). The main ones are: {', '.join(task_titles)}.")

        # Part D: Efficiency Coaching Advice
        if has_efficiency:
            advice = coach.get_coaching_advice(actor, locale=locale)
            summary_advice = advice.get("spoken_summary")
            if summary_advice and summary_advice not in parts:
                parts.append(str(summary_advice))

        # Part E: Task Optimization
        if has_optimize and not has_efficiency:
            opt = coach.optimize_task_execution(actor, task_description=transcript, locale=locale)
            summary_opt = opt.get("spoken_summary")
            if summary_opt and summary_opt not in parts:
                parts.append(str(summary_opt))

        # Part F: Daily Briefing
        if has_briefing and not has_tasks:
            briefing = coach.get_daily_briefing(actor, locale=locale)
            summary_brief = briefing.get("spoken_summary")
            if summary_brief and summary_brief not in parts:
                parts.append(str(summary_brief))

        # Part G: Executive Strategic Point
        if has_exec:
            exec_briefing = coach.get_executive_briefing(actor, locale=locale)
            summary_exec = exec_briefing.get("spoken_summary")
            if summary_exec and summary_exec not in parts:
                parts.append(str(summary_exec))

        if parts:
            return " ".join(parts)

    # 3. Open catalog check
    if is_open_catalog_question(transcript):
        from backend.app.services.company_intelligence_service import CompanyIntelligenceService

        profile = CompanyIntelligenceService(db).get_profile(company_id)
        retail_enabled = bool(getattr(profile, "has_retail_commerce", False)) or "retail" in set(getattr(profile, "active_modules", ()) or ())
        products = list(getattr(profile, "public_products", ()) or ())
        return spoken_catalog_answer(
            products,
            retail_enabled=retail_enabled,
            locale=locale,
            currency=getattr(profile, "currency_code", None),
        )

    return None
