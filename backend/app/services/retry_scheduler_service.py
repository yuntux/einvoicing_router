"""RetrySchedulerService — cycle de retry des envois en échec, alerting et rejeu
manuel (spec.md § 4.7). Couvre deux natures d'envoi actif sur le même cycle
30 min x 3h : le routage mail (§ 4.5/§ 4.6) et, depuis le lot 6, la notification
webhook vers Odoo (§ 4.4) — la méthode API AFNOR elle-même (consultation en polling)
n'a pas de notion d'envoi actif/échec (§ 4.7)."""

from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.invoicing import Invoice, InvoiceRouting, TransferStatus
from app.models.referential import PartnerDirectory, RoutingMethod, TargetApplication
from app.services import (
    billing_manager_contact_service,
    mail_router_service,
    router_settings_service,
    webhook_notification_service,
)
from app.services.mail_sender import MailSenderProtocol, OutgoingMail, SmtpMailSender
from app.services.webhook_sender import WebhookSenderProtocol

RETRY_INTERVAL = timedelta(minutes=30)
RETRY_WINDOW = timedelta(hours=3)
# 3h / 30min = 6 tentatives au maximum après l'échec initial (§ 4.7).
MAX_ATTEMPTS = RETRY_WINDOW // RETRY_INTERVAL


def _pending_status_filter(now: datetime):
    return (InvoiceRouting.transfer_status == TransferStatus.TO_SEND) | (
        (InvoiceRouting.transfer_status == TransferStatus.RETRYING)
        & (InvoiceRouting.next_attempt_at.is_not(None))
        & (InvoiceRouting.next_attempt_at <= now)
    )


def run_send_cycle(
    db: Session,
    *,
    now: datetime | None = None,
    sender: MailSenderProtocol | None = None,
    webhook_sender: WebhookSenderProtocol | None = None,
) -> None:
    """Job périodique unique (appelé par le scheduler, § 4.7) : couvre à la fois le
    tout premier envoi d'une facture routée (statut `to_send`) et les rejeux
    automatiques programmés (statut `retrying`, échéance dépassée), pour les cibles
    mail et pour les notifications webhook des cibles API AFNOR qui en ont une
    configurée."""
    now = now or datetime.utcnow()

    mail_pending = (
        db.query(InvoiceRouting)
        .join(TargetApplication, InvoiceRouting.target_application_id == TargetApplication.id)
        .filter(TargetApplication.routing_method == RoutingMethod.MAIL)
        .filter(_pending_status_filter(now))
        .all()
    )
    for routing in mail_pending:
        _attempt(
            db,
            invoice=routing.invoice,
            routing=routing,
            target=routing.target_application,
            sender=sender,
            webhook_sender=webhook_sender,
        )

    webhook_pending = (
        db.query(InvoiceRouting)
        .join(TargetApplication, InvoiceRouting.target_application_id == TargetApplication.id)
        .filter(TargetApplication.routing_method == RoutingMethod.AFNOR_API)
        .filter(func.json_extract(TargetApplication.parameters, "$.webhook_url").is_not(None))
        .filter(_pending_status_filter(now))
        .all()
    )
    for routing in webhook_pending:
        _attempt(
            db,
            invoice=routing.invoice,
            routing=routing,
            target=routing.target_application,
            sender=sender,
            webhook_sender=webhook_sender,
        )


def replay_manual(
    db: Session,
    *,
    routing: InvoiceRouting,
    sender: MailSenderProtocol | None = None,
    webhook_sender: WebhookSenderProtocol | None = None,
) -> bool:
    """Rejeu manuel depuis l'IHM (§ 4.7) : essai unique, ne relance pas le cycle de
    retry automatique — un nouvel échec retombe directement en échec définitif, sans
    limite de nombre d'essais manuels ultérieurs."""
    target = routing.target_application
    invoice = routing.invoice
    success = _send(
        db, invoice=invoice, routing=routing, target=target, sender=sender, webhook_sender=webhook_sender
    )
    if success:
        routing.transfer_status = TransferStatus.SENT
        routing.next_attempt_at = None
    else:
        routing.transfer_status = TransferStatus.FAILED_FINAL
        routing.next_attempt_at = None
    db.commit()
    return success


def _send(
    db: Session,
    *,
    invoice: Invoice,
    routing: InvoiceRouting,
    target: TargetApplication,
    sender: MailSenderProtocol | None,
    webhook_sender: WebhookSenderProtocol | None,
) -> bool:
    if target.routing_method == RoutingMethod.MAIL:
        return mail_router_service.send_routing(
            db, invoice=invoice, routing=routing, target=target, sender=sender
        )
    return webhook_notification_service.send_new_invoice_notification(
        db, invoice=invoice, routing=routing, target=target, sender=webhook_sender
    )


def alert_unrouted_invoice(
    db: Session, *, invoice: Invoice, sender: MailSenderProtocol | None = None
) -> None:
    """Alerte "facture sans règle de routage active" (§ 4.7), envoyée une seule fois
    par facture (cf. `Invoice.unrouted_alert_sent`, posé par l'appelant) — jamais
    rejouée à chaque cycle de polling tant qu'elle reste sans cible."""
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


def alert_new_partner_without_routing_rule(
    db: Session, *, partner: PartnerDirectory, sender: MailSenderProtocol | None = None
) -> None:
    """Alerte envoyée une seule fois, à la création automatique d'un `PartnerDirectory`
    (§ 4.4, première facture reçue d'un fournisseur inconnu) qui n'a encore aucune
    règle de routage — ce fournisseur apparaît en rouge sur la page Règles de routage
    tant qu'aucune case n'y est cochée pour lui."""
    _send_alert(
        db,
        sender=sender,
        subject=f"Nouveau fournisseur détecté sans règle de routage : {partner.siren}",
        body=(
            f"Une facture vient d'être reçue d'un fournisseur inconnu jusqu'ici "
            f"(SIREN {partner.siren}), ajouté automatiquement à l'annuaire. Aucune règle "
            "de routage n'existe encore pour lui : configurez-en au moins une depuis la "
            "page Règles de routage pour que ses factures soient routées (il y apparaît "
            "en rouge tant que ce n'est pas fait)."
        ),
    )


def _attempt(
    db: Session,
    *,
    invoice: Invoice,
    routing: InvoiceRouting,
    target: TargetApplication,
    sender: MailSenderProtocol | None,
    webhook_sender: WebhookSenderProtocol | None = None,
) -> bool:
    success = _send(
        db, invoice=invoice, routing=routing, target=target, sender=sender, webhook_sender=webhook_sender
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
        if target.routing_method == RoutingMethod.MAIL:
            _alert_final_failure(db, invoice=invoice, target=target, sender=sender)
        # Sinon (notification webhook, § 4.7) : repli silencieux sur le polling
        # classique, pas d'alerte — le contenu reste consultable par Odoo.
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
