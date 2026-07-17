import asyncio
import logging
import smtplib
from email.message import EmailMessage
from urllib.parse import quote

from app.core.config import Settings


logger = logging.getLogger(__name__)


def _send_sync(message: EmailMessage, settings: Settings) -> None:
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as client:
        if settings.smtp_use_tls:
            client.starttls()
        if settings.smtp_username:
            client.login(settings.smtp_username, settings.smtp_password)
        client.send_message(message)


async def send_email(to_email: str, subject: str, body: str, settings: Settings) -> None:
    if not settings.smtp_host:
        if settings.is_production:
            raise RuntimeError("SMTP is not configured")
        logger.warning("Development email to=%s subject=%s body=%s", to_email, subject, body)
        return
    message = EmailMessage()
    message["From"] = settings.smtp_from_email
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)
    await asyncio.to_thread(_send_sync, message, settings)


async def send_verification_email(to_email: str, token: str, settings: Settings) -> None:
    url = f"{settings.frontend_url}/?verify={quote(token)}"
    await send_email(to_email, "Verify your RyThM Chatbot account", f"Verify: {url}", settings)


async def send_reset_email(to_email: str, token: str, settings: Settings) -> None:
    url = f"{settings.frontend_url}/?reset={quote(token)}"
    await send_email(to_email, "Reset your RyThM Chatbot password", f"Reset: {url}", settings)
