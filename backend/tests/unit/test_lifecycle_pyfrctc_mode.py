"""LifecycleService en mode `certified_platform_client_mode = "pyfrctc"` (spec.md § 4.2, lot 6) :
génération CDAR réelle + transmission via AfnorClientAdapter (mockée, sans réseau)."""

from datetime import date
from unittest.mock import patch

import pytest

from app.config import settings
from app.models.lifecycle import AfnorFlow, AfnorFlowState
from app.models.referential import Company
from app.models.invoicing import Invoice
from app.services.lifecycle_service import ManualEventInput, create_manual_event


@pytest.fixture(autouse=True)
def _pyfrctc_mode(monkeypatch):
    monkeypatch.setattr(settings, "certified_platform_client_mode", "pyfrctc")
    yield


def _make_invoice(db):
    company = Company(siren="123456789", name="Acheteur SAS")
    db.add(company)
    db.commit()
    db.refresh(company)

    invoice = Invoice(
        company_id=company.id,
        emitter_siren="987654321",
        invoice_number="F-1",
        invoice_date=date(2026, 1, 1),
        file_path="/tmp/x.pdf",
        certified_platform_flow_id="flow-abc",
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    return invoice


def test_manual_event_generates_and_sends_real_cdar(db_session):
    invoice = _make_invoice(db_session)

    with patch("app.afnor.client.adapter.afnor_client_adapter.send_cdar") as mock_send:
        mock_send.return_value = {"id": "superpdp-flow-42"}
        event = create_manual_event(
            db_session,
            invoice=invoice,
            side="purchase",
            data=ManualEventInput(status="approved"),
        )

    mock_send.assert_called_once()
    flow = db_session.get(AfnorFlow, event.afnor_flow_id)
    assert flow.state == AfnorFlowState.SENT
    assert flow.flow_id == "superpdp-flow-42"
    assert flow.file_bin is not None
    assert flow.data_dict is not None


def test_manual_event_survives_transmission_failure(db_session):
    invoice = _make_invoice(db_session)

    with patch("app.afnor.client.adapter.afnor_client_adapter.send_cdar") as mock_send:
        mock_send.side_effect = RuntimeError("SuperPDP unreachable")
        event = create_manual_event(
            db_session,
            invoice=invoice,
            side="purchase",
            data=ManualEventInput(status="approved"),
        )

    # L'événement métier reste enregistré même si la transmission échoue.
    assert event.status == "approved"
    flow = db_session.get(AfnorFlow, event.afnor_flow_id)
    assert flow.state == AfnorFlowState.ERROR
