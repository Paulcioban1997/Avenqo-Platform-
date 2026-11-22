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
        "autorise", "autorises", "autorisee", "autorisees", "autorisation", "autorisations",
        "permission", "permissions", "droit", "droits", "mes", "mon",
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


def is_marketing_acquisition_question(text: str) -> bool:
    """Detect inquiries seeking customer acquisition, business growth, or marketing advice."""
    norm = unicodedata.normalize("NFKD", text.casefold())
    norm = "".join(c for c in norm if not unicodedata.combining(c))
    if re.search(
        r"\b(attirer\s+(?:plus\s+de\s+|des\s+)?clients?|trouver\s+(?:des\s+|plus\s+de\s+)?clients?|avoir\s+plus\s+de\s+clients?|"
        r"acquisition\s+clients?|strategie\s+commerciale|attirer\s+du\s+monde|faire\s+venir\s+des\s+clients|"
        r"attract\s+(?:more\s+)?(?:clients?|customers?)|get\s+more\s+(?:clients?|customers?)|customer\s+acquisition|"
        r"atraer\s+(?:mas\s+)?clientes?|captar\s+clientes?|como\s+conseguir\s+clientes?|"
        r"cum\s+(?:sa\s+)?atragem\s+mai\s+multi\s+clienti|atragerea\s+clientilor)\b",
        norm,
    ):
        return True
    words = _words(text)
    marketing_target = bool(words & {"clients", "client", "clientele", "customers", "customer", "clientes", "cliente", "clienti"})
    marketing_action = bool(words & {"attirer", "trouver", "attract", "atraer", "captar", "atragem", "prospecter", "acquisition"})
    return marketing_target and marketing_action


def is_catalog_pagination_question(text: str) -> tuple[bool, int]:
    """Detect inquiries asking for next paginated catalog items (e.g. 'les 5 prochains', 'produits suivants')."""
    norm = unicodedata.normalize("NFKD", text.casefold())
    norm = "".join(c for c in norm if not unicodedata.combining(c))

    # Strict exclusion: CRM appointments, bookings, or meeting slots must NEVER be routed as catalog pagination
    if any(
        term in norm
        for term in (
            "rendez vous", "rendez-vous", "rdv", "appointment", "appointments",
            "booking", "bookings", "reservation", "reservations", "creneau", "creneaux",
            "horaire", "horaires", "heure", "heures", "date", "dates", "rencontre",
        )
    ):
        return False, 0

    match = re.search(
        r"\b(?:les?\s+)?(?:(\d+|cinq|trois|quatre|deux|dix|cinco|tres|cuatro|cinci|trei|patru|five|three|four|ten)\s+)?(?:prochains?|suivants?|next|siguientes?|urmatoarele?)\s*(?:produits?|articles?|items?|planches?|accessoires?)?\b|"
        r"\b(?:quels?\s+sont\s+les?\s+)?(?:(\d+|cinq|trois|quatre|deux|dix|five|three|four|ten)\s+)?(?:prochains?|suivants?)\b",
        norm,
    )
    if match:
        num_str = match.group(1) or match.group(2)
        word_to_num = {
            "cinq": 5, "five": 5, "cinco": 5, "cinci": 5,
            "trois": 3, "three": 3, "tres": 3, "trei": 3,
            "quatre": 4, "four": 4, "cuatro": 4, "patru": 4,
            "deux": 2, "two": 2, "dos": 2, "doi": 2,
            "dix": 10, "ten": 10, "diez": 10, "zece": 10,
        }
        count = 5
        if num_str:
            if num_str.isdigit():
                count = int(num_str)
            elif num_str in word_to_num:
                count = word_to_num[num_str]
        return True, max(1, min(count, 10))
    return False, 0


def is_ordinal_product_question(text: str) -> tuple[bool, int]:
    """Detect inquiries about an ordinal product previously presented (e.g. 'Combien coûte le deuxième ?')."""
    norm = unicodedata.normalize("NFKD", text.casefold())
    norm = "".join(c for c in norm if not unicodedata.combining(c))

    # Strict exclusion: CRM appointments, employee tasks, or client inquiries must NEVER be routed as catalog ordinals
    if any(
        term in norm
        for term in (
            "rendez vous", "rendez-vous", "rdv", "appointment", "appointments",
            "booking", "bookings", "reservation", "reservations", "creneau", "creneaux",
            "horaire", "horaires", "heure", "heures", "date", "dates", "rencontre",
            "tache", "taches", "task", "tasks", "client", "clients",
        )
    ):
        return False, 0

    match = re.search(
        r"\b(?:combien\s+coute|quel\s+est\s+le\s+prix\s+d[ue]|et\s+le|prix\s+d[ue]|how\s+much\s+(?:is|does)\s+the|cuanto\s+cuesta\s+el|cat\s+costa\s+al)\s+"
        r"(?:le\s+)?(premier|deuxieme|troisieme|quatrieme|cinquieme|1er|2e|2eme|3e|3eme|4e|5e|first|second|third|fourth|fifth|primero|segundo|tercero|primul|al\s+doilea|al\s+treilea)\b|"
        r"\b(premier|deuxieme|troisieme|quatrieme|cinquieme|1er|2e|2eme|3e|3eme|4e|5e|first|second|third|fourth|fifth|segundo|tercero)\s*(?:produit|article|one|item)?\s*(?:combien|coute|prix)?\b",
        norm,
    )
    if match:
        ord_word = match.group(1) or match.group(2)
        mapping = {
            "premier": 1, "1er": 1, "first": 1, "primero": 1, "primul": 1,
            "deuxieme": 2, "2e": 2, "2eme": 2, "second": 2, "segundo": 2, "al doilea": 2,
            "troisieme": 3, "3e": 3, "3eme": 3, "third": 3, "tercero": 3, "al treilea": 3,
            "quatrieme": 4, "4e": 4, "4eme": 4, "fourth": 4, "cuarto": 4,
            "cinquieme": 5, "5e": 5, "5eme": 5, "fifth": 5, "quinto": 5,
        }
        idx = mapping.get(ord_word, 0)
        if idx > 0:
            return True, idx
    return False, 0


def is_superlative_product_question(text: str) -> tuple[bool, str | None]:
    """Detect superlative product queries (e.g. 'Quelle planche est la plus chère ?')."""
    norm = unicodedata.normalize("NFKD", text.casefold())
    norm = "".join(c for c in norm if not unicodedata.combining(c))
    is_expensive = bool(re.search(
        r"\b(plus\s+chere?|le\s+plus\s+cher|most\s+expensive|highest\s+price|mas\s+car[ao]|cea\s+mai\s+scumpa|cel\s+mai\s+scump)\b",
        norm,
    ))
    if not is_expensive:
        return False, None
    category = None
    if re.search(r"\b(planche|planches|snowboard|snowboards)\b", norm):
        category = "planche"
    elif re.search(r"\b(accessoire|accessoires|accessories|accessory)\b", norm):
        category = "accessoire"
    return True, category


def is_open_catalog_question(text: str) -> bool:
    words = _words(text)
    products = bool(words & {
        "produit", "produits", "product", "products", "article", "articles",
        "catalogue", "catalog", "catalogs", "catalogues", "item", "items",
        "planche", "planches", "snowboard", "snowboards",
        "accessoire", "accessoires", "accessory", "accessories",
        "equipement", "equipements", "equipment", "gant", "gants", "casque", "casques",
    })
    if not products:
        return False
    listing = bool(words & {
        "quels", "quelles", "quel", "quelle", "liste", "what", "which",
        "catalogue", "catalog", "chacun", "chacune", "tous", "toutes", "all", "every", "each",
        "avez", "avons", "proposez", "vendez", "disponible", "disponibles",
    })
    for_sale = bool(words & {"vente", "vendre", "sale", "sales"})
    prices = bool(words & {"prix", "price", "prices", "tarif", "tarifs", "combien", "cout"})
    stock_inquiry = bool(words & {
        "stock", "stocks", "inventaire", "inventory", "disponible", "disponibles",
        "disponibilite", "disponibilites", "restant", "restants",
    })
    # Distinguish general catalog price inquiries from specific item inquiries ("combien coûte X")
    is_general_price = prices and (listing or bool(words & {"catalogue", "catalog", "produits", "products", "articles"}))
    is_category_mention = (len(words) <= 4) and bool(words & {
        "accessoire", "accessoires", "accessory", "accessories",
        "catalogue", "catalog", "planche", "planches", "snowboard", "snowboards",
    }) and not bool(words & {"combien", "cout", "coute"})
    return listing or for_sale or stock_inquiry or is_general_price or is_category_mention


_EXPLICIT_INSURANCE_TERMS = frozenset({
    "police", "polices", "prime", "primes", "couverture", "couvertures",
    "sinistre", "sinistres", "contrat", "contrats", "responsabilite",
    "vehicule", "vehicules", "habitation", "vie", "auto", "automobile",
    "indemnisation", "indemnisations", "courtier", "courtiers", "souscription",
    "prejudice", "remboursement", "assureur", "assureurs", "reclamation", "reclamations",
    "franchise", "franchises", "dommage", "dommages",
})

_CATALOG_SHOPPING_PHRASES = frozenset({
    "hiver", "saison", "magasin", "boutique", "stock", "inventaire",
    "catalogue", "rayon", "articles", "vendez", "proposez", "achetez",
    "achat", "modele", "modeles", "marque", "marques", "taille", "tailles",
    "prix", "combien", "tarif", "disponible", "disponibles",
})


def disambiguate_telephony_catalog_query(
    transcript: str,
    *,
    active_modules: set[str],
    company_industry: str | None = None,
    company_services: list[str] | None = None,
    has_catalog_accessories: bool = False,
) -> str:
    """Contextual telephony disambiguation for 8kHz acoustic confusion (assurances vs accessoires).

    Never blind:
    1. If business offers insurance (module, industry or services), returns original transcript.
    2. If utterance contains explicit insurance terms (police, sinistre, prime...), returns original transcript.
    3. If company is pure retail with verified accessories in stock and utterance asks about catalog/shopping,
       resolves the acoustic confusion to 'accessoire(s)'.
    """
    if not transcript or not re.search(r"\b(l['’])?assurance(s)?\b", transcript, flags=re.IGNORECASE):
        return transcript

    # Rule 1: Business legitimately offers insurance
    insurance_modules = {"insurance", "assurances", "finance", "assurances_auto", "assurances_habitation"}
    if active_modules & insurance_modules:
        return transcript

    ind = (company_industry or "").lower()
    if any(k in ind for k in ("assurance", "insurance", "finance", "mutuelle", "courtage")):
        return transcript

    services = [str(s).lower() for s in (company_services or [])]
    if any(any(k in s for k in ("assurance", "insurance", "garantie")) for s in services):
        return transcript

    # Rule 2: Explicit insurance intent
    words = _words(transcript)
    if words & _EXPLICIT_INSURANCE_TERMS:
        return transcript

    # Rule 3: Business is pure retail with verified accessories, and inquiry is shopping/catalog oriented
    if "retail" in active_modules and has_catalog_accessories:
        if (words & _CATALOG_SHOPPING_PHRASES) or is_open_catalog_question(transcript):
            return re.sub(r"\b(l['’])?assurance(s)?\b", r"\1accessoire\2", transcript, flags=re.IGNORECASE)

    return transcript


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


def spoken_superlative_product_answer(
    products: Any,
    category: str | None,
    *,
    locale: str,
    currency: str | None = None,
) -> str:
    loc = locale.lower()
    french = loc.startswith("fr")
    spanish = loc.startswith("es")
    romanian = loc.startswith("ro")

    rows = [
        row for row in products
        if isinstance(row, dict) and str(row.get("name") or row.get("title") or row.get("product_name") or "").strip()
    ]
    if category:
        cat_rows = [
            r for r in rows
            if category in (str(r.get("category") or r.get("product_category") or "")).lower()
            or category in (str(r.get("name") or r.get("title") or r.get("product_name") or "")).lower()
        ]
        # Strict category filtering: do NOT fall back to other categories when requested category is absent
        rows = cat_rows
        if not rows:
            cat_name = "accessoires" if category == "accessoire" else ("planches" if category == "planche" else category)
            if spanish:
                return f"No se encontró ningún producto en la categoría '{cat_name}' en nuestro catálogo."
            if romanian:
                return f"Nu a fost găsit niciun produs în categoria '{cat_name}' în catalogul nostru."
            return (
                f"Aucun produit dans la catégorie '{cat_name}' n'a été trouvé dans notre catalogue."
                if french else
                f"No products in the '{cat_name}' category were found in our catalog."
            )

    if not rows:
        return (
            "Aucun produit correspondant n'a été trouvé dans le catalogue."
            if french else
            "No matching products were found in the catalog."
        )

    def _parse_price(r: dict) -> float:
        p = r.get("price")
        if p is None or p == "":
            return -1.0
        try:
            return float(str(p).replace("$", "").replace("€", "").replace(",", ".").strip())
        except (ValueError, TypeError):
            return -1.0

    priced_rows = [r for r in rows if _parse_price(r) > 0]
    if not priced_rows:
        if spanish:
            return "Ningún producto en esta categoría tiene un precio verificable en nuestro catálogo."
        if romanian:
            return "Niciun produs din această categorie nu are un preț verificabil în catalogul nostru."
        return (
            "Aucun produit dans cette sélection ne dispose d'un prix vérifiable dans notre catalogue."
            if french else
            "No products in this selection have a verifiable price in our catalog."
        )

    best = max(priced_rows, key=_parse_price)
    name = str(best.get("name") or best.get("title") or best.get("product_name") or "").strip()
    price = best.get("price")
    unit = str(best.get("currency") or currency or "$").strip()
    if unit in ("CAD", "USD", ""):
        unit = "$"

    cat_label = "planche" if category == "planche" else ("accessoire" if category == "accessoire" else ("produit" if french else "item"))

    is_live = best.get("is_live_stock") is True
    is_demo = best.get("is_demo") is True or str(best.get("freshness_status") or "").upper() == "DEMO_SIMULATION"
    if is_demo:
        price_provenance = " (precio de demostración)" if spanish else (" (preț demonstrativ)" if romanian else (" (prix de démonstration)" if french else " (demo price)"))
    elif not is_live:
        price_provenance = " (datos históricos de referencia)" if spanish else (" (date de referință istorice)" if romanian else (" (données issues du catalogue de référence historique)" if french else " (data from historical reference catalog)"))
    else:
        price_provenance = ""

    if spanish:
        art = "La" if cat_label in ("planche", "tabla") else "El"
        return f"{art} {cat_label} más cara de nuestro catálogo es {name} a un precio de {price} {unit}{price_provenance}."
    if romanian:
        return f"Cel mai scump produs ({cat_label}) din catalogul nostru este {name} la prețul de {price} {unit}{price_provenance}."
    if french:
        genre_fem = cat_label in ("planche",)
        article_fem = "La" if genre_fem else "Le"
        adj_fem = "chère" if genre_fem else "cher"
        if genre_fem:
            return f"La {cat_label} la plus chère de notre catalogue est {name} au prix de {price} {unit}{price_provenance}."
        return f"L'{cat_label} le plus cher de notre catalogue est {name} au prix de {price} {unit}{price_provenance}." if cat_label.startswith("a") else f"Le {cat_label} le plus cher de notre catalogue est {name} au prix de {price} {unit}{price_provenance}."
    return f"The most expensive {cat_label} in our catalog is {name} priced at {price} {unit}{price_provenance}."


def spoken_ordinal_product_answer(
    presented_products: list[dict[str, Any]],
    ordinal_index: int,
    *,
    locale: str,
) -> str:
    loc = locale.lower()
    french = loc.startswith("fr")
    spanish = loc.startswith("es")
    romanian = loc.startswith("ro")

    if not presented_products or ordinal_index < 1 or ordinal_index > len(presented_products):
        if spanish:
            return "No tengo el detalle de ese artículo en la lista mencionada."
        if romanian:
            return "Nu am detaliile acelui articol din lista menționată."
        return (
            "Je n'ai pas le détail de cet article dans la liste mentionnée précédemment."
            if french else
            "I do not have the details for that item in the previously mentioned list."
        )

    item = presented_products[ordinal_index - 1]
    name = item.get("name", "")
    price_text = item.get("price_text", "")
    available = item.get("available", "")
    ord_names_fr = {1: "premier", 2: "deuxième", 3: "troisième", 4: "quatrième", 5: "cinquième"}
    ord_name = ord_names_fr.get(ordinal_index, f"{ordinal_index}e")

    if spanish:
        ord_names_es = {1: "primer", 2: "segundo", 3: "tercer", 4: "cuarto", 5: "quinto"}
        return f"El {ord_names_es.get(ordinal_index, str(ordinal_index))} producto mencionado es {name}, a {price_text}{available}."
    if romanian:
        ord_names_ro = {1: "primul", 2: "al doilea", 3: "al treilea", 4: "al patrulea", 5: "al cincilea"}
        return f"Al {ord_names_ro.get(ordinal_index, str(ordinal_index))} produs menționat este {name}, la {price_text}{available}."
    if french:
        return f"Le {ord_name} produit mentionné est {name}, au prix de {price_text}{available}."
    ord_names_en = {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth"}
    return f"The {ord_names_en.get(ordinal_index, f'{ordinal_index}th')} product mentioned is {name}, priced at {price_text}{available}."


def spoken_catalog_answer(
    products: Any,
    *,
    retail_enabled: bool,
    locale: str,
    currency: str | None = None,
    query: str | None = None,
    offset: int = 0,
    limit: int = 3,
    call: Any | None = None,
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

    # Optional category / semantic filter based on query or inherited from call session context
    active_category = None
    is_accessories_query = False
    if query:
        query_norm = unicodedata.normalize("NFKD", query.casefold())
        query_norm = "".join(c for c in query_norm if not unicodedata.combining(c))
        if re.search(r"\b(accessoire|accessoires|accessory|accessories)\b", query_norm):
            active_category = "accessoire"
            is_accessories_query = True
        elif re.search(r"\b(planche|planches|snowboard|snowboards)\b", query_norm):
            active_category = "planche"

    # If query does not specify a category and this is pagination, inherit previous category filter from call context
    if not active_category and offset > 0 and call is not None:
        ctx_cat = (call.source_context or {}).get("catalog_category_filter")
        if ctx_cat:
            active_category = ctx_cat
            if active_category == "accessoire":
                is_accessories_query = True

    if active_category == "accessoire":
        acc_rows = [
            r for r in rows
            if "accessoire" in (str(r.get("category") or r.get("product_category") or "")).lower()
            or "accessory" in (str(r.get("category") or r.get("product_category") or "")).lower()
            or "accessories" in (str(r.get("category") or r.get("product_category") or "")).lower()
            or "accessoire" in (str(r.get("name") or r.get("product_name") or "")).lower()
            or "accessory" in (str(r.get("name") or r.get("product_name") or "")).lower()
            or "accessories" in (str(r.get("name") or r.get("product_name") or "")).lower()
            or any(k in (str(r.get("name") or r.get("product_name") or "")).lower() for k in ("casque", "gant", "masque", "chapeau", "lunette", "fart", "fixation"))
        ]
        if not acc_rows:
            if spanish:
                return "Actualmente no tenemos accesorios disponibles en nuestro catálogo. ¿Desea información sobre nuestros otros productos?"
            if romanian:
                return "În prezent nu avem accesorii disponibile în catalogul nostru. Doriți informații despre celelalte produse?"
            return (
                "Nous n'avons actuellement aucun accessoire disponible dans notre catalogue. Souhaitez-vous des renseignements sur nos autres articles ?"
                if french else
                "We do not currently have any accessories available in our catalog. Would you like information on our other items?"
            )
        rows = acc_rows
    elif active_category == "planche":
        board_rows = [
            r for r in rows
            if "planche" in (str(r.get("category") or r.get("product_category") or "")).lower()
            or "snowboard" in (str(r.get("category") or r.get("product_category") or "")).lower()
            or "planche" in (str(r.get("name") or r.get("product_name") or "")).lower()
            or "snowboard" in (str(r.get("name") or r.get("product_name") or "")).lower()
        ]
        if board_rows:
            rows = board_rows
    elif query:
        query_norm = unicodedata.normalize("NFKD", query.casefold())
        query_norm = "".join(c for c in query_norm if not unicodedata.combining(c))
        query_words = set(re.findall(r"\b\w+\b", query_norm))
        stopwords = {
            "quel", "quels", "quelle", "quelles", "combien", "coute", "coutent", "prix",
            "tarif", "tarifs", "est", "sont", "le", "la", "les", "du", "de", "des",
            "un", "une", "avez", "vous", "notre", "votre", "catalogue", "produit", "produits",
            "article", "articles", "what", "which", "how", "much", "is", "are", "the", "a", "an",
            "in", "for", "do", "you", "have", "price", "catalog", "product", "products",
            "pour", "dans", "avec", "sur", "vos", "nos", "prochain", "prochains", "suivant", "suivants",
        }
        specific_tokens = {w for w in query_words if w not in stopwords and len(w) >= 3}
        if specific_tokens:
            name_matches = []
            for r in rows:
                r_name_norm = unicodedata.normalize("NFKD", str(r.get("name") or r.get("title") or r.get("product_name") or "").casefold())
                r_name_norm = "".join(c for c in r_name_norm if not unicodedata.combining(c))
                score = sum(1 for tok in specific_tokens if tok in r_name_norm)
                if score > 0:
                    name_matches.append((score, r))
            if name_matches:
                name_matches.sort(key=lambda x: x[0], reverse=True)
                rows = [m[1] for m in name_matches]

    target_slice = rows[offset : offset + limit]
    if not target_slice and offset > 0:
        if spanish:
            return f"No hay más productos disponibles en esta sección del catálogo. Hemos recorrido los {len(rows)} artículos."
        if romanian:
            return f"Nu mai există alte produse în această secțiune. Am parcurs toate cele {len(rows)} articole."
        return (
            f"Il n'y a plus d'autres articles dans cette sélection. Nous avons parcouru les {len(rows)} produits disponibles."
            if french else
            f"There are no more items in this section. We have reviewed all {len(rows)} available products."
        )

    spoken = []
    presented_records = []
    for row in target_slice:
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
        else:
            available = ", données de référence" if french else ", reference data"

        spoken.append(f"{name}, {price_text}{available}")
        presented_records.append({
            "name": name,
            "price": price,
            "currency": unit,
            "price_text": price_text,
            "category": str(row.get("category") or row.get("product_category") or ""),
            "available": available,
        })

    if call is not None:
        ctx = dict(call.source_context or {})
        ctx["presented_catalog_products"] = presented_records
        ctx["catalog_pagination_offset"] = offset + len(target_slice)
        ctx["catalog_category_filter"] = active_category
        call.source_context = ctx

    extra = ""
    remaining = len(rows) - (offset + len(target_slice))
    if remaining > 0:
        if spanish:
            extra = f" Y {remaining} {'artículo' if remaining == 1 else 'artículos'} más en el catálogo."
        elif romanian:
            extra = f" Și încă {remaining} {'articol' if remaining == 1 else 'articole'} în catalog."
        elif french:
            extra = f" Et {remaining} autre{'s' if remaining > 1 else ''} article{'s' if remaining > 1 else ''} au catalogue."
        else:
            extra = f" And {remaining} more items in the catalog."

    hist_note = ""
    if any(not r.get("is_live_stock") for r in target_slice):
        hist_note = (
            " (Données issues de notre catalogue de référence historique.)"
            if french else
            " (Data from our historical reference catalog.)"
        )

    if is_accessories_query:
        if spanish:
            return "Como accesorios, ofrecemos en particular: " + " ; ".join(spoken) + "." + extra + hist_note
        if romanian:
            return "Ca accesorii, vă oferim în special: " + " ; ".join(spoken) + "." + extra + hist_note
        if french:
            return "Nous proposons notamment comme accessoires : " + " ; ".join(spoken) + "." + extra + hist_note
        return "As accessories, we notably offer: " + "; ".join(spoken) + "." + extra + hist_note
    if spanish:
        return "Tenemos en el catálogo: " + " ; ".join(spoken) + "." + extra + hist_note
    if romanian:
        return "Avem în catalog: " + " ; ".join(spoken) + "." + extra + hist_note
    if french:
        return "Nous avons au catalogue : " + " ; ".join(spoken) + "." + extra + hist_note
    return "In our catalog, we have: " + "; ".join(spoken) + "." + extra + hist_note


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
    call: Any | None = None,
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

    # 2. Marketing / customer acquisition advice
    if is_marketing_acquisition_question(transcript):
        if not authenticated_staff or user_id is None:
            loc = locale.lower()
            if loc.startswith("es"):
                return "Los consejos de estrategia de marketing y captación de clientes están reservados para colaboradores autenticados. Ingrese su NIP en el teclado para identificarse."
            if loc.startswith("ro"):
                return "Consilierea privind strategia de marketing și atragerea clienților este rezervată angajaților autentificați prin PIN. Vă rugăm să introduceți codul PIN pe tastatura telefonului."
            if loc.startswith("fr"):
                return "Les conseils de stratégie marketing et d'acquisition client sont réservés aux employés authentifiés par NIP. Veuillez saisir votre code NIP sur le clavier de votre téléphone pour vous identifier."
            return "Marketing strategy and customer acquisition advice is reserved for employees authenticated with a PIN. Please enter your PIN on your phone keypad to authenticate."

        from backend.app.services.employee_coach_service import EmployeeCoachService
        actor = db.get(User, user_id)
        if actor is not None and actor.company_id == company_id:
            coach = EmployeeCoachService(db)
            mktg = coach.get_marketing_acquisition_advice(actor, query=transcript, locale=locale)
            summary_mktg = mktg.get("spoken_summary")
            if summary_mktg:
                return str(summary_mktg)

    # 3. Check for employee internal requests: identity, modules, coach tasks, coaching efficiency, briefing, optimize, executive
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

    # 4. Ordinal product lookup in conversational memory (e.g. "Combien coûte le deuxième ?")
    is_ord, ord_idx = is_ordinal_product_question(transcript)
    if is_ord and call is not None:
        presented = list((call.source_context or {}).get("presented_catalog_products") or [])
        if presented:
            return spoken_ordinal_product_answer(presented, ord_idx, locale=locale)

    # 5. Superlative product inquiries (e.g. "Quelle planche est la plus chère ?")
    is_sup, sup_cat = is_superlative_product_question(transcript)
    if is_sup:
        from backend.app.services.company_intelligence_service import CompanyIntelligenceService

        profile = CompanyIntelligenceService(db).get_profile(company_id)
        products = list(getattr(profile, "public_products", ()) or ())
        return spoken_superlative_product_answer(
            products,
            sup_cat,
            locale=locale,
            currency=getattr(profile, "currency_code", None),
        )

    # 6. Catalog pagination (e.g. "Quels sont les cinq prochains produits ?")
    is_page, req_count = is_catalog_pagination_question(transcript)
    if is_page:
        from backend.app.services.company_intelligence_service import CompanyIntelligenceService

        profile = CompanyIntelligenceService(db).get_profile(company_id)
        retail_enabled = bool(getattr(profile, "has_retail_commerce", False)) or "retail" in set(getattr(profile, "active_modules", ()) or ())
        products = list(getattr(profile, "public_products", ()) or ())
        current_offset = int((call.source_context or {}).get("catalog_pagination_offset", 3)) if call is not None else 3
        return spoken_catalog_answer(
            products,
            retail_enabled=retail_enabled,
            locale=locale,
            currency=getattr(profile, "currency_code", None),
            query=transcript,
            offset=current_offset,
            limit=req_count,
            call=call,
        )

    # 7. Open catalog check
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
            query=transcript,
            offset=0,
            limit=3,
            call=call,
        )

    return None
