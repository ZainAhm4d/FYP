"""
Email sender — supports Resend, SendGrid, and SMTP.

Priority order (first configured provider wins):
  1. Resend     — if RESEND_API_KEY is set       (resend.com, 3 000 free/month)
  2. SendGrid   — if SENDGRID_API_KEY is set
  3. SMTP       — if SMTP_HOST is set             (Gmail App Password, etc.)
  4. Dry-run    — logs to console; no email sent

Add ONE of the following blocks to .env:

  # Resend (recommended)
  RESEND_API_KEY=re_xxxxxxxxxxxxxxxxxxxxxxxx
  REPORT_FROM_EMAIL=you@yourdomain.com   # must be a verified domain in Resend

  # SendGrid
  SENDGRID_API_KEY=SG.xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
  REPORT_FROM_EMAIL=noreply@yourdomain.com

  # Gmail SMTP (App Password)
  SMTP_HOST=smtp.gmail.com
  SMTP_PORT=587
  SMTP_USER=you@gmail.com
  SMTP_PASSWORD=xxxx-xxxx-xxxx-xxxx
  REPORT_FROM_EMAIL=you@gmail.com
"""
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from app.core.config import settings


def send_report_email(
    recipient: str,
    subject: str,
    html_body: str,
    pdf_bytes: Optional[bytes] = None,
    pdf_filename: str = "report.pdf",
) -> bool:
    """
    Send an email. Returns True on success (or dry-run), False on error.
    Provider priority: Resend → SendGrid → SMTP → dry-run.
    """
    if getattr(settings, "RESEND_API_KEY", None):
        return _via_resend(recipient, subject, html_body, pdf_bytes, pdf_filename)
    if getattr(settings, "SENDGRID_API_KEY", None):
        return _via_sendgrid(recipient, subject, html_body, pdf_bytes, pdf_filename)
    if getattr(settings, "SMTP_HOST", None):
        return _via_smtp(recipient, subject, html_body, pdf_bytes, pdf_filename)

    print(
        f"[Email dry-run] No provider configured — would have sent:\n"
        f"  To: {recipient}\n"
        f"  Subject: {subject}\n"
        f"  Set RESEND_API_KEY (or SENDGRID_API_KEY / SMTP_HOST) in .env to enable real sending."
    )
    return True


# ── Resend ────────────────────────────────────────────────────────────────────

def _via_resend(recipient, subject, html_body, pdf_bytes, pdf_filename) -> bool:
    try:
        import resend
        import base64

        resend.api_key = settings.RESEND_API_KEY

        params: dict = {
            "from":    settings.REPORT_FROM_EMAIL,
            "to":      [recipient],
            "subject": subject,
            "html":    html_body,
        }
        if pdf_bytes:
            params["attachments"] = [{
                "filename": pdf_filename,
                "content":  list(pdf_bytes),   # Resend SDK accepts a list of byte ints
            }]

        resend.Emails.send(params)
        print(f"[Resend] Report sent to {recipient}")
        return True
    except Exception as exc:
        print(f"[Resend] Error sending to {recipient}: {exc}")
        return False


# ── SendGrid ──────────────────────────────────────────────────────────────────

def _via_sendgrid(recipient, subject, html_body, pdf_bytes, pdf_filename) -> bool:
    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import (
            Attachment, Disposition, FileContent, FileName, FileType, Mail,
        )
        import base64

        msg = Mail(
            from_email=settings.REPORT_FROM_EMAIL,
            to_emails=recipient,
            subject=subject,
            html_content=html_body,
        )
        if pdf_bytes:
            msg.attachment = Attachment(
                FileContent(base64.b64encode(pdf_bytes).decode()),
                FileName(pdf_filename),
                FileType("application/pdf"),
                Disposition("attachment"),
            )
        resp = SendGridAPIClient(settings.SENDGRID_API_KEY).send(msg)
        return resp.status_code in (200, 202)
    except Exception as exc:
        print(f"[SendGrid] Error sending to {recipient}: {exc}")
        return False


# ── SMTP ──────────────────────────────────────────────────────────────────────

def _via_smtp(recipient, subject, html_body, pdf_bytes, pdf_filename) -> bool:
    try:
        msg = MIMEMultipart("mixed")
        msg["Subject"] = subject
        msg["From"]    = settings.REPORT_FROM_EMAIL
        msg["To"]      = recipient

        msg.attach(MIMEText(html_body, "html"))

        if pdf_bytes:
            part = MIMEApplication(pdf_bytes, Name=pdf_filename)
            part["Content-Disposition"] = f'attachment; filename="{pdf_filename}"'
            msg.attach(part)

        port     = int(getattr(settings, "SMTP_PORT", 587))
        use_tls  = getattr(settings, "SMTP_USE_TLS", True)
        smtp_user = getattr(settings, "SMTP_USER", None)
        smtp_pass = getattr(settings, "SMTP_PASSWORD", None)

        with smtplib.SMTP(settings.SMTP_HOST, port, timeout=15) as srv:
            srv.ehlo()
            if use_tls:
                srv.starttls()
                srv.ehlo()
            if smtp_user and smtp_pass:
                srv.login(smtp_user, smtp_pass)
            srv.sendmail(settings.REPORT_FROM_EMAIL, [recipient], msg.as_string())

        print(f"[SMTP] Sent report to {recipient}")
        return True
    except Exception as exc:
        print(f"[SMTP] Error sending to {recipient}: {exc}")
        return False
