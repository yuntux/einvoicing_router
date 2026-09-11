"""RetrySchedulerService — cycle de retry des envois en échec, alerting et rejeu
manuel (spec.md § 4.7)."""

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.invoicing import Invoice, InvoiceRouting, TransferStatus
from app.models.referential import RoutingMethod, TargetApplication
from app.services import billing_manager_contact_service, mail_router_service, router_settings_service
from app.services.mail_sender import MailSenderProtocol, OutgoingMail, SmtpMailSender

RETRY_INTERVAL = timedelta(minutes=30)
RETRY_WINDOW = timedelta(hours=3)
# 3h / 30min = 6 tentatives au maximum après l'échec initial (§ 4.7).
MAX_ATTEMPTS = RETRY_WINDOW // RETRY_INTERVAL


def run_send_cycle(
    db: Session, *, now: datetime | None = None, sender: MailSenderProtocol | None = None
) -> None:
    """Job périodique unique (appelé par le scheduler, § 4.7) : couvre à la fois le
    tout premier envoi d'une facture routée (statut `to_send`) et les rejeux
    automatiques programmés (statut `retrying`, échéance dépassée).

    Ne s'applique qu'aux applications cibles de méthode mail — la méthode API AFNOR
    n'a pas de notion d'envoi actif/échec en mode polling (§ 4.7)."""
    now = now or datetime.utcnow()
    pending = (
        db.query(InvoiceRouting)
        .join(TargetApplication, InvoiceRouting.target_application_id == TargetApplication.id)
        .filter(TargetApplication.routing_method == RoutingMethod.MAIL)
        .filter(
            (InvoiceRouting.transfer_status == TransferStatus.TO_SEND)
            | (
                (InvoiceRouting.transfer_status == TransferStatus.RETRYING)
                & (InvoiceRouting.next_attempt_at.is_not(None))
                & (InvoiceRouting.next_attempt_at <= now)
            )
        )
        .all()
    )
    for routing in pending:
        _attempt(
            db,
            invoice=routing.invoice,
            routing=routing,
            target=routing.target_application,
            sender=sender,
        )


def replay_manual(
    db: Session, *, routing: InvoiceRouting, sender: MailSenderProtocol | None = None
) -> bool:
    """Rejeu manuel depuis l'IHM (§ 4.7) : essai unique, ne relance pas le cycle de
    retry automatique — un nouvel échec retombe directement en échec définitif, sans
    limite de nombre d'essais manuels ultérieurs."""
    target = routing.target_application
    invoice = routing.invoice
    success = mail_router_service.send_routing(
        db, invoice=invoice, routing=routing, target=target, sender=sender
    )
    if success:
        routing.transfer_status = TransferStatus.SENT
        routing.next_attempt_at = None
    else:
        routing.transfer_status = TransferStatus.FAILED_FINAL
        routing.next_attempt_at = None
    db.commit()
    return success


def alert_unrouted_invoice(
    db: Session, *, invoice: Invoice, sender: MailSenderProtocol | None = None
) -> None:
    """Alerte "facture sans règle de routage active" (§ 4.7), envoyée dès la réception
    de la facture (appelée par `InvoiceIngestionService`)."""
    _send_alert(
        db,
        sender=sender,
        subject=f"Facture non routée : {invoice.invoice_number}",
        body=(
            f"La facture {invoice.invoice_number} (émetteur SIREN {invoice.emitter_siren}) "
            "n'a résolu aucune application cible à sa réception. Une action corrective "
            "est nécessaire (création d'une règle de routage, ou routage manuel)."
        ),
    )


def _attempt(
    db: Session,
    *,
    invoice: Invoice,
    routing: InvoiceRouting,
    target: TargetApplication,
    sender: MailSenderProtocol | None,
) -> bool:
    success = mail_router_service.send_routing(
        db, invoice=invoice, routing=routing, target=target, sender=sender
    )
    if success:
        routing.transfer_status = TransferStatus.SENT
        routing.next_attempt_at = None
        db.commit()
        return True

    routing.attempt_count += 1
    if routing.attempt_count >= MAX_ATTEMPTS:
        routing.transfer_status = TransferStatus.FAILED_FINAL
        routing.next_attempt_at = None
        db.commit()
        _alert_final_failure(db, invoice=invoice, target=target, sender=sender)
    else:
        routing.transfer_status = TransferStatus.RETRYING
        routing.next_attempt_at = datetime.utcnow() + RETRY_INTERVAL
        db.commit()
    return False


def _alert_final_failure(
    db: Session,
    *,
    invoice: Invoice,
    target: TargetApplication,
    sender: MailSenderProtocol | None,
) -> None:
    _send_alert(
        db,
        sender=sender,
        subject=f"Échec définitif de routage : {invoice.invoice_number} -> {target.name}",
        body=(
            f"L'envoi de la facture {invoice.invoice_number} vers l'application cible "
            f"{target.name} a échoué après {MAX_ATTEMPTS} tentatives réparties sur 3 heures. "
            "L'envoi reste consultable en erreur et peut être rejoué manuellement depuis l'IHM."
        ),
    )


def _send_alert(
    db: Session, *, sender: MailSenderProtocol | None, subject: str, body: str
) -> None:
    contacts = billing_manager_contact_service.list_contacts(db)
    if not contacts:
        return
    sender = sender or SmtpMailSender()
    settings_row = router_settings_service.get_settings(db)
    mail = OutgoingMail(
        to=[contact.email for contact in contacts],
        cc=[],
        bcc=[],
        subject=subject,
        body=body,
    )
    try:
        sender.send(mail, router_settings=settings_row)
    except Exception:
        # Une alerte qui échoue à partir ne doit jamais faire échouer le flux appelant
        # (ingestion ou cycle de retry) — au pire l'incident reste visible en base.
        pass
