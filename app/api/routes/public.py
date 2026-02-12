"""
Public endpoints (no auth required).
Website keyword analysis for lead generation.
"""
import logging
import re
from collections import Counter
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.db.session import get_db as _get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/public", tags=["public"])

# ── Stop words: language + generic web/business terms ─────────────

_LANG_STOPS = frozenset(
    "le la les de des du un une et en est il elle on nous vous ils elles "
    "ce cette ces son sa ses leur leurs mon ma mes ton ta tes notre nos votre vos "
    "que qui quoi dont où au aux par pour dans avec sans sur sous entre "
    "ne pas plus aussi très tout tous toute toutes même autre autres "
    "je tu il nous vous ils se me te lui eux y être avoir faire "
    "été fait sont ont peut peuvent avons sommes êtes sera seront "
    "mais ou car ni donc or si bien comme plus moins ici là quand comment "
    "après avant pendant depuis lors encore déjà aussi ainsi alors ensuite "
    "chez vers contre parmi durant malgré sauf selon outre "
    "non oui peu beaucoup trop assez chaque quelque plusieurs certain "
    "aucun nul tel quel lequel laquelle lesquels lesquelles "
    "ceci cela celui celle ceux celles "
    "the and for with from this that are was were has have been will "
    "not but all can had her his they them these those "
    "about into through during before after above below between "
    "www http https com org net html php asp jsp "
    "de het een van in is dat op te zijn was met voor niet hij zij ze "
    "er aan als ook door maar worden nog wel bij haar die deze "
    "geen alle uit dan nu kan tot meer om over naar wij hen wat werd mijn uw".split()
)

# Generic business/web words NOT useful for procurement matching
_BIZ_STOPS = frozenset(
    # Business generics
    "entreprise société compagnie societe sarl sprl srl bvba "
    "client clients clientèle satisfaction qualité expérience "
    "professionnel professionnels professionnelle "
    "spécialisé spécialisée spécialisés spécialiste "
    "années année ans expert expertise "
    "devis gratuit demande demander appeler téléphone email mail "
    "équipe team partenaire partenaires collaborateur "
    # Web/page generics
    "accueil home page bienvenue welcome contact contactez "
    "services service produits produit solutions solution "
    "site web internet ligne online numéro horaires "
    "cookies politique confidentialité mentions légales conditions "
    "droits réservés copyright plan menu navigation "
    "top amp lire suite voir savoir découvrir cliquez retour "
    "suivant précédent fermer ouvrir charger afficher "
    "nouveau nouvelle nouveaux nouvelles actualité actualités "
    "plus infos information informations détails détail "
    # Location generics (keep specific cities but remove vague ones)
    "région belgique belgium bruxelles france luxembourg "
    "wallonie flandre europe situé située adresse siège bureau "
    "province ville commune pays quartier secteur zone local locale "
    # Calendar
    "lundi mardi mercredi jeudi vendredi samedi dimanche "
    "janvier février mars avril mai juin juillet août septembre octobre novembre décembre "
    # HTML entity fragments (artifacts from bad decoding)
    "eacute egrave agrave ccedil ocirc ucirc iuml euml acirc nbsp "
    "rsquo lsquo rdquo ldquo ndash mdash hellip "
    # Generic adjectives/nouns useless for procurement
    "grand grande grands petit petite petits beau belle bon bonne "
    "meilleur meilleure premier première dernier dernière "
    "réalisation réalisations projet projets travail travaux "
    "disponible disponibles possible possibles "
    "différent différents différente type types "
    "besoin besoins offre offres prix tarif tarifs "
    "création réalisation photo photos image images galerie portfolio "
    "société sociétés groupe entreprises "
    "vente achat commande magasin boutique "
    "culture culturel culturelle nature naturel naturelle "
    "famille familial familiale particulier particuliers "
    "conseil conseils accompagnement aide suivi gestion "
    "mise place point jour oeuvre ".split()
)

# Common first names and proper nouns that appear on company sites
_NAME_STOPS = frozenset(
    "jean pierre paul jacques michel philippe andré bernard louis "
    "marc daniel françois patrick claude robert christian alain "
    "thierry laurent nicolas dominique vincent olivier didier "
    "marie anne catherine isabelle christine nathalie sophie "
    "jacky jackie serge eric henri yves pascal gérard stéphane "
    "david thomas martin dupont dumont lambert leroy janssen "
    "pirot peeters maes claes willems mertens".split()
)

STOP_WORDS = _LANG_STOPS | _BIZ_STOPS | _NAME_STOPS

# ── Procurement-relevant keyword boosters ─────────────────────────
# Words that signal real procurement relevance get extra weight

PROCUREMENT_BOOSTERS = frozenset(
    # Construction & BTP
    "construction bâtiment chantier gros-œuvre béton coffrage ferraillage "
    "maçonnerie fondation terrassement excavation démolition désamiantage "
    "toiture couverture étanchéité charpente ardoise zinc bardage "
    "plomberie sanitaire tuyauterie canalisation chauffage hvac climatisation "
    "ventilation thermique pompe chaudière radiateur "
    "électricité câblage éclairage tableau domotique courant "
    "peinture enduit décoration revêtement tapisserie "
    "menuiserie ébénisterie parquet plancher boiserie "
    "carrelage dallage pavage sol faïence mosaïque "
    "isolation acoustique façade ite rénovation réhabilitation "
    "ascenseur élévateur monte-charge escalator "
    "voirie route asphalt enrobé chaussée trottoir piste cyclable "
    "signalisation marquage égouttage assainissement "
    # Green spaces
    "espaces-verts jardinage paysagiste plantation élagage "
    "fauchage tonte pelouse gazon haie taille abattage débroussaillage "
    "broyage gyrobroyage rognage souche arbre "
    "aménagement paysager parc jardin arrosage "
    "pépinière clôture terrassement pavage engazonnement "
    "espaces verts parcs jardins aménagements extérieur extérieurs "
    "abords végétalisation semis gazon engrais phytosanitaire "
    # Cleaning & maintenance
    "nettoyage propreté ménage hygiène désinfection "
    "entretien maintenance dépannage réparation "
    # IT & digital
    "informatique logiciel développement software application "
    "infrastructure réseau serveur cloud hébergement cybersécurité "
    "erp crm saas intégration migration données "
    # Security
    "sécurité gardiennage surveillance alarme vidéo caméra "
    "contrôle accès incendie extincteur détection "
    # Transport & logistics
    "transport logistique livraison déménagement fret camion "
    "collecte déchets recyclage tri conteneur benne "
    # Food & catering
    "restauration catering repas cuisine traiteur cantine "
    # Professional services
    "architecture architecte urbanisme conception "
    "ingénierie ingénieur bureau études géotechnique topographie "
    "formation enseignement cours éducation coaching "
    "comptabilité audit fiscal fiduciaire "
    "juridique avocat droit notaire conseil "
    "communication marketing publicité événement "
    "imprimerie impression print édition graphisme "
    "traduction interprétation traducteur "
    # Supplies
    "fourniture mobilier meuble bureau équipement matériel "
    "véhicule automobile flotte leasing "
    "textile vêtement uniforme epi protection "
    "médical santé soins paramédical ambulance "
    "pharma pharmaceutique médicament laboratoire "
    "alimentaire denrée boisson eau potable".split()
)

# ── CPV keyword mapping ───────────────────────────────────────────

CPV_SUGGESTIONS = [
    (["construction", "bâtiment", "travaux", "chantier", "gros-œuvre", "génie civil", "béton", "maçonnerie"], "45000000", "Travaux de construction"),
    (["plomberie", "sanitaire", "tuyauterie", "chauffage", "hvac", "climatisation", "ventilation", "chaudière"], "45330000", "Travaux de plomberie / HVAC"),
    (["électricité", "électrique", "câblage", "éclairage", "domotique", "courant"], "45310000", "Travaux d'électricité"),
    (["peinture", "revêtement", "décoration", "enduit", "tapisserie"], "45440000", "Travaux de peinture"),
    (["toiture", "couverture", "étanchéité", "toit", "charpente", "ardoise", "zinc"], "45261000", "Travaux de toiture"),
    (["voirie", "route", "asphalt", "enrobé", "chaussée", "trottoir", "signalisation", "marquage"], "45233000", "Travaux de voirie"),
    (["espaces verts", "jardinage", "paysagiste", "plantation", "élagage", "fauchage", "tonte", "gyrobroyage", "broyage", "rognage", "taille", "haie", "débroussaillage", "arbre"], "77310000", "Services de plantation et d'entretien d'espaces verts"),
    (["nettoyage", "propreté", "entretien", "ménage", "hygiène", "désinfection"], "90910000", "Services de nettoyage"),
    (["informatique", "logiciel", "développement", "software", "application", "web", "digital", "saas", "erp", "crm"], "72000000", "Services informatiques"),
    (["sécurité", "gardiennage", "surveillance", "alarme", "vidéo", "caméra"], "79710000", "Services de sécurité"),
    (["transport", "logistique", "livraison", "déménagement", "fret", "camion"], "60000000", "Services de transport"),
    (["mobilier", "meuble", "bureau", "équipement", "fourniture"], "39100000", "Mobilier"),
    (["restauration", "catering", "repas", "cuisine", "traiteur", "cantine"], "55520000", "Services de restauration"),
    (["architecture", "architecte", "conception", "urbanisme"], "71200000", "Services d'architecture"),
    (["ingénierie", "ingénieur", "étude", "bureau études", "géotechnique", "topographie"], "71300000", "Services d'ingénierie"),
    (["formation", "enseignement", "cours", "éducation", "coaching"], "80500000", "Services de formation"),
    (["médical", "santé", "soins", "paramédical", "ambulance"], "85100000", "Services de santé"),
    (["imprimerie", "impression", "print", "édition", "graphisme"], "79800000", "Services d'impression"),
    (["communication", "marketing", "publicité", "événement"], "79340000", "Services de publicité"),
    (["comptabilité", "audit", "fiscal", "fiduciaire"], "79210000", "Services comptables"),
    (["juridique", "avocat", "droit", "conseil juridique", "notaire"], "79100000", "Services juridiques"),
    (["assurance", "courtage", "police", "sinistre"], "66510000", "Services d'assurance"),
    (["télécom", "réseau", "fibre", "câble", "internet"], "64200000", "Services de télécommunications"),
    (["menuiserie", "bois", "ébénisterie", "parquet", "plancher"], "45420000", "Travaux de menuiserie"),
    (["carrelage", "sol", "revêtement sol", "pavage", "dallage", "faïence"], "45431000", "Travaux de carrelage"),
    (["ascenseur", "élévateur", "escalator", "monte-charge"], "45313000", "Installation d'ascenseurs"),
    (["démolition", "désamiantage", "déconstruction", "terrassement", "excavation"], "45110000", "Travaux de démolition / terrassement"),
    (["isolation", "thermique", "acoustique", "façade", "bardage", "ite"], "45320000", "Travaux d'isolation"),
    (["déchet", "déchets", "collecte", "recyclage", "tri", "conteneur", "benne"], "90500000", "Services liés aux déchets"),
    (["véhicule", "automobile", "flotte", "leasing"], "34100000", "Véhicules à moteur"),
    (["textile", "vêtement", "uniforme", "epi", "protection"], "18100000", "Vêtements professionnels"),
]


# ── Request / Response models ─────────────────────────────────────

class AnalyzeRequest(BaseModel):
    url: str

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith(("http://", "https://")):
            v = "https://" + v
        parsed = urlparse(v)
        if not parsed.netloc or "." not in parsed.netloc:
            raise ValueError("URL invalide")
        host = parsed.hostname or ""
        if host in ("localhost", "127.0.0.1", "0.0.0.0") or host.startswith(("192.168.", "10.", "172.")):
            raise ValueError("URL locale non autorisée")
        return v


class AnalyzeResponse(BaseModel):
    url: str
    company_name: str | None = None
    meta_description: str | None = None
    keywords: list[str]
    suggested_cpv: list[dict[str, str]]
    raw_word_count: int = 0


# ── HTML text extraction ──────────────────────────────────────────

def _strip_tags(html: str) -> str:
    html = re.sub(r"<(script|style|noscript|svg|path)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)
    html = re.sub(r"<[^>]+>", " ", html)
    for entity, char in [("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'),
                          ("&#39;", "'"), ("&apos;", "'"), ("&nbsp;", " "), ("&eacute;", "é"),
                          ("&egrave;", "è"), ("&agrave;", "à"), ("&ccedil;", "ç"),
                          ("&ocirc;", "ô"), ("&ucirc;", "û"), ("&iuml;", "ï"),
                          ("&euml;", "ë"), ("&acirc;", "â")]:
        html = html.replace(entity, char)
    html = re.sub(r"&#?\w+;", " ", html)  # remaining entities
    html = re.sub(r"\s+", " ", html).strip()
    return html


def _extract_meta(html: str, name: str) -> str | None:
    pattern = rf'<meta\s[^>]*(?:name|property)\s*=\s*["\']?{re.escape(name)}["\']?\s[^>]*content\s*=\s*["\']([^"\']*)["\']'
    m = re.search(pattern, html, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    pattern2 = rf'<meta\s[^>]*content\s*=\s*["\']([^"\']*)["\'][^>]*(?:name|property)\s*=\s*["\']?{re.escape(name)}["\']?'
    m2 = re.search(pattern2, html, re.IGNORECASE)
    return m2.group(1).strip() if m2 else None


def _extract_title(html: str) -> str | None:
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    return _strip_tags(m.group(1)).strip() if m else None


def _extract_headings(html: str) -> list[str]:
    headings = []
    for m in re.finditer(r"<h[1-3][^>]*>(.*?)</h[1-3]>", html, re.IGNORECASE | re.DOTALL):
        text = _strip_tags(m.group(1)).strip()
        if text and len(text) > 2:
            headings.append(text)
    return headings


def _extract_strong(html: str) -> list[str]:
    items = []
    for m in re.finditer(r"<(?:strong|b)[^>]*>(.*?)</(?:strong|b)>", html, re.IGNORECASE | re.DOTALL):
        text = _strip_tags(m.group(1)).strip()
        if text and 3 < len(text) < 100:
            items.append(text)
    return items


def _extract_li(html: str) -> list[str]:
    """Extract <li> items — often contain service descriptions."""
    items = []
    for m in re.finditer(r"<li[^>]*>(.*?)</li>", html, re.IGNORECASE | re.DOTALL):
        text = _strip_tags(m.group(1)).strip()
        if text and 3 < len(text) < 150:
            items.append(text)
    return items


def _is_relevant_word(w: str) -> bool:
    """Check if a single word is relevant for procurement."""
    if len(w) < 3 or w in STOP_WORDS:
        return False
    # Numbers/codes → skip
    if re.match(r"^\d+$", w):
        return False
    return True


def _is_procurement_relevant(w: str) -> bool:
    """Check if word matches known procurement vocabulary."""
    return w in PROCUREMENT_BOOSTERS


def _tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-zàâäéèêëïîôùûüÿçœæ-]{3,}", text.lower())
    return [w for w in words if _is_relevant_word(w)]


def _extract_keywords_from_html(html: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "company_name": None,
        "meta_description": None,
        "keywords": [],
        "raw_word_count": 0,
    }

    title = _extract_title(html)
    meta_desc = _extract_meta(html, "description")
    meta_kw = _extract_meta(html, "keywords")
    og_title = _extract_meta(html, "og:title")
    og_desc = _extract_meta(html, "og:description")
    headings = _extract_headings(html)
    strong_texts = _extract_strong(html)
    li_texts = _extract_li(html)

    # Company name: clean up HTML entities
    raw_name = og_title or title or ""
    raw_name = raw_name.replace("&amp;", "&").replace("&#39;", "'").strip()
    # Remove common suffixes
    for suffix in [" - Accueil", " | Accueil", " - Home", " | Home", " – Accueil"]:
        if raw_name.endswith(suffix):
            raw_name = raw_name[:-len(suffix)]
    result["company_name"] = raw_name or None
    result["meta_description"] = (og_desc or meta_desc or "").replace("&amp;", "&").strip() or None

    # ── Weighted word counting ──
    weighted: Counter = Counter()

    # Process all text sources with weights
    sources = [
        (5, [title, og_title]),
        (4, [meta_desc, og_desc]),
        (3, headings),
        (2, strong_texts),
        (1, li_texts),
    ]
    for weight, texts in sources:
        for text in texts:
            if not text:
                continue
            for w in _tokenize(text):
                weighted[w] += weight
                # Boost procurement-relevant words
                if _is_procurement_relevant(w):
                    weighted[w] += weight * 2

    # Meta keywords (explicit = high value)
    if meta_kw:
        for kw in meta_kw.split(","):
            kw = kw.strip().lower()
            if kw and len(kw) >= 3:
                for w in _tokenize(kw):
                    weighted[w] += 6
                    if _is_procurement_relevant(w):
                        weighted[w] += 6

    # Body text (weight 1, but procurement words get boosted)
    body_text = _strip_tags(html)
    body_words = _tokenize(body_text)
    for w in body_words:
        weighted[w] += 1
        if _is_procurement_relevant(w):
            weighted[w] += 3

    # ── Extract meaningful phrases (2-3 words) from key text ──
    phrase_counter: Counter = Counter()
    important_texts = [meta_desc, og_desc] + headings + strong_texts + li_texts[:20]
    for text in important_texts:
        if not text:
            continue
        words = re.findall(r"[a-zàâäéèêëïîôùûüÿçœæ-]+", text.lower())
        for n in (2, 3):
            for i in range(len(words) - n + 1):
                phrase_words = words[i:i+n]
                # Skip if all words are stops
                if all(w in STOP_WORDS for w in phrase_words):
                    continue
                # Require meaningful non-stop words: 2+ for any phrase length
                non_stop = [w for w in phrase_words if w not in STOP_WORDS and len(w) > 2]
                if n == 2 and len(non_stop) < 2:
                    continue
                if len(non_stop) < 2:
                    continue
                # At least one word must be > 3 chars and relevant
                if not any(len(w) > 3 and _is_relevant_word(w) for w in phrase_words):
                    continue
                phrase = " ".join(phrase_words)
                if len(phrase) > 5:
                    # Extra boost if phrase contains procurement word
                    boost = 2 if any(_is_procurement_relevant(w) for w in phrase_words) else 1
                    phrase_counter[phrase] += 3 * boost

    # ── Build final keyword list ──
    # Single words: only keep those with meaningful score
    min_score = 3
    top_words = [(w, s) for w, s in weighted.most_common(60) if s >= min_score and len(w) > 2]

    # Phrases: filter out those containing only generic terms
    top_phrases = []
    for phrase, score in phrase_counter.most_common(20):
        words_in_phrase = phrase.split()
        # At least one non-stop word
        has_substance = any(w not in STOP_WORDS and len(w) > 3 for w in words_in_phrase)
        if has_substance and score >= 3:
            top_phrases.append((phrase, score))

    # Merge: procurement-relevant words first, then phrases, then rest
    seen = set()
    keywords = []

    # 1) Procurement-relevant single words (most valuable)
    for w, s in top_words:
        if _is_procurement_relevant(w) and w not in seen:
            keywords.append(w)
            seen.add(w)

    # 2) Good phrases
    for phrase, s in top_phrases[:8]:
        if phrase not in seen:
            # Don't add phrase if ALL its words are already in keywords
            phrase_words = set(phrase.split()) - STOP_WORDS
            if not phrase_words.issubset(seen):
                keywords.append(phrase)
                seen.add(phrase)

    # 3) Remaining single words — ONLY if procurement-adjacent or very high score
    for w, s in top_words:
        if w not in seen and not any(w in p for p in keywords):
            # Must be either: known procurement term, OR score >= 8 AND word >= 5 chars
            if _is_procurement_relevant(w):
                keywords.append(w)
                seen.add(w)
            elif s >= 8 and len(w) >= 5:
                keywords.append(w)
                seen.add(w)

    result["keywords"] = keywords[:20]
    result["raw_word_count"] = len(body_words)
    return result


def _suggest_cpv(keywords: list[str]) -> list[dict[str, str]]:
    matches: list[tuple[int, str, str]] = []
    kw_text = " ".join(keywords).lower()

    for trigger_words, cpv_code, cpv_label in CPV_SUGGESTIONS:
        score = 0
        for trigger in trigger_words:
            tl = trigger.lower()
            if tl in kw_text:
                score += 3
            for kw in keywords:
                kl = kw.lower()
                if tl in kl or kl in tl:
                    score += 2
                elif tl[:4] == kl[:4] and len(tl) > 4:  # stem match
                    score += 1
        if score > 0:
            matches.append((score, cpv_code, cpv_label))

    matches.sort(key=lambda x: x[0], reverse=True)
    return [{"code": cpv, "label": label} for _, cpv, label in matches[:5]]


# ── API endpoint ──────────────────────────────────────────────────

@router.post("/analyze-website", response_model=AnalyzeResponse)
async def analyze_website(req: AnalyzeRequest) -> AnalyzeResponse:
    """
    Analyze a website to extract business keywords and suggest CPV codes.
    Public endpoint — no auth required.
    """
    url = req.url
    try:
        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; ProcureWatch/1.0; +https://procurewatch.eu)",
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "fr,nl,en",
            },
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except httpx.TimeoutException:
        raise HTTPException(status_code=422, detail="Le site ne répond pas (timeout)")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=422, detail=f"Erreur HTTP {e.response.status_code}")
    except Exception as e:
        logger.warning("Website fetch failed for %s: %s", url, e)
        raise HTTPException(status_code=422, detail="Impossible d'accéder à ce site")

    ct = resp.headers.get("content-type", "")
    if "html" not in ct.lower() and "text" not in ct.lower():
        raise HTTPException(status_code=422, detail="Ce site ne renvoie pas de HTML")

    html = resp.text
    if len(html) < 100:
        raise HTTPException(status_code=422, detail="Page trop courte pour être analysée")

    extracted = _extract_keywords_from_html(html)
    keywords = extracted["keywords"]

    if not keywords:
        raise HTTPException(status_code=422, detail="Aucun mot-clé pertinent trouvé. Essayez une page plus détaillée.")

    return AnalyzeResponse(
        url=url,
        company_name=extracted.get("company_name"),
        meta_description=extracted.get("meta_description"),
        keywords=keywords,
        suggested_cpv=_suggest_cpv(keywords),
        raw_word_count=extracted.get("raw_word_count", 0),
    )


# ── Preview matches (teaser) ─────────────────────────────────────

class PreviewRequest(BaseModel):
    keywords: list[str]
    cpv_codes: list[str] = []

class PreviewNotice(BaseModel):
    title: str
    authority: str | None = None
    cpv: str | None = None
    source: str | None = None
    publication_date: str | None = None
    deadline: str | None = None

class PreviewResponse(BaseModel):
    total_matches: int
    sample: list[PreviewNotice]


@router.post("/preview-matches", response_model=PreviewResponse)
def preview_matches(
    req: PreviewRequest,
    db: Session = Depends(_get_db),
) -> PreviewResponse:
    """
    Public teaser: count matching notices for given keywords + CPV codes.
    Returns total count + 5 sample notices. No auth required.
    """
    from app.models.notice import ProcurementNotice
    from sqlalchemy import or_

    if not req.keywords and not req.cpv_codes:
        return PreviewResponse(total_matches=0, sample=[])

    N = ProcurementNotice
    filters = []

    # Keyword matching (ILIKE on title + description)
    for kw in req.keywords[:10]:  # cap at 10
        kw_clean = kw.strip()
        if len(kw_clean) < 2:
            continue
        pat = f"%{kw_clean}%"
        filters.append(or_(
            N.title.ilike(pat),
            N.description.ilike(pat),
        ))

    # CPV prefix matching
    for cpv in req.cpv_codes[:5]:  # cap at 5
        cpv_clean = cpv.replace("-", "").strip()
        if len(cpv_clean) >= 2:
            filters.append(N.cpv_main_code.ilike(f"{cpv_clean}%"))

    if not filters:
        return PreviewResponse(total_matches=0, sample=[])

    base_q = db.query(N).filter(or_(*filters))

    total = base_q.count()

    # Get 5 most recent samples
    samples = (
        base_q
        .order_by(N.publication_date.desc().nullslast())
        .limit(5)
        .all()
    )

    return PreviewResponse(
        total_matches=total,
        sample=[
            PreviewNotice(
                title=n.title or "—",
                authority=n.authority_name,
                cpv=n.cpv_main_code,
                source="BOSA" if n.source and "BOSA" in n.source else "TED",
                publication_date=n.publication_date.isoformat() if n.publication_date else None,
                deadline=n.deadline.isoformat() if n.deadline else None,
            )
            for n in samples
        ],
    )
