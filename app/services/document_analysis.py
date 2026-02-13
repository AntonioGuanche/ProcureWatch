"""Phase 2: On-demand PDF document analysis.

Pipeline per document:
  1. If extracted_text is empty → download PDF to /tmp → extract text → store
  2. Truncate text to ~6K tokens → send to Claude for structured analysis
  3. Cache analysis JSON in notice_documents.ai_analysis
  4. Return structured result

Cost: ~€0.01/document (Sonnet, ~2K input + ~500 output tokens).

Usage:
    from app.services.document_analysis import analyze_document
    result = await analyze_document(db, doc, notice, lang="fr")
"""
import hashlib
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.notice import ProcurementNotice
from app.models.notice_document import NoticeDocument

logger = logging.getLogger(__name__)

# Max text sent to Claude (chars). ~6K tokens ≈ 24K chars.
MAX_ANALYSIS_TEXT = 24_000


# ── Step 1: Ensure extracted text exists ──────────────────────────


def _is_pdf_document(doc: NoticeDocument) -> bool:
    """Check if document looks like a PDF."""
    ft = (doc.file_type or "").lower()
    if "pdf" in ft:
        return True
    url = (doc.url or "").lower()
    return url.endswith(".pdf") or ".pdf?" in url


def _download_and_extract_text(doc: NoticeDocument) -> Optional[str]:
    """Download document to /tmp, verify it's a PDF, extract text, delete file.

    Smart Content-Type detection: checks server response before downloading
    the full body. Skips HTML/XML pages gracefully (marks as 'skipped'
    instead of 'failed') so the batch can move on to the next document.
    This handles TED docs with unknown file_type (e.g. cloud.3p.eu URLs).
    """
    import requests
    from app.documents.pdf_extractor import extract_text_from_pdf

    url = doc.url
    if not url:
        return None

    # Skip known inaccessible platforms (reCAPTCHA, auth walls)
    skip_domains = ("cloud.3p.eu",)
    url_lower = url.lower()
    for domain in skip_domains:
        if domain in url_lower:
            logger.info("Document %s on blocked domain %s, skipping", doc.id, domain)
            doc.download_status = "skipped"
            doc.download_error = f"Blocked domain: {domain} (reCAPTCHA)"
            doc.extraction_status = "skipped"
            doc.extraction_error = f"Blocked domain: {domain}"
            return None

    # Generate a temp filename from doc id
    suffix = ".pdf"
    tmp_dir = Path(tempfile.gettempdir()) / "procurewatch_docs"
    tmp_dir.mkdir(exist_ok=True)
    tmp_path = tmp_dir / f"{doc.id}{suffix}"

    try:
        logger.info("Downloading document %s from %s", doc.id, url[:120])
        resp = requests.get(url, timeout=60, stream=True, allow_redirects=True)
        resp.raise_for_status()

        # Check Content-Type BEFORE downloading the whole body
        content_type = (
            resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
        )

        # Skip non-downloadable content (HTML portals, XML feeds, etc.)
        skip_types = ("text/html", "text/xml", "application/xml", "text/plain")
        if any(content_type.startswith(t) for t in skip_types):
            logger.info(
                "Document %s is %s (not PDF), skipping", doc.id, content_type
            )
            resp.close()
            doc.content_type = content_type
            doc.download_status = "skipped"
            doc.download_error = f"Not a PDF: Content-Type={content_type}"
            doc.extraction_status = "skipped"
            doc.extraction_error = f"Not a PDF: {content_type}"
            if not doc.file_type:
                doc.file_type = content_type.split("/")[-1].upper()[:50]
            return None

        sha256_hash = hashlib.sha256()
        size = 0
        with open(tmp_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    sha256_hash.update(chunk)
                    size += len(chunk)
                    f.write(chunk)
                # Safety: skip files > 50 MB
                if size > 50 * 1024 * 1024:
                    logger.warning("Document %s too large (%d bytes), skipping", doc.id, size)
                    tmp_path.unlink(missing_ok=True)
                    doc.download_status = "skipped"
                    doc.download_error = f"Too large: {size} bytes"
                    doc.extraction_status = "skipped"
                    return None

        # Update download metadata
        doc.sha256 = sha256_hash.hexdigest()
        doc.file_size = size
        doc.content_type = content_type or "application/octet-stream"
        doc.downloaded_at = datetime.now(timezone.utc)
        doc.download_status = "ok"
        doc.download_error = None

        # Update file_type from Content-Type if not already set
        if not doc.file_type:
            if "pdf" in content_type:
                doc.file_type = "PDF"
            elif "zip" in content_type:
                doc.file_type = "ZIP"
            elif content_type:
                doc.file_type = content_type.split("/")[-1].upper()[:50]

        # Only extract text from PDFs
        if "pdf" not in (content_type or "") and not (doc.url or "").lower().endswith(".pdf"):
            logger.info("Document %s is %s, not extracting text", doc.id, content_type)
            doc.extraction_status = "skipped"
            doc.extraction_error = f"Not a PDF: {content_type}"
            return None

        # Extract text from PDF
        text = extract_text_from_pdf(tmp_path)
        # Strip NUL bytes — PostgreSQL TEXT columns reject \x00
        if text:
            text = text.replace("\x00", "")
        doc.extracted_text = text or ""
        doc.extracted_at = datetime.now(timezone.utc)
        doc.extraction_status = "ok"
        doc.extraction_error = None

        logger.info(
            "Extracted %d chars from document %s (%d bytes, %s)",
            len(text or ""), doc.id, size, content_type,
        )
        return text

    except Exception as e:
        logger.warning("Download/extract failed for document %s: %s", doc.id, e)
        doc.download_status = "failed"
        doc.download_error = str(e)[:2000]
        return None

    finally:
        tmp_path.unlink(missing_ok=True)


def ensure_extracted_text(db: Session, doc: NoticeDocument) -> Optional[str]:
    """Ensure document has extracted_text. Downloads + extracts if needed.

    Returns extracted text or None.
    """
    # Already have text
    if doc.extracted_text:
        return doc.extracted_text

    # Not a PDF → can't extract
    if not _is_pdf_document(doc):
        return None

    # Portal link (HTML), not a real PDF file
    if "publicprocurement.be" in (doc.url or ""):
        return None

    # Download + extract
    text = _download_and_extract_text(doc)
    db.commit()
    return text


# ── Step 2: AI analysis prompt ────────────────────────────────────


def _build_analysis_prompt(
    text: str,
    notice: ProcurementNotice,
    lang: str = "fr",
) -> str:
    """Build prompt for Claude to analyze extracted PDF text."""
    # Truncate
    if len(text) > MAX_ANALYSIS_TEXT:
        text = text[:MAX_ANALYSIS_TEXT] + "\n\n[... texte tronqué ...]"

    # Notice context
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

    lang_instructions = {
        "fr": "Réponds en français.",
        "nl": "Antwoord in het Nederlands.",
        "en": "Reply in English.",
        "de": "Antworte auf Deutsch.",
    }
    lang_instr = lang_instructions.get(lang, lang_instructions["fr"])

    return f"""Tu es un expert en marchés publics belges et européens.
Analyse le document ci-dessous (extrait d'un cahier des charges / avis de marché) et fournis une analyse structurée pour aider un entrepreneur à décider s'il doit soumissionner.

## Contexte du marché
{notice_context}

## Texte extrait du document
{text}

---

{lang_instr} Structure ta réponse en JSON avec exactement ces clés:

{{
  "objet": "Description claire de l'objet du marché (2-3 phrases)",
  "lots": ["Lot 1: ...", "Lot 2: ..."] ou null si pas de lots,
  "criteres_attribution": ["Critère 1 (pondération)", "Critère 2 (pondération)"] ou null,
  "conditions_participation": {{
    "capacite_technique": "Résumé des exigences techniques/références demandées" ou null,
    "capacite_financiere": "Résumé (CA min, ratio, etc.)" ou null,
    "agreations": ["Classe X catégorie Y", ...] ou null,
    "certifications": ["ISO 9001", "VCA", ...] ou null
  }},
  "budget": {{
    "valeur_estimee": "montant ou fourchette" ou null,
    "cautionnement": "5% du montant" ou null
  }},
  "calendrier": {{
    "date_limite": "JJ/MM/AAAA HH:MM" ou null,
    "duree_marche": "X mois" ou null,
    "delai_execution": "X jours ouvrables" ou null,
    "visite_obligatoire": "date et lieu" ou null
  }},
  "points_attention": [
    "Point clé 1 pour un soumissionnaire",
    "Point clé 2",
    "Point clé 3"
  ],
  "score_accessibilite_pme": "facile|moyen|difficile — évaluation de l'accessibilité pour une PME"
}}

Sois factuel. Si une information n'est pas dans le document, mets null. Ne devine pas."""


# ── Step 3: Call Claude API ───────────────────────────────────────


async def _call_claude(prompt: str) -> Optional[str]:
    """Call Anthropic API and return text response."""
    if not settings.anthropic_api_key:
        logger.warning("ANTHROPIC_API_KEY not set — cannot analyze document")
        return None

    try:
        import httpx

        async with httpx.AsyncClient(timeout=60.0) as client:
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
            "Claude analysis: input=%s output=%s tokens",
            usage.get("input_tokens", "?"),
            usage.get("output_tokens", "?"),
        )
        return text.strip() if text.strip() else None

    except ImportError:
        logger.error("httpx not installed — pip install httpx")
        return None
    except Exception as e:
        logger.exception("Claude API call failed: %s", e)
        return None


# ── Public API ────────────────────────────────────────────────────


async def analyze_document(
    db: Session,
    doc: NoticeDocument,
    notice: ProcurementNotice,
    lang: str = "fr",
    force: bool = False,
) -> Optional[dict]:
    """Analyze a document: download if needed → extract text → Claude analysis.

    Returns dict with analysis or None on failure.
    Caches result in doc.ai_analysis.
    """
    # Return cached if available
    if not force and doc.ai_analysis:
        return _parse_cached(doc)

    # Step 1: ensure we have text
    text = ensure_extracted_text(db, doc)
    if not text or len(text.strip()) < 50:
        return {
            "status": "no_text",
            "message": (
                "Le document ne contient pas de texte extractible "
                "(PDF scanné/image ou document vide)."
            ),
        }

    # Step 2: build prompt + call Claude
    prompt = _build_analysis_prompt(text, notice, lang=lang)
    raw_response = await _call_claude(prompt)

    if not raw_response:
        return {"status": "error", "message": "Impossible de générer l'analyse IA."}

    # Step 3: cache and return
    doc.ai_analysis = raw_response
    doc.ai_analysis_generated_at = datetime.now(timezone.utc)
    db.commit()

    return _parse_cached(doc)


def _parse_cached(doc: NoticeDocument) -> dict:
    """Parse cached ai_analysis (JSON string) into dict."""
    import json

    raw = doc.ai_analysis or ""

    # Try to extract JSON from markdown fences
    if "```" in raw:
        import re
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
        if match:
            raw = match.group(1)

    try:
        parsed = json.loads(raw)
        return {
            "status": "ok",
            "analysis": parsed,
            "generated_at": (
                doc.ai_analysis_generated_at.isoformat()
                if doc.ai_analysis_generated_at
                else None
            ),
            "cached": True,
        }
    except (json.JSONDecodeError, TypeError):
        # Fallback: return raw text
        return {
            "status": "ok",
            "analysis": {"raw_text": doc.ai_analysis},
            "generated_at": (
                doc.ai_analysis_generated_at.isoformat()
                if doc.ai_analysis_generated_at
                else None
            ),
            "cached": True,
        }


# ── Batch operations (admin) ─────────────────────────────────────


def batch_download_and_extract(
    db: Session,
    limit: int = 100,
    source: Optional[str] = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Download PDFs and extract text for documents that don't have it yet.

    Only processes PDF documents that haven't been downloaded/extracted.
    Downloads to /tmp (ephemeral), extracts text, stores in DB, deletes file.

    Args:
        db: Database session
        limit: Max documents to process
        source: Filter by notice source (BOSA_EPROC, TED_EU)
        dry_run: If True, just count eligible documents

    Returns:
        Stats dict
    """
    from sqlalchemy import text as sql_text

    # Count eligible: documents not yet processed (extraction_status IS NULL).
    # Includes docs with unknown file_type (e.g. cloud.3p.eu URLs from TED).
    # Excludes:
    #   - publicprocurement.be portal HTML pages (handled by BOSA crawler)
    #   - cloud.3p.eu (reCAPTCHA, not automatable)
    #   - docs already processed (extraction_status IS NOT NULL, includes 'skipped')
    # NOTE: ted.europa.eu is NOT excluded — after TED links fix, those are real PDFs
    where_clause = (
        "WHERE nd.extraction_status IS NULL "
        "  AND nd.url NOT LIKE '%%publicprocurement.be%%' "
        "  AND nd.url NOT LIKE '%%cloud.3p.eu%%' "
    )
    if source:
        where_clause += "  AND n.source = :source "

    count_sql = f"""
        SELECT COUNT(*) FROM notice_documents nd
        JOIN notices n ON n.id = nd.notice_id
        {where_clause}
    """
    params: dict[str, Any] = {}
    if source:
        params["source"] = source

    total_eligible = db.execute(sql_text(count_sql), params).scalar() or 0

    if dry_run:
        return {
            "total_eligible": total_eligible,
            "dry_run": True,
            "message": "Set dry_run=false to download and extract PDFs.",
        }

    # Fetch documents
    fetch_sql = f"""
        SELECT nd.id FROM notice_documents nd
        JOIN notices n ON n.id = nd.notice_id
        {where_clause}
        ORDER BY n.publication_date DESC NULLS LAST
        LIMIT :lim
    """
    params["lim"] = limit
    rows = db.execute(sql_text(fetch_sql), params).fetchall()

    stats: dict[str, Any] = {
        "total_eligible": total_eligible,
        "attempted": 0,
        "downloaded": 0,
        "extracted": 0,
        "skipped_not_pdf": 0,
        "skipped_too_large": 0,
        "errors": 0,
        "dry_run": False,
    }

    for (doc_id,) in rows:
        doc = db.query(NoticeDocument).filter(NoticeDocument.id == doc_id).first()
        if not doc:
            continue

        stats["attempted"] += 1

        try:
            text = _download_and_extract_text(doc)
            db.commit()

            if doc.download_status == "ok":
                stats["downloaded"] += 1
            elif doc.download_status == "skipped":
                if doc.download_error and "Too large" in doc.download_error:
                    stats["skipped_too_large"] += 1
                else:
                    stats["skipped_not_pdf"] += 1
            if text:
                stats["extracted"] += 1

        except Exception as e:
            logger.warning("Batch extract error for doc %s: %s", doc_id, e)
            stats["errors"] += 1
            db.rollback()

    logger.info(
        "Batch download: attempted=%d downloaded=%d extracted=%d errors=%d",
        stats["attempted"], stats["downloaded"], stats["extracted"], stats["errors"],
    )
    return stats
