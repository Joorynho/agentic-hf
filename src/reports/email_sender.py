"""Optional email sender for daily reports. Requires SMTP config in .env."""
from __future__ import annotations

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


class EmailSender:
    """Send HTML emails via SMTP. Silently no-ops if not configured."""

    def __init__(self) -> None:
        self._host = os.environ.get("SMTP_HOST", "")
        self._port = int(os.environ.get("SMTP_PORT", "587"))
        self._user = os.environ.get("SMTP_USER", "")
        self._pass = os.environ.get("SMTP_PASS", "")
        self._from = os.environ.get("SMTP_FROM", "") or self._user
        self._to = os.environ.get("REPORT_EMAIL_TO", "")

    @property
    def is_configured(self) -> bool:
        return bool(self._host and self._user and self._pass and self._to)

    def send(self, subject: str, html_body: str) -> bool:
        """Send an HTML email. Returns True on success."""
        if not self.is_configured:
            return False
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self._from
            msg["To"] = self._to
            msg.attach(MIMEText(html_body, "html"))

            with smtplib.SMTP(self._host, self._port) as server:
                server.starttls()
                server.login(self._user, self._pass)
                server.sendmail(self._from, self._to.split(","), msg.as_string())
            logger.info("[email] Report sent to %s", self._to)
            return True
        except Exception as e:
            logger.error("[email] Failed to send report: %s", e)
            return False
