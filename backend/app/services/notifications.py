"""Email notification service.

Uses SMTP when configured, otherwise logs notifications to the console.
This allows the platform to work out-of-the-box without an SMTP server
while supporting real email delivery in production.
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import settings

logger = logging.getLogger(__name__)


def _get_smtp():
    """Create an SMTP connection if configured, else return None."""
    if not settings.smtp_host:
        return None
    try:
        smtp = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10)
        if settings.smtp_tls:
            smtp.starttls()
        if settings.smtp_user and settings.smtp_password:
            smtp.login(settings.smtp_user, settings.smtp_password)
        return smtp
    except Exception as e:
        logger.warning("SMTP connection failed: %s", e)
        return None


def send_email(to: str, subject: str, body_text: str, body_html: str | None = None) -> bool:
    """Send an email. Returns True if sent, False if logged only."""
    smtp = _get_smtp()
    if smtp is None:
        logger.info("[EMAIL-LOG] To: %s | Subject: %s | Body: %s", to, subject, body_text)
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg.attach(MIMEText(body_text, "plain"))
    if body_html:
        msg.attach(MIMEText(body_html, "html"))

    try:
        smtp.sendmail(settings.smtp_from, [to], msg.as_string())
        return True
    except Exception as e:
        logger.warning("Failed to send email to %s: %s", to, e)
        return False
    finally:
        try:
            smtp.quit()
        except Exception:
            pass


# ── Notification helpers ────────────────────────────────────────────


def _url(path: str) -> str:
    """Build a frontend URL from a path."""
    return f"{settings.frontend_url}{path}"


def notify_new_message(recipient_email: str, sender_name: str):
    """Notify a user about a new in-app message."""
    send_email(
        to=recipient_email,
        subject=f"New message from {sender_name} – NeighbourGood",
        body_text=(
            f"Hi! You have a new message from {sender_name} on NeighbourGood.\n\n"
            f"Log in to read and reply: {_url('/messages')}\n"
        ),
    )


def notify_booking_request(owner_email: str, borrower_name: str, resource_title: str):
    """Notify resource owner about a new borrow request."""
    send_email(
        to=owner_email,
        subject=f"New booking request for {resource_title} – NeighbourGood",
        body_text=(
            f"Hi! {borrower_name} would like to borrow your \"{resource_title}\".\n\n"
            f"Log in to approve or decline: {_url('/bookings')}\n"
        ),
    )


def notify_booking_status(borrower_email: str, resource_title: str, new_status: str):
    """Notify borrower about a booking status change."""
    send_email(
        to=borrower_email,
        subject=f"Booking {new_status}: {resource_title} – NeighbourGood",
        body_text=(
            f"Your booking for \"{resource_title}\" has been {new_status}.\n\n"
            f"Log in to see details: {_url('/bookings')}\n"
        ),
    )


def notify_password_reset(to_email: str, token: str):
    """Email a password reset link. The link carries the raw token; only its hash is stored."""
    send_email(
        to=to_email,
        subject="Reset your NeighbourGood password",
        body_text=(
            "Someone asked to reset the password for your NeighbourGood account.\n\n"
            "Choose a new password here (the link works once and expires in 1 hour): "
            f"{_url('/reset-password?token=' + token)}\n\n"
            "If you did not ask for this, you can ignore this email.\n"
        ),
    )
