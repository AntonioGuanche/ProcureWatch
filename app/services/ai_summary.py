"""AI summary service: generate structured summaries from procurement notice metadata.

Phase 1 intelligence — uses structured fields only (title, description, CPV, org, value, deadline).
No document download required. Cost: ~€0.003/summary.

Usage:
    from app.services.ai_summary import generate_summary
    summary = await generate_summary(db, notice, lang="fr")
"""
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.notice import ProcurementNotice

logger = logging.getLogger(__name__)

# Country → language mapping for auto-translation
COUNTRY_LANG_MAP = {
    "BE": ["fr", "nl", "de"],
    "FR": ["fr"],
    "NL": ["nl", "en"],
    "DE": ["de"],
    "AT": ["de"],
    "LU": ["fr", "de"],
    "IT": ["it"],
    "ES": ["es"],
}


def _build_prompt(notice: ProcurementNotice, lang: str = "fr") -> str:
    """Build structured prompt for Claude from notice metadata."""
    # Extract organisation name
    org_name = None
    if notice.organisation_names and isinstance(notice.organisation_names, dict):
        for pref in ("fra", "FR", "fr", "eng", "EN", "en", "nld", "NL", "nl", "default"):
            if pref in notice.organisation_names:
                org_name = notice.organisation_names[pref]
                break
        if not org_name:
            org_name = next(iter(notice.organisation_names.values()), None)

    # Build context block
    parts = []
    if notice.title:
        parts.append(f"**Titre**: {notice.title}")
    if notice.description:
        # Truncate long descriptions
        desc = notice.description[:2000]
        if len(notice.description) > 2000:
            desc += "..."
        parts.append(f"**Description**: {desc}")
    if notice.cpv_main_code:
        parts.append(f"**Code CPV principal**: {notice.cpv_main_code}")
    if org_name:
        parts.append(f"**Pouvoir adjudicateur**: {org_name}")
    if notice.estimated_value:
        parts.append(f"**Valeur estimée**: {notice.estimated_value:,.2f} EUR")
    if notice.deadline:
        parts.append(f"**Date limite**: {notice.deadline.strftime('%d/%m/%Y %H:%M')}")
    if notice.notice_type:
        parts.append(f"**Type de marché**: {notice.notice_type}")
    if notice.form_type:
        parts.append(f"**Type de formulaire**: {notice.form_type}")
    if notice.nuts_codes and isinstance(notice.nuts_codes, list):
        parts.append(f"**Lieu**: {', '.join(notice.nuts_codes[:5])}")

    # CAN-specific fields
    if notice.award_winner_name:
        parts.append(f"**Adjudicataire**: {notice.award_winner_name}")
    if notice.award_value:
        parts.append(f"**Valeur du contrat**: {notice.award_value:,.2f} EUR")
    if notice.number_tenders_received:
        parts.append(f"**Offres reçues**: {notice.number_tenders_received}")

    notice_data = "\n".join(parts)

    lang_instructions = {
        "fr": "Réponds en français.",
        "nl": "Antwoord in het Nederlands.",
        "en": "Reply in English.",
        "de": "Antworte auf Deutsch.",
    }
    lang_instruction = lang_instructions.get(lang, lang_instructions["fr"])

    is_can = bool(notice.award_winner_name or notice.award_value)

    if is_can:
        return f"""Tu es un expert en marchés publics belges et européens. Analyse cet avis d'attribution de marché et fournis un résumé structuré.

{notice_data}

{lang_instruction} Structure ta réponse en exactement 5 points concis:
1. 🏗️ **Objet** : Quel est le marché attribué ? (1-2 phrases)
2. 🏢 **Adjudicateur & Adjudicataire** : Qui passe le marché et qui l'a remporté ?
3. 💰 **Montant & Concurrence** : Valeur du contrat et nombre d'offres reçues
4. 📍 **Lieu & Type** : Zone géographique et type de procédure
5. 💡 **À retenir** : Information clé pour un entrepreneur (benchmark de prix, niveau de concurrence, etc.)

Sois factuel et concis. Maximum 200 mots."""
    else:
        return f"""Tu es un expert en marchés publics belges et européens. Analyse cet avis de marché et fournis un résumé structuré pour aider un entrepreneur à décider s'il doit y répondre.

{notice_data}

{lang_instruction} Structure ta réponse en exactement 5 points concis:
1. 🏗️ **Objet** : De quoi s'agit-il ? (1-2 phrases claires)
2. 🏢 **Qui** : Quel pouvoir adjudicateur ?
3. 💰 **Budget & Conditions** : Valeur estimée, critères connus
4. 📅 **Échéance** : Date limite de soumission et délai restant
5. 💡 **À retenir** : Information clé ou point d'attention pour un soumissionnaire potentiel

Sois factuel et concis. Maximum 200 mots."""


async def generate_summary(
    db: Session,
    notice: ProcurementNotice,
    lang: str = "fr",
    force: bool = False,
) -> Optional[str]:
    """Generate AI summary for a notice. Returns cached version if available.

    Args:
        db: Database session.
        notice: The notice to summarize.
        lang: Target language (fr, nl, en, de).
        force: If True, regenerate even if cached.

    Returns:
        Summary text, or None if generation failed.
    """
    # Return cached if available and same language
    if not force and notice.ai_summary and notice.ai_summary_lang == lang:
        return notice.ai_summary

    if not settings.anthropic_api_key:
        logger.warning("ANTHROPIC_API_KEY not set — cannot generate AI summary")
        return None

    # Build prompt
    prompt = _build_prompt(notice, lang=lang)

    try:
        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": settings.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": settings.ai_model,
                    "max_tokens": settings.ai_summary_max_tokens,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            response.raise_for_status()
            data = response.json()

        # Extract text from response
        content = data.get("content", [])
        summary_text = ""
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                summary_text += block.get("text", "")

        if not summary_text.strip():
            logger.warning("Empty AI summary for notice %s", notice.id)
            return None

        # Cache in database
        notice.ai_summary = summary_text.strip()
        notice.ai_summary_lang = lang
        notice.ai_summary_generated_at = datetime.now(timezone.utc)
        db.commit()

        logger.info(
            "AI summary generated for notice %s (lang=%s, tokens=%s)",
            notice.id,
            lang,
            data.get("usage", {}).get("output_tokens", "?"),
        )
        return notice.ai_summary

    except ImportError:
        logger.error("httpx not installed — pip install httpx")
        return None
    except Exception as e:
        logger.exception("AI summary generation failed for notice %s: %s", notice.id, e)
        return None


def check_ai_usage(db: Session, user: Any) -> Optional[str]:
    """Check if user can use AI summaries. Returns error message or None.

    Handles monthly reset and plan limits.
    """
    from app.services.subscription import effective_plan, get_plan_limits

    plan = effective_plan(user)
    limits = get_plan_limits(plan)

    if limits.ai_summaries_per_month == 0:
        return (
            f"Votre plan {limits.display_name} n'inclut pas les résumés IA. "
            "Passez au plan supérieur pour y accéder."
        )

    # Unlimited
    if limits.ai_summaries_per_month == -1:
        return None

    # Monthly reset check
    now = datetime.now(timezone.utc)
    if user.ai_usage_reset_at:
        last_reset = user.ai_usage_reset_at
        if hasattr(last_reset, "tzinfo") and last_reset.tzinfo is None:
            from datetime import timezone as tz
            last_reset = last_reset.replace(tzinfo=tz.utc)
        # Reset if new month
        if now.month != last_reset.month or now.year != last_reset.year:
            user.ai_usage_count = 0
            user.ai_usage_reset_at = now
            db.commit()
    else:
        user.ai_usage_reset_at = now
        db.commit()

    if user.ai_usage_count >= limits.ai_summaries_per_month:
        return (
            f"Vous avez utilisé vos {limits.ai_summaries_per_month} résumés IA "
            f"pour ce mois (plan {limits.display_name}). "
            "Passez au plan supérieur pour en obtenir davantage."
        )

    return None


def increment_ai_usage(db: Session, user: Any) -> None:
    """Increment AI usage counter after successful generation."""
    user.ai_usage_count = (user.ai_usage_count or 0) + 1
    db.commit()
