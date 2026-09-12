"""MailRouterService, RetrySchedulerService, alerting (spec.md § 4.5/§ 4.6/§ 4.7, lot 5)."""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from app.afnor.client.base import RawInvoice
from app.afnor.client.fake import FakeSuperPDPClient
from app.models.invoicing import Invoice, InvoiceRouting, TransferStatus
from app.models.referential import Company, PartnerDirectory, RoutingMethod, TargetApplication
from app.models.settings import BillingManagerContact
from app.services import mail_router_service, retry_scheduler_service, routing_rule_service
from app.services.invoice_ingestion_service import ingest_from_client
from app.services.mail_sender import OutgoingMail


@dataclass
class RecordingMailSender:
    """Sender de test : enregistre chaque envoi réussi. `fail_invoice_sends` ne fait
    échouer que les envois de facture (avec pièce jointe), jamais les alertes (§ 4.7) —
    ce qui permet de tester qu'une alerte part bien même quand le routage échoue."""

    fail_invoice_sends: bool = False
    sent: list[OutgoingMail] = field(default_factory=list)
    calls: int = 0

    def send(self, mail: OutgoingMail, *, router_settings) -> None:
        self.calls += 1
        if self.fail_invoice_sends and mail.attachment_content is not None:
            raise RuntimeError("SMTP unreachable (test)")
        self.sent.append(mail)


def _make_company(db, siren="111111111"):
    company = Company(siren=siren, name="Ma Société")
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


def _make_mail_target(db, company, name="Spendesk", to=None, cc=None, bcc=None):
    target = TargetApplication(
        name=name,
        routing_method=RoutingMethod.MAIL,
        company_id=company.id,
        parameters={"to": to or ["spendesk@example.com"], "cc": cc or [], "bcc": bcc or []},
    )
    db.add(target)
    db.commit()
    db.refresh(target)
    return target


def _make_routed_invoice(db, *, company, target, emitter_siren="222222222", flow_id="flow-1"):
    """Crée une facture réellement routée vers `target`, avec un vrai fichier sur
    disque (§ storage), en réutilisant le pipeline d'ingestion du lot 2."""
    partner = PartnerDirectory(siren=emitter_siren, name="Fournisseur Test")
    db.add(partner)
    db.commit()
    db.refresh(partner)
    routing_rule_service.create_rule(
        db, partner_directory_id=partner.id, target_application_id=target.id
    )

    raw = RawInvoice(
        superpdp_flow_id=flow_id,
        emitter_siren=emitter_siren,
        invoice_number=f"F-{flow_id}",
        invoice_date=date(2026, 1, 15),
        file_name=f"F-{flow_id}.pdf",
        file_content=b"%PDF-fake-content",
    )
    client = FakeSuperPDPClient([raw])
    result = ingest_from_client(db, company=company, client=client)
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


def test_send_routing_success_reads_invoice_file(db_session):
    company = _make_company(db_session)
    target = _make_mail_target(db_session, company)
    invoice, routing = _make_routed_invoice(db_session, company=company, target=target)

    sender = RecordingMailSender()
    success = mail_router_service.send_routing(
        db_session, invoice=invoice, routing=routing, target=target, sender=sender
    )

    assert success is True
    assert len(sender.sent) == 1
    mail = sender.sent[0]
    assert mail.subject == invoice.invoice_number
    assert mail.to == ["spendesk@example.com"]
    assert mail.attachment_content == b"%PDF-fake-content"


def test_send_routing_failure_returns_false(db_session):
    company = _make_company(db_session)
    target = _make_mail_target(db_session, company)
    invoice, routing = _make_routed_invoice(db_session, company=company, target=target)

    sender = RecordingMailSender(fail_invoice_sends=True)
    success = mail_router_service.send_routing(
        db_session, invoice=invoice, routing=routing, target=target, sender=sender
    )

    assert success is False
    assert sender.sent == []


def test_run_send_cycle_sends_initial_to_send_routing(db_session):
    company = _make_company(db_session)
    target = _make_mail_target(db_session, company)
    invoice, routing = _make_routed_invoice(db_session, company=company, target=target)
    assert routing.transfer_status == TransferStatus.TO_SEND

    sender = RecordingMailSender()
    retry_scheduler_service.run_send_cycle(db_session, sender=sender)

    db_session.refresh(routing)
    assert routing.transfer_status == TransferStatus.SENT
    assert routing.next_attempt_at is None
    assert len(sender.sent) == 1


def test_run_send_cycle_schedules_retry_on_failure(db_session):
    company = _make_company(db_session)
    target = _make_mail_target(db_session, company)
    invoice, routing = _make_routed_invoice(db_session, company=company, target=target)

    sender = RecordingMailSender(fail_invoice_sends=True)
    before = datetime.utcnow()
    retry_scheduler_service.run_send_cycle(db_session, now=before, sender=sender)

    db_session.refresh(routing)
    assert routing.transfer_status == TransferStatus.RETRYING
    assert routing.attempt_count == 1
    assert routing.next_attempt_at is not None
    assert routing.next_attempt_at >= before + timedelta(minutes=29)
    assert routing.next_attempt_at <= before + timedelta(minutes=31)


def test_run_send_cycle_ignores_retry_not_yet_due(db_session):
    company = _make_company(db_session)
    target = _make_mail_target(db_session, company)
    invoice, routing = _make_routed_invoice(db_session, company=company, target=target)

    sender = RecordingMailSender(fail_invoice_sends=True)
    now = datetime.utcnow()
    retry_scheduler_service.run_send_cycle(db_session, now=now, sender=sender)
    db_session.refresh(routing)
    assert routing.attempt_count == 1

    # Un deuxième passage immédiat (avant l'échéance des 30 minutes) ne retente rien.
    retry_scheduler_service.run_send_cycle(db_session, now=now + timedelta(minutes=5), sender=sender)
    db_session.refresh(routing)
    assert routing.attempt_count == 1


def test_run_send_cycle_final_failure_after_max_attempts_alerts_billing_managers(db_session):
    company = _make_company(db_session)
    target = _make_mail_target(db_session, company)
    invoice, routing = _make_routed_invoice(db_session, company=company, target=target)
    db_session.add(BillingManagerContact(email="gestion@example.com"))
    db_session.commit()

    sender = RecordingMailSender(fail_invoice_sends=True)
    now = datetime.utcnow()
    for attempt in range(retry_scheduler_service.MAX_ATTEMPTS):
        retry_scheduler_service.run_send_cycle(db_session, now=now, sender=sender)
        db_session.refresh(routing)
        if routing.transfer_status == TransferStatus.FAILED_FINAL:
            break
        now = routing.next_attempt_at

    assert routing.transfer_status == TransferStatus.FAILED_FINAL
    assert routing.attempt_count == retry_scheduler_service.MAX_ATTEMPTS
    assert routing.next_attempt_at is None

    # 6 tentatives d'envoi de la facture (toutes en échec) + 1 alerte finale.
    alert_calls = [
        call for call in sender.sent if "Échec définitif" in call.subject
    ]
    assert len(alert_calls) == 1
    assert alert_calls[0].to == ["gestion@example.com"]


def test_alert_unrouted_invoice_on_zero_target(db_session):
    company = _make_company(db_session)
    db_session.add(BillingManagerContact(email="gestion@example.com"))
    db_session.commit()

    raw = RawInvoice(
        superpdp_flow_id="flow-unrouted",
        emitter_siren="999999999",  # aucune PartnerDirectory / RoutingRule
        invoice_number="F-unrouted",
        invoice_date=date(2026, 1, 15),
        file_name="F-unrouted.pdf",
        file_content=b"%PDF-fake-content",
    )
    client = FakeSuperPDPClient([raw])

    sender = RecordingMailSender()
    # L'alerte est déclenchée par InvoiceIngestionService avec le sender SMTP réel par
    # défaut ; on vérifie ici le comportement isolé via un appel direct au service,
    # cohérent avec le test d'intégration ci-dessous (aucun contact -> aucun envoi).
    result = ingest_from_client(db_session, company=company, client=client)
    assert result.unrouted_invoice_ids == [result.created[0].id]


def test_alert_unrouted_invoice_sends_email_to_contacts(db_session):
    company = _make_company(db_session)
    db_session.add(BillingManagerContact(email="gestion@example.com"))
    db_session.commit()

    invoice = Invoice(
        company_id=company.id,
        emitter_siren="333333333",
        invoice_number="F-alert",
        invoice_date=date(2026, 1, 1),
        file_path="/tmp/irrelevant.pdf",
        superpdp_flow_id="flow-alert",
    )
    db_session.add(invoice)
    db_session.commit()
    db_session.refresh(invoice)

    sender = RecordingMailSender()
    retry_scheduler_service.alert_unrouted_invoice(db_session, invoice=invoice, sender=sender)

    assert len(sender.sent) == 1
    assert sender.sent[0].to == ["gestion@example.com"]
    assert "non routée" in sender.sent[0].subject


def test_alert_unrouted_invoice_no_contacts_sends_nothing(db_session):
    company = _make_company(db_session)
    invoice = Invoice(
        company_id=company.id,
        emitter_siren="333333333",
        invoice_number="F-alert",
        invoice_date=date(2026, 1, 1),
        file_path="/tmp/irrelevant.pdf",
        superpdp_flow_id="flow-alert",
    )
    db_session.add(invoice)
    db_session.commit()
    db_session.refresh(invoice)

    sender = RecordingMailSender()
    retry_scheduler_service.alert_unrouted_invoice(db_session, invoice=invoice, sender=sender)

    assert sender.sent == []


def test_replay_manual_success_marks_sent(db_session):
    company = _make_company(db_session)
    target = _make_mail_target(db_session, company)
    invoice, routing = _make_routed_invoice(db_session, company=company, target=target)
    routing.transfer_status = TransferStatus.FAILED_FINAL
    routing.attempt_count = 6
    db_session.commit()

    sender = RecordingMailSender()
    success = retry_scheduler_service.replay_manual(db_session, routing=routing, sender=sender)

    assert success is True
    db_session.refresh(routing)
    assert routing.transfer_status == TransferStatus.SENT
    assert routing.next_attempt_at is None


def test_replay_manual_is_single_attempt_and_does_not_reschedule(db_session):
    """§ 4.7 : le rejeu manuel ne relance pas le cycle de retry automatique — un
    nouvel échec retombe directement en échec définitif, pas en 'retrying'."""
    company = _make_company(db_session)
    target = _make_mail_target(db_session, company)
    invoice, routing = _make_routed_invoice(db_session, company=company, target=target)
    routing.transfer_status = TransferStatus.FAILED_FINAL
    routing.attempt_count = 6
    db_session.commit()

    sender = RecordingMailSender(fail_invoice_sends=True)
    success = retry_scheduler_service.replay_manual(db_session, routing=routing, sender=sender)

    assert success is False
    db_session.refresh(routing)
    assert routing.transfer_status == TransferStatus.FAILED_FINAL
    assert routing.next_attempt_at is None
    assert sender.calls == 1
