"""Keyword translation service for multilingual procurement search.

Expands user keywords (FR/NL/EN) to include translations in the other
two languages, so a search for "nettoyage" also matches notices titled
"schoonmaak" (NL) or "cleaning services" (EN).

Architecture:
  - Static dictionary of ~300 procurement concept groups (FR / NL / EN)
  - Normalised lookup index built once at import time
  - expand_keywords()  → given a keyword, returns {fr, nl, en} set
  - expand_search_terms() → given a query string, returns expanded tsquery-ready string

The dictionary covers the most common CPV domains encountered in
Belgian (BOSA) and EU (TED) procurement notices.
"""
import re
from typing import Optional

# ---------------------------------------------------------------------------
# Procurement concept dictionary — (FR, NL, EN) tuples
# Each tuple represents a single concept in three languages.
# Multiple words per language are separated within the string.
# ---------------------------------------------------------------------------

_CONCEPTS: list[tuple[str, str, str]] = [
    # ── Construction & travaux ──
    ("construction", "bouw", "construction"),
    ("travaux", "werken", "works"),
    ("travaux de construction", "bouwwerken", "construction works"),
    ("bâtiment", "gebouw", "building"),
    ("bâtiments", "gebouwen", "buildings"),
    ("rénovation", "renovatie", "renovation"),
    ("démolition", "sloop", "demolition"),
    ("fondations", "funderingen", "foundations"),
    ("gros œuvre", "ruwbouw", "structural works"),
    ("toiture", "dakwerken", "roofing"),
    ("charpente", "dakstructuur", "roof structure"),
    ("façade", "gevel", "facade"),
    ("isolation", "isolatie", "insulation"),
    ("étanchéité", "waterdichting", "waterproofing"),
    ("maçonnerie", "metselwerk", "masonry"),
    ("béton", "beton", "concrete"),
    ("coffrage", "bekisting", "formwork"),
    ("ferraillage", "wapening", "reinforcement"),
    ("terrassement", "grondwerken", "earthworks"),
    ("excavation", "uitgraving", "excavation"),
    ("voirie", "wegenis", "roadworks"),
    ("revêtement routier", "wegverharding", "road surfacing"),
    ("asphalte", "asfalt", "asphalt"),
    ("pavage", "bestrating", "paving"),
    ("trottoir", "voetpad", "pavement"),
    ("pont", "brug", "bridge"),
    ("tunnel", "tunnel", "tunnel"),
    ("génie civil", "burgerlijke bouwkunde", "civil engineering"),
    ("canalisation", "riolering", "sewerage"),
    ("assainissement", "sanering", "remediation"),
    ("drainage", "drainage", "drainage"),
    ("forage", "boring", "drilling"),

    # ── Espaces verts & environnement ──
    ("espaces verts", "groenaanleg", "green areas"),
    ("entretien espaces verts", "groenonderhoud", "green maintenance"),
    ("jardinage", "tuinieren", "gardening"),
    ("plantation", "beplanting", "planting"),
    ("élagage", "snoeiwerken", "pruning"),
    ("tonte", "maaien", "mowing"),
    ("arbre", "boom", "tree"),
    ("arbres", "bomen", "trees"),
    ("parc", "park", "park"),
    ("paysagiste", "landschapsarchitect", "landscape architect"),
    ("aménagement paysager", "landschapsinrichting", "landscaping"),
    ("environnement", "milieu", "environment"),
    ("déchets", "afval", "waste"),
    ("collecte de déchets", "afvalinzameling", "waste collection"),
    ("recyclage", "recyclage", "recycling"),
    ("traitement des déchets", "afvalverwerking", "waste treatment"),
    ("dépollution", "bodemsanering", "soil remediation"),
    ("eau", "water", "water"),
    ("épuration", "waterzuivering", "water treatment"),
    ("station d'épuration", "waterzuiveringsstation", "wastewater treatment plant"),

    # ── Nettoyage & entretien ──
    ("nettoyage", "schoonmaak", "cleaning"),
    ("nettoyage de bâtiments", "gebouwenreiniging", "building cleaning"),
    ("nettoyage industriel", "industriële reiniging", "industrial cleaning"),
    ("entretien", "onderhoud", "maintenance"),
    ("maintenance", "onderhoud", "maintenance"),
    ("réparation", "herstelling", "repair"),
    ("réparations", "herstellingen", "repairs"),

    # ── Informatique & digital ──
    ("informatique", "informatica", "information technology"),
    ("logiciel", "software", "software"),
    ("matériel informatique", "hardware", "hardware"),
    ("développement logiciel", "softwareontwikkeling", "software development"),
    ("système d'information", "informatiesysteem", "information system"),
    ("réseau", "netwerk", "network"),
    ("infrastructure informatique", "IT-infrastructuur", "IT infrastructure"),
    ("cybersécurité", "cyberbeveiliging", "cybersecurity"),
    ("cloud", "cloud", "cloud"),
    ("hébergement", "hosting", "hosting"),
    ("serveur", "server", "server"),
    ("base de données", "databank", "database"),
    ("site web", "website", "website"),
    ("application mobile", "mobiele applicatie", "mobile application"),
    ("intelligence artificielle", "kunstmatige intelligentie", "artificial intelligence"),
    ("numérisation", "digitalisering", "digitization"),
    ("télécommunications", "telecommunicatie", "telecommunications"),

    # ── Consulting & services intellectuels ──
    ("conseil", "advies", "consulting"),
    ("consultance", "consultancy", "consultancy"),
    ("étude", "studie", "study"),
    ("études", "studies", "studies"),
    ("audit", "audit", "audit"),
    ("expertise", "expertise", "expertise"),
    ("formation", "opleiding", "training"),
    ("coaching", "coaching", "coaching"),
    ("recherche", "onderzoek", "research"),
    ("analyse", "analyse", "analysis"),
    ("stratégie", "strategie", "strategy"),
    ("gestion de projet", "projectbeheer", "project management"),

    # ── Architecture & ingénierie ──
    ("architecture", "architectuur", "architecture"),
    ("architecte", "architect", "architect"),
    ("ingénierie", "ingenieursdiensten", "engineering"),
    ("ingénieur", "ingenieur", "engineer"),
    ("bureau d'études", "studiebureau", "design office"),
    ("conception", "ontwerp", "design"),
    ("urbanisme", "stedenbouw", "urban planning"),
    ("aménagement du territoire", "ruimtelijke ordening", "spatial planning"),
    ("géomètre", "landmeter", "surveyor"),
    ("topographie", "topografie", "topography"),
    ("contrôle technique", "technische controle", "technical inspection"),

    # ── Énergie ──
    ("énergie", "energie", "energy"),
    ("électricité", "elektriciteit", "electricity"),
    ("gaz", "gas", "gas"),
    ("chauffage", "verwarming", "heating"),
    ("climatisation", "airconditioning", "air conditioning"),
    ("ventilation", "ventilatie", "ventilation"),
    ("HVAC", "HVAC", "HVAC"),
    ("énergie solaire", "zonne-energie", "solar energy"),
    ("panneaux solaires", "zonnepanelen", "solar panels"),
    ("éolien", "windenergie", "wind energy"),
    ("éclairage", "verlichting", "lighting"),
    ("éclairage public", "openbare verlichting", "public lighting"),
    ("installation électrique", "elektrische installatie", "electrical installation"),

    # ── Transport & mobilité ──
    ("transport", "transport", "transport"),
    ("véhicule", "voertuig", "vehicle"),
    ("véhicules", "voertuigen", "vehicles"),
    ("autobus", "autobus", "bus"),
    ("bus", "bus", "bus"),
    ("tramway", "tram", "tram"),
    ("chemin de fer", "spoorweg", "railway"),
    ("rail", "spoor", "rail"),
    ("voie ferrée", "spoorweg", "railway track"),
    ("signalisation", "signalisatie", "signalling"),
    ("signalisation routière", "verkeerssignalisatie", "road signalling"),
    ("stationnement", "parkeren", "parking"),
    ("mobilité", "mobiliteit", "mobility"),
    ("piste cyclable", "fietspad", "cycle path"),
    ("logistique", "logistiek", "logistics"),

    # ── Santé & social ──
    ("santé", "gezondheid", "health"),
    ("médical", "medisch", "medical"),
    ("hôpital", "ziekenhuis", "hospital"),
    ("soins", "zorg", "care"),
    ("soins de santé", "gezondheidszorg", "healthcare"),
    ("équipement médical", "medische apparatuur", "medical equipment"),
    ("pharmacie", "apotheek", "pharmacy"),
    ("médicament", "geneesmiddel", "medicine"),
    ("médicaments", "geneesmiddelen", "medicines"),
    ("laboratoire", "laboratorium", "laboratory"),
    ("ambulance", "ambulance", "ambulance"),
    ("aide sociale", "sociale bijstand", "social assistance"),

    # ── Alimentation & restauration ──
    ("alimentation", "voeding", "food"),
    ("restauration", "catering", "catering"),
    ("repas", "maaltijden", "meals"),
    ("cantine", "kantine", "canteen"),
    ("boissons", "dranken", "beverages"),
    ("produits alimentaires", "voedingsmiddelen", "food products"),
    ("produits laitiers", "zuivelproducten", "dairy products"),
    ("viande", "vlees", "meat"),
    ("fruits", "fruit", "fruit"),
    ("légumes", "groenten", "vegetables"),

    # ── Sécurité ──
    ("sécurité", "beveiliging", "security"),
    ("gardiennage", "bewaking", "guarding"),
    ("surveillance", "bewaking", "surveillance"),
    ("alarme", "alarm", "alarm"),
    ("incendie", "brand", "fire"),
    ("protection incendie", "brandbeveiliging", "fire protection"),
    ("détection incendie", "branddetectie", "fire detection"),
    ("caméra", "camera", "camera"),
    ("vidéosurveillance", "videobewaking", "video surveillance"),
    ("contrôle d'accès", "toegangscontrole", "access control"),
    ("sécurité routière", "verkeersveiligheid", "road safety"),
    ("défense", "defensie", "defence"),

    # ── Mobilier & équipement ──
    ("mobilier", "meubilair", "furniture"),
    ("mobilier de bureau", "kantoormeubelen", "office furniture"),
    ("équipement", "uitrusting", "equipment"),
    ("matériel", "materiaal", "material"),
    ("fournitures", "leveringen", "supplies"),
    ("fournitures de bureau", "kantoorbenodigdheden", "office supplies"),
    ("papeterie", "kantoorbenodigdheden", "stationery"),
    ("vêtements", "kleding", "clothing"),
    ("uniformes", "uniformen", "uniforms"),
    ("vêtements de travail", "werkkleding", "workwear"),
    ("textile", "textiel", "textile"),

    # ── Finance & assurance ──
    ("assurance", "verzekering", "insurance"),
    ("assurances", "verzekeringen", "insurances"),
    ("banque", "bank", "bank"),
    ("services financiers", "financiële diensten", "financial services"),
    ("comptabilité", "boekhouding", "accounting"),
    ("fiscalité", "fiscaliteit", "taxation"),

    # ── Juridique ──
    ("juridique", "juridisch", "legal"),
    ("avocat", "advocaat", "lawyer"),
    ("notaire", "notaris", "notary"),
    ("marché public", "overheidsopdracht", "public procurement"),
    ("marchés publics", "overheidsopdrachten", "public procurement"),
    ("contrat", "contract", "contract"),
    ("réglementation", "regelgeving", "regulation"),

    # ── Communication & impression ──
    ("communication", "communicatie", "communication"),
    ("impression", "drukwerk", "printing"),
    ("imprimerie", "drukkerij", "printing house"),
    ("publication", "publicatie", "publication"),
    ("graphisme", "grafisch ontwerp", "graphic design"),
    ("traduction", "vertaling", "translation"),
    ("interprétation", "tolkdiensten", "interpretation"),
    ("publicité", "reclame", "advertising"),
    ("événement", "evenement", "event"),
    ("événements", "evenementen", "events"),

    # ── Plomberie & installations ──
    ("plomberie", "sanitair", "plumbing"),
    ("sanitaire", "sanitair", "sanitary"),
    ("tuyauterie", "leidingwerk", "piping"),
    ("ascenseur", "lift", "elevator"),
    ("ascenseurs", "liften", "elevators"),

    # ── Peinture & finitions ──
    ("peinture", "schilderwerk", "painting"),
    ("revêtement de sol", "vloerbedekking", "floor covering"),
    ("carrelage", "betegeling", "tiling"),
    ("menuiserie", "schrijnwerk", "joinery"),
    ("vitrerie", "beglazing", "glazing"),
    ("serrurerie", "slotenmakerij", "locksmithing"),
    ("plâtrerie", "pleisterwerk", "plastering"),
    ("faux plafond", "verlaagd plafond", "suspended ceiling"),

    # ── Immobilier ──
    ("immobilier", "vastgoed", "real estate"),
    ("location", "verhuur", "rental"),
    ("bail", "huurovereenkomst", "lease"),
    ("gestion immobilière", "vastgoedbeheer", "property management"),
    ("déménagement", "verhuizing", "moving"),

    # ── Éducation ──
    ("enseignement", "onderwijs", "education"),
    ("école", "school", "school"),
    ("université", "universiteit", "university"),
    ("bibliothèque", "bibliotheek", "library"),
    ("formation professionnelle", "beroepsopleiding", "vocational training"),
    ("sport", "sport", "sport"),
    ("culture", "cultuur", "culture"),

    # ── Divers ──
    ("service", "dienst", "service"),
    ("services", "diensten", "services"),
    ("fourniture", "levering", "supply"),
    ("livraison", "levering", "delivery"),
    ("achat", "aankoop", "purchase"),
    ("location", "huur", "rental"),
    ("accord-cadre", "raamovereenkomst", "framework agreement"),
    ("marché", "opdracht", "contract"),
    ("lot", "perceel", "lot"),
    ("concession", "concessie", "concession"),
    ("appel d'offres", "aanbesteding", "tender"),
    ("soumission", "inschrijving", "submission"),
    ("cahier des charges", "bestek", "specifications"),
    ("procédure ouverte", "open procedure", "open procedure"),
    ("procédure négociée", "onderhandelingsprocedure", "negotiated procedure"),
    ("procédure restreinte", "beperkte procedure", "restricted procedure"),
    ("dialogue compétitif", "concurrentiegerichte dialoog", "competitive dialogue"),
]


# ---------------------------------------------------------------------------
# Build normalised lookup index
# ---------------------------------------------------------------------------

def _normalise(s: str) -> str:
    """Lowercase, strip accents (basic), collapse whitespace."""
    s = s.lower().strip()
    # Basic accent folding for lookup (not exhaustive, but covers FR/NL)
    for src, dst in [
        ("é", "e"), ("è", "e"), ("ê", "e"), ("ë", "e"),
        ("à", "a"), ("â", "a"), ("ä", "a"),
        ("ù", "u"), ("û", "u"), ("ü", "u"),
        ("ô", "o"), ("ö", "o"),
        ("î", "i"), ("ï", "i"),
        ("ç", "c"), ("ñ", "n"),
    ]:
        s = s.replace(src, dst)
    s = re.sub(r"\s+", " ", s)
    return s


# Index: normalised_term → set of concept indices
_TERM_INDEX: dict[str, set[int]] = {}

for _idx, (_fr, _nl, _en) in enumerate(_CONCEPTS):
    for _term in (_fr, _nl, _en):
        _key = _normalise(_term)
        if _key:
            _TERM_INDEX.setdefault(_key, set()).add(_idx)


# ---------------------------------------------------------------------------
# Public API — Static (instant, no DB)
# ---------------------------------------------------------------------------

def translate_keyword(keyword: str) -> dict[str, list[str]]:
    """Look up a keyword in the STATIC dictionary only.

    Returns:
        {"original": "nettoyage", "fr": [...], "nl": [...], "en": [...], "found": True}
        If not found: {"original": "xyz", "fr": [], "nl": [], "en": [], "found": False}
    """
    key = _normalise(keyword)
    if not key:
        return {"original": keyword, "fr": [], "nl": [], "en": [], "found": False}

    # Exact match
    concept_ids = _TERM_INDEX.get(key, set())

    # If no exact match, try substring match (for compound terms)
    if not concept_ids:
        for indexed_key, ids in _TERM_INDEX.items():
            if key in indexed_key or indexed_key in key:
                concept_ids |= ids
        # Limit to best 3 matches to avoid noise
        if len(concept_ids) > 3:
            concept_ids = set(list(concept_ids)[:3])

    if not concept_ids:
        return {"original": keyword, "fr": [], "nl": [], "en": [], "found": False}

    fr_set: set[str] = set()
    nl_set: set[str] = set()
    en_set: set[str] = set()

    for idx in concept_ids:
        fr, nl, en = _CONCEPTS[idx]
        fr_set.add(fr)
        nl_set.add(nl)
        en_set.add(en)

    return {
        "original": keyword,
        "fr": sorted(fr_set),
        "nl": sorted(nl_set),
        "en": sorted(en_set),
        "found": True,
        "source": "static",
    }


# ---------------------------------------------------------------------------
# DB Cache layer
# ---------------------------------------------------------------------------

def _get_cached_translation(keyword: str, db: "Session") -> Optional[dict]:
    """Check the translation_cache table for a previously AI-translated keyword."""
    import json
    from app.models.translation_cache import TranslationCache

    key = _normalise(keyword)
    row = db.query(TranslationCache).filter(
        TranslationCache.keyword_normalised == key
    ).first()

    if not row:
        return None

    return {
        "original": keyword,
        "fr": json.loads(row.fr) if row.fr else [],
        "nl": json.loads(row.nl) if row.nl else [],
        "en": json.loads(row.en) if row.en else [],
        "found": True,
        "source": row.source,
    }


def _save_cached_translation(
    keyword: str, fr: list[str], nl: list[str], en: list[str],
    db: "Session", source: str = "ai",
) -> None:
    """Save an AI-generated translation to the cache."""
    import json
    from app.models.translation_cache import TranslationCache

    key = _normalise(keyword)
    existing = db.query(TranslationCache).filter(
        TranslationCache.keyword_normalised == key
    ).first()

    if existing:
        existing.fr = json.dumps(fr, ensure_ascii=False)
        existing.nl = json.dumps(nl, ensure_ascii=False)
        existing.en = json.dumps(en, ensure_ascii=False)
        existing.source = source
    else:
        row = TranslationCache(
            keyword_normalised=key,
            keyword_original=keyword,
            fr=json.dumps(fr, ensure_ascii=False),
            nl=json.dumps(nl, ensure_ascii=False),
            en=json.dumps(en, ensure_ascii=False),
            source=source,
        )
        db.add(row)

    try:
        db.commit()
    except Exception:
        db.rollback()


# ---------------------------------------------------------------------------
# AI Translation via Claude Haiku
# ---------------------------------------------------------------------------

import logging
logger = logging.getLogger(__name__)

_AI_PROMPT = """You are a multilingual procurement terminology translator.
Given a keyword used in public procurement (marchés publics / overheidsopdrachten / public procurement),
provide accurate translations in French, Dutch, and English.

Return ONLY a JSON object with this exact structure (no markdown, no explanation):
{{"fr": ["term1", "term2"], "nl": ["term1", "term2"], "en": ["term1", "term2"]}}

Rules:
- Include 1-3 translations per language (the keyword itself + close synonyms used in procurement)
- Include the original keyword in the appropriate language list
- Focus on terms actually used in procurement notice titles and descriptions
- If the keyword is too generic or not procurement-related, still translate it literally

Keyword: "{keyword}"
"""


async def _call_ai_translate(keyword: str) -> Optional[dict[str, list[str]]]:
    """Call Claude Haiku to translate a procurement keyword."""
    import json
    import httpx
    from app.core.config import settings

    if not settings.anthropic_api_key:
        logger.warning("ANTHROPIC_API_KEY not set — cannot AI-translate")
        return None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": settings.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 200,
                    "messages": [
                        {"role": "user", "content": _AI_PROMPT.format(keyword=keyword)}
                    ],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            text = data["content"][0]["text"].strip()
            # Strip markdown fences if present
            text = re.sub(r"^```json\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
            parsed = json.loads(text)

            fr = parsed.get("fr", [])
            nl = parsed.get("nl", [])
            en = parsed.get("en", [])

            if not isinstance(fr, list) or not isinstance(nl, list) or not isinstance(en, list):
                logger.warning("AI translation returned invalid structure")
                return None

            return {"fr": fr, "nl": nl, "en": en}

    except Exception as e:
        logger.warning(f"AI translation failed for '{keyword}': {e}")
        return None


async def translate_keyword_smart(
    keyword: str, db: Optional["Session"] = None,
) -> dict:
    """Smart translation: static → DB cache → AI fallback.

    This is the full pipeline used by the API endpoint.
    For search/watchlist (sync paths), use translate_keyword() instead.
    """
    # 1. Static dictionary (instant)
    result = translate_keyword(keyword)
    if result["found"]:
        return result

    # 2. DB cache
    if db:
        cached = _get_cached_translation(keyword, db)
        if cached:
            return cached

    # 3. AI fallback
    ai_result = await _call_ai_translate(keyword)
    if ai_result:
        result = {
            "original": keyword,
            "fr": ai_result["fr"],
            "nl": ai_result["nl"],
            "en": ai_result["en"],
            "found": True,
            "source": "ai",
        }
        # Save to cache
        if db:
            _save_cached_translation(
                keyword, ai_result["fr"], ai_result["nl"], ai_result["en"], db
            )
        return result

    # 4. Nothing found
    return {"original": keyword, "fr": [], "nl": [], "en": [], "found": False, "source": "none"}


def expand_keyword(keyword: str) -> list[str]:
    """Return all translations for a keyword as a flat list (deduplicated).

    Example: expand_keyword("nettoyage") → ["nettoyage", "schoonmaak", "cleaning"]
    """
    result = translate_keyword(keyword)
    if not result["found"]:
        return [keyword]  # Return original if no translation found

    all_terms: set[str] = set()
    all_terms.add(keyword)  # Always include the original
    for lang in ("fr", "nl", "en"):
        for term in result[lang]:
            all_terms.add(term)

    return sorted(all_terms)


def expand_keywords_list(keywords: list[str]) -> list[str]:
    """Expand a list of keywords with translations.

    Preserves original keywords and adds translations.
    Deduplicates the result.

    Example:
        ["nettoyage", "bâtiment"]
        → ["nettoyage", "schoonmaak", "cleaning",
           "bâtiment", "gebouw", "building"]
    """
    seen: set[str] = set()
    result: list[str] = []

    for kw in keywords:
        expanded = expand_keyword(kw)
        for term in expanded:
            lower = term.lower()
            if lower not in seen:
                seen.add(lower)
                result.append(term)

    return result


def expand_tsquery_terms(raw_query: str) -> str:
    """Expand a user search query for PostgreSQL tsquery.

    Each word/term gets expanded with OR'd translations, while
    preserving AND logic between different concepts.

    Example:
        "nettoyage bâtiment"
        → "(nettoyage | schoonmaak | cleaning) & (bâtiment | gebouw | building)"

    Handles OR operator:
        "nettoyage OR entretien"
        → "(nettoyage | schoonmaak | cleaning) | (entretien | onderhoud | maintenance)"
    """
    raw_query = raw_query.strip()
    if not raw_query:
        return ""

    # Split on OR to preserve user's explicit OR logic
    or_groups = re.split(r"\bOR\b", raw_query, flags=re.IGNORECASE)

    expanded_groups: list[str] = []

    for group in or_groups:
        tokens = group.strip().split()
        if not tokens:
            continue

        expanded_tokens: list[str] = []
        for token in tokens:
            clean = re.sub(r"[^\w\-*]", "", token, flags=re.UNICODE)
            if not clean:
                continue

            # Remove trailing :* for lookup, we'll re-add it
            lookup = clean.rstrip("*").rstrip(":")

            translations = expand_keyword(lookup)
            if len(translations) > 1:
                # Multiple translations → OR group
                parts = [f"{t}:*" for t in translations]
                expanded_tokens.append(f"({' | '.join(parts)})")
            else:
                expanded_tokens.append(f"{clean}:*")

        if expanded_tokens:
            expanded_groups.append(" & ".join(expanded_tokens))

    if not expanded_groups:
        return ""

    if len(expanded_groups) == 1:
        return expanded_groups[0]

    return " | ".join(f"({g})" for g in expanded_groups)


def get_dictionary_stats() -> dict:
    """Return dictionary statistics."""
    return {
        "total_concepts": len(_CONCEPTS),
        "total_indexed_terms": len(_TERM_INDEX),
        "languages": ["fr", "nl", "en"],
    }
