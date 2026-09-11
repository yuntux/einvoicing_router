"""MailRouterService — routage vers Spendesk et le comptable, par email
(spec.md § 4.5/§ 4.6) : même mécanisme générique de transfert par email pour les deux,
seuls les destinataires (portés par l'application cible) diffèrent."""

from pathlib import Path

from sqlalchemy.orm import Session

from app.models.invoicing import Invoice, InvoiceRouting
from app.models.referential import TargetApplication
from app.services import router_settings_service
from app.services.mail_sender import MailSenderProtocol, OutgoingMail, SmtpMailSender

ROUTING_EMAIL_BODY = (
    "Message automatique du routeur de factures électroniques : une facture reçue "
    "via la plateforme agréée (SuperPDP) vous a été transférée en pièce jointe."
)


def send_routing(
    db: Session,
    *,
    invoice: Invoice,
    routing: InvoiceRouting,
    target: TargetApplication,
    sender: MailSenderProtocol | None = None,
) -> bool:
    """Tente l'envoi mail pour une `InvoiceRouting` donnée. Ne gère ni le comptage des
    tentatives ni la planification du retry (§ 4.7) — c'est le rôle de
    `RetrySchedulerService`, seul appelant de cette fonction.

    Retourne True en cas de succès, False en cas d'échec (toute exception levée par le
    sender est interprétée comme un échec d'envoi, jamais propagée)."""
    sender = sender or SmtpMailSender()
    router_settings = router_settings_service.get_settings(db)

    mail = OutgoingMail(
        to=list(target.parameters.get("to") or []),
        cc=list(target.parameters.get("cc") or []),
        bcc=list(target.parameters.get("bcc") or []),
        subject=invoice.invoice_number,
        body=ROUTING_EMAIL_BODY,
        attachment_filename=Path(invoice.file_path).name,
        attachment_content=Path(invoice.file_path).read_bytes(),
    )

    try:
        sender.send(mail, router_settings=router_settings)
    except Exception:
        return False
    return True
