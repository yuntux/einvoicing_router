from datetime import date

import pytest

from app.models.invoicing import Invoice
from app.models.lifecycle import AfnorFlow, EventDirection
from app.models.referential import Company
from app.services import cdar_service
from app.services.lifecycle_service import (
    LifecycleValidationError,
    ManualEventInput,
    create_incoming_event,
    create_manual_event,
)


def _make_invoice(db, company_siren="555555555"):
    company = Company(siren=company_siren, name="Ma Société")
    db.add(company)
    db.commit()
    db.refresh(company)

    invoice = Invoice(
        company_id=company.id,
        emitter_siren="666666666",
        invoice_number="F-001",
        invoice_date=date(2026, 1, 1),
        file_path="/tmp/fake.pdf",
        certified_platform_flow_id="flow-abc",
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    return invoice


def test_create_manual_event_approved(db_session):
    invoice = _make_invoice(db_session)
    event = create_manual_event(
        db_session,
        invoice=invoice,
        side="purchase",
        data=ManualEventInput(status="approved"),
    )
    assert event.status == "approved"
    assert event.direction == "out"
    assert event.afnor_flow_id is not None
    assert invoice.lifecycle_status == "approved"


def test_create_manual_event_dispute_requires_reason(db_session):
    invoice = _make_invoice(db_session)
    with pytest.raises(LifecycleValidationError, match="motif est requis"):
        create_manual_event(
            db_session,
            invoice=invoice,
            side="purchase",
            data=ManualEventInput(status="dispute"),
        )


def test_create_manual_event_dispute_with_reason_succeeds(db_session):
    invoice = _make_invoice(db_session)
    event = create_manual_event(
        db_session,
        invoice=invoice,
        side="purchase",
        data=ManualEventInput(status="dispute", reason="TX_TVA_ERR", comment="Taux erroné"),
    )
    assert len(event.details) == 1
    assert event.details[0].reason == "TX_TVA_ERR"


def test_create_manual_event_refused_requires_confirmation(db_session):
    invoice = _make_invoice(db_session)
    with pytest.raises(LifecycleValidationError, match="confirmation explicite"):
        create_manual_event(
            db_session,
            invoice=invoice,
            side="purchase",
            data=ManualEventInput(status="refused", reason="DOUBLON"),
        )


def test_create_manual_event_refused_with_confirmation_succeeds(db_session):
    invoice = _make_invoice(db_session)
    event = create_manual_event(
        db_session,
        invoice=invoice,
        side="purchase",
        data=ManualEventInput(status="refused", reason="DOUBLON", confirmed=True),
    )
    assert event.status == "refused"


def test_create_manual_event_rejects_non_manual_status(db_session):
    invoice = _make_invoice(db_session)
    with pytest.raises(LifecycleValidationError, match="pas saisissable manuellement"):
        create_manual_event(
            db_session,
            invoice=invoice,
            side="purchase",
            data=ManualEventInput(status="payment_sent"),
        )


def test_create_manual_event_rejects_wrong_side(db_session):
    invoice = _make_invoice(db_session)
    with pytest.raises(LifecycleValidationError, match="réservé aux factures de vente"):
        create_manual_event(
            db_session,
            invoice=invoice,
            side="purchase",
            data=ManualEventInput(status="completed"),
        )


def _generate_cdar_bytes(invoice, *, status, **kwargs) -> bytes:
    """Génère un CDAR réel (round-trip avec le parsing testé ici) — pas d'échantillon
    externe disponible (aucun n'existe dans le dépôt ni dans `pyfrctc`), cf. exploration
    de conception."""
    data_dict = cdar_service.build_data_dict(
        invoice=invoice, buyer_company=invoice.company, status=status, **kwargs
    )
    return cdar_service.generate(data_dict)


def test_create_incoming_event_dispute_with_detail(db_session):
    invoice = _make_invoice(db_session)
    xml_bytes = _generate_cdar_bytes(
        invoice, status="dispute", reason="TX_TVA_ERR", action="NIN", comment="Taux erroné."
    )

    event = create_incoming_event(db_session, invoice=invoice, flow_id="cdar-flow-1", xml_bytes=xml_bytes)

    assert event is not None
    assert event.status == "dispute"
    assert event.direction == "in"
    assert len(event.details) == 1
    assert event.details[0].reason == "TX_TVA_ERR"
    assert event.details[0].action == "NIN"
    assert event.details[0].comment == "Taux erroné."
    assert invoice.lifecycle_status == "dispute"

    flow = db_session.query(AfnorFlow).filter(AfnorFlow.flow_id == "cdar-flow-1").one()
    assert flow.direction == EventDirection.IN
    assert flow.invoice_id == invoice.id


def test_create_incoming_event_records_state_flow_type(db_session):
    """Régression : les statuts purement techniques (`ap_received` "Reçue par la
    plateforme", etc.) transitent par le flux `StateSupplierInvoiceLC`, distinct de
    `SupplierInvoiceLC` — un CDAR reçu via ce flux doit rester rattaché à la facture
    et créer son événement, avec le bon `AfnorFlow.flow_type` (cf. l'incident du
    statut "Reçue par la plateforme" jamais visible côté Tricatel)."""
    invoice = _make_invoice(db_session)
    xml_bytes = _generate_cdar_bytes(invoice, status="ap_received")

    event = create_incoming_event(
        db_session,
        invoice=invoice,
        flow_id="cdar-flow-state-1",
        xml_bytes=xml_bytes,
        flow_type="StateSupplierInvoiceLC",
    )

    assert event is not None
    assert event.status == "ap_received"

    flow = db_session.query(AfnorFlow).filter(AfnorFlow.flow_id == "cdar-flow-state-1").one()
    assert flow.flow_type == "StateSupplierInvoiceLC"


def test_create_incoming_event_payment_sent_creates_payment_line(db_session):
    from app.models.lifecycle import LifecycleEventPayment

    invoice = _make_invoice(db_session)
    payment = LifecycleEventPayment(amount=123.45, currency="EUR", payment_date=date(2026, 1, 5))
    xml_bytes = _generate_cdar_bytes(invoice, status="payment_sent", payments=[payment])

    event = create_incoming_event(db_session, invoice=invoice, flow_id="cdar-flow-2", xml_bytes=xml_bytes)

    assert event is not None
    assert event.status == "payment_sent"
    assert len(event.payments) == 1
    assert event.payments[0].amount == 123.45
    assert event.payments[0].currency == "EUR"
    assert event.payments[0].payment_date == date(2026, 1, 5)


def test_create_incoming_event_is_idempotent(db_session):
    invoice = _make_invoice(db_session)
    xml_bytes = _generate_cdar_bytes(invoice, status="approved")

    first = create_incoming_event(db_session, invoice=invoice, flow_id="cdar-flow-3", xml_bytes=xml_bytes)
    second = create_incoming_event(db_session, invoice=invoice, flow_id="cdar-flow-3", xml_bytes=xml_bytes)

    assert first is not None
    assert second is None
    assert db_session.query(AfnorFlow).filter(AfnorFlow.flow_id == "cdar-flow-3").count() == 1


def test_create_incoming_event_skips_flow_id_already_used_outgoing(db_session):
    """Un CDAR reçu ne doit jamais être traité une seconde fois s'il correspond à un
    `flow_id` déjà connu sous forme d'`AfnorFlow` SORTANT — SuperPDP peut exposer un
    même flux technique côté `flow_direction="out"` (cf. l'incident du statut
    ap_received), l'idempotence doit donc porter sur le `flow_id` seul, pas sur le
    couple (flow_id, direction)."""
    invoice = _make_invoice(db_session)
    outgoing_flow = AfnorFlow(
        invoice_id=invoice.id,
        flow_id="shared-flow-id",
        direction=EventDirection.OUT,
        flow_type="SupplierInvoiceLC",
        syntax="CDAR",
    )
    db_session.add(outgoing_flow)
    db_session.commit()

    xml_bytes = _generate_cdar_bytes(invoice, status="approved")
    event = create_incoming_event(db_session, invoice=invoice, flow_id="shared-flow-id", xml_bytes=xml_bytes)

    assert event is None
    assert db_session.query(AfnorFlow).filter(AfnorFlow.flow_id == "shared-flow-id").count() == 1


def test_create_incoming_event_unknown_status_keeps_flow_but_no_event(db_session, monkeypatch):
    invoice = _make_invoice(db_session)
    xml_bytes = _generate_cdar_bytes(invoice, status="approved")
    monkeypatch.setattr(cdar_service, "resolve_status_key", lambda code: None)

    event = create_incoming_event(db_session, invoice=invoice, flow_id="cdar-flow-4", xml_bytes=xml_bytes)

    assert event is None
    flow = db_session.query(AfnorFlow).filter(AfnorFlow.flow_id == "cdar-flow-4").one()
    assert flow.direction == EventDirection.IN
    # Aucun LifecycleEvent créé pour ce flow (statut non reconnu) : le seul rattaché à
    # cette facture reste... aucun.
    assert invoice.lifecycle_status is None
