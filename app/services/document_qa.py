"""Document Q&A: ask questions about notice documents using Claude AI.

Pipeline:
  1. Gather all extracted text from notice documents
  2. Build Q&A prompt with document context + user question
  3. Send to Claude → structured answer with source references

Usage:
    from app.services.document_qa import ask_document_question
    result = await ask_document_question(db, notice, question="Quelles sont les agréations requises?", lang="fr")

Cost: ~€0.01-0.03/question depending on document volume.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.notice import ProcurementNotice
from app.models.notice_document import NoticeDocument

logger = logging.getLogger(__name__)

# Max chars of document text sent to Claude (~8K tokens ≈ 32K chars).
MAX_QA_CONTEXT = 32_000


def _gather_document_texts(
    db: Session,
    notice_id: str,
) -> list[dict[str, Any]]:
    """Gather all available extracted text for a notice's documents.

    Returns list of {"doc_id", "title", "text", "file_type"}.
    """
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


def _build_qa_prompt(
    question: str,
    doc_texts: list[dict[str, Any]],
    notice: ProcurementNotice,
    lang: str = "fr",
) -> str:
    """Build Q&A prompt with document context."""

    # Notice metadata context
    ctx_parts = []
    if notice.title:
        ctx_parts.append(f"Titre: {notice.title}")
    if notice.cpv_main_code:
        ctx_parts.append(f"CPV: {notice.cpv_main_code}")
    org = None
    if notice.organisation_names and isinstance(notice.organisation_names, dict):
        org = next(iter(notice.organisation_names.values()), None)
    if org:
        ctx_parts.append(f"Pouvoir adjudicateur: {org}")
    if notice.estimated_value:
        ctx_parts.append(f"Valeur estimée: {notice.estimated_value:,.2f} EUR")
    if notice.deadline:
        ctx_parts.append(f"Date limite: {notice.deadline.strftime('%d/%m/%Y')}")

    notice_context = "\n".join(ctx_parts) if ctx_parts else "(pas de métadonnées)"

    # Concatenate document texts with headers, respecting token budget
    remaining = MAX_QA_CONTEXT
    doc_sections = []
    for i, dt in enumerate(doc_texts, 1):
        header = f"--- DOCUMENT {i}: {dt['title']} ({dt['file_type'] or 'PDF'}) ---"
        text = dt["text"]
        if len(text) > remaining:
            text = text[:remaining] + "\n[... texte tronqué ...]"
        doc_sections.append(f"{header}\n{text}")
        remaining -= len(text)
        if remaining <= 0:
            break

    all_docs_text = "\n\n".join(doc_sections)

    lang_instructions = {
        "fr": "Réponds en français.",
        "nl": "Antwoord in het Nederlands.",
        "en": "Reply in English.",
        "de": "Antworte auf Deutsch.",
    }
    lang_instr = lang_instructions.get(lang, lang_instructions["fr"])

    return f"""Tu es un expert en marchés publics belges et européens.
L'utilisateur te pose une question sur un marché public. Réponds en te basant UNIQUEMENT sur les documents fournis ci-dessous.

## Contexte du marché
{notice_context}

## Documents disponibles
{all_docs_text}

---

## Question de l'utilisateur
{question}

---

{lang_instr} Réponds de façon claire et structurée:
- Cite les passages pertinents des documents quand c'est possible
- Indique de quel document provient chaque information (Document 1, Document 2, etc.)
- Si l'information n'est pas dans les documents, dis-le clairement. Ne devine pas.
- Sois concis mais complet"""


async def _call_claude_qa(prompt: str) -> Optional[str]:
    """Call Anthropic API for Q&A response."""
    if not settings.anthropic_api_key:
        logger.warning("ANTHROPIC_API_KEY not set — cannot answer question")
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

        content = data.get("content", [])
        text = ""
        for block in content:
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
        logger.error("httpx not installed — pip install httpx")
        return None
    except Exception as e:
        logger.exception("Claude Q&A API call failed: %s", e)
        return None


# ── Public API ────────────────────────────────────────────────────


async def ask_document_question(
    db: Session,
    notice: ProcurementNotice,
    question: str,
    lang: str = "fr",
) -> dict[str, Any]:
    """Ask a question about a notice's documents.

    Returns dict with answer, sources, status.
    """
    # Step 1: gather document texts
    doc_texts = _gather_document_texts(db, notice.id)

    if not doc_texts:
        return {
            "status": "no_documents",
            "answer": None,
            "message": (
                "Aucun document avec du texte extractible n'est disponible "
                "pour ce marché. Les documents n'ont peut-être pas encore "
                "été téléchargés ou sont des scans non-OCR."
            ),
            "sources": [],
        }

    # Step 2: build prompt and call Claude
    prompt = _build_qa_prompt(question, doc_texts, notice, lang=lang)
    answer = await _call_claude_qa(prompt)

    if not answer:
        return {
            "status": "error",
            "answer": None,
            "message": "Impossible de générer une réponse. Réessayez plus tard.",
            "sources": [],
        }

    # Step 3: return structured response
    sources = [
        {
            "document_id": dt["doc_id"],
            "title": dt["title"],
            "file_type": dt["file_type"],
            "text_length": len(dt["text"]),
        }
        for dt in doc_texts
    ]

    return {
        "status": "ok",
        "answer": answer,
        "question": question,
        "sources": sources,
        "documents_used": len(doc_texts),
        "lang": lang,
    }
