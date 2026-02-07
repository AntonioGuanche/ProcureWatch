"""Notification service: watchlist match digests (HTML email to outbox or SMTP)."""
import html
from typing import Any, Optional

from app.notifications.emailer import send_email_html


def _extract_buyer_name(organisation_names: Any) -> str:
    """Extract a single buyer name from multilingual dict. Priority: FR > NL > EN > first available > N/A."""
    if not organisation_names:
        return "N/A"
    if isinstance(organisation_names, dict):
        return (
            organisation_names.get("FR")
            or organisation_names.get("NL")
            or organisation_names.get("EN")
            or next(iter(organisation_names.values()), "N/A")
        )
    return str(organisation_names)


def _fmt(value: Any) -> str:
    """Format value for HTML: escape once for safety (charset=utf-8 in email). Use em dash if empty."""
    if value is None:
        return "—"
    if hasattr(value, "isoformat"):
        return value.isoformat()[:10] if value else "—"
    s = str(value).strip()
    if not s:
        return "—"
    return html.escape(s)


def _build_watchlist_digest_html(watchlist_name: str, new_matches: list[dict[str, Any]]) -> str:
    """Build HTML email body: heading + table of matches (title, buyer, deadline, link)."""
    rows = []
    for m in new_matches:
        title = _fmt(m.get("title"))
        buyer = _fmt(_extract_buyer_name(m.get("buyer")))
        deadline = _fmt(m.get("deadline"))
        link = m.get("link")
        if link and str(link).strip():
            link_esc = html.escape(str(link).strip())
            link_cell = f'<a href="{link_esc}">View</a>'
        else:
            link_cell = "—"
        rows.append(f"<tr><td>{title}</td><td>{buyer}</td><td>{deadline}</td><td>{link_cell}</td></tr>")
    table_rows = "\n".join(rows)
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Watchlist: {html.escape(watchlist_name)}</title></head>
<body>
<h2>New matches for watchlist: {html.escape(watchlist_name)}</h2>
<p>{len(new_matches)} new notice(s) matched.</p>
<table border="1" cellpadding="6" cellspacing="0" style="border-collapse: collapse;">
<thead><tr><th>Title</th><th>Buyer</th><th>Deadline</th><th>Link</th></tr></thead>
<tbody>
{table_rows}
</tbody>
</table>
<p><small>ProcureWatch watchlist notification</small></p>
</body>
</html>"""


def send_watchlist_notification(
    watchlist: Any,
    new_matches: list[dict[str, Any]],
    to_address: Optional[str] = None,
) -> None:
    """
    Send HTML email listing new matches for a watchlist (title, buyer, deadline, link).
    Uses existing EMAIL config; in FILE mode saves to data/outbox/ (or EMAIL_OUTBOX_DIR).
    Each match dict may have: title, buyer, deadline, link (optional: id, source, publication_date).
    """
    if not new_matches:
        return
    watchlist_name = getattr(watchlist, "name", "Watchlist")
    to = to_address or getattr(watchlist, "notify_email", None) or "alerts@procurewatch.local"
    subject = f"ProcureWatch: {len(new_matches)} new match(es) for {watchlist_name}"
    html_body = _build_watchlist_digest_html(watchlist_name, new_matches)
    send_email_html(to=to, subject=subject, html_body=html_body)
