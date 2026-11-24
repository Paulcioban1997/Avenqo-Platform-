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

from backend.app.core.permissions import is_executive_role, normalize_role, resolve_verified_staff_role
from backend.app.models import Company, CompanyMembership, User, VoiceBusinessConfig
from backend.app.services.semantic_product_search import semantic_search_products


def _words(text: str) -> set[str]:
    normalized = unicodedata.normalize("NFKD", text.casefold())
    ascii_text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return set(re.findall(r"[a-z0-9]+", ascii_text))


def sanitize_retail_voice_text(text: str, *, locale: str = "fr-CA") -> str:
    """Eliminate raw technical schema/JSON identifiers from spoken voice output.

    Never allows technical fields such as compare_at_price, inventory_quantity,
    product_variant, normalized_data, or source_updated_at to be spoken aloud.
    """
    if not text:
        return ""
    loc = (locale or "fr-CA").casefold()
    is_fr = loc.startswith("fr")
    is_es = loc.startswith("es")
    is_ro = loc.startswith("ro")

    replacements: list[tuple[str, str]] = [
        (
            r"\bcompare[_\s]+at[_\s]+price\b\s*[:=]?",
            "prix comparatif" if is_fr else ("precio comparativo" if is_es else ("preț comparativ" if is_ro else "original price")),
        ),
        (
            r"\b(?:inventory[_\s]+quantity|inventory[_\s]+level|stock[_\s]+quantity)\b\s*[:=]?",
            "quantité en stock" if is_fr else ("cantidad en stock" if is_es else ("cantitate în stoc" if is_ro else "stock quantity")),
        ),
        (
            r"\bproduct[_\s]+variants?\b\s*[:=]?",
            "variante du produit" if is_fr else ("variante del producto" if is_es else ("variantă de produs" if is_ro else "product variant")),
        ),
        (
            r"\bvariant[_\s]+id\b\s*[:=]?",
            "référence de variante" if is_fr else ("referencia de variante" if is_es else ("cod variantă" if is_ro else "variant reference")),
        ),
        (
            r"\bnormalized[_\s]+data\b\s*[:=]?",
            "données du catalogue" if is_fr else ("datos del catálogo" if is_es else ("datele din catalog" if is_ro else "catalog data")),
        ),
        (
            r"\bsource[_\s]+updated[_\s]+at\b\s*[:=]?",
            "dernière mise à jour" if is_fr else ("última actualización" if is_es else ("ultima actualizare" if is_ro else "last update")),
        ),
        (
            r"\bunit[_\s]+price\b\s*[:=]?",
            "prix de vente" if is_fr else ("precio de venta" if is_es else ("preț de vânzare" if is_ro else "selling price")),
        ),
        (
            r"\bfreshness[_\s]+status\b\s*[:=]\s*stale\b",
            "données de stock non récentes" if is_fr else ("datos de stock no recientes" if is_es else ("date de stoc expirate" if is_ro else "stock data not recent")),
        ),
        (
            r"\bfreshness[_\s]+status\b\s*[:=]\s*unconfirmed[_\s]+historical\b",
            "données de référence historique" if is_fr else ("datos de referencia histórica" if is_es else ("date istorice de referință" if is_ro else "historical reference data")),
        ),
        (
            r"\bfreshness[_\s]+status\b\s*[:=]\s*demo[_\s]+simulation\b",
            "données de démonstration" if is_fr else ("datos de demostración" if is_es else ("date demonstrative" if is_ro else "demo data")),
        ),
        (
            r"\bis[_\s]+live[_\s]+stock\b\s*[:=]\s*false\b",
            "stock non vérifié en temps réel" if is_fr else ("stock no verificado en tiempo real" if is_es else ("stoc neverificat în timp real" if is_ro else "stock not verified in real time")),
        ),
        (
            r"\bis[_\s]+live[_\s]+stock\b\s*[:=]\s*true\b",
            "synchronisation récente" if is_fr else ("sincronización reciente" if is_es else ("sincronizare recentă" if is_ro else "recent sync")),
        ),
        (
            r"\b(?:freshness[_\s]+status|stock[_\s]+availability|stock[_\s]+status|price[_\s]+status|is[_\s]+live[_\s]+stock)\b\s*[:=]?",
            "état du stock" if is_fr else ("estado del stock" if is_es else ("starea stocului" if is_ro else "stock status")),
        ),
        (
            r"\b(?:in[_\s]+stock)\b\s*[:=]\s*true\b",
            "indiqué en stock au catalogue (à confirmer)" if is_fr else ("indicado en stock en el catálogo (sin confirmar)" if is_es else ("menționat în stoc în catalog (neconfirmat)" if is_ro else "listed in stock in catalog (unverified)")),
        ),
        (
            r"\b(?:in[_\s]+stock)\b\s*[:=]\s*false\b",
            "indiqué en rupture au catalogue" if is_fr else ("indicado agotado en el catálogo" if is_es else ("menționat cu stoc epuizat în catalog" if is_ro else "listed out of stock in catalog")),
        ),
        (
            r"\b(?:product[_\s]+id|product[_\s]+name|product[_\s]+category|historical[_\s]+observed[_\s]+units)\b\s*[:=]?",
            "",
        ),
    ]
    cleaned = text
    replaced_any = False
    for pattern, repl in replacements:
        updated = re.sub(pattern, repl, cleaned, flags=re.IGNORECASE)
        if updated != cleaned:
            replaced_any = True
            cleaned = updated
    if not replaced_any:
        return text
    # Clean stray punctuation artifacts left after replacing key-value syntax (preserve French spacing before : ; ? !)
    cleaned = re.sub(r"\(\s*\)", "", cleaned)
    cleaned = re.sub(r"\s+([,.])", r"\1", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def is_ambiguous_commercial_selling_question(text: str) -> bool:
    """Detect open commercial selling questions from staff/owners that benefit from one short clarification.

    Examples:
        - "Quels sont les produits que je peux vendre ?"
        - "Quels produits je pourrais vendre ?"
        - "What products can I sell?"
        - "¿Qué productos puedo vender?"
        - "Ce produse pot să vând?"

    Does NOT match when the caller already specified a filter or intent
    (e.g., in-stock only, highest-margin, accessories, snowboards, prices, full catalog).
    """
    norm = unicodedata.normalize("NFKD", text.casefold())
    norm = "".join(c for c in norm if not unicodedata.combining(c))
    words = _words(text)
    if words & {
        "en stock", "stock", "disponible", "disponibles", "rentable", "rentables", "marge", "marges",
        "promouvoir", "promotion", "promotions", "opportunite", "opportunites", "meilleur", "meilleurs",
        "meilleures", "accessoire", "accessoires", "planche", "planches", "snowboard", "snowboards",
        "prix", "price", "tarif", "tarifs", "catalogue", "catalog", "liste", "tous", "toutes",
        "margin", "profitable", "promote", "available", "inventory", "accessories",
    }:
        return False
    return bool(
        re.search(
            r"\b(quels?\s+(?:sont\s+les?\s+)?(?:produits?|articles?)\s+que\s+je\s+(?:peux|pourrais|dois|devrais)\s+vendre|"
            r"quels?\s+(?:produits?|articles?)\s+je\s+(?:peux|pourrais|dois|devrais)\s+vendre|"
            r"qu['’]?est\s*ce\s+que\s+je\s+(?:peux|pourrais)\s+vendre|que\s+puis\s*je\s+vendre|"
            r"what\s+products?\s+(?:can|could|should)\s+i\s+sell|which\s+products?\s+(?:can|could|should)\s+i\s+sell|"
            r"que\s+productos?\s+(?:puedo|podria)\s+vender|"
            r"ce\s+produse\s+(?:pot|as\s+putea)\s+(?:sa\s+)?vand)\b",
            norm,
        )
    )


def spoken_commercial_selling_clarification(locale: str) -> str:
    """Return one concise clarification question for open commercial selling queries."""
    loc = (locale or "fr-CA").casefold()
    if loc.startswith("es"):
        return "¿Prefiere ver los productos confirmados en stock, los más rentables o las mejores oportunidades para promocionar?"
    if loc.startswith("ro"):
        return "Doriți să vedeți produsele confirmate în stoc, cele mai profitabile sau cele mai bune oportunități de promovare?"
    if loc.startswith("en"):
        return "Would you like to see products currently confirmed in stock, the most profitable items, or the best opportunities to promote?"
    return "Voulez-vous voir les produits confirmés en stock, les plus rentables, ou les meilleures opportunités à promouvoir ?"


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

    # Strict exclusion: CRM appointments, bookings, or general conversational next-step queries
    if any(
        term in norm
        for term in (
            "rendez vous", "rendez-vous", "rdv", "appointment", "appointments",
            "booking", "bookings", "reservation", "reservations", "creneau", "creneaux",
            "horaire", "horaires", "heure", "heures", "date", "dates", "rencontre",
            "what next", "what's next", "what should i do next", "what do we do next",
            "what happens next", "and next", "et ensuite", "que faire ensuite", "quoi d'autre",
            "what else", "et apres", "y despues", "ce facem acum", "ce urmeaza", "quand",
        )
    ):
        return False, 0

    match = re.search(
        r"\b(?:les?\s+|the\s+)?(?:(\d+|cinq|trois|quatre|deux|dix|cinco|tres|cuatro|cinci|trei|patru|five|three|four|ten)\s+)(?:prochains?|suivants?|next|siguientes?|urmatoarele?)\s*(?:produits?|articles?|items?|planches?|accessoires?)?\b|"
        r"\b(?:les?\s+|the\s+|los?\s+|urmatoarele\s+)?(?:prochains?|suivants?|next|siguientes?|urmatoarele)\s+(?:(\d+|cinq|trois|quatre|deux|dix|cinco|tres|cuatro|cinci|trei|patru|five|three|four|ten)\s+)(?:produits?|articles?|items?|planches?|accessoires?|ones?)?\b|"
        r"\b(?:les?\s+|the\s+|los?\s+|urmatoarele\s+)(?:prochains?|suivants?|next|siguientes?|urmatoarele)\s+(?:produits?|articles?|items?|planches?|accessoires?|ones?)\b|"
        r"\b(?:quels?\s+sont\s+les?\s+|what\s+are\s+the\s+)(?:(\d+|cinq|trois|quatre|deux|dix|five|three|four|ten)\s+)?(?:prochains?|suivants?|next)\s*(?:produits?|articles?|items?|planches?|accessoires?)\b",
        norm,
    )
    if match:
        num_str = match.group(1) or match.group(2) or match.group(3)
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

    # Conversational pauses, hold requests, or polite time delays must NEVER be routed as catalog ordinals
    if any(
        phrase in norm
        for phrase in (
            "one second", "a second", "just a second", "wait a second", "give me a second",
            "hold on a second", "hold on", "second please", "seconds please",
            "une seconde", "un instant", "attends", "attendez", "attendez une seconde",
            "attends une seconde", "juste une seconde", "un moment", "juste un instant",
            "un segundo", "espera un segundo", "o secunda", "stai o secunda", "asteapta",
        )
    ):
        return False, 0

    match = re.search(
        r"\b(?:combien\s+coute|quel\s+est\s+le\s+prix\s+d[ue]|et\s+le|prix\s+d[ue]|how\s+much\s+(?:is|does)\s+the|cuanto\s+cuesta\s+el|cat\s+costa\s+al)\s+"
        r"(?:le\s+|the\s+|el\s+)?(premier|deuxieme|troisieme|quatrieme|cinquieme|1er|2e|2eme|3e|3eme|4e|5e|first|second|third|fourth|fifth|primero|segundo|tercero|primul|al\s+doilea|al\s+treilea)\b|"
        r"\b(?:le\s+|the\s+|el\s+)(premier|deuxieme|troisieme|quatrieme|cinquieme|1er|2e|2eme|3e|3eme|4e|5e|first|second|third|fourth|fifth|segundo|tercero)\s*(?:produit|article|one|item)\s*(?:combien|coute|prix)?\b|"
        r"\b(premier|deuxieme|troisieme|quatrieme|cinquieme|1er|2e|2eme|3e|3eme|4e|5e|first|third|fourth|fifth|primero|segundo|tercero)\s+(?:produit|article|option|item)\b",
        norm,
    )
    if match:
        ord_word = match.group(1) or match.group(2) or match.group(3)
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


def is_superlative_service_question(text: str) -> bool:
    """Detect queries asking for the most expensive CRM service/prestation."""
    norm = unicodedata.normalize("NFKD", text.casefold())
    norm = "".join(c for c in norm if not unicodedata.combining(c))
    has_service_noun = bool(re.search(
        r"\b(service|services|prestation|prestations|forfait|forfaits|consultation|soin|soins|coupe)\b",
        norm,
    ))
    has_superlative = bool(re.search(
        r"\b(plus\s+chere?|le\s+plus\s+cher|most\s+expensive|highest\s+price|mas\s+car[ao]|cea\s+mai\s+scumpa|cel\s+mai\s+scump)\b",
        norm,
    ))
    return has_service_noun and has_superlative


def is_superlative_product_question(text: str) -> tuple[bool, str | None]:
    """Detect superlative product queries (e.g. 'Quelle planche est la plus chère ?')."""
    norm = unicodedata.normalize("NFKD", text.casefold())
    norm = "".join(c for c in norm if not unicodedata.combining(c))

    # Strict exclusion: CRM services, appointments, treatments belong to CRM, NOT retail products
    if any(
        term in norm
        for term in (
            "service", "services", "prestation", "prestations", "forfait", "forfaits",
            "consultation", "consultations", "rendez vous", "rendez-vous", "rdv",
            "appointment", "appointments", "soin", "soins", "coupe", "coupes",
            "seance", "seances", "abonnement", "abonnements",
        )
    ):
        return False, None

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


def is_business_hours_question(text: str) -> bool:
    norm = unicodedata.normalize("NFKD", text.casefold())
    norm = "".join(c for c in norm if not unicodedata.combining(c))
    if any(term in norm for term in ("rendez", "rdv", "appointment", "booking", "reservation", "tache", "task")):
        return False
    return bool(re.search(r"\b(heures?|horaires?|hours?|ouvert\w*|ferme\w*|fermeture|opening|schedule|orar|programul|horario\w*)\b", norm))


def is_business_location_question(text: str) -> bool:
    norm = unicodedata.normalize("NFKD", text.casefold())
    norm = "".join(c for c in norm if not unicodedata.combining(c))
    if any(term in norm for term in ("site web", "courriel", "email", "rendez")):
        return False
    return bool(re.search(r"\b(adresses?|address\w*|ou etes|ou vous trouver|ou se trouve|emplacement|localisation|where are you|adresa|ubicacion\w*|donde estan)\b", norm))


def is_services_overview_question(text: str) -> bool:
    norm = unicodedata.normalize("NFKD", text.casefold())
    norm = "".join(c for c in norm if not unicodedata.combining(c))
    if any(term in norm for term in ("plus cher", "cher", "moins cher", "expensive", "cheapest", "combien coute", "prix du", "prix de", "rendez")):
        return False
    return bool(re.search(r"\b(quels sont vos services|vos prestations|quelles prestations|liste des services|quels services|ce servicii|servicii oferite|que servicios|servicios ofrecen|what services do you offer|what services do you provide)\b", norm))


def is_business_contact_question(text: str) -> bool:
    norm = unicodedata.normalize("NFKD", text.casefold())
    norm = "".join(c for c in norm if not unicodedata.combining(c))
    return bool(re.search(r"\b(site web|site internet|website|boutique en ligne|commander en ligne|online store|courriel|email|numero de telephone|comment vous joindre|how to reach|cum va putem contacta)\b", norm))


def is_open_catalog_question(text: str) -> bool:
    norm = unicodedata.normalize("NFKD", text.casefold())
    norm = "".join(c for c in norm if not unicodedata.combining(c))
    if any(
        term in norm
        for term in (
            "rendez vous", "rendez-vous", "rdv", "appointment", "appointments",
            "booking", "bookings", "reservation", "reservations", "creneau", "creneaux",
        )
    ):
        return False
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


def _parse_money_value(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    raw = str(value).replace("$", "").replace("€", "").replace("£", "").replace(",", ".").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except (ValueError, TypeError):
        return None


def _format_spoken_price_number(raw: Any, numeric: float | None) -> str:
    if numeric is not None:
        if numeric.is_integer():
            return str(int(numeric))
        return f"{numeric:.2f}".rstrip("0").rstrip(".")
    return str(raw).strip()


def _extract_profitability_score(row: dict[str, Any]) -> tuple[float, float] | None:
    """Return (margin_amount, margin_pct) ONLY when authorized cost/margin data is present.

    Never substitutes selling price for profitability.
    """
    price_val = _parse_money_value(row.get("price"))
    margin_amt = _parse_money_value(
        row.get("profit_margin_amount")
        if row.get("profit_margin_amount") is not None
        else (row.get("profit_margin") if row.get("profit_margin") is not None else row.get("gross_margin"))
    )
    margin_pct = _parse_money_value(
        row.get("profit_margin_pct")
        if row.get("profit_margin_pct") is not None
        else (row.get("gross_margin_pct") if row.get("gross_margin_pct") is not None else row.get("margin_pct"))
    )
    unit_cost = _parse_money_value(
        row.get("unit_cost")
        if row.get("unit_cost") is not None
        else (row.get("cost_price") if row.get("cost_price") is not None else row.get("cost"))
    )
    if margin_amt is None and unit_cost is not None and price_val is not None:
        margin_amt = round(price_val - unit_cost, 2)
    if margin_pct is None and margin_amt is not None and price_val is not None and price_val > 0:
        margin_pct = round((margin_amt / price_val) * 100.0, 2)
    if margin_amt is None and margin_pct is None:
        return None
    return (
        margin_amt if margin_amt is not None else 0.0,
        margin_pct if margin_pct is not None else 0.0,
    )


def _apply_catalog_view_mode(
    rows: list[dict[str, Any]],
    *,
    view_mode: str | None,
) -> list[dict[str, Any]]:
    """Apply persisted filter/ordering mode before slicing any catalog page."""
    if not view_mode or view_mode == "default":
        return rows
    if view_mode == "in_stock":
        return [
            r for r in rows
            if r.get("is_live_stock") is True
            and (r.get("in_stock") is True or r.get("stock_availability") == "IN_STOCK")
        ]
    if view_mode == "promote":
        def _promo_key(r: dict[str, Any]) -> tuple[int, float, float]:
            p_val = _parse_money_value(r.get("price")) or 0.0
            c_val = _parse_money_value(r.get("compare_at_price")) or 0.0
            if c_val > p_val > 0:
                discount_amt = c_val - p_val
                discount_pct = discount_amt / c_val
                return (1, round(discount_pct, 4), round(discount_amt, 2))
            return (0, 0.0, p_val)
        return sorted(rows, key=_promo_key, reverse=True)
    if view_mode == "profitable":
        scored: list[tuple[tuple[float, float], dict[str, Any]]] = []
        for r in rows:
            prof = _extract_profitability_score(r)
            if prof is not None:
                scored.append((prof, r))
        scored.sort(key=lambda pair: (pair[0][0], pair[0][1]), reverse=True)
        return [pair[1] for pair in scored]
    return rows


def spoken_profitability_unavailable_answer(locale: str) -> str:
    loc = (locale or "fr-CA").casefold()
    if loc.startswith("es"):
        return "No puedo determinar los productos más rentables solo a partir del catálogo porque no disponemos de los datos de costos o márgenes. ¿Desea ver los artículos en promoción con precio comparativo o el catálogo por precio?"
    if loc.startswith("ro"):
        return "Nu pot determina cele mai profitabile produse doar din catalog deoarece nu avem datele de cost sau marjă. Doriți să vedeți produsele la promoție cu preț comparativ sau catalogul după preț?"
    if loc.startswith("en"):
        return "I cannot determine the most profitable products from the catalog alone because unit cost and margin data are unavailable. Would you like to see discounted promotions or the catalog by price instead?"
    return "Je ne peux pas établir quels produits sont les plus rentables à partir du catalogue seul, car les données de coûts et de marges ne sont pas disponibles. Souhaitez-vous voir les articles en promotion avec prix comparatif ou le catalogue général ?"


def is_profitability_catalog_question(text: str) -> bool:
    norm = unicodedata.normalize("NFKD", text.casefold())
    norm = "".join(c for c in norm if not unicodedata.combining(c))
    words = _words(text)
    has_profit_word = bool(words & {"rentable", "rentables", "marge", "marges", "profitable", "margin", "margins", "profitabile"})
    has_catalog_word = bool(words & {"produit", "produits", "article", "articles", "catalogue", "catalog", "product", "products", "vendre", "sell"})
    return has_profit_word and has_catalog_word


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
    view_mode: str | None = None,
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

    # Inherit persisted filter/ordering mode when paginating (offset > 0)
    active_view_mode = view_mode
    if active_view_mode is None and offset > 0 and call is not None:
        active_view_mode = (call.source_context or {}).get("catalog_view_mode")
    if active_view_mode:
        rows = _apply_catalog_view_mode(rows, view_mode=active_view_mode)
        if not rows and active_view_mode == "in_stock":
            if spanish:
                return "Actualmente ningún producto tiene stock confirmado en tiempo real."
            if romanian:
                return "În prezent niciun produs nu are stoc confirmat în timp real."
            return (
                "Aucun produit n'a actuellement de stock confirmé en temps réel."
                if french else
                "No products currently have confirmed real-time stock."
            )
        if not rows and active_view_mode == "profitable":
            return spoken_profitability_unavailable_answer(locale)

    # Optional category / semantic filter based on query or inherited from call session context
    active_category = None
    is_accessories_query = False
    # Always run specific caller requests through semantic head-noun matching.
    # A modifier such as "snowboard" in "casque de snowboard" must NOT
    # force the broad "planche" branch before the helmet is considered.
    # Only an inherited filter from a previous catalog page may bypass
    # a fresh semantic search.

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
        sem = semantic_search_products(rows, query, limit=max(limit + offset, 20))
        if sem.status == "not_found":
            q_norm_nf = "".join(
                c for c in unicodedata.normalize("NFKD", query.casefold()) if not unicodedata.combining(c)
            )
            if re.search(r"\b(accessoire|accessoires|accessory|accessories)\b", q_norm_nf) and not sem.related_other_category:
                if spanish:
                    return "Actualmente no tenemos accesorios disponibles en nuestro catálogo. ¿Desea información sobre nuestros otros productos?"
                if romanian:
                    return "În prezent nu avem accesorii disponibile în catalogul nostru. Doriți informații despre celelalte produse?"
                return (
                    "Nous n'avons actuellement aucun accessoire disponible dans notre catalogue. Souhaitez-vous des renseignements sur nos autres articles ?"
                    if french else
                    "We do not currently have any accessories available in our catalog. Would you like information on our other items?"
                )
            other_note = ""
            if sem.related_other_category:
                other_names = ", ".join(str(x.get("name") or "") for x in sem.related_other_category[:2] if x.get("name"))
                if other_names and sem.not_found_reason == "no_protective_helmet_in_catalog":
                    if spanish:
                        other_note = f" Solo tenemos auriculares de audio ({other_names}), no cascos de protección."
                    elif romanian:
                        other_note = f" Avem doar căști audio ({other_names}), nu căști de protecție."
                    elif french:
                        other_note = f" Nous avons bien un casque audio ({other_names}), mais aucun casque de protection."
                    else:
                        other_note = f" We only carry audio headphones ({other_names}), not protective helmets."
            if spanish:
                return f"No tenemos ese producto en nuestro catálogo.{other_note}"
            if romanian:
                return f"Nu avem acest produs în catalogul nostru.{other_note}"
            return (
                f"Nous n'avons pas ce produit dans notre catalogue.{other_note}"
                if french else
                f"We do not carry that product in our catalog.{other_note}"
            )
        if sem.status == "ambiguous" and sem.matches:
            first_p = sem.matches[0].product
            p_name = str(first_p.get("name") or "").strip()
            p_price = first_p.get("price")
            p_unit = str(first_p.get("currency") or currency or "$").strip().upper()
            p_sym = "$" if p_unit in ("CAD", "USD", "$") or not p_unit else ("€" if p_unit in ("EUR", "€") else p_unit)
            price_str = f"{_format_spoken_price_number(p_price, _parse_money_value(p_price))} {p_sym}" if p_price not in (None, "") else ""
            if french:
                return (
                    f"Si vous parlez de notre casque audio {p_name}, il est à {price_str}. "
                    "Si vous cherchez plutôt un casque de protection, nous n'en avons pas au catalogue."
                ).strip()
            if spanish:
                return f"Si se refiere a nuestros auriculares {p_name}, cuestan {price_str}. No tenemos cascos de protección en el catálogo."
            if romanian:
                return f"Dacă vă referiți la căștile audio {p_name}, costă {price_str}. Nu avem căști de protecție în catalog."
            return f"If you mean our audio headphones {p_name}, they are priced at {price_str}. We do not carry protective helmets in our catalog."
        if sem.status == "found" and sem.matches:
            rows = [m.product for m in sem.matches]
            if all(m.match_reason == "accessories_category_match" for m in sem.matches):
                active_category = "accessoire"
                is_accessories_query = True
            elif all(m.product_domain == "snowboard" for m in sem.matches):
                active_category = "planche"

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
        compare_at = row.get("compare_at_price")
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
            p_num = _parse_money_value(price)
            c_num = _parse_money_value(compare_at)
            price_disp = _format_spoken_price_number(price, p_num) if isinstance(price, float) else str(price).strip()
            price_text = f"{price_disp} {unit}".strip()
            if p_num is not None and c_num is not None and c_num > p_num:
                cmp_disp = _format_spoken_price_number(compare_at, c_num)
                if spanish:
                    price_text += f" en lugar de {cmp_disp} {unit}"
                elif romanian:
                    price_text += f" redus de la {cmp_disp} {unit}"
                elif french:
                    price_text += f" au lieu de {cmp_disp} {unit}"
                else:
                    price_text += f" down from {cmp_disp} {unit}"
            if is_demo_row:
                demo_tag = " (precio de demostración)" if spanish else (" (preț demonstrativ)" if romanian else (" (prix démonstration)" if french else " (demo price)"))
                price_text += demo_tag

        available = ""
        stock_avail = row.get("stock_availability")
        if is_demo_row:
            available = ", datos de demostración" if spanish else (", date demonstrative" if romanian else (", données de démonstration" if french else ", demo data"))
        elif is_live and (stock_avail == "IN_STOCK" or row.get("in_stock") is True):
            available = ", disponible" if spanish else (", disponibil" if romanian else (", disponible" if french else ", available"))
        elif is_live and (stock_avail == "OUT_OF_STOCK" or row.get("in_stock") is False):
            available = ", agotado" if spanish else (", stoc epuizat" if romanian else (", en rupture de stock" if french else ", out of stock"))
        # NEVER repeat ", stock non confirmé, données non récentes" on every product!
        # A single concise note is appended ONCE at the end when live stock is not synced.

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
        ctx["catalog_view_mode"] = active_view_mode
        ctx["last_voice_topic"] = "retail_catalog"
        call.source_context = ctx

    extra = ""
    remaining = len(rows) - (offset + len(target_slice))
    if remaining > 0:
        if spanish:
            extra = f" Y {remaining} {'artículo' if remaining == 1 else 'artículos'} más en el catálogo. ¿Desea continuar?"
        elif romanian:
            extra = f" Și încă {remaining} {'articol' if remaining == 1 else 'articole'} în catalog. Doriți să continuăm?"
        elif french:
            extra = f" Et {remaining} autre{'s' if remaining > 1 else ''} article{'s' if remaining > 1 else ''} au catalogue. Voulez-vous continuer ?"
        else:
            extra = f" And {remaining} more items in the catalog. Would you like to continue?"

    hist_note = ""
    if any(not r.get("is_live_stock") and not r.get("is_demo") for r in target_slice):
        if spanish:
            hist_note = " El stock en tiempo real no está confirmado por teléfono."
        elif romanian:
            hist_note = " Stocul în timp real nu este confirmat la telefon."
        elif french:
            hist_note = " Le stock en temps réel est non confirmé."
        else:
            hist_note = " Live stock availability is unconfirmed."

    if is_accessories_query:
        if spanish:
            raw_ans = "Como accesorios, ofrecemos en particular: " + " ; ".join(spoken) + "." + extra + hist_note
        elif romanian:
            raw_ans = "Ca accesorii, vă oferim în special: " + " ; ".join(spoken) + "." + extra + hist_note
        elif french:
            raw_ans = "Nous proposons notamment comme accessoires : " + " ; ".join(spoken) + "." + extra + hist_note
        else:
            raw_ans = "As accessories, we notably offer: " + "; ".join(spoken) + "." + extra + hist_note
        return sanitize_retail_voice_text(raw_ans, locale=locale)
    if spanish:
        raw_ans = "Tenemos en el catálogo: " + " ; ".join(spoken) + "." + extra + hist_note
    elif romanian:
        raw_ans = "Avem în catalog: " + " ; ".join(spoken) + "." + extra + hist_note
    elif french:
        raw_ans = "Nous avons au catalogue : " + " ; ".join(spoken) + "." + extra + hist_note
    else:
        raw_ans = "In our catalog, we have: " + "; ".join(spoken) + "." + extra + hist_note
    return sanitize_retail_voice_text(raw_ans, locale=locale)


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

    # Strip leading attention check when paired with an actual business question
    # (e.g. "Allô, tu m'entends ? Quel est le prix des casques ?" -> "Quel est le prix des casques ?")
    from backend.app.voice.turn_control import extract_request_after_attention_check
    embedded_after_attn = extract_request_after_attention_check(transcript)
    if embedded_after_attn:
        transcript = embedded_after_attn

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

    # 4. Superlative CRM service inquiries (e.g. "Quel service est le plus cher ?")
    if is_superlative_service_question(transcript):
        from backend.app.services.company_intelligence_service import CompanyIntelligenceService

        profile = CompanyIntelligenceService(db).get_profile(company_id)
        services = list(getattr(profile, "configured_crm_services", ()) or ())
        priced_services = []
        for s in services:
            p = s.get("price")
            if p is not None:
                try:
                    val = float(str(p).replace("$", "").replace("€", "").strip())
                    priced_services.append((val, s))
                except (ValueError, TypeError):
                    pass
        if priced_services:
            priced_services.sort(key=lambda x: x[0], reverse=True)
            top_val, top_s = priced_services[0]
            curr = top_s.get("currency") or getattr(profile, "currency_code", "CAD")
            dur = top_s.get("duration_minutes")
            dur_str = f" d'une durée de {dur} minutes" if dur else ""
            name = top_s.get("name", "Service")
            loc = locale.lower()
            if loc.startswith("fr"):
                return f"Notre prestation la plus chère est {name} au tarif de {top_val:g} {curr}{dur_str}."
            elif loc.startswith("es"):
                return f"Nuestro servicio más exclusivo es {name} a {top_val:g} {curr}."
            elif loc.startswith("ro"):
                return f"Cel mai scump serviciu al nostru este {name} la {top_val:g} {curr}."
            return f"Our most expensive service is {name} at {top_val:g} {curr}."

    # 5. Ordinal product lookup in conversational memory (e.g. "Combien coûte le deuxième ?")
    is_ord, ord_idx = is_ordinal_product_question(transcript)
    if is_ord and call is not None:
        presented = list((call.source_context or {}).get("presented_catalog_products") or [])
        if presented:
            return spoken_ordinal_product_answer(presented, ord_idx, locale=locale)

    # 6. Superlative product inquiries (e.g. "Quelle planche est la plus chère ?")
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

    # 7. Catalog pagination (e.g. "Quels sont les cinq prochains produits ?")
    is_page, req_count = is_catalog_pagination_question(transcript)
    if is_page:
        from backend.app.services.company_intelligence_service import CompanyIntelligenceService

        presented = list((call.source_context or {}).get("presented_catalog_products") or []) if call is not None else []
        has_catalog_context = bool(presented) or any(w in transcript.lower() for w in ("produit", "article", "catalogue", "planche", "accessoire", "product", "item"))
        if has_catalog_context:
            profile = CompanyIntelligenceService(db).get_profile(company_id)
            retail_enabled = bool(getattr(profile, "has_retail_commerce", False)) or "retail" in set(getattr(profile, "active_modules", ()) or ())
            products = list(getattr(profile, "public_products", ()) or ())
            current_offset = int((call.source_context or {}).get("catalog_pagination_offset", 3)) if call is not None else 3
            saved_view_mode = (call.source_context or {}).get("catalog_view_mode") if call is not None else None
            return spoken_catalog_answer(
                products,
                retail_enabled=retail_enabled,
                locale=locale,
                currency=getattr(profile, "currency_code", None),
                query=None,
                offset=current_offset,
                limit=req_count,
                call=call,
                view_mode=saved_view_mode,
            )

    # 7a. Follow-up after commercial selling clarification
    if call is not None and (call.source_context or {}).get("pending_retail_clarification"):
        words_fu = _words(transcript)
        wants_in_stock = bool(words_fu & {"stock", "disponible", "disponibles", "available", "stoc", "confirmes", "confirme"})
        wants_profitable = bool(words_fu & {"rentable", "rentables", "marge", "marges", "profitable", "margin", "profit", "profitabile"})
        wants_promote = bool(words_fu & {"promouvoir", "promotion", "promotions", "opportunite", "opportunites", "promote", "promocionar", "promovare"})
        if wants_in_stock or wants_profitable or wants_promote:
            from backend.app.services.company_intelligence_service import CompanyIntelligenceService

            ctx_fu = dict(call.source_context or {})
            ctx_fu.pop("pending_retail_clarification", None)
            ctx_fu["last_voice_topic"] = "retail_catalog"
            call.source_context = ctx_fu
            profile = CompanyIntelligenceService(db).get_profile(company_id)
            retail_enabled = bool(getattr(profile, "has_retail_commerce", False)) or "retail" in set(getattr(profile, "active_modules", ()) or ())
            products = [p for p in (getattr(profile, "public_products", ()) or ()) if isinstance(p, dict)]
            if wants_in_stock:
                live_available = _apply_catalog_view_mode(products, view_mode="in_stock")
                if not live_available:
                    loc = locale.lower()
                    if loc.startswith("es"):
                        return "Actualmente ningún producto tiene stock confirmado en tiempo real porque la sincronización no es reciente. ¿Desea ver los precios indicativos del catálogo?"
                    if loc.startswith("ro"):
                        return "În prezent niciun produs nu are stoc confirmat în timp real deoarece sincronizarea nu este recentă. Doriți să vedeți catalogul indicativ?"
                    if loc.startswith("en"):
                        return "No products currently have confirmed real-time stock because the inventory sync is not recent. Would you like to review the indicative catalog?"
                    return "Aucun produit n'a actuellement de stock confirmé en temps réel car la synchronisation d'inventaire n'est pas récente. Voulez-vous consulter le catalogue indicatif ?"
                return spoken_catalog_answer(
                    products,
                    retail_enabled=retail_enabled,
                    locale=locale,
                    currency=getattr(profile, "currency_code", None),
                    offset=0,
                    limit=3,
                    call=call,
                    view_mode="in_stock",
                )
            if wants_profitable:
                # Never confuse selling price with profitability: require verified server-side executive role
                # (canonical role normalized across Enum/string) and real cost/margin evidence.
                verified_role = resolve_verified_staff_role(db, company_id, user_id, fallback_role=staff_role)
                if not is_executive_role(verified_role):
                    loc = locale.lower()
                    if loc.startswith("es"):
                        return "Los datos de rentabilidad y márgenes están reservados a la dirección."
                    if loc.startswith("ro"):
                        return "Datele de profitabilitate și marje sunt rezervate conducerii."
                    if loc.startswith("en"):
                        return "Profitability and margin data are restricted to management."
                    return "Les données de rentabilité et de marges sont réservées à la direction."
                profitable_rows = _apply_catalog_view_mode(products, view_mode="profitable")
                if not profitable_rows:
                    ctx_no_prof = dict(call.source_context or {})
                    ctx_no_prof.pop("catalog_view_mode", None)
                    call.source_context = ctx_no_prof
                    return spoken_profitability_unavailable_answer(locale)
                return spoken_catalog_answer(
                    products,
                    retail_enabled=retail_enabled,
                    locale=locale,
                    currency=getattr(profile, "currency_code", None),
                    offset=0,
                    limit=3,
                    call=call,
                    view_mode="profitable",
                )
            # Promotion opportunities: discount-aware ranking persisted across pagination
            return spoken_catalog_answer(
                products,
                retail_enabled=retail_enabled,
                locale=locale,
                currency=getattr(profile, "currency_code", None),
                offset=0,
                limit=3,
                call=call,
                view_mode="promote",
            )

    # 7a-bis. Direct profitability catalog question (even without prior clarification)
    if authenticated_staff and is_profitability_catalog_question(transcript):
        from backend.app.services.company_intelligence_service import CompanyIntelligenceService

        verified_role = resolve_verified_staff_role(db, company_id, user_id, fallback_role=staff_role)
        if not is_executive_role(verified_role):
            loc = locale.lower()
            if loc.startswith("es"):
                return "Los datos de rentabilidad y márgenes están reservados a la dirección."
            if loc.startswith("ro"):
                return "Datele de profitabilitate și marje sunt rezervate conducerii."
            if loc.startswith("en"):
                return "Profitability and margin data are restricted to management."
            return "Les données de rentabilité et de marges sont réservées à la direction."
        profile = CompanyIntelligenceService(db).get_profile(company_id)
        retail_enabled = bool(getattr(profile, "has_retail_commerce", False)) or "retail" in set(getattr(profile, "active_modules", ()) or ())
        products = [p for p in (getattr(profile, "public_products", ()) or ()) if isinstance(p, dict)]
        profitable_rows = _apply_catalog_view_mode(products, view_mode="profitable")
        if not profitable_rows:
            return spoken_profitability_unavailable_answer(locale)
        return spoken_catalog_answer(
            products,
            retail_enabled=retail_enabled,
            locale=locale,
            currency=getattr(profile, "currency_code", None),
            offset=0,
            limit=3,
            call=call,
            view_mode="profitable",
        )

    # 7b. Ambiguous commercial selling intent from authenticated staff/owner
    if authenticated_staff and is_ambiguous_commercial_selling_question(transcript):
        if call is not None:
            ctx_amb = dict(call.source_context or {})
            ctx_amb["last_voice_topic"] = "retail_commercial_clarification"
            ctx_amb["pending_retail_clarification"] = True
            call.source_context = ctx_amb
        return spoken_commercial_selling_clarification(locale)

    # 7c. Open catalog check
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

    # 8. Business hours fast-path
    if is_business_hours_question(transcript):
        from backend.app.services.company_intelligence_service import CompanyIntelligenceService
        profile = CompanyIntelligenceService(db).get_profile(company_id)
        comp = db.get(Company, company_id)
        cfg = db.scalar(select(VoiceBusinessConfig).where(VoiceBusinessConfig.company_id == company_id))
        raw_hours = getattr(comp, "business_hours", None) or getattr(cfg, "opening_hours", None) or (profile.business_configuration.get("opening_hours") if getattr(profile, "business_configuration", None) else None) or {}
        hours_dict = {}
        if isinstance(raw_hours, dict) and "weekly" in raw_hours and isinstance(raw_hours["weekly"], dict):
            for day, ranges in raw_hours["weekly"].items():
                if isinstance(ranges, list) and ranges:
                    r_str = ", ".join(f"{r.get('open')} à {r.get('close')}" for r in ranges if isinstance(r, dict) and r.get("open") and r.get("close"))
                    if r_str:
                        hours_dict[day.lower()] = r_str
        elif isinstance(raw_hours, dict):
            for day, val in raw_hours.items():
                if isinstance(val, dict) and val.get("open") and val.get("close"):
                    hours_dict[day.lower()] = f"{val.get('open')} à {val.get('close')}"
                elif isinstance(val, str) and val.strip():
                    hours_dict[day.lower()] = val.strip()
        day_map_fr = {
            "monday": "lundi", "tuesday": "mardi", "wednesday": "mercredi",
            "thursday": "jeudi", "friday": "vendredi", "saturday": "samedi", "sunday": "dimanche"
        }
        loc = locale.lower()
        if hours_dict:
            if loc.startswith("fr"):
                summary = ", ".join(f"{day_map_fr.get(day, day)}: {h}" for day, h in hours_dict.items())
                return f"Nos heures d'ouverture sont : {summary}."
            elif loc.startswith("es"):
                summary = ", ".join(f"{day}: {h}" for day, h in hours_dict.items())
                return f"Nuestro horario de atención es: {summary}."
            elif loc.startswith("ro"):
                summary = ", ".join(f"{day}: {h}" for day, h in hours_dict.items())
                return f"Programul nostru de lucru este: {summary}."
            else:
                summary = ", ".join(f"{day}: {h}" for day, h in hours_dict.items())
                return f"Our opening hours are: {summary}."
        else:
            if loc.startswith("fr"):
                return "Nos heures d'ouverture ne sont pas encore configurées dans le système."
            elif loc.startswith("es"):
                return "Nuestro horario de atención aún no está configurado en el sistema."
            elif loc.startswith("ro"):
                return "Programul de lucru nu este încă configurat în sistem."
            return "Our opening hours are not yet configured in the system."

    # 9. Business address / location fast-path
    if is_business_location_question(transcript):
        from backend.app.services.company_intelligence_service import CompanyIntelligenceService
        comp = db.get(Company, company_id)
        cfg = db.scalar(select(VoiceBusinessConfig).where(VoiceBusinessConfig.company_id == company_id))
        profile = CompanyIntelligenceService(db).get_profile(company_id)
        biz_cfg = getattr(profile, "business_configuration", None) or {}
        call_policy = (cfg.call_policy if cfg and isinstance(cfg.call_policy, dict) else {}) if cfg else {}
        addr_parts = []
        if call_policy.get("business_address"):
            addr_parts.append(str(call_policy["business_address"]).strip())
        for f in ("address", "city", "province", "postal_code"):
            val = getattr(comp, f, None) or biz_cfg.get(f) or call_policy.get(f)
            if val and str(val).strip() and str(val).strip() not in addr_parts:
                addr_parts.append(str(val).strip())
        loc = locale.lower()
        if addr_parts:
            full_addr = ", ".join(addr_parts)
            if loc.startswith("fr"):
                return f"Notre établissement est situé à l'adresse suivante : {full_addr}."
            elif loc.startswith("es"):
                return f"Nuestra empresa está ubicada en: {full_addr}."
            elif loc.startswith("ro"):
                return f"Compania noastră este situată la adresa: {full_addr}."
            return f"Our business is located at: {full_addr}."
        else:
            if loc.startswith("fr"):
                return "Notre adresse physique n'est pas encore renseignée dans le système."
            elif loc.startswith("es"):
                return "Nuestra dirección aún no está registrada en el sistema."
            elif loc.startswith("ro"):
                return "Adresa fizică nu este încă înregistrată în sistem."
            return "Our physical address is not yet registered in the system."

    # 10. Services overview fast-path
    if is_services_overview_question(transcript):
        from backend.app.services.company_intelligence_service import CompanyIntelligenceService
        cfg = db.scalar(select(VoiceBusinessConfig).where(VoiceBusinessConfig.company_id == company_id))
        profile = CompanyIntelligenceService(db).get_profile(company_id)
        services = list(getattr(profile, "configured_crm_services", ()) or ())
        if not services and cfg and cfg.services:
            services = [s for s in cfg.services if isinstance(s, dict) and s.get("name")]
        loc = locale.lower()
        if services:
            def _sym(curr: Any) -> str:
                c = str(curr or "").strip().upper()
                return "$" if c in ("CAD", "USD", "$") or not c else ("€" if c in ("EUR", "€") else ("£" if c in ("GBP", "£") else c))
            summary_list = []
            for s in services[:5]:
                name = s.get("name", "")
                price = s.get("price")
                dur = s.get("duration_minutes")
                curr = _sym(s.get("currency"))
                item_str = name
                if price is not None:
                    item_str += f" ({price} {curr}"
                    if dur:
                        item_str += f", {dur} min"
                    item_str += ")"
                summary_list.append(item_str)
            summary = ", ".join(summary_list)
            if loc.startswith("fr"):
                return f"Nous proposons les prestations suivantes : {summary}. Souhaitez-vous planifier un rendez-vous ?"
            elif loc.startswith("es"):
                return f"Ofrecemos los siguientes servicios: {summary}. ¿Desea concertar una cita?"
            elif loc.startswith("ro"):
                return f"Oferim următoarele servicii: {summary}. Doriți să programați o întâlnire?"
            return f"We offer the following services: {summary}. Would you like to book an appointment?"
        else:
            if loc.startswith("fr"):
                return "Nos prestations de services ne sont pas encore configurées dans le système."
            elif loc.startswith("es"):
                return "Nuestros servicios aún no están configurados en el sistema."
            elif loc.startswith("ro"):
                return "Serviciile noastre nu sunt încă configurate în sistem."
            return "Our services are not yet configured in the system."

    # 11. Website and online store fast-path
    if is_business_contact_question(transcript):
        from backend.app.services.company_intelligence_service import CompanyIntelligenceService
        profile = CompanyIntelligenceService(db).get_profile(company_id)
        comp = db.get(Company, company_id)
        web = getattr(profile, "website", None) or getattr(comp, "website", None)
        online_store = getattr(profile, "online_store_url", None)
        email = getattr(profile, "email", None) or getattr(comp, "email", None)
        phone = getattr(profile, "phone", None) or getattr(comp, "phone", None)
        loc = locale.lower()
        items = []
        if online_store:
            items.append(f"boutique en ligne : {online_store}" if loc.startswith("fr") else f"online store: {online_store}")
        elif web:
            items.append(f"site web : {web}" if loc.startswith("fr") else f"website: {web}")
        if email:
            items.append(f"courriel : {email}" if loc.startswith("fr") else f"email: {email}")
        if phone:
            items.append(f"téléphone : {phone}" if loc.startswith("fr") else f"phone: {phone}")
        if items:
            details = ", ".join(items)
            if loc.startswith("fr"):
                return f"Voici nos coordonnées : {details}."
            elif loc.startswith("es"):
                return f"Nuestros datos de contacto son: {details}."
            elif loc.startswith("ro"):
                return f"Datele noastre de contact sunt: {details}."
            return f"Our contact details are: {details}."

    return None
