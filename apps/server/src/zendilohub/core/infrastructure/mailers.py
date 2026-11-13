import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from zendilohub.core.config import MailConfig
from zendilohub.core.domain.mailer import MailMessage

logger = logging.getLogger(__name__)


class SmtpMailer:
    def __init__(self, config: MailConfig) -> None:
        self._config = config

    async def send(self, message: MailMessage) -> None:
        await asyncio.to_thread(self._send, self._compose(message))

    def _compose(self, message: MailMessage) -> EmailMessage:
        mail = EmailMessage()
        mail['From'] = self._config.sender
        mail['To'] = message.to
        mail['Subject'] = message.subject
        mail['Date'] = formatdate(localtime=False)
        mail['Message-ID'] = make_msgid(domain=self._config.sender.rsplit('@', 1)[-1].rstrip('>'))
        mail.set_content(message.text)
        return mail

    def _send(self, mail: EmailMessage) -> None:
        config = self._config
        context = ssl.create_default_context()
        smtp_class = smtplib.SMTP_SSL if config.security == 'ssl' else smtplib.SMTP
        kwargs = {'context': context} if config.security == 'ssl' else {}
        with smtp_class(config.host or '', config.port, timeout=30, **kwargs) as smtp:  # type: ignore[arg-type]
            if config.security == 'starttls':
                smtp.starttls(context=context)
            if config.username:
                smtp.login(config.username, config.password or '')
            smtp.send_message(mail)


class LogMailer:
    """Without SMTP settings, e-mails (and the links in them) go to the log; fine for development."""

    async def send(self, message: MailMessage) -> None:
        logger.info(
            'E-mail not sent (no SMTP configured)',
            extra={'to': message.to, 'subject': message.subject, 'text': message.text},
        )
