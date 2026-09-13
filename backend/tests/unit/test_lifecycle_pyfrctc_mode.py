"""LifecycleService en mode `certified_platform_client_mode = "pyfrctc"` (spec.md § 4.2, lot 6) :
génération CDAR réelle + transmission via AfnorClientAdapter (mockée, sans réseau)."""

from datetime import date
from unittest.mock import patch

import pytest

from app.config import settings
from app.models.lifecycle import AfnorFlow, AfnorFlowState, LifecycleEvent
from app.models.referential import Company
from app.models.invoicing import Invoice
from app.services.lifecycle_service import (
    LifecycleValidationError,
    ManualEventInput,
    create_manual_event,
    retry_cdar,
)


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


def test_retry_cdar_resends_after_a_failure(db_session):
    invoice = _make_invoice(db_session)
    with patch("app.afnor.client.adapter.afnor_client_adapter.send_cdar") as mock_send:
        mock_send.side_effect = RuntimeError("SuperPDP unreachable")
        event = create_manual_event(
            db_session,
            invoice=invoice,
            side="purchase",
            data=ManualEventInput(status="suspended", reason="SIRET_ERR"),
        )
    flow = db_session.get(AfnorFlow, event.afnor_flow_id)
    assert flow.state == AfnorFlowState.ERROR

    with patch("app.afnor.client.adapter.afnor_client_adapter.send_cdar") as mock_send:
        mock_send.return_value = {"id": "superpdp-flow-99"}
        retry_cdar(db_session, invoice=invoice, flow=flow, event=event)

    mock_send.assert_called_once()
    db_session.refresh(flow)
    assert flow.state == AfnorFlowState.SENT
    assert flow.flow_id == "superpdp-flow-99"


def test_retry_cdar_rejects_a_flow_that_was_never_in_error(db_session):
    invoice = _make_invoice(db_session)
    with patch("app.afnor.client.adapter.afnor_client_adapter.send_cdar") as mock_send:
        mock_send.return_value = {"id": "superpdp-flow-1"}
        event = create_manual_event(
            db_session,
            invoice=invoice,
            side="purchase",
            data=ManualEventInput(status="approved"),
        )
    flow = db_session.get(AfnorFlow, event.afnor_flow_id)
    assert flow.state == AfnorFlowState.SENT

    with pytest.raises(LifecycleValidationError):
        retry_cdar(db_session, invoice=invoice, flow=flow, event=event)


def test_retry_cdar_with_overrides_updates_the_event_detail(db_session):
    invoice = _make_invoice(db_session)
    with patch("app.afnor.client.adapter.afnor_client_adapter.send_cdar") as mock_send:
        mock_send.side_effect = RuntimeError("SuperPDP unreachable")
        event = create_manual_event(
            db_session,
            invoice=invoice,
            side="purchase",
            data=ManualEventInput(status="suspended", reason="SIRET_ERR"),
        )
    flow = db_session.get(AfnorFlow, event.afnor_flow_id)

    with patch("app.afnor.client.adapter.afnor_client_adapter.send_cdar") as mock_send:
        mock_send.return_value = {"id": "superpdp-flow-99"}
        retry_cdar(
            db_session,
            invoice=invoice,
            flow=flow,
            event=event,
            overrides=ManualEventInput(status="suspended", reason="SIRET_ERR", comment="corrigé"),
        )

    db_session.refresh(event)
    assert event.details[0].reason == "SIRET_ERR"
    assert event.details[0].comment == "corrigé"
    assert flow.data_dict["MDG-37"][0]["MDT-113"] == "SIRET_ERR"
