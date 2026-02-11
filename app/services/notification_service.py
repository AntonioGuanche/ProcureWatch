"""Notification service: consolidated watchlist digest (1 email per user).

Groups all active watchlists for a user, builds ONE email with all matches,
and sends via Resend/SMTP/file depending on EMAIL_MODE.
"""
import logging
import os
from typing import Any, Optional

from app.notifications.emailer import send_email_html
from app.services.email_templates import build_consolidated_digest_html, build_digest_html

logger = logging.getLogger(__name__)


def _extract_buyer_name(organisation_names: Any) -> str:
    """Extract buyer name from multilingual dict. Priority: FR > NL > EN > first."""
    if not organisation_names:
        return "—"
    if isinstance(organisation_names, dict):
        return (
            organisation_names.get("FR")
            or organisation_names.get("NL")
            or organisation_names.get("EN")
            or next(iter(organisation_names.values()), "—")
        )
    return str(organisation_names)


def _get_app_url() -> str:
    return os.environ.get("APP_URL", "https://procurewatch.eu")


def _normalize_matches(raw_matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize buyer field (can be dict from ORM or already string)."""
    out = []
    for m in raw_matches:
        entry = dict(m)
        buyer = entry.get("buyer")
        if isinstance(buyer, dict):
            entry["buyer"] = _extract_buyer_name(buyer)
        elif buyer is None:
            entry["buyer"] = "—"
        out.append(entry)
    return out


# ── Consolidated digest (preferred: 1 email per user) ────────────────

def send_consolidated_digest(
    to_address: str,
    user_name: str,
    watchlist_results: list[dict[str, Any]],
) -> None:
    """
    Send ONE consolidated email containing matches from ALL watchlists.

    watchlist_results: list of dicts, each with:
        - watchlist_name: str
        - watchlist_keywords: str (comma-sep, for display)
        - matches: list[dict] with title, buyer, deadline, link, source, etc.
    """
    # Filter out watchlists with no matches
    with_matches = [wr for wr in watchlist_results if wr.get("matches")]
    if not with_matches:
        return

    total = sum(len(wr["matches"]) for wr in with_matches)
    n_wl = len(with_matches)
    app_url = _get_app_url()

    # Normalize buyer fields
    for wr in with_matches:
        wr["matches"] = _normalize_matches(wr["matches"])

    subject = f"🔍 ProcureWatch: {total} nouvelle{'s' if total != 1 else ''} opportunité{'s' if total != 1 else ''}"
    if n_wl == 1:
        subject += f" – {with_matches[0]['watchlist_name']}"
    else:
        subject += f" depuis {n_wl} veilles"

    html_body = build_consolidated_digest_html(
        user_name=user_name,
        watchlist_results=with_matches,
        app_url=app_url,
    )

    send_email_html(to=to_address, subject=subject, html_body=html_body)
    logger.info(
        f"Consolidated digest sent: {total} matches from {n_wl} watchlist(s) → {to_address}"
    )


# ── Single watchlist notification (backward compat) ──────────────────

def send_watchlist_notification(
    watchlist: Any,
    new_matches: list[dict[str, Any]],
    to_address: Optional[str] = None,
) -> None:
    """Send digest for a single watchlist (legacy, used by admin test endpoint)."""
    if not new_matches:
        return

    watchlist_name = getattr(watchlist, "name", "Watchlist")
    to = to_address or getattr(watchlist, "notify_email", None) or "alerts@procurewatch.local"
    app_url = _get_app_url()

    normalized = _normalize_matches(new_matches)
    subject = f"🔍 ProcureWatch: {len(normalized)} nouvelle{'s' if len(normalized) != 1 else ''} opportunité{'s' if len(normalized) != 1 else ''} – {watchlist_name}"
    html_body = build_digest_html(watchlist_name, normalized, app_url=app_url)

    send_email_html(to=to, subject=subject, html_body=html_body)
    logger.info(f"Digest sent: {len(normalized)} matches → {to} (watchlist: {watchlist_name})")
