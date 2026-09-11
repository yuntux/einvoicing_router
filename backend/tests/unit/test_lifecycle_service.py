from datetime import date

import pytest

from app.models.invoicing import Invoice
from app.models.referential import Company
from app.services.lifecycle_service import (
    LifecycleValidationError,
    ManualEventInput,
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
        superpdp_flow_id="flow-abc",
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
