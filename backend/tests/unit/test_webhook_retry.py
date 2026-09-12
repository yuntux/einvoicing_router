"""Notification webhook vers Odoo — même cycle de retry que le mail, mais repli
silencieux sans alerte au bout des 6 tentatives (spec.md § 4.4/§ 4.7, lot 6)."""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from unittest.mock import patch

from app.afnor.client.base import RawInvoice
from app.afnor.client.fake import FakeCertifiedPlatformClient
from app.models.invoicing import InvoiceRouting, TransferStatus
from app.models.referential import (
    Company,
    PartnerDirectory,
    RoutingMethod,
    TargetApplication,
)
from app.models.settings import BillingManagerContact
from app.services import retry_scheduler_service, routing_rule_service
from app.services.invoice_ingestion_service import ingest_from_client
from app.services.webhook_sender import OutgoingWebhook


@dataclass
class RecordingWebhookSender:
    fail: bool = False
    sent: list[OutgoingWebhook] = field(default_factory=list)
    calls: int = 0

    def send(self, webhook: OutgoingWebhook) -> None:
        self.calls += 1
        if self.fail:
            raise RuntimeError("webhook endpoint unreachable (test)")
        self.sent.append(webhook)


def _make_afnor_api_routing(db, *, webhook_url="https://odoo.example.com/webhook", siren="222222222"):
    company = Company(siren="111111111", name="Ma Société")
    db.add(company)
    db.commit()
    db.refresh(company)

    target = TargetApplication(
        name="Odoo",
        routing_method=RoutingMethod.AFNOR_API,
        company_id=company.id,
        parameters={
            "client_id": "client-odoo",
            "client_secret_hash": "hash",
            "app_type": "confidential",
            "webhook_url": webhook_url,
        },
    )
    db.add(target)
    db.commit()
    db.refresh(target)

    partner = PartnerDirectory(siren=siren, name="Fournisseur")
    db.add(partner)
    db.commit()
    db.refresh(partner)
    routing_rule_service.set_rule_active(
        db,
        partner_directory_id=partner.id,
        target_application_id=target.id,
        active=True,
    )

    raw = RawInvoice(
        certified_platform_flow_id="flow-webhook-1",
        emitter_siren=siren,
        invoice_number="F-webhook-1",
        invoice_date=date(2026, 1, 15),
        file_name="F-webhook-1.pdf",
        file_content=b"%PDF-fake-content",
    )
    result = ingest_from_client(db, company=company, client=FakeCertifiedPlatformClient([raw]))
    invoice = result.created[0]
    routing = (
        db.query(InvoiceRouting)
        .filter(
            InvoiceRouting.invoice_id == invoice.id,
            InvoiceRouting.target_application_id == target.id,
        )
        .one()
    )
    return invoice, routing


def test_run_send_cycle_sends_webhook_for_initial_routing(db_session):
    invoice, routing = _make_afnor_api_routing(db_session)
    assert routing.transfer_status == TransferStatus.TO_SEND

    webhook_sender = RecordingWebhookSender()
    retry_scheduler_service.run_send_cycle(db_session, webhook_sender=webhook_sender)

    db_session.refresh(routing)
    assert routing.transfer_status == TransferStatus.SENT
    assert len(webhook_sender.sent) == 1
    assert webhook_sender.sent[0].payload["event"] == "invoice.routed"


def test_run_send_cycle_without_webhook_url_is_never_dispatched(db_session):
    invoice, routing = _make_afnor_api_routing(db_session, webhook_url=None)

    webhook_sender = RecordingWebhookSender()
    retry_scheduler_service.run_send_cycle(db_session, webhook_sender=webhook_sender)

    db_session.refresh(routing)
    assert routing.transfer_status == TransferStatus.TO_SEND
    assert webhook_sender.calls == 0


def test_webhook_final_failure_is_silent_no_billing_alert(db_session):
    invoice, routing = _make_afnor_api_routing(db_session)
    db_session.add(BillingManagerContact(email="gestion@example.com"))
    db_session.commit()

    webhook_sender = RecordingWebhookSender(fail=True)
    now = datetime.utcnow()
    with patch("app.services.retry_scheduler_service.SmtpMailSender") as mock_smtp_cls:
        for _ in range(retry_scheduler_service.MAX_ATTEMPTS):
            retry_scheduler_service.run_send_cycle(
                db_session, now=now, webhook_sender=webhook_sender
            )
            db_session.refresh(routing)
            if routing.transfer_status == TransferStatus.FAILED_FINAL:
                break
            now = routing.next_attempt_at

        assert routing.transfer_status == TransferStatus.FAILED_FINAL
        assert routing.attempt_count == retry_scheduler_service.MAX_ATTEMPTS
        # Repli silencieux sur le polling (§ 4.7) : l'échec définitif d'une notification
        # webhook ne doit jamais instancier le sender mail par défaut des alertes.
        mock_smtp_cls.assert_not_called()


def test_run_send_cycle_ignores_retry_not_yet_due_for_webhook(db_session):
    invoice, routing = _make_afnor_api_routing(db_session)
    webhook_sender = RecordingWebhookSender(fail=True)
    now = datetime.utcnow()
    retry_scheduler_service.run_send_cycle(db_session, now=now, webhook_sender=webhook_sender)
    db_session.refresh(routing)
    assert routing.attempt_count == 1

    retry_scheduler_service.run_send_cycle(
        db_session, now=now + timedelta(minutes=5), webhook_sender=webhook_sender
    )
    db_session.refresh(routing)
    assert routing.attempt_count == 1
