"""Abstraction d'envoi SMTP (spec.md § 4.5/§ 4.9.1).

Symétrique au client AFNOR "fake" (§ 4.1, lot 2) : `MailRouterService` et
`RetrySchedulerService` dépendent de `MailSenderProtocol`, pas directement de
`smtplib`, afin de rester testables sans serveur SMTP réel."""

from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol
import smtplib


@dataclass
class OutgoingMail:
    to: list[str]
    cc: list[str]
    bcc: list[str]
    subject: str
    body: str
    attachment_filename: str | None = None
    attachment_content: bytes | None = None


class MailSenderProtocol(Protocol):
    def send(self, mail: OutgoingMail, *, router_settings) -> None:
        """Envoie le message ; lève une exception en cas d'échec (charge à l'appelant
        de l'interpréter comme un échec d'envoi, § 4.7)."""
        ...


class SmtpMailSender:
    """Implémentation réelle, via le serveur SMTP mutualisé (`RouterSettings`,
    § 4.9.1) — un seul serveur d'envoi pour toutes les applications cibles mail."""

    def send(self, mail: OutgoingMail, *, router_settings) -> None:
        message = EmailMessage()
        message["Subject"] = mail.subject
        message["From"] = router_settings.smtp_from_address
        message["To"] = ", ".join(mail.to)
        if mail.cc:
            message["Cc"] = ", ".join(mail.cc)
        message.set_content(mail.body)
        if mail.attachment_content is not None:
            message.add_attachment(
                mail.attachment_content,
                maintype="application",
                subtype="octet-stream",
                filename=mail.attachment_filename or "piece-jointe",
            )

        recipients = [*mail.to, *mail.cc, *mail.bcc]
        with smtplib.SMTP(router_settings.smtp_host, router_settings.smtp_port) as smtp:
            if router_settings.smtp_use_tls:
                smtp.starttls()
            if router_settings.smtp_username:
                smtp.login(router_settings.smtp_username, router_settings.smtp_password or "")
            smtp.send_message(message, to_addrs=recipients)
