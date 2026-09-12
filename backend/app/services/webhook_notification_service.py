"""WebhookNotificationService — notification push vers Odoo (spec.md § 4.4/§ 4.7,
lot 6) : complément au polling, pour réduire la latence de consultation d'Odoo.

Un échec de livraison suit le même cycle de retry que le routage mail (§ 4.7), géré
par `RetrySchedulerService`, mais son échec définitif reste **silencieux** — le
contenu reste de toute façon consultable par Odoo au prochain cycle de polling."""

from sqlalchemy.orm import Session

from app.models.invoicing import Invoice, InvoiceRouting
from app.models.referential import TargetApplication
from app.services.webhook_sender import HttpWebhookSender, OutgoingWebhook, WebhookSenderProtocol


def send_new_invoice_notification(
    db: Session,
    *,
    invoice: Invoice,
    routing: InvoiceRouting,
    target: TargetApplication,
    sender: WebhookSenderProtocol | None = None,
) -> bool:
    """Notifie l'application OAuth d'Odoo qu'une nouvelle facture lui a été routée.

    Retourne True en cas de succès, False sinon (jamais d'exception propagée). Ne fait
    rien et retourne False si aucune URL de webhook n'est configurée (repli silencieux
    sur le polling, § 4.7)."""
    if not target.webhook_url:
        return False

    sender = sender or HttpWebhookSender()
    webhook = OutgoingWebhook(
        url=target.webhook_url,
        payload={
            "event": "invoice.routed",
            "invoice_id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "emitter_siren": invoice.emitter_siren,
        },
    )
    try:
        sender.send(webhook)
    except Exception:
        return False
    return True


def notify_lifecycle_event(
    db: Session,
    *,
    invoice: Invoice,
    status: str,
    sender: WebhookSenderProtocol | None = None,
) -> None:
    """Notification "au mieux" (best effort) d'un nouveau message de cycle de vie —
    y compris ceux générés depuis l'IHM du routeur elle-même (§ 4.4) — vers chaque
    application cible API AFNOR déjà destinataire de cette facture. Volontairement non
    tracée dans le cycle de retry (§ 4.7) : un échec ici n'a aucune conséquence au-delà
    d'une latence supplémentaire, la facture restant consultable au prochain polling."""
    sender = sender or HttpWebhookSender()
    for routing in invoice.routings:
        target = routing.target_application
        if not target.webhook_url:
            continue
        webhook = OutgoingWebhook(
            url=target.webhook_url,
            payload={
                "event": "lifecycle_event.created",
                "invoice_id": invoice.id,
                "invoice_number": invoice.invoice_number,
                "status": status,
            },
        )
        try:
            sender.send(webhook)
        except Exception:
            continue
