"""Mailer: message assembly only. Never touches the network."""

from pathlib import Path

import pytest

from wohnung import mailer


def _report(tmp_path: Path) -> Path:
    md = tmp_path / "2026-09-14-0900.md"
    md.write_text(
        "# Report\n\nTop pick: <a href=\"https://example.com/x\">link</a>\n\n- item one\n",
        encoding="utf-8",
    )
    return md


def test_build_message_from_markdown_has_html_and_text(tmp_path):
    md = _report(tmp_path)
    msg = mailer.build_message(md, to=["a@example.com"], cc=["b@example.com"], sender="me@example.com")
    assert msg["To"] == "a@example.com"
    assert msg["Cc"] == "b@example.com"
    assert msg["From"] == "me@example.com"
    assert "2026-09-14-0900" in msg["Subject"]
    body = msg.get_body(preferencelist=("html",))
    assert body is not None
    assert "https://example.com/x" in body.get_content()
    assert msg.get_body(preferencelist=("plain",)) is not None
    assert not list(msg.iter_attachments())  # no sibling .pdf -> no attachment


def test_build_message_attaches_sibling_pdf(tmp_path):
    md = _report(tmp_path)
    md.with_suffix(".pdf").write_bytes(b"%PDF-1.4 fake")
    msg = mailer.build_message(md, to=["a@example.com"], cc=None, sender="me@example.com")
    atts = list(msg.iter_attachments())
    assert len(atts) == 1
    assert atts[0].get_filename() == "2026-09-14-0900.pdf"
    assert atts[0].get_content_type() == "application/pdf"


def test_build_message_from_pdf_path_attaches_it(tmp_path):
    pdf = tmp_path / "r.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    msg = mailer.build_message(pdf, to=["a@example.com"], cc=None, sender="me@example.com")
    assert [a.get_filename() for a in msg.iter_attachments()] == ["r.pdf"]


def test_markdown_to_html_basics():
    html = mailer.markdown_to_html("# T\n\n**bold** & <a href=\"u\">l</a>\n\n- a\n- b\n")
    assert "<h1>T</h1>" in html
    assert "<strong>bold</strong> &amp; <a href=\"u\">l</a>" in html
    assert "<ul>\n<li>a</li>\n<li>b</li>\n</ul>" in html


def test_send_report_requires_env(tmp_path, monkeypatch):
    for k in ("EMAIL_HOST", "EMAIL_HOST_USER", "EMAIL_HOST_PASSWORD"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(mailer, "load_env", lambda: None)  # don't read a real .env
    with pytest.raises(RuntimeError, match="EMAIL_HOST"):
        mailer.send_report(_report(tmp_path), to=["a@example.com"])


def test_send_report_uses_smtp(tmp_path, monkeypatch):
    monkeypatch.setattr(mailer, "load_env", lambda: None)
    monkeypatch.setenv("EMAIL_HOST", "smtp.example.com")
    monkeypatch.setenv("EMAIL_HOST_USER", "me@example.com")
    monkeypatch.setenv("EMAIL_HOST_PASSWORD", "pw")
    monkeypatch.delenv("EMAIL_PORT", raising=False)
    monkeypatch.delenv("EMAIL_USE_SSL", raising=False)
    monkeypatch.delenv("EMAIL_USE_TLS", raising=False)
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port):
            sent["host"], sent["port"] = host, port

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def ehlo(self):
            pass

        def starttls(self, context=None):
            sent["tls"] = True

        def login(self, u, p):
            sent["login"] = (u, p)

        def send_message(self, msg, to_addrs=None):
            sent["to_addrs"] = to_addrs

    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    rcpts = mailer.send_report(_report(tmp_path), to=["a@example.com"], cc=["b@example.com"])
    assert rcpts == ["a@example.com", "b@example.com"]
    assert sent == {"host": "smtp.example.com", "port": 587, "tls": True,
                    "login": ("me@example.com", "pw"), "to_addrs": rcpts}
