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
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/public", tags=["public"])

# ── French stop words ──────────────────────────────────────────────

STOP_WORDS_FR = frozenset(
    "le la les de des du un une et en est il elle on nous vous ils elles "
    "ce cette ces son sa ses leur leurs mon ma mes ton ta tes notre nos votre vos "
    "que qui quoi dont où au aux par pour dans avec sans sur sous entre "
    "ne pas plus aussi très tout tous toute toutes même autre autres "
    "je tu il nous vous ils se me te lui eux y être avoir faire "
    "été fait a été sont ont peut peuvent fait faire avons sommes êtes "
    "mais ou car ni donc or si bien comme plus moins ici là où quand comment "
    "après avant pendant depuis lors encore déjà aussi ainsi alors ensuite "
    "chez vers entre contre parmi durant malgré sauf selon sous outre "
    "non oui peu beaucoup trop assez chaque quelque plusieurs certain "
    "aucun nul tel quel lequel laquelle lesquels lesquelles "
    "ceci cela celui celle ceux celles dont "
    "the and for with from this that are was were has have been will "
    "not but all can had her his they them these those "
    "about into through during before after above below between "
    "www http https com org net html php".split()
)

STOP_WORDS_NL = frozenset(
    "de het een van in is dat op te zijn was met voor niet hij zij ze "
    "er aan als het ook door maar worden nog wel bij haar die deze "
    "geen alle uit dan nu kan tot meer al om over naar wij hen wat "
    "tot u ons onze hun hun werd mijn uw".split()
)

STOP_WORDS = STOP_WORDS_FR | STOP_WORDS_NL

# ── CPV keyword mapping (simplified) ──────────────────────────────

CPV_SUGGESTIONS = [
    (["construction", "bâtiment", "travaux", "chantier", "gros œuvre", "génie civil", "bouw"], "45000000", "Travaux de construction"),
    (["plomberie", "sanitaire", "tuyauterie", "chauffage", "hvac", "climatisation"], "45330000", "Travaux de plomberie"),
    (["électricité", "électrique", "câblage", "éclairage", "installation électrique"], "45310000", "Travaux d'électricité"),
    (["peinture", "revêtement", "décoration", "papier peint", "enduit"], "45440000", "Travaux de peinture"),
    (["toiture", "couverture", "étanchéité", "toit", "charpente"], "45261000", "Travaux de toiture"),
    (["voirie", "route", "asphalt", "enrobé", "chaussée", "trottoir", "piste cyclable"], "45233000", "Travaux de voirie"),
    (["espaces verts", "jardinage", "paysagiste", "entretien vert", "plantation", "élagage"], "77310000", "Services d'espaces verts"),
    (["nettoyage", "propreté", "entretien", "ménage", "hygiène"], "90910000", "Services de nettoyage"),
    (["informatique", "logiciel", "développement", "software", "application", "web", "digital"], "72000000", "Services informatiques"),
    (["sécurité", "gardiennage", "surveillance", "alarme", "vidéo"], "79710000", "Services de sécurité"),
    (["transport", "logistique", "livraison", "déménagement", "fret"], "60000000", "Services de transport"),
    (["mobilier", "meuble", "bureau", "équipement", "fourniture"], "39100000", "Mobilier"),
    (["restauration", "catering", "repas", "cuisine", "traiteur"], "55520000", "Services de restauration"),
    (["architecture", "architecte", "conception", "design", "urbanisme"], "71200000", "Services d'architecture"),
    (["ingénierie", "ingénieur", "étude", "conseil technique", "bureau d'études"], "71300000", "Services d'ingénierie"),
    (["formation", "enseignement", "cours", "éducation", "coaching"], "80500000", "Services de formation"),
    (["médical", "santé", "soins", "hôpital", "médecin", "paramédical"], "85100000", "Services de santé"),
    (["imprimerie", "impression", "print", "édition", "graphisme"], "79800000", "Services d'impression"),
    (["communication", "marketing", "publicité", "événement", "relations publiques"], "79340000", "Services de publicité"),
    (["comptabilité", "audit", "fiscal", "fiduciaire", "expertise comptable"], "79210000", "Services comptables"),
    (["juridique", "avocat", "droit", "conseil juridique", "notaire"], "79100000", "Services juridiques"),
    (["assurance", "courtage", "police", "sinistre"], "66510000", "Services d'assurance"),
    (["télécom", "réseau", "fibre", "câble", "internet"], "64200000", "Services de télécommunications"),
    (["menuiserie", "bois", "charpente", "ébénisterie", "parquet"], "45420000", "Travaux de menuiserie"),
    (["carrelage", "sol", "revêtement sol", "pavage", "dallage"], "45431000", "Travaux de carrelage"),
    (["ascenseur", "élévateur", "escalier roulant", "monte-charge"], "45313000", "Installation d'ascenseurs"),
    (["démolition", "désamiantage", "déconstruction", "terrassement"], "45110000", "Travaux de démolition"),
    (["isolation", "thermique", "acoustique", "façade", "bardage"], "45320000", "Travaux d'isolation"),
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
        # Block local/private URLs
        host = parsed.hostname or ""
        if host in ("localhost", "127.0.0.1", "0.0.0.0") or host.startswith("192.168.") or host.startswith("10."):
            raise ValueError("URL locale non autorisée")
        return v


class AnalyzeResponse(BaseModel):
    url: str
    company_name: str | None = None
    meta_description: str | None = None
    keywords: list[str]
    suggested_cpv: list[dict[str, str]]
    raw_word_count: int = 0


# ── HTML text extraction (no BeautifulSoup dependency) ────────────

def _strip_tags(html: str) -> str:
    """Remove HTML tags, scripts, styles."""
    # Remove script/style blocks
    html = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # Remove HTML comments
    html = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)
    # Remove tags
    html = re.sub(r"<[^>]+>", " ", html)
    # Decode common entities
    for entity, char in [("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'),
                          ("&#39;", "'"), ("&apos;", "'"), ("&nbsp;", " "), ("&eacute;", "é"),
                          ("&egrave;", "è"), ("&agrave;", "à"), ("&ccedil;", "ç")]:
        html = html.replace(entity, char)
    # Collapse whitespace
    html = re.sub(r"\s+", " ", html).strip()
    return html


def _extract_meta(html: str, name: str) -> str | None:
    """Extract content of a <meta name='...'> or <meta property='...'> tag."""
    pattern = rf'<meta\s[^>]*(?:name|property)\s*=\s*["\']?{re.escape(name)}["\']?\s[^>]*content\s*=\s*["\']([^"\']*)["\']'
    m = re.search(pattern, html, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    # Try reversed order (content before name)
    pattern2 = rf'<meta\s[^>]*content\s*=\s*["\']([^"\']*)["\'][^>]*(?:name|property)\s*=\s*["\']?{re.escape(name)}["\']?'
    m2 = re.search(pattern2, html, re.IGNORECASE)
    return m2.group(1).strip() if m2 else None


def _extract_title(html: str) -> str | None:
    """Extract <title> content."""
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    return _strip_tags(m.group(1)).strip() if m else None


def _extract_headings(html: str) -> list[str]:
    """Extract H1-H3 text content."""
    headings = []
    for m in re.finditer(r"<h[1-3][^>]*>(.*?)</h[1-3]>", html, re.IGNORECASE | re.DOTALL):
        text = _strip_tags(m.group(1)).strip()
        if text and len(text) > 2:
            headings.append(text)
    return headings


def _extract_strong(html: str) -> list[str]:
    """Extract <strong>/<b> text."""
    items = []
    for m in re.finditer(r"<(?:strong|b)[^>]*>(.*?)</(?:strong|b)>", html, re.IGNORECASE | re.DOTALL):
        text = _strip_tags(m.group(1)).strip()
        if text and 3 < len(text) < 100:
            items.append(text)
    return items


def _tokenize(text: str) -> list[str]:
    """Tokenize text into lowercase words, min length 3."""
    words = re.findall(r"[a-zàâäéèêëïîôùûüÿçœæ]{3,}", text.lower())
    return [w for w in words if w not in STOP_WORDS and len(w) >= 3]


def _extract_keywords_from_html(html: str) -> dict[str, Any]:
    """Parse HTML and extract keywords with weighting."""
    result: dict[str, Any] = {
        "company_name": None,
        "meta_description": None,
        "keywords": [],
    }

    # 1) Extract structured data
    title = _extract_title(html)
    meta_desc = _extract_meta(html, "description")
    meta_kw = _extract_meta(html, "keywords")
    og_title = _extract_meta(html, "og:title")
    og_desc = _extract_meta(html, "og:description")
    headings = _extract_headings(html)
    strong_texts = _extract_strong(html)

    result["company_name"] = og_title or title
    result["meta_description"] = og_desc or meta_desc

    # 2) Weighted word counting
    weighted: Counter = Counter()

    # Title words (weight 5)
    if title:
        for w in _tokenize(title):
            weighted[w] += 5
    if og_title:
        for w in _tokenize(og_title):
            weighted[w] += 5

    # Meta description (weight 4)
    for text in [meta_desc, og_desc]:
        if text:
            for w in _tokenize(text):
                weighted[w] += 4

    # Meta keywords (weight 4)
    if meta_kw:
        for kw in meta_kw.split(","):
            kw = kw.strip().lower()
            if kw and kw not in STOP_WORDS and len(kw) >= 3:
                weighted[kw] += 6  # Explicit keywords get high weight
                # Also add individual words
                for w in _tokenize(kw):
                    weighted[w] += 4

    # Headings (weight 3)
    for h in headings:
        for w in _tokenize(h):
            weighted[w] += 3

    # Strong/bold text (weight 2)
    for s in strong_texts:
        for w in _tokenize(s):
            weighted[w] += 2

    # Body text (weight 1)
    body_text = _strip_tags(html)
    for w in _tokenize(body_text):
        weighted[w] += 1

    # 3) Extract compound terms from headings and meta (2-3 word phrases)
    phrase_counter: Counter = Counter()
    important_texts = [meta_desc, og_desc, meta_kw] + headings + strong_texts
    for text in important_texts:
        if not text:
            continue
        words = text.lower().split()
        for n in (2, 3):
            for i in range(len(words) - n + 1):
                phrase = " ".join(words[i:i+n])
                # Clean phrase
                phrase = re.sub(r"[^a-zàâäéèêëïîôùûüÿçœæ\s-]", "", phrase).strip()
                if phrase and len(phrase) > 5:
                    all_stop = all(w in STOP_WORDS for w in phrase.split())
                    if not all_stop:
                        phrase_counter[phrase] += 3

    # 4) Merge: take top single words + top phrases
    top_words = [w for w, _ in weighted.most_common(30) if len(w) > 2]
    top_phrases = [p for p, _ in phrase_counter.most_common(10) if len(p) > 5]

    # Combine: phrases first (more specific), then single words
    seen = set()
    keywords = []
    for phrase in top_phrases:
        if phrase not in seen:
            keywords.append(phrase)
            seen.add(phrase)
    for word in top_words:
        if word not in seen and not any(word in p for p in keywords):
            keywords.append(word)
            seen.add(word)

    result["keywords"] = keywords[:20]
    result["raw_word_count"] = sum(weighted.values())
    return result


def _suggest_cpv(keywords: list[str]) -> list[dict[str, str]]:
    """Match keywords to CPV codes."""
    matches: list[tuple[int, str, str]] = []
    kw_text = " ".join(keywords).lower()

    for trigger_words, cpv_code, cpv_label in CPV_SUGGESTIONS:
        score = 0
        for trigger in trigger_words:
            if trigger.lower() in kw_text:
                score += 2
            # Also check if any keyword contains this trigger
            for kw in keywords:
                if trigger.lower() in kw.lower() or kw.lower() in trigger.lower():
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
        raise HTTPException(status_code=422, detail=f"Le site a répondu avec l'erreur {e.response.status_code}")
    except Exception as e:
        logger.warning("Website fetch failed for %s: %s", url, e)
        raise HTTPException(status_code=422, detail="Impossible d'accéder à ce site")

    content_type = resp.headers.get("content-type", "")
    if "html" not in content_type.lower() and "text" not in content_type.lower():
        raise HTTPException(status_code=422, detail="Ce site ne renvoie pas de HTML")

    html = resp.text
    if len(html) < 100:
        raise HTTPException(status_code=422, detail="Page trop courte pour être analysée")

    # Extract keywords
    extracted = _extract_keywords_from_html(html)
    keywords = extracted["keywords"]

    if not keywords:
        raise HTTPException(status_code=422, detail="Aucun mot-clé trouvé sur cette page. Essayez la page d'accueil.")

    # Suggest CPV codes
    cpv_suggestions = _suggest_cpv(keywords)

    return AnalyzeResponse(
        url=url,
        company_name=extracted.get("company_name"),
        meta_description=extracted.get("meta_description"),
        keywords=keywords,
        suggested_cpv=cpv_suggestions,
        raw_word_count=extracted.get("raw_word_count", 0),
    )
