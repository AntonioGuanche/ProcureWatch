"""Notice Q&A: ask questions about notice content using Claude AI.

Smart context gathering (3 layers):
  1. PDF documents with extracted text -> richest source (cahiers des charges)
  2. Notice description + raw_data fields -> always available, works for all notices
  3. Both combined when PDFs exist

This means Q&A works for ALL notices, not just those with PDFs.

Usage:
    from app.services.document_qa import ask_document_question
    result = await ask_document_question(db, notice, question="Quelles agreations?", lang="fr")
"""
import logging
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.notice import ProcurementNotice
from app.models.notice_document import NoticeDocument

logger = logging.getLogger(__name__)

MAX_QA_CONTEXT = 32_000  # ~8K tokens


# -- Context gathering --


def _gather_document_texts(db: Session, notice_id: str) -> list[dict[str, Any]]:
    """Gather extracted text from notice's downloaded documents (PDFs)."""
    docs = (
        db.query(NoticeDocument)
        .filter(
            NoticeDocument.notice_id == notice_id,
            NoticeDocument.extracted_text.isnot(None),
            NoticeDocument.extracted_text != "",
        )
        .all()
    )
    results = []
    for doc in docs:
        text = (doc.extracted_text or "").strip()
        if len(text) < 20:
            continue
        results.append({
            "doc_id": doc.id,
            "title": doc.title or "Document",
            "text": text,
            "file_type": doc.file_type,
        })
    return results


def _extract_notice_context(notice: ProcurementNotice) -> str:
    """Build rich text context from notice fields + raw_data.

    Used as primary context for TED notices or supplementary for BOSA.
    """
    parts: list[str] = []

    if notice.description:
        parts.append(f"DESCRIPTION:\n{notice.description}")

    raw = notice.raw_data
    if isinstance(raw, dict):
        # TED multilingual text fields
        for field_key, label in [
            ("description-glo", "Description globale"),
            ("description-lot", "Description des lots"),
            ("description-proc", "Description procedure"),
            ("title-lot", "Titres des lots"),
            ("additional-information-lot", "Informations complementaires"),
        ]:
            text = _flatten(raw.get(field_key))
            if text and text not in (notice.description or ""):
                parts.append(f"\n{label.upper()}:\n{text}")

        for key, label in [
            ("procedure-type", "Type de procedure"),
            ("contract-nature-main-proc", "Nature du marche"),
            ("award-criterion-type-lot", "Criteres d'attribution"),
            ("business-name", "Adjudicataire"),
            ("tender-value", "Valeur attribuee"),
            ("received-submissions-type-val", "Offres recues"),
            ("place-of-performance", "Lieu d'execution"),
        ]:
            text = _flatten(raw.get(key))
            if text:
                parts.append(f"{label}: {text}")

        # BOSA-specific fields
        for key, label in [
            ("descriptionTechnical", "Details techniques"),
            ("conditionsParticipation", "Conditions de participation"),
            ("technicalCapacity", "Capacite technique"),
            ("economicFinancialCapacity", "Capacite financiere"),
        ]:
            val = raw.get(key)
            text = val.strip() if isinstance(val, str) else _flatten(val)
            if text and text not in (notice.description or ""):
                parts.append(f"\n{label}:\n{text}")

    full = "\n".join(parts)
    return full[:MAX_QA_CONTEXT] if len(full) > MAX_QA_CONTEXT else full


def _flatten(val: Any) -> str:
    """Flatten a TED multilingual value to a single text string."""
    if val is None:
        return ""
    if isinstance(val, str):
        return val.strip()
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, list):
        return "\n".join(filter(None, (_flatten(v) for v in val[:20])))
    if isinstance(val, dict):
        for lang in ("fra", "fr", "eng", "en", "nld", "nl", "deu", "de"):
            if lang in val:
                return _flatten(val[lang])
        for v in val.values():
            t = _flatten(v)
            if t:
                return t
    return ""


# -- Prompt building --


def _build_prompt(
    question: str,
    doc_texts: list[dict[str, Any]],
    notice_context: str,
    notice: ProcurementNotice,
    lang: str = "fr",
) -> str:
    """Build Q&A prompt combining document texts and notice context."""

    meta = []
    if notice.title:
        meta.append(f"Titre: {notice.title}")
    if notice.cpv_main_code:
        meta.append(f"CPV: {notice.cpv_main_code}")
    org = None
    if notice.organisation_names and isinstance(notice.organisation_names, dict):
        org = next(iter(notice.organisation_names.values()), None)
    if org:
        meta.append(f"Pouvoir adjudicateur: {org}")
    if notice.estimated_value:
        meta.append(f"Valeur estimee: {notice.estimated_value:,.2f} EUR")
    if notice.deadline:
        meta.append(f"Date limite: {notice.deadline.strftime('%d/%m/%Y')}")
    if notice.source:
        meta.append(f"Source: {notice.source}")
    header = "\n".join(meta) if meta else "(pas de metadonnees)"

    remaining = MAX_QA_CONTEXT
    sections = []

    # PDFs first (richest)
    for i, dt in enumerate(doc_texts, 1):
        label = f"DOCUMENT {i}: {dt['title']} ({dt['file_type'] or 'PDF'})"
        text = dt["text"]
        if len(text) > remaining:
            text = text[:remaining] + "\n[... tronque ...]"
        sections.append(f"--- {label} ---\n{text}")
        remaining -= len(text)
        if remaining <= 500:
            break

    # Notice context (supplementary or primary)
    if remaining > 500 and notice_context:
        nc = notice_context[:remaining]
        sections.append(f"--- DONNEES DE L'AVIS ---\n{nc}")

    all_context = "\n\n".join(sections)
    has_docs = len(doc_texts) > 0

    source_note = (
        "Cite les documents par numero (Document 1, 2...) quand possible."
        if has_docs
        else "Les informations proviennent des donnees de l'avis de marche."
    )

    lang_map = {
        "fr": "Reponds en francais.",
        "nl": "Antwoord in het Nederlands.",
        "en": "Reply in English.",
        "de": "Antworte auf Deutsch.",
    }

    return f"""Tu es un expert en marches publics belges et europeens.
Reponds a la question en te basant UNIQUEMENT sur les informations fournies ci-dessous.

## Metadonnees
{header}

## Contenu disponible
{all_context}

---

## Question
{question}

---

{lang_map.get(lang, lang_map['fr'])} {source_note}
Si l'information n'est pas disponible, dis-le clairement. Ne devine pas.
Sois concis mais complet."""


# -- Claude API call --


async def _call_claude(prompt: str) -> Optional[str]:
    """Call Anthropic API for Q&A response."""
    if not settings.anthropic_api_key:
        logger.warning("ANTHROPIC_API_KEY not set")
        return None

    try:
        import httpx

        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": settings.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": settings.ai_model,
                    "max_tokens": 2000,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            response.raise_for_status()
            data = response.json()

        text = ""
        for block in data.get("content", []):
            if isinstance(block, dict) and block.get("type") == "text":
                text += block.get("text", "")

        usage = data.get("usage", {})
        logger.info(
            "Document Q&A: input=%s output=%s tokens",
            usage.get("input_tokens", "?"),
            usage.get("output_tokens", "?"),
        )
        return text.strip() if text.strip() else None

    except ImportError:
        logger.error("httpx not installed")
        return None
    except Exception as e:
        logger.exception("Claude Q&A failed: %s", e)
        return None


# -- Public API --


async def ask_document_question(
    db: Session,
    notice: ProcurementNotice,
    question: str,
    lang: str = "fr",
) -> dict[str, Any]:
    """Ask a question about a notice - uses PDFs + notice data as context.

    Works for ALL notices: BOSA with PDFs, TED with descriptions, or mixed.
    """
    doc_texts = _gather_document_texts(db, notice.id)
    notice_context = _extract_notice_context(notice)

    if not doc_texts and not notice_context:
        return {
            "status": "no_content",
            "answer": None,
            "message": (
                "Aucune information disponible pour ce marche. "
                "Ni documents telecharges, ni description dans l'avis."
            ),
            "sources": [],
        }

    prompt = _build_prompt(question, doc_texts, notice_context, notice, lang=lang)
    answer = await _call_claude(prompt)

    if not answer:
        return {
            "status": "error",
            "answer": None,
            "message": "Impossible de generer une reponse. Reessayez plus tard.",
            "sources": [],
        }

    sources = [
        {
            "document_id": dt["doc_id"],
            "title": dt["title"],
            "file_type": dt["file_type"],
            "text_length": len(dt["text"]),
        }
        for dt in doc_texts
    ]
    if notice_context:
        sources.append({
            "document_id": None,
            "title": "Donnees de l'avis",
            "file_type": "NOTICE",
            "text_length": len(notice_context),
        })

    return {
        "status": "ok",
        "answer": answer,
        "question": question,
        "sources": sources,
        "documents_used": len(doc_texts),
        "notice_data_used": bool(notice_context),
        "lang": lang,
    }
