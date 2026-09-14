"""Email a report via SMTP. Credentials come from the environment (loaded from .env at
the repo root), recipients from criteria.toml's [email] section. Named `mailer` (not
`email`) so it does not shadow the stdlib `email` package that smtplib depends on."""

from __future__ import annotations

import html
import os
import re
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent


def _bool(v: str | None, default: bool = False) -> bool:
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def load_env() -> None:
    """Load .env from the repo root into the environment (no-op if absent)."""
    load_dotenv(ROOT / ".env")


_ANCHOR_SPLIT = re.compile(r"(<a\s[^>]*>.*?</a>)", re.I | re.S)


def markdown_to_html(md: str) -> str:
    """Minimal, dependency-free markdown -> HTML good enough for an email body:
    headings, bullet lists, paragraphs, **bold**, and pass-through of existing <a> tags."""
    out: list[str] = []
    in_list = False

    def close_list():
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    for raw in md.splitlines():
        line = raw.rstrip()
        if not line:
            close_list()
            continue
        parts = _ANCHOR_SPLIT.split(line)
        esc = "".join(p if re.match(r"<a\s", p, re.I) else html.escape(p) for p in parts)
        esc = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc)
        m = re.match(r"^(#{1,6})\s+(.*)", esc)
        if m:
            close_list()
            lvl = len(m.group(1))
            out.append(f"<h{lvl}>{m.group(2)}</h{lvl}>")
            continue
        m = re.match(r"^\s*[-*]\s+(.*)", esc)
        if m:
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{m.group(1)}</li>")
            continue
        close_list()
        out.append(f"<p>{esc}</p>")
    close_list()
    return "<html><body>" + "\n".join(out) + "</body></html>"


def build_message(
    path, to: list[str], cc: list[str] | None, sender: str,
    subject: str | None = None, body_text: str | None = None,
) -> EmailMessage:
    """Assemble the email. A .md report becomes the HTML body (plain-text alternative
    kept) and its sibling .pdf, if present, is attached. A .pdf path is attached with a
    short body. Pure: no env, no network."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)
    cc = cc or []
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject or f"Wohnungsfinder report — {p.stem}"

    attachments: list[Path] = []
    if p.suffix.lower() == ".md":
        md = p.read_text(encoding="utf-8")
        msg.set_content(body_text or md)
        msg.add_alternative(markdown_to_html(md), subtype="html")
        sib = p.with_suffix(".pdf")
        if sib.exists():
            attachments.append(sib)
    else:
        msg.set_content(
            body_text
            or "Hi,\n\nHere is the latest apartment shortlist (PDF attached).\n\n— Wohnungsfinder"
        )
        attachments.append(p)
    for a in attachments:
        msg.add_attachment(a.read_bytes(), maintype="application", subtype="pdf", filename=a.name)
    return msg


def _smtp_settings() -> dict:
    load_env()
    missing = [
        k for k in ("EMAIL_HOST", "EMAIL_HOST_USER", "EMAIL_HOST_PASSWORD") if not os.environ.get(k)
    ]
    if missing:
        raise RuntimeError(f"missing email env var(s) {', '.join(missing)}; check the .env file")
    return {
        "host": os.environ["EMAIL_HOST"],
        "port": int(os.environ.get("EMAIL_PORT", "587")),
        "user": os.environ["EMAIL_HOST_USER"],
        "password": os.environ["EMAIL_HOST_PASSWORD"],
        "sender": os.environ.get("DEFAULT_FROM_EMAIL") or os.environ["EMAIL_HOST_USER"],
        "use_ssl": _bool(os.environ.get("EMAIL_USE_SSL"), default=False),
        "use_tls": _bool(os.environ.get("EMAIL_USE_TLS"), default=True),
    }


def _connect_and(s: dict, action) -> None:
    ctx = ssl.create_default_context()
    if s["use_ssl"]:
        with smtplib.SMTP_SSL(s["host"], s["port"], context=ctx) as conn:
            conn.login(s["user"], s["password"])
            action(conn)
    else:
        with smtplib.SMTP(s["host"], s["port"]) as conn:
            conn.ehlo()
            if s["use_tls"]:
                conn.starttls(context=ctx)
                conn.ehlo()
            conn.login(s["user"], s["password"])
            action(conn)


def send_report(
    path, to: list[str], cc: list[str] | None = None,
    subject: str | None = None, body_text: str | None = None,
) -> list[str]:
    """Send the report. Returns the full recipient list. Raises on missing config or
    SMTP failure (the caller surfaces it; never fail silently)."""
    s = _smtp_settings()
    msg = build_message(path, to=to, cc=cc, sender=s["sender"], subject=subject, body_text=body_text)
    recipients = list(to) + list(cc or [])
    _connect_and(s, lambda conn: conn.send_message(msg, to_addrs=recipients))
    return recipients


def verify_login() -> str:
    """Connect + authenticate without sending, to confirm credentials work."""
    s = _smtp_settings()
    _connect_and(s, lambda conn: None)
    return f"login OK as {s['user']} via {s['host']}:{s['port']}"
