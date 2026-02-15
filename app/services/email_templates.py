"""HTML email templates for ProcureWatch notifications.

Design: matches the landing page aesthetic (Navy #1B2D4F + Teal #10b981, Inter font, clean cards).
Consolidated digest: one email per user grouping all active watchlists.
"""
import html
from datetime import datetime
from typing import Any, Optional


# ── Helpers ──────────────────────────────────────────────────────────

def _esc(value: Any) -> str:
    if value is None:
        return "—"
    if hasattr(value, "isoformat"):
        return value.isoformat()[:10] if value else "—"
    s = str(value).strip()
    return html.escape(s) if s else "—"


def _fmt_date(dt: Any) -> str:
    if not dt:
        return "—"
    if hasattr(dt, "strftime"):
        return dt.strftime("%d/%m/%Y")
    s = str(dt).strip()[:10]
    if len(s) == 10 and s[4] == "-":
        return f"{s[8:10]}/{s[5:7]}/{s[0:4]}"
    return s or "—"


def _deadline_style(deadline: Any) -> tuple[str, str]:
    """Return (color, label) based on urgency."""
    if not deadline:
        return "#94a3b8", "—"
    try:
        if hasattr(deadline, "date"):
            d = deadline.date()
        elif hasattr(deadline, "isoformat"):
            d = deadline
        else:
            d = datetime.fromisoformat(str(deadline)[:10]).date()
        days = (d - datetime.now().date()).days
        date_str = _fmt_date(deadline)
        if days < 0:
            return "#94a3b8", f"{date_str}"
        if days <= 3:
            return "#ef4444", f"{date_str} · {days}j"
        if days <= 7:
            return "#f59e0b", f"{date_str} · {days}j"
        return "#10b981", date_str
    except Exception:
        return "#94a3b8", _fmt_date(deadline)


def _source_pill(source: Any) -> str:
    s = str(source or "").upper()
    if "BOSA" in s:
        return '<span style="display:inline-block;background:#ecfdf5;color:#059669;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:700;letter-spacing:0.3px;">BOSA</span>'
    if "TED" in s:
        return '<span style="display:inline-block;background:#eff6ff;color:#2563eb;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:700;letter-spacing:0.3px;">TED</span>'
    return f'<span style="display:inline-block;background:#f1f5f9;color:#64748b;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:700;">{_esc(s)}</span>'


# ── Shared layout ────────────────────────────────────────────────────

_FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"

_HEADER = """
<tr><td style="padding:0;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#1B2D4F;border-radius:16px 16px 0 0;">
    <tr>
      <td style="padding:32px 36px 28px;">
        <table width="100%" cellpadding="0" cellspacing="0">
          <tr>
            <td>
              <div style="font-size:24px;font-weight:800;color:#ffffff;letter-spacing:-0.5px;font-family:{font};">
                <!--[if mso]><span style="font-size:24px;font-weight:bold;color:#ffffff;">&#x1F50D; ProcureWatch</span><![endif]-->
                <!--[if !mso]><!-->
                <span style="margin-right:6px;">&#x1F50D;</span> ProcureWatch
                <!--<![endif]-->
              </div>
              <div style="font-size:13px;color:#94a3b8;margin-top:6px;">
                Veille march&eacute;s publics &mdash; Belgique &amp; Europe
              </div>
            </td>
            <td align="right" style="vertical-align:top;">
              {badge}
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</td></tr>
""".replace("{font}", _FONT)

_FOOTER = """
<tr><td style="padding:28px 36px;background:#f8fafc;border-radius:0 0 16px 16px;">
  <table width="100%" cellpadding="0" cellspacing="0">
    <tr><td align="center">
      <div style="margin-bottom:16px;">
        <a href="{app_url}" style="display:inline-block;background:#10b981;color:#ffffff;padding:12px 36px;border-radius:10px;text-decoration:none;font-size:14px;font-weight:700;font-family:{font};">
          Voir toutes les opportunit&eacute;s &rarr;
        </a>
      </div>
      <div style="font-size:12px;color:#94a3b8;line-height:1.7;">
        Vous recevez cet email car vous avez activ&eacute; des alertes sur ProcureWatch.<br/>
        <a href="{app_url}" style="color:#64748b;text-decoration:underline;">G&eacute;rer mes alertes</a>
        &nbsp;&middot;&nbsp;
        <a href="{app_url}" style="color:#64748b;text-decoration:underline;">Se d&eacute;sinscrire</a>
      </div>
      <div style="font-size:11px;color:#cbd5e1;margin-top:12px;">
        &copy; {year} ProcureWatch &middot; Bruxelles, Belgique
      </div>
    </td></tr>
  </table>
</td></tr>
""".replace("{font}", _FONT)


# ── Notice type helpers ───────────────────────────────────────────────

_NOTICE_TYPE_LABELS: dict[str, tuple[str, str, str]] = {
    # key: (label, bg_color, text_color)
    "CONTRACT_NOTICE": ("Opportunité", "#ecfdf5", "#059669"),
    "cn": ("Opportunité", "#ecfdf5", "#059669"),
    "COMPETITION": ("Mise en concurrence", "#ecfdf5", "#059669"),
    "CONTRACT_AWARD_NOTICE": ("Attribution", "#fef3c7", "#d97706"),
    "can": ("Attribution", "#fef3c7", "#d97706"),
    "RESULT": ("Résultat", "#fef3c7", "#d97706"),
    "CONCESSION_AWARD_NOTICE": ("Concession", "#fef3c7", "#d97706"),
    "PRIOR_INFORMATION_NOTICE": ("Info préalable", "#f0f9ff", "#0369a1"),
    "pin": ("Info préalable", "#f0f9ff", "#0369a1"),
    "PLANNING": ("Planification", "#f0f9ff", "#0369a1"),
    "MODIFICATION_NOTICE": ("Modification", "#faf5ff", "#7c3aed"),
    "CHANGE": ("Rectificatif", "#faf5ff", "#7c3aed"),
    "DESIGN_CONTEST_NOTICE": ("Concours", "#fff7ed", "#ea580c"),
}


def _notice_type_pill(notice_type: Any) -> str:
    t = str(notice_type or "").strip()
    label, bg, color = _NOTICE_TYPE_LABELS.get(t, ("Avis", "#f1f5f9", "#475569"))
    return f'<span style="display:inline-block;background:{bg};color:{color};padding:3px 10px;border-radius:12px;font-size:11px;font-weight:700;letter-spacing:0.3px;">{html.escape(label)}</span>'


def _fmt_value(value: Any) -> str:
    """Format estimated value nicely: 1234567.89 → '1.234.567 €'"""
    if not value:
        return ""
    try:
        v = float(value)
        if v <= 0:
            return ""
        if v >= 1_000_000:
            return f"{v / 1_000_000:,.1f} M€".replace(",", ".")
        if v >= 1_000:
            return f"{v / 1_000:,.0f} K€".replace(",", ".")
        return f"{v:,.0f} €".replace(",", ".")
    except (ValueError, TypeError):
        return ""


# NUTS code → readable Belgian regions
_NUTS_REGIONS: dict[str, str] = {
    "BE1": "Bruxelles",
    "BE10": "Bruxelles",
    "BE100": "Bruxelles",
    "BE2": "Flandre",
    "BE21": "Anvers",
    "BE22": "Limbourg",
    "BE23": "Flandre orientale",
    "BE24": "Brabant flamand",
    "BE25": "Flandre occidentale",
    "BE3": "Wallonie",
    "BE31": "Brabant wallon",
    "BE32": "Hainaut",
    "BE33": "Liège",
    "BE34": "Luxembourg (BE)",
    "BE35": "Namur",
}


def _fmt_region(nuts_code: Any) -> str:
    if not nuts_code:
        return ""
    code = str(nuts_code).strip().upper()
    # Try exact, then progressively shorter
    for length in (len(code), 4, 3, 2):
        label = _NUTS_REGIONS.get(code[:length])
        if label:
            return label
    # Non-Belgian: show country-level
    if len(code) >= 2 and not code.startswith("BE"):
        return code[:2]  # e.g. "FR", "NL", "DE"
    return ""

def _notice_card(m: dict, idx: int) -> str:
    title = _esc(m.get("title", "Sans titre"))
    buyer = _esc(m.get("buyer", "—"))
    cpv = _esc(m.get("cpv", ""))
    pub_date = _fmt_date(m.get("publication_date"))
    deadline = m.get("deadline")
    dl_color, dl_label = _deadline_style(deadline)
    source = m.get("source", "")
    notice_type = m.get("notice_type", "")
    estimated_value = m.get("estimated_value")
    region = m.get("region", "")
    app_link = m.get("app_link", "")
    source_link = m.get("link", "")

    # Primary CTA: ProcureWatch app link; fallback to source
    primary_link = app_link or source_link
    link_html = ""
    if primary_link and str(primary_link).strip():
        link_html = f'<a href="{html.escape(str(primary_link).strip())}" style="display:inline-block;background:#1B2D4F;color:#ffffff;padding:8px 20px;border-radius:8px;text-decoration:none;font-size:12px;font-weight:600;font-family:{_FONT};">Voir le dossier &rarr;</a>'

    # Source link as secondary (small text)
    source_link_html = ""
    if source_link and app_link and str(source_link).strip():
        source_link_html = f'<a href="{html.escape(str(source_link).strip())}" style="color:#94a3b8;font-size:11px;text-decoration:underline;margin-left:12px;">source</a>'

    cpv_html = ""
    if cpv and cpv != "—":
        cpv_html = f'<span style="display:inline-block;background:#f1f5f9;color:#475569;padding:2px 8px;border-radius:6px;font-size:11px;font-weight:600;font-family:Consolas,Monaco,monospace;margin-left:8px;">{cpv}</span>'

    # Value badge
    value_str = _fmt_value(estimated_value)
    value_html = ""
    if value_str:
        value_html = f'<span style="display:inline-block;background:#fefce8;color:#a16207;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:700;margin-left:8px;">&#x1F4B0; {value_str}</span>'

    # Region
    region_str = _fmt_region(region)
    region_html = ""
    if region_str:
        region_html = f'<span style="color:#94a3b8;margin:0 6px;">&middot;</span><span style="color:#94a3b8;">&#x1F4CD;</span> {html.escape(region_str)}'

    bg = "#ffffff" if idx % 2 == 0 else "#fafbfc"

    return f"""
    <tr>
      <td style="padding:0;">
        <table width="100%" cellpadding="0" cellspacing="0" style="background:{bg};border-bottom:1px solid #f1f5f9;">
          <tr>
            <td style="padding:18px 24px;">
              <!-- Row 1: Type + Source + Value + Deadline -->
              <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:10px;">
                <tr>
                  <td>{_notice_type_pill(notice_type)}{_source_pill(source)}{cpv_html}{value_html}</td>
                  <td align="right">
                    <span style="font-size:12px;font-weight:700;color:{dl_color};font-family:{_FONT};">
                      &#x23F0; {dl_label}
                    </span>
                  </td>
                </tr>
              </table>
              <!-- Row 2: Title -->
              <div style="font-size:15px;font-weight:700;color:#1e293b;line-height:1.5;margin-bottom:8px;font-family:{_FONT};">
                {title}
              </div>
              <!-- Row 3: Buyer + Date + Region + CTA -->
              <table width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td style="font-size:12px;color:#64748b;font-family:{_FONT};line-height:1.6;">
                    <span style="color:#94a3b8;">&#x1F3E2;</span> {buyer}
                    <span style="color:#cbd5e1;margin:0 6px;">&middot;</span>
                    <span style="color:#94a3b8;">&#x1F4C5;</span> {pub_date}
                    {region_html}
                  </td>
                  <td align="right" style="white-space:nowrap;">{link_html}{source_link_html}</td>
                </tr>
              </table>
            </td>
          </tr>
        </table>
      </td>
    </tr>"""


# ── Consolidated digest (1 email, multiple watchlists) ───────────────

def build_consolidated_digest_html(
    user_name: str,
    watchlist_results: list[dict[str, Any]],
    app_url: str = "https://procurewatch.eu",
) -> str:
    """
    Build ONE consolidated email for a user with ALL their watchlist matches.

    watchlist_results: list of dicts, each with:
        - watchlist_name: str
        - watchlist_keywords: str (comma-sep keywords, for display)
        - matches: list[dict] (title, buyer, deadline, link, source, publication_date, cpv)
    """
    total = sum(len(wr["matches"]) for wr in watchlist_results)
    n_watchlists = len(watchlist_results)
    now_str = datetime.now().strftime("%d/%m/%Y")

    badge = f'<div style="background:#10b981;color:#ffffff;padding:7px 16px;border-radius:24px;font-size:13px;font-weight:700;font-family:{_FONT};white-space:nowrap;">{total} nouvelle{"s" if total != 1 else ""}</div>'

    # Build watchlist sections
    sections_html = ""
    for wr in watchlist_results:
        wl_name = html.escape(wr.get("watchlist_name", "Veille"))
        wl_keywords = html.escape(wr.get("watchlist_keywords", ""))
        matches = wr.get("matches", [])
        count = len(matches)

        keywords_html = ""
        if wl_keywords:
            pills = "".join(
                f'<span style="display:inline-block;background:#f0fdf4;color:#16a34a;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:600;margin:0 3px 3px 0;">{html.escape(k.strip())}</span>'
                for k in wl_keywords.split(",")[:5]
                if k.strip()
            )
            keywords_html = f'<div style="margin-top:8px;">{pills}</div>'

        # Section header
        sections_html += f"""
        <tr><td style="padding:0;">
          <table width="100%" cellpadding="0" cellspacing="0" style="background:#ffffff;">
            <tr>
              <td style="padding:20px 24px 12px;">
                <table width="100%" cellpadding="0" cellspacing="0">
                  <tr>
                    <td>
                      <div style="font-size:11px;text-transform:uppercase;letter-spacing:1.5px;color:#10b981;font-weight:700;font-family:{_FONT};">Veille</div>
                      <div style="font-size:17px;font-weight:800;color:#1B2D4F;margin-top:3px;letter-spacing:-0.3px;font-family:{_FONT};">
                        {wl_name}
                      </div>
                      {keywords_html}
                    </td>
                    <td align="right" style="vertical-align:top;">
                      <div style="background:#f1f5f9;color:#475569;padding:4px 12px;border-radius:12px;font-size:12px;font-weight:700;font-family:{_FONT};">
                        {count} r&eacute;sultat{"s" if count != 1 else ""}
                      </div>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
          </table>
        </td></tr>"""

        # Notice cards
        for i, m in enumerate(matches[:20]):
            sections_html += _notice_card(m, i)

        if count > 20:
            sections_html += f"""
            <tr><td style="padding:12px 24px;text-align:center;background:#fff;">
              <span style="font-size:13px;color:#64748b;font-family:{_FONT};">
                &hellip; et {count - 20} autres.
                <a href="{html.escape(app_url)}" style="color:#10b981;font-weight:600;text-decoration:none;">Voir tout &rarr;</a>
              </span>
            </td></tr>"""

        # Divider between watchlists
        sections_html += f"""
        <tr><td style="padding:0;">
          <div style="height:2px;background:linear-gradient(90deg,#10b981 0%,#e2e8f0 40%,#e2e8f0 100%);"></div>
        </td></tr>"""

    # Greeting
    greeting = html.escape(user_name) if user_name else "Bonjour"

    return f"""<!DOCTYPE html>
<html lang="fr" xmlns:v="urn:schemas-microsoft-com:vml">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <title>ProcureWatch &ndash; Vos nouvelles opportunit&eacute;s</title>
    <!--[if !mso]><!-->
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
        * {{ font-family: 'Inter', {_FONT}; }}
    </style>
    <!--<![endif]-->
</head>
<body style="margin:0;padding:0;background-color:#f1f5f9;-webkit-font-smoothing:antialiased;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#f1f5f9;">
<tr><td align="center" style="padding:24px 16px;">
<table role="presentation" width="640" cellpadding="0" cellspacing="0" style="max-width:640px;width:100%;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.06);">

    {_HEADER.replace("{badge}", badge)}

    <!-- Greeting -->
    <tr><td style="background:#ffffff;padding:24px 36px 16px;">
      <div style="font-size:15px;color:#334155;font-family:{_FONT};line-height:1.6;">
        {greeting},<br/>
        Voici vos <strong style="color:#1B2D4F;">{total} nouvelle{"s" if total != 1 else ""} opportunit&eacute;{"s" if total != 1 else ""}</strong>
        depuis {n_watchlists} veille{"s" if n_watchlists != 1 else ""} active{"s" if n_watchlists != 1 else ""}
        &mdash; <span style="color:#94a3b8;">{now_str}</span>
      </div>
    </td></tr>

    <!-- Watchlist sections -->
    {sections_html}

    {_FOOTER.replace("{app_url}", html.escape(app_url)).replace("{year}", str(datetime.now().year))}

</table>
</td></tr>
</table>
</body>
</html>"""


# ── Single watchlist digest (backward compat) ────────────────────────

def build_digest_html(
    watchlist_name: str,
    matches: list[dict[str, Any]],
    app_url: str = "https://procurewatch.eu",
) -> str:
    """Build digest for a single watchlist (wraps consolidated builder)."""
    return build_consolidated_digest_html(
        user_name="",
        watchlist_results=[{
            "watchlist_name": watchlist_name,
            "watchlist_keywords": "",
            "matches": matches,
        }],
        app_url=app_url,
    )


# ── Welcome email ────────────────────────────────────────────────────

def build_welcome_email_html(
    user_name: str = "",
    app_url: str = "https://procurewatch.eu",
) -> str:
    greeting = f"Bonjour {html.escape(user_name)}," if user_name else "Bonjour,"
    badge = '<div style="background:#10b981;color:#fff;padding:7px 16px;border-radius:24px;font-size:13px;font-weight:700;">Bienvenue !</div>'

    return f"""<!DOCTYPE html>
<html lang="fr">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Bienvenue sur ProcureWatch</title>
<style>@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');</style>
</head>
<body style="margin:0;padding:0;background:#f1f5f9;-webkit-font-smoothing:antialiased;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;">
<tr><td align="center" style="padding:24px 16px;">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.06);">

    {_HEADER.replace("{badge}", badge)}

    <tr><td style="background:#fff;padding:32px 36px;">
      <h2 style="color:#1B2D4F;font-size:20px;font-weight:800;margin:0 0 16px;font-family:{_FONT};">{greeting}</h2>
      <p style="color:#334155;font-size:15px;line-height:1.7;margin:0 0 16px;font-family:{_FONT};">
        Bienvenue sur <strong>ProcureWatch</strong>, votre plateforme de veille march&eacute;s publics.
      </p>

      <!-- Steps -->
      <table width="100%" cellpadding="0" cellspacing="0" style="margin:20px 0;">
        <tr>
          <td width="40" style="vertical-align:top;padding-right:12px;">
            <div style="width:32px;height:32px;border-radius:50%;background:#10b981;color:#fff;text-align:center;line-height:32px;font-size:14px;font-weight:800;">1</div>
          </td>
          <td style="padding-bottom:14px;font-size:14px;color:#334155;line-height:1.6;font-family:{_FONT};">
            <strong>Cr&eacute;ez une veille</strong> avec vos mots-cl&eacute;s et codes CPV
          </td>
        </tr>
        <tr>
          <td width="40" style="vertical-align:top;padding-right:12px;">
            <div style="width:32px;height:32px;border-radius:50%;background:#10b981;color:#fff;text-align:center;line-height:32px;font-size:14px;font-weight:800;">2</div>
          </td>
          <td style="padding-bottom:14px;font-size:14px;color:#334155;line-height:1.6;font-family:{_FONT};">
            <strong>Activez les alertes email</strong> pour recevoir un digest quotidien
          </td>
        </tr>
        <tr>
          <td width="40" style="vertical-align:top;padding-right:12px;">
            <div style="width:32px;height:32px;border-radius:50%;background:#10b981;color:#fff;text-align:center;line-height:32px;font-size:14px;font-weight:800;">3</div>
          </td>
          <td style="font-size:14px;color:#334155;line-height:1.6;font-family:{_FONT};">
            <strong>Ne ratez plus aucune opportunit&eacute;</strong>
          </td>
        </tr>
      </table>

      <div style="text-align:center;margin:28px 0 0;">
        <a href="{html.escape(app_url)}" style="display:inline-block;background:#10b981;color:#fff;padding:13px 40px;border-radius:10px;text-decoration:none;font-weight:700;font-size:15px;font-family:{_FONT};">
          Acc&eacute;der &agrave; ProcureWatch &rarr;
        </a>
      </div>
    </td></tr>

    <tr><td style="padding:20px 36px;text-align:center;background:#f8fafc;border-radius:0 0 16px 16px;">
      <div style="font-size:11px;color:#cbd5e1;">&copy; {datetime.now().year} ProcureWatch &middot; Bruxelles, Belgique</div>
    </td></tr>

</table>
</td></tr></table>
</body></html>"""
