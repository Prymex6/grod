"""Outgoing email.

With no SMTP host configured the message is only written to the log, so a
fresh checkout never tries to reach a mail server.
"""

import logging
from email.message import EmailMessage

import aiosmtplib

from grod.config import get_settings

logger = logging.getLogger(__name__)


async def send_email(*, to: str, subject: str, body: str) -> None:
    """Send one plain-text message; never raise at the call site."""
    settings = get_settings()
    if not settings.smtp_host:
        logger.info("Email not sent (no SMTP host). To: %s, subject: %s\n%s", to, subject, body)
        return

    message = EmailMessage()
    message["From"] = settings.email_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    try:
        await aiosmtplib.send(
            message,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            start_tls=settings.smtp_use_tls,
            username=settings.smtp_username or None,
            password=settings.smtp_password or None,
        )
    except aiosmtplib.SMTPException, OSError:
        # A broken mail server must not tell an attacker whether an account exists.
        logger.exception("Sending an email to %s failed", to)
