"""
Email sending: file mode (write to outbox) or SMTP mode.
Config-driven via app.core.config (EMAIL_MODE, EMAIL_*).
"""
import os
import smtplib
from datetime import datetime, timezone
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

from app.core.config import settings


def _outbox_dir() -> Path:
    """Resolve outbox dir; prefer EMAIL_OUTBOX_DIR from env at call time (for tests)."""
    raw = os.environ.get("EMAIL_OUTBOX_DIR") or settings.email_outbox_dir
    p = Path(raw)
    if not p.is_absolute():
        p = Path.cwd() / p
    return p


def _email_mode() -> str:
    """Parse EMAIL_MODE: strip whitespace and comments (e.g. 'file # use outbox' -> 'file'), default 'file'."""
    raw = getattr(settings, "email_mode", None) or os.environ.get("EMAIL_MODE") or "file"
    mode = str(raw).split("#")[0].strip().lower()
    return mode if mode else "file"


def send_email(to: str, subject: str, body: str, from_addr: Optional[str] = None) -> None:
    """
    Send email: if EMAIL_MODE=file write to EMAIL_OUTBOX_DIR with timestamped .txt (include headers).
    If EMAIL_MODE=smtp send via smtplib (TLS if EMAIL_SMTP_USE_TLS).
    """
    from_addr = from_addr or settings.email_from or "noreply@procurewatch.local"
    mode = _email_mode()

    if mode == "file":
        _send_email_file(to=to, subject=subject, body=body, from_addr=from_addr)
    else:
        _send_email_smtp(to=to, subject=subject, body=body, from_addr=from_addr)


def _send_email_file(to: str, subject: str, body: str, from_addr: str) -> None:
    """Write email to outbox as timestamped .txt file (headers + body)."""
    _write_email_to_outbox(to=to, subject=subject, body=body, from_addr=from_addr, content_type="text/plain")


def _write_email_to_outbox(
    to: str,
    subject: str,
    body: str,
    from_addr: str,
    content_type: str = "text/plain",
) -> None:
    """Write email to outbox as timestamped file (headers + body)."""
    outbox = _outbox_dir()
    outbox.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    ts = now.strftime("%Y-%m-%dT%H-%M-%S-") + f"{now.microsecond // 1000:03d}Z"
    ext = "html" if "html" in content_type else "txt"
    filename = f"email_{ts}.{ext}"
    path = outbox / filename
    ct = f"{content_type}; charset=utf-8" if "charset" not in content_type else content_type
    content = f"From: {from_addr}\nTo: {to}\nSubject: {subject}\nContent-Type: {ct}\n\n{body}"
    path.write_text(content, encoding="utf-8")


def send_email_html(
    to: str,
    subject: str,
    html_body: str,
    from_addr: Optional[str] = None,
) -> None:
    """
    Send HTML email: if EMAIL_MODE=file write to outbox with Content-Type: text/html; else SMTP sends MIMEText(html).
    Uses same mode parsing as send_email() (strip whitespace and comments).
    """
    from_addr = from_addr or settings.email_from or "noreply@procurewatch.local"
    mode = _email_mode()
    if mode == "file":
        _write_email_to_outbox(
            to=to,
            subject=subject,
            body=html_body,
            from_addr=from_addr,
            content_type="text/html; charset=utf-8",
        )
    else:
        _send_email_smtp(to=to, subject=subject, body=html_body, from_addr=from_addr, subtype="html")


def _send_email_smtp(
    to: str,
    subject: str,
    body: str,
    from_addr: str,
    subtype: str = "plain",
) -> None:
    """Send email via SMTP (TLS if configured). subtype: 'plain' or 'html'."""
    host = settings.email_smtp_host
    port = settings.email_smtp_port or (587 if settings.email_smtp_use_tls else 25)
    if not host:
        raise ValueError("EMAIL_SMTP_HOST is required when EMAIL_MODE=smtp")
    msg = MIMEText(body, subtype, "utf-8")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to
    if settings.email_smtp_use_tls:
        with smtplib.SMTP(host, port) as server:
            server.starttls()
            if settings.email_smtp_username and settings.email_smtp_password:
                server.login(settings.email_smtp_username, settings.email_smtp_password)
            server.sendmail(from_addr, [to], msg.as_string())
    else:
        with smtplib.SMTP(host, port) as server:
            if settings.email_smtp_username and settings.email_smtp_password:
                server.login(settings.email_smtp_username, settings.email_smtp_password)
            server.sendmail(from_addr, [to], msg.as_string())
    return None
