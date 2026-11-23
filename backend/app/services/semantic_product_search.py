"""Universal semantic product search with head-noun preservation, concept disambiguation,
multilingual synonyms (FR/EN/ES/RO), and explicit not-found / ambiguity reporting.

Never substitutes unrelated catalog items when a specific product search has no reliable match
(e.g., searching for a snowboard protective helmet will never return a snowboard or audio headphones).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
import re
import unicodedata
from typing import Any, Sequence


_STOPWORDS: frozenset[str] = frozenset({
    # French
    "le", "la", "les", "un", "une", "des", "du", "de", "d", "l", "au", "aux", "a",
    "en", "et", "ou", "est", "sont", "etait", "quel", "quels", "quelle", "quelles",
    "combien", "coute", "coutent", "prix", "tarif", "tarifs", "avez", "vous", "avons",
    "nous", "notre", "votre", "nos", "vos", "mon", "ma", "mes", "ce", "cet", "cette",
    "ces", "je", "tu", "il", "elle", "on", "me", "te", "se", "que", "qui", "quoi",
    "cherche", "voudrais", "veux", "aimerai", "aimerais", "savoir", "voir", "trouver",
    "proposez", "vendez", "vendre", "acheter", "disponible", "disponibles", "stock",
    "inventaire", "catalogue", "produit", "produits", "article", "articles", "magasin",
    "boutique", "commerce", "entreprise", "compagnie", "quincaillerie",
    "pour", "avec", "sans", "dans", "sur", "mettre", "porter", "tete",
    "oui", "non", "merci", "bonjour", "salut", "allo", "estce", "y", "a-t-il",
    "prochain", "prochains", "prochaine", "prochaines", "suivant", "suivants",
    "suivante", "suivantes", "autre", "autres", "suite",
    "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf", "dix",
    # English
    "the", "an", "of", "in", "on", "for", "to", "with", "without", "and", "or",
    "is", "are", "was", "what", "which", "how", "much", "do", "does", "you", "we",
    "have", "sell", "offer", "price", "prices", "cost", "catalog", "product", "products",
    "item", "items", "stock", "available", "looking", "want", "need", "find", "show",
    "store", "shop", "business", "company", "tienda", "negocio", "empresa", "magazin", "companie",
    "your", "our", "my", "this", "that", "these", "those", "any", "some", "me",
    "next", "more", "other", "others", "two", "three", "four", "five", "ten",
    # Spanish
    "el", "los", "las", "uno", "una", "unos", "unas", "del", "al", "para", "con",
    "sin", "cual", "cuales", "cuanto", "cuesta", "cuestan", "precio", "precios",
    "tienen", "tienes", "producto", "productos", "articulo", "articulos", "catalogo",
    "disponible", "disponibles", "busco", "quiero", "saber",
    "siguiente", "siguientes", "otro", "otros", "dos", "tres", "cuatro", "cinco", "diez",
    # Romanian
    "care", "este", "sunt", "cat", "costa", "pret", "pretul", "preturi", "aveti",
    "produs", "produse", "articol", "articole", "catalog", "stoc", "pentru", "cu",
    "fara", "din", "la", "pe", "caut", "vreau",
    "urmatoare", "urmatoarele", "alt", "alte", "doi", "trei", "patru", "cinci", "zece",
})

_BROWSE_ONLY_QUERIES: frozenset[str] = frozenset({
    "", "all", "tous", "toutes", "tout", "produits", "produit", "product", "products",
    "catalogue", "catalog", "catalogues", "articles", "article", "items", "item",
    "inventaire", "inventory", "stock", "liste", "list",
})

# Prepositions splitting head noun and modifier in Romance languages (FR/ES/RO)
_ROMANCE_PREPS: frozenset[str] = frozenset({"de", "du", "des", "d", "pour", "a", "au", "aux", "para", "pentru"})

# Ambiguous polysemous tokens whose domain sense must be checked against product concept
_AMBIGUOUS_CASQUE_TOKENS: frozenset[str] = frozenset({"casque", "casques", "casca", "casti"})

# Protective headgear / helmet concept signals
_PROTECTIVE_HELMET_TOKENS: frozenset[str] = frozenset({
    "helmet", "helmets", "casco", "cascos", "headgear", "hard hat", "hardhat",
    "protection", "protecteur", "protectrice", "securite", "safety", "protectie", "proteccion",
    "tete", "head", "cabeza", "cap", "crane", "ski", "snowboard", "snowboards",
    "velo", "bike", "bicycle", "cycling", "moto", "motorcycle", "skate", "skateboard",
    "chantier", "construction", "escalade", "climbing", "glisse",
})

# Audio headphones / headset concept signals
_AUDIO_HEADPHONES_TOKENS: frozenset[str] = frozenset({
    "headphone", "headphones", "headset", "headsets", "earbud", "earbuds", "earphone", "earphones",
    "ecouteur", "ecouteurs", "audio", "bluetooth", "musique", "music", "son", "sound",
    "wireless", "sansfil", "anc", "noise", "cancelling", "hifi", "stereo", "micro",
    "microphone", "gaming", "auricular", "auriculares", "audifono", "audifonos",
})

# Cross-lingual concept synonym groups (canonical stem -> equivalent tokens across FR/EN/ES/RO)
_CONCEPT_SYNONYMS: dict[str, frozenset[str]] = {
    "snowboard": frozenset({"snowboard", "snowboards", "planche", "planches", "board", "boards", "tabla", "tablas"}),
    "ski": frozenset({"ski", "skis", "esqui", "schi"}),
    "helmet_protective": frozenset({"helmet", "helmets", "casco", "cascos", "headgear"}),
    "headphones_audio": frozenset({
        "headphone", "headphones", "headset", "headsets", "earbud", "earbuds",
        "earphone", "earphones", "ecouteur", "ecouteurs", "auricular", "auriculares",
    }),
    "gloves": frozenset({"gant", "gants", "glove", "gloves", "moufle", "moufles", "mitaine", "mitaines", "guante", "guantes", "manusa", "manusi"}),
    "goggles": frozenset({"lunette", "lunettes", "masque", "masques", "goggle", "goggles", "eyewear", "gafas", "ochelari"}),
    "bindings": frozenset({"fixation", "fixations", "binding", "bindings", "fijacion", "fijaciones"}),
    "boots": frozenset({"botte", "bottes", "boot", "boots", "chaussure", "chaussures", "shoe", "shoes", "bota", "botas", "cizma", "cizme"}),
    "jacket": frozenset({"veste", "vestes", "manteau", "manteaux", "blouson", "jacket", "jackets", "coat", "coats", "chaqueta", "geaca"}),
    "wax": frozenset({"fart", "wax", "cire", "cera"}),
    "accessories": frozenset({"accessoire", "accessoires", "accessory", "accessories", "accesorio", "accesorios", "accesoriu", "accesorii"}),
    "tire": frozenset({"pneu", "pneus", "tire", "tires", "tyre", "tyres", "neumatico", "anvelopa"}),
    "brake": frozenset({"frein", "freins", "brake", "brakes", "freno", "frana"}),
    "oil": frozenset({"huile", "oil", "aceite", "ulei"}),
    "filter": frozenset({"filtre", "filtres", "filter", "filters", "filtro", "filtru"}),
    "battery": frozenset({"batterie", "batteries", "battery", "bateria", "baterie"}),
    "charger": frozenset({"chargeur", "chargeurs", "charger", "chargers", "cargador", "incarcator"}),
    "chair": frozenset({"chaise", "chaises", "chair", "chairs", "silla", "scaun"}),
    "shampoo": frozenset({"shampoing", "shampooing", "shampoo", "champu", "sampon"}),
    "winter": frozenset({"hiver", "winter", "invierno", "iarna"}),
    "summer": frozenset({"ete", "summer", "verano", "vara"}),
    "waterproof": frozenset({"impermeable", "impermeables", "waterproof", "etanche"}),
    "drill": frozenset({"perceuse", "perceuses", "drill", "drills", "taladro", "bormasina"}),
    "car": frozenset({"auto", "voiture", "vehicule", "car", "vehicle", "coche", "masina"}),
}

_TOKEN_TO_CONCEPTS: dict[str, set[str]] = {}
for _concept_key, _syn_set in _CONCEPT_SYNONYMS.items():
    for _tok in _syn_set:
        _TOKEN_TO_CONCEPTS.setdefault(_tok, set()).add(_concept_key)


def _fold_ascii(text: str) -> str:
    norm = unicodedata.normalize("NFKD", (text or "").casefold())
    return "".join(ch for ch in norm if not unicodedata.combining(ch))


def _tokenize_ordered(text: str) -> list[str]:
    folded = _fold_ascii(text)
    # Normalize common contractions before splitting
    folded = re.sub(r"\b(?:d|l|qu|j|m|t|s|n)['’]", " ", folded)
    return re.findall(r"[a-z0-9]+", folded)


def _stem_token(tok: str) -> str:
    if len(tok) >= 5 and tok.endswith("ies"):
        return tok[:-3] + "y"
    if len(tok) >= 5 and tok.endswith("es") and not tok.endswith(("ques", "ches", "shes", "xes", "zes")):
        return tok[:-1]
    if len(tok) >= 4 and tok.endswith("s") and not tok.endswith("ss"):
        return tok[:-1]
    return tok


def _content_tokens(tokens: list[str]) -> list[str]:
    return [t for t in tokens if t not in _STOPWORDS and len(t) >= 2]


def _extract_head_and_modifiers(raw_query: str) -> tuple[list[str], list[str], bool]:
    """Separate the primary requested product type (head noun) from context modifiers.

    Examples:
        - "Quel est le prix des casques pour le snowboard ?" -> head=['casques'], mod=['snowboard']
        - "casque de protection pour la tête" -> head=['casque'], mod=['protection', 'tete']
        - "snowboard helmet" -> head=['helmet'], mod=['snowboard']
        - "Avenqo Headphones X" -> head=['avenqo', 'headphones', 'x'], mod=[]
    """
    ordered = _tokenize_ordered(raw_query)
    if not ordered:
        return [], [], False

    # Look for a Romance preposition pattern: <content_noun> (de|du|des|pour|a|au|para|pentru) <modifier_noun>
    # Ignore leading framing words ("prix des casques" -> skip "prix des"!)
    content_positions: list[tuple[int, str]] = [
        (idx, tok) for idx, tok in enumerate(ordered)
        if tok not in _STOPWORDS and len(tok) >= 2
    ]
    if len(content_positions) >= 2:
        first_idx, first_tok = content_positions[0]
        second_idx, _second_tok = content_positions[1]
        between = ordered[first_idx + 1 : second_idx]
        if any(p in _ROMANCE_PREPS for p in between):
            # Romance noun phrase: HEAD prep MODIFIER...
            heads = [first_tok]
            modifiers = [tok for _, tok in content_positions[1:]]
            return heads, modifiers, True

        # Check English compound noun phrase: "<modifier> <head_concept>" (e.g. "snowboard helmet", "ski gloves")
        # Trigger when final content token is a recognized product noun distinct from preceding modifier concept
        last_tok = content_positions[-1][1]
        first_concepts = _TOKEN_TO_CONCEPTS.get(first_tok, set()) | _TOKEN_TO_CONCEPTS.get(_stem_token(first_tok), set())
        last_concepts = _TOKEN_TO_CONCEPTS.get(last_tok, set()) | _TOKEN_TO_CONCEPTS.get(_stem_token(last_tok), set())
        if (
            len(content_positions) == 2
            and last_concepts
            and first_concepts
            and first_concepts.isdisjoint(last_concepts)
            and (second_idx == first_idx + 1)
        ):
            return [last_tok], [first_tok], True

    all_content = [tok for _, tok in content_positions]
    return all_content, [], False


def _product_text_blob(row: dict[str, Any]) -> tuple[str, str, str]:
    name = str(row.get("name") or row.get("product_name") or row.get("title") or "").strip()
    cat = str(row.get("category") or row.get("product_category") or "").strip()
    desc = str(row.get("description") or row.get("body_html") or "").strip()
    sku = str(row.get("sku") or "").strip()
    tags_raw = row.get("tags") or row.get("attributes") or ""
    tags = " ".join(str(x) for x in tags_raw) if isinstance(tags_raw, (list, tuple, set)) else str(tags_raw)
    return name, f"{cat} {tags} {sku}".strip(), desc


def _classify_product_domain(name: str, meta: str, desc: str) -> str:
    """Identify coarse product domain for polysemy conflict prevention."""
    tokens = set(_tokenize_ordered(f"{name} {meta} {desc}"))
    stems = {_stem_token(t) for t in tokens}
    combined = tokens | stems

    has_audio = bool(combined & _AUDIO_HEADPHONES_TOKENS)
    has_helmet = bool(combined & {"helmet", "helmets", "casco", "cascos", "headgear", "hardhat"}) or (
        bool(combined & _AMBIGUOUS_CASQUE_TOKENS) and not has_audio
    )
    has_board = bool(combined & {"snowboard", "snowboards", "planche", "planches"}) and not has_helmet

    if has_audio and not has_helmet:
        return "audio_headphones"
    if has_helmet and not has_audio:
        return "protective_helmet"
    if has_board:
        return "snowboard"
    return "general"


def _classify_query_casque_sense(raw_query: str) -> str | None:
    """When query uses French/Romanian 'casque'/'cască' or explicit helmet/headphone terms,
    return 'protective_helmet', 'audio_headphones', 'ambiguous_casque', or None.
    """
    tokens = set(_tokenize_ordered(raw_query))
    stems = {_stem_token(t) for t in tokens}
    combined = tokens | stems

    explicit_helmet = bool(combined & {"helmet", "helmets", "casco", "cascos", "headgear", "hardhat"})
    explicit_audio = bool(combined & _AUDIO_HEADPHONES_TOKENS)
    has_ambiguous_casque = bool(combined & _AMBIGUOUS_CASQUE_TOKENS)

    if explicit_helmet and not explicit_audio:
        return "protective_helmet"
    if explicit_audio and not explicit_helmet and not has_ambiguous_casque:
        return "audio_headphones"
    if has_ambiguous_casque:
        if explicit_audio:
            return "audio_headphones"
        if bool(combined & _PROTECTIVE_HELMET_TOKENS):
            return "protective_helmet"
        return "ambiguous_casque"
    return None


def _tokens_match(query_tok: str, prod_tokens: set[str], prod_stems: set[str], prod_text: str) -> float:
    """Return match strength [0.0 .. 1.0] between a single query token and a product."""
    q_stem = _stem_token(query_tok)
    if query_tok in prod_tokens or q_stem in prod_stems:
        return 1.0
    # Concept synonym match (e.g. "gants" <-> "gloves", "planche" <-> "snowboard")
    q_concepts = _TOKEN_TO_CONCEPTS.get(query_tok, set()) | _TOKEN_TO_CONCEPTS.get(q_stem, set())
    if q_concepts:
        for pt in prod_tokens | prod_stems:
            p_concepts = _TOKEN_TO_CONCEPTS.get(pt, set())
            if q_concepts & p_concepts:
                return 0.92
    # Substring containment for longer terms (>= 5 chars)
    if len(q_stem) >= 5 and q_stem in prod_text:
        return 0.85
    # Strict typo tolerance for ASR/spelling errors (e.g., "snowbord" -> "snowboard")
    if len(q_stem) >= 5:
        best_sim = 0.0
        for pt in prod_tokens:
            if len(pt) >= 5 and abs(len(pt) - len(q_stem)) <= 2:
                sim = SequenceMatcher(None, q_stem, pt).ratio()
                if sim > best_sim:
                    best_sim = sim
        if best_sim >= 0.84:
            return round(best_sim * 0.85, 3)
    return 0.0


@dataclass(frozen=True, slots=True)
class SemanticProductMatch:
    product: dict[str, Any]
    score: float
    match_reason: str
    product_domain: str


@dataclass(frozen=True, slots=True)
class SemanticSearchResult:
    status: str  # "found" | "ambiguous" | "not_found" | "browse_catalog"
    query: str
    matches: tuple[SemanticProductMatch, ...] = ()
    related_other_category: tuple[dict[str, Any], ...] = ()
    ambiguity_note: str | None = None
    not_found_reason: str | None = None
    freshness_summary: dict[str, Any] = field(default_factory=dict)

    @property
    def found(self) -> bool:
        return self.status in {"found", "ambiguous", "browse_catalog"} and bool(self.matches)


def summarize_catalog_freshness(products: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Compute ONE concise freshness summary across a product slice (never repeated per item)."""
    total = len(products)
    if total == 0:
        return {"all_live": False, "any_live": False, "live_count": 0, "unverified_count": 0}
    live_count = sum(1 for p in products if p.get("is_live_stock") is True)
    unverified_count = total - live_count
    statuses = sorted({str(p.get("freshness_status") or "UNKNOWN").upper() for p in products})
    return {
        "all_live": live_count == total,
        "any_live": live_count > 0,
        "live_count": live_count,
        "unverified_count": unverified_count,
        "freshness_statuses": statuses,
    }


def semantic_search_products(
    products: Sequence[dict[str, Any]],
    query: str | None,
    *,
    category: str | None = None,
    limit: int = 10,
) -> SemanticSearchResult:
    """Perform structured semantic product search across a tenant's catalog.

    Returns:
      - `status="browse_catalog"` when query is empty/generic ("all", "catalogue", "produits").
      - `status="found"` with ranked matches when reliable product matches exist.
      - `status="ambiguous"` when a polysemous term (e.g. French "casque" without audio/protection context)
        only matches a different/single sense in the catalog (e.g. audio headphones, no protective helmets).
      - `status="not_found"` with `matches=()` when a specific product search finds NO reliable match
        (never falls back to returning unrelated catalog products!).
    """
    valid_rows = [
        row for row in products
        if isinstance(row, dict)
        and str(row.get("name") or row.get("product_name") or row.get("title") or "").strip()
    ]
    effective_query = " ".join(part.strip() for part in (query or "", category or "") if part and part.strip()).strip()
    ordered_q = _tokenize_ordered(effective_query)
    content_q = _content_tokens(ordered_q)

    # Pure broad catalog browsing (no specific product/category keywords)
    if not effective_query or (len(ordered_q) <= 2 and all(t in _BROWSE_ONLY_QUERIES or t in _STOPWORDS for t in ordered_q)) or not content_q:
        top = valid_rows[: max(1, limit)]
        return SemanticSearchResult(
            status="browse_catalog",
            query=effective_query,
            matches=tuple(
                SemanticProductMatch(
                    product=r,
                    score=1.0,
                    match_reason="catalog_browse",
                    product_domain=_classify_product_domain(*_product_text_blob(r)),
                )
                for r in top
            ),
            freshness_summary=summarize_catalog_freshness(top),
        )

    casque_sense = _classify_query_casque_sense(effective_query)
    heads, modifiers, has_head_modifier_split = _extract_head_and_modifiers(effective_query)

    # Special case: query explicitly asks for broad "accessories" category
    q_stems = {_stem_token(t) for t in content_q}
    asking_accessories_broad = (
        len(content_q) <= 2
        and bool(q_stems & {"accessoire", "accessory", "accesorio", "accesoriu"})
    )

    scored_matches: list[SemanticProductMatch] = []
    other_category_notes: list[dict[str, Any]] = []

    for row in valid_rows:
        name, meta, desc = _product_text_blob(row)
        domain = _classify_product_domain(name, meta, desc)
        name_tokens = set(_tokenize_ordered(name))
        meta_tokens = set(_tokenize_ordered(meta))
        desc_tokens = set(_tokenize_ordered(desc))
        all_tokens = name_tokens | meta_tokens | desc_tokens
        name_stems = {_stem_token(t) for t in name_tokens}
        meta_stems = {_stem_token(t) for t in meta_tokens}
        all_stems = {_stem_token(t) for t in all_tokens}
        folded_name = _fold_ascii(name)
        folded_all = _fold_ascii(f"{name} {meta} {desc}")

        # 1. Polysemy / domain conflict guard for protective helmet vs audio headphones
        if casque_sense == "protective_helmet":
            if domain == "audio_headphones":
                other_category_notes.append({
                    "name": name,
                    "price": row.get("price"),
                    "currency": row.get("currency"),
                    "product_domain": "audio_headphones",
                    "matches_requested_type": False,
                    "mismatch_reason": "audio_headphones_not_protective_helmet",
                })
                continue
            if domain == "snowboard":
                # A snowboard board is NEVER a snowboard helmet!
                continue
            if domain == "protective_helmet":
                scored_matches.append(
                    SemanticProductMatch(
                        product=row,
                        score=1.0,
                        match_reason="protective_helmet_domain_match",
                        product_domain=domain,
                    )
                )
                continue
            # Also check if product explicitly mentions helmet/casco/protection in name/category
            if not (all_tokens & {"helmet", "helmets", "casco", "cascos", "headgear", "casque", "casques"}):
                continue

        elif casque_sense == "audio_headphones":
            if domain == "protective_helmet" or domain == "snowboard":
                continue
            if domain == "audio_headphones":
                scored_matches.append(
                    SemanticProductMatch(
                        product=row,
                        score=1.0,
                        match_reason="audio_headphones_domain_match",
                        product_domain=domain,
                    )
                )
                continue

        elif casque_sense == "ambiguous_casque":
            if domain == "protective_helmet":
                scored_matches.append(
                    SemanticProductMatch(
                        product=row,
                        score=1.0,
                        match_reason="protective_helmet_match",
                        product_domain=domain,
                    )
                )
                continue
            if domain == "audio_headphones":
                scored_matches.append(
                    SemanticProductMatch(
                        product=row,
                        score=0.78,
                        match_reason="audio_headphones_ambiguous_casque",
                        product_domain=domain,
                    )
                )
                continue
            # Ignore snowboards or unrelated items for a "casques" query
            continue

        # 2. Broad accessories category lookup
        if asking_accessories_broad:
            if (
                bool((name_stems | meta_stems) & {"accessoire", "accessory", "accesorio", "accesoriu"})
                or domain in {"protective_helmet", "audio_headphones"}
                or bool((name_stems | meta_stems) & {"gant", "glove", "masque", "lunette", "goggle", "fart", "wax", "fixation", "binding"})
            ):
                scored_matches.append(
                    SemanticProductMatch(
                        product=row,
                        score=0.9,
                        match_reason="accessories_category_match",
                        product_domain=domain,
                    )
                )
            continue

        # 3. General head-noun + modifier scoring (universal across all industries!)
        if has_head_modifier_split and heads:
            head_scores = [
                max(
                    _tokens_match(h, name_tokens, name_stems, folded_name),
                    _tokens_match(h, meta_tokens, meta_stems, _fold_ascii(meta)) * 0.92,
                    _tokens_match(h, all_tokens, all_stems, folded_all) * 0.72,
                )
                for h in heads
            ]
            best_head = max(head_scores) if head_scores else 0.0
            if best_head < 0.65:
                # Head noun NOT matched -> NEVER substitute a product that only matched the modifier!
                continue
            mod_scores = [
                _tokens_match(m, all_tokens, all_stems, folded_all)
                for m in modifiers
            ]
            mod_avg = (sum(mod_scores) / len(mod_scores)) if mod_scores else 0.0
            final_score = round(best_head * 0.75 + mod_avg * 0.25, 3)
            scored_matches.append(
                SemanticProductMatch(
                    product=row,
                    score=final_score,
                    match_reason="head_and_modifier_match" if mod_avg > 0 else "head_noun_match",
                    product_domain=domain,
                )
            )
            continue

        # 4. General multi-token lexical + concept + category + description scoring
        name_hits = [_tokens_match(t, name_tokens, name_stems, folded_name) for t in content_q]
        meta_hits = [_tokens_match(t, meta_tokens, meta_stems, _fold_ascii(meta)) for t in content_q]
        all_hits = [_tokens_match(t, all_tokens, all_stems, folded_all) for t in content_q]

        per_tok_best = [
            max(nh, mh * 0.92, ah * 0.70)
            for nh, mh, ah in zip(name_hits, meta_hits, all_hits)
        ]
        matched_count = sum(1 for s in per_tok_best if s >= 0.65)
        if matched_count == 0:
            continue
        coverage = matched_count / len(content_q)
        avg_score = sum(per_tok_best) / len(per_tok_best)
        # Require strong relevance (especially on multi-word queries) so unrelated items never sneak in
        if len(content_q) >= 2 and coverage < 0.5:
            continue
        if avg_score < 0.55:
            continue
        scored_matches.append(
            SemanticProductMatch(
                product=row,
                score=round(avg_score, 3),
                match_reason="semantic_lexical_match",
                product_domain=domain,
            )
        )

    scored_matches.sort(key=lambda m: m.score, reverse=True)
    top_matches = tuple(scored_matches[: max(1, limit)])
    freshness = summarize_catalog_freshness([m.product for m in top_matches])

    if not top_matches:
        reason = "no_matching_product_in_catalog"
        if casque_sense == "protective_helmet":
            reason = "no_protective_helmet_in_catalog"
        return SemanticSearchResult(
            status="not_found",
            query=effective_query,
            matches=(),
            related_other_category=tuple(other_category_notes[:3]),
            not_found_reason=reason,
            freshness_summary=summarize_catalog_freshness(valid_rows),
        )

    # Check if an ambiguous "casque" query only matched audio headphones (no protective helmets)
    if casque_sense == "ambiguous_casque":
        domains_found = {m.product_domain for m in top_matches}
        if domains_found == {"audio_headphones"}:
            names_str = ", ".join(str(m.product.get("name") or "") for m in top_matches[:2])
            return SemanticSearchResult(
                status="ambiguous",
                query=effective_query,
                matches=top_matches,
                ambiguity_note=(
                    f"In French, 'casque' can mean audio headphones or a protective helmet. "
                    f"The catalog only has audio headphones ({names_str}) and no protective helmets."
                ),
                freshness_summary=freshness,
            )

    return SemanticSearchResult(
        status="found",
        query=effective_query,
        matches=top_matches,
        related_other_category=tuple(other_category_notes[:3]),
        freshness_summary=freshness,
    )


__all__ = [
    "SemanticProductMatch",
    "SemanticSearchResult",
    "semantic_search_products",
    "summarize_catalog_freshness",
]
