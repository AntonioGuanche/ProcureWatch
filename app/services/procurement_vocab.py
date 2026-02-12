"""
Procurement vocabulary cache.

Builds a set of words that actually appear in procurement notice titles.
Used by the website keyword analyser to filter out irrelevant words
(brand names, proper nouns, gibberish) without hard-coded stop lists.

Cache refreshes every 6 hours.  First call is ~1-2s (queries 50K titles),
subsequent calls are instant (in-memory set).
"""

import logging
import re
import time
from collections import Counter

logger = logging.getLogger(__name__)

# ── Cache state ────────────────────────────────────────────────────
_vocab_cache: set[str] | None = None
_vocab_ts: float = 0
_VOCAB_TTL = 6 * 3600  # 6 hours

# Minimum notice appearances for a word to be considered "procurement vocabulary"
_MIN_NOTICE_COUNT = 3


def _build_vocab() -> set[str]:
    """Query DB and build vocabulary from notice titles."""
    from app.db.session import SessionLocal
    from app.models.notice import ProcurementNotice as N

    db = SessionLocal()
    try:
        # Sample up to 60K titles (covers most of the corpus)
        rows = (
            db.query(N.title)
            .filter(N.title.isnot(None))
            .order_by(N.publication_date.desc().nulls_last())
            .limit(60_000)
            .all()
        )

        counter: Counter[str] = Counter()
        for (title,) in rows:
            # Tokenise: lowercase words ≥ 3 chars, use set() to count per-title
            words = set(re.findall(r"[a-zàâäéèêëïîôùûüÿçœæ-]{3,}", title.lower()))
            counter.update(words)

        # Keep words appearing in N+ distinct notices
        vocab = {w for w, c in counter.items() if c >= _MIN_NOTICE_COUNT and len(w) >= 3}

        logger.info(
            "Procurement vocabulary built: %d unique words from %d titles",
            len(vocab), len(rows),
        )
        return vocab

    finally:
        db.close()


def get_procurement_vocab() -> set[str]:
    """
    Return cached set of words found in procurement notice titles.
    Thread-safe for reads (worst case: two threads build simultaneously, harmless).
    """
    global _vocab_cache, _vocab_ts

    if _vocab_cache is not None and (time.time() - _vocab_ts) < _VOCAB_TTL:
        return _vocab_cache

    try:
        _vocab_cache = _build_vocab()
        _vocab_ts = time.time()
    except Exception:
        logger.exception("Failed to build procurement vocabulary, using empty set")
        if _vocab_cache is None:
            _vocab_cache = set()
        # Don't update timestamp → will retry on next call
    return _vocab_cache


def is_in_procurement_vocab(word: str) -> bool:
    """Check if a word appears in the procurement vocabulary."""
    return word.lower() in get_procurement_vocab()


def invalidate_cache() -> None:
    """Force rebuild on next call (e.g. after bulk import)."""
    global _vocab_ts
    _vocab_ts = 0
