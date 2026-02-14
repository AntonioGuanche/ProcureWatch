"""Translation API endpoints — keyword expansion for multilingual search.

GET /api/translate?q=nettoyage   → translations (static + AI fallback)
GET /api/translate/expand?q=nettoyage+bâtiment → expanded list for multiple keywords
GET /api/translate/stats         → dictionary stats
"""
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.translation_service import (
    translate_keyword,
    translate_keyword_smart,
    expand_keyword,
    expand_keywords_list,
    expand_tsquery_terms,
    get_dictionary_stats,
)

router = APIRouter(
    prefix="/translate",
    tags=["translation"],
)


@router.get("")
async def translate_single(
    q: str = Query(..., min_length=1, max_length=200, description="Keyword to translate"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Translate a single keyword to FR/NL/EN.

    Uses static dictionary first, then DB cache, then AI fallback.
    AI results are cached for future lookups.

    Example: /api/translate?q=prothèse+de+hanche
    → {"original": "prothèse de hanche", "fr": [...], "nl": ["heupprothese"], "en": ["hip prosthesis"], "found": true, "source": "ai"}
    """
    return await translate_keyword_smart(q.strip(), db=db)


@router.get("/expand")
def expand_keywords(
    q: str = Query(..., min_length=1, max_length=500, description="Keywords to expand (space-separated)"),
) -> dict[str, Any]:
    """Expand multiple keywords with translations (static dictionary only, instant).

    Example: /api/translate/expand?q=nettoyage+bâtiment
    → {"original": ["nettoyage", "bâtiment"],
       "expanded": ["nettoyage", "schoonmaak", "cleaning", "bâtiment", "gebouw", "building"],
       "tsquery": "(nettoyage:* | schoonmaak:* | cleaning:*) & (bâtiment:* | gebouw:* | building:*)"}
    """
    terms = q.strip().split()
    expanded = expand_keywords_list(terms)
    tsquery = expand_tsquery_terms(q.strip())

    return {
        "original": terms,
        "expanded": expanded,
        "tsquery": tsquery,
        "original_count": len(terms),
        "expanded_count": len(expanded),
    }


@router.get("/stats")
def dictionary_stats() -> dict[str, Any]:
    """Return translation dictionary statistics."""
    return get_dictionary_stats()
