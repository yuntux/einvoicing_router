"""Abstraction d'envoi SMTP (spec.md § 4.5/§ 4.9.1).

Symétrique au client AFNOR "fake" (§ 4.1, lot 2) : `MailRouterService` et
`RetrySchedulerService` dépendent de `MailSenderProtocol`, pas directement de
`smtplib`, afin de rester testables sans serveur SMTP réel."""

from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol
import smtplib
import socket


class Ipv4SmtpConnection(smtplib.SMTP):
    """`smtplib.SMTP` forcé sur IPv4 — plusieurs hébergeurs de messagerie (constaté
    avec Exchange Online/Microsoft 365, code `4.7.25` "Service unavailable, sending
    IPv6 address ... must have reverse DNS record") rejettent une connexion SMTP
    entrante depuis une IPv6 sans enregistrement PTR (reverse DNS) associé — un
    réglage hors de portée du routeur lui-même (côté hébergeur), et que l'ordre de
    résolution DNS du système peut préférer IPv6 sans prévenir. On résout donc
    explicitement en IPv4 ici plutôt que de dépendre de cet ordre.

    `self._host` (utilisé par `starttls()` comme `server_hostname` pour la
    validation TLS/SNI du certificat, cf. `smtplib.SMTP.__init__`/`.starttls`) reste
    le nom d'hôte d'origine — seule la résolution de socket ci-dessous est forcée en
    IPv4, la validation du certificat continue de porter sur le nom d'hôte réel."""

    def _get_socket(self, host, port, timeout):
        if timeout is not None and not timeout:
            raise ValueError("Non-blocking socket (timeout=0) is not supported")
        ipv4_address = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)[0][4][0]
        return socket.create_connection((ipv4_address, port), timeout, self.source_address)


@dataclass
class OutgoingMail:
    to: list[str]
    cc: list[str]
    bcc: list[str]
    subject: str
    body: str
    attachment_filename: str | None = None
    attachment_content: bytes | None = None
    # Adresse d'expédition propre à l'application cible (§ 4.9.1) — `None` = utiliser
    # l'adresse globale `RouterSettings.smtp_from_address` (comportement par défaut,
    # inchangé pour les applications qui ne définissent pas ce champ).
    from_address: str | None = None


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
        message["From"] = mail.from_address or router_settings.smtp_from_address
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
        with Ipv4SmtpConnection(router_settings.smtp_host, router_settings.smtp_port) as smtp:
            if router_settings.smtp_use_tls:
                smtp.starttls()
            if router_settings.smtp_username:
                smtp.login(router_settings.smtp_username, router_settings.smtp_password or "")
            smtp.send_message(message, to_addrs=recipients)
