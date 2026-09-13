def _make_invoice_via_api(client, siren="777777772"):
    company = client.post(
        "/api/ihm/companies", json={"siren": siren, "name": "Ma Société"}
    ).json()
    invoice = client.post(
        "/api/test/invoices/simulate",
        json={
            "company_id": company["id"],
            "emitter_siren": "888888880",
            "invoice_number": "F-100",
            "invoice_date": "2026-02-01",
        },
    ).json()
    return invoice


def test_get_lifecycle_catalog(client):
    response = client.get("/api/ihm/lifecycle-catalog")
    assert response.status_code == 200
    body = response.json()
    keys = {s["key"] for s in body["statuses"]}
    assert "dispute" in keys
    assert "submitted" in keys
    manual_purchase = [s for s in body["statuses"] if s["manual_side"] == "purchase"]
    assert {s["key"] for s in manual_purchase} == {
        "approved",
        "partially_approved",
        "dispute",
        "suspended",
        "refused",
    }
    assert "TX_TVA_ERR" in body["reasons"]
    assert "NOA" in body["actions"]


def test_create_and_list_lifecycle_events(client):
    invoice = _make_invoice_via_api(client)

    create_resp = client.post(
        f"/api/ihm/invoices/{invoice['id']}/lifecycle-events",
        json={"status": "approved"},
    )
    assert create_resp.status_code == 201
    event = create_resp.json()
    assert event["status"] == "approved"

    list_resp = client.get(f"/api/ihm/invoices/{invoice['id']}/lifecycle-events")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    detail_resp = client.get(f"/api/ihm/invoices/{invoice['id']}")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["lifecycle_status"] == "approved"


def test_create_lifecycle_event_missing_reason_returns_422(client):
    invoice = _make_invoice_via_api(client)
    response = client.post(
        f"/api/ihm/invoices/{invoice['id']}/lifecycle-events",
        json={"status": "dispute"},
    )
    assert response.status_code == 422


def test_lifecycle_event_exposes_amount_currency_payments_and_attachments(client, db_session):
    """Champs stockés en base mais absents de la réponse jusque-là (§ 6.2) — un
    événement reçu automatiquement (jamais créé manuellement) peut porter un montant,
    des lignes de paiement et des pièces jointes."""
    from datetime import date

    from app.models.lifecycle import (
        EventDirection,
        LifecycleEvent,
        LifecycleEventAttachment,
        LifecycleEventPayment,
    )

    invoice = _make_invoice_via_api(client)

    event = LifecycleEvent(
        invoice_id=invoice["id"],
        company_id=invoice["company_id"],
        status="payment_sent",
        direction=EventDirection.IN,
        amount=100.5,
        currency="EUR",
    )
    db_session.add(event)
    db_session.commit()
    db_session.add(
        LifecycleEventPayment(event_id=event.id, amount=100.5, currency="EUR", payment_date=date(2026, 3, 1))
    )
    db_session.add(
        LifecycleEventAttachment(event_id=event.id, filename="justificatif.pdf", file_path="/tmp/justificatif.pdf")
    )
    db_session.commit()

    response = client.get(f"/api/ihm/invoices/{invoice['id']}/lifecycle-events")
    assert response.status_code == 200
    [payload] = [e for e in response.json() if e["id"] == event.id]
    assert payload["amount"] == 100.5
    assert payload["currency"] == "EUR"
    assert payload["payments"] == [
        {"id": payload["payments"][0]["id"], "amount": 100.5, "currency": "EUR", "payment_date": "2026-03-01"}
    ]
    assert payload["attachments"] == [
        {"id": payload["attachments"][0]["id"], "filename": "justificatif.pdf", "has_file": True}
    ]


def test_invoice_detail_exposes_afnor_flows(client, db_session):
    from app.models.lifecycle import AfnorFlow, AfnorFlowType, EventDirection

    invoice = _make_invoice_via_api(client)
    flow = AfnorFlow(
        invoice_id=invoice["id"],
        flow_id="flow-123",
        direction=EventDirection.IN,
        flow_type=AfnorFlowType.SUPPLIER_INVOICE_LC,
        state="done",
        file_bin=b"<xml/>",
    )
    db_session.add(flow)
    db_session.commit()

    response = client.get(f"/api/ihm/invoices/{invoice['id']}")
    assert response.status_code == 200
    [payload] = response.json()["afnor_flows"]
    assert payload["flow_id"] == "flow-123"
    assert payload["state"] == "done"
    assert payload["has_file"] is True

    download = client.get(f"/api/ihm/invoices/{invoice['id']}/afnor-flows/{flow.id}/download")
    assert download.status_code == 200
    assert download.content == b"<xml/>"


def test_download_afnor_flow_without_file_returns_404(client, db_session):
    from app.models.lifecycle import AfnorFlow, AfnorFlowType, EventDirection

    invoice = _make_invoice_via_api(client)
    flow = AfnorFlow(
        invoice_id=invoice["id"],
        direction=EventDirection.IN,
        flow_type=AfnorFlowType.SUPPLIER_INVOICE_LC,
        state="created",
    )
    db_session.add(flow)
    db_session.commit()

    response = client.get(f"/api/ihm/invoices/{invoice['id']}/afnor-flows/{flow.id}/download")
    assert response.status_code == 404


def test_download_lifecycle_event_attachment(client, db_session, tmp_path):
    from app.models.lifecycle import EventDirection, LifecycleEvent, LifecycleEventAttachment

    invoice = _make_invoice_via_api(client)
    event = LifecycleEvent(
        invoice_id=invoice["id"], company_id=invoice["company_id"], status="approved", direction=EventDirection.IN
    )
    db_session.add(event)
    db_session.commit()

    file_path = tmp_path / "justificatif.pdf"
    file_path.write_bytes(b"%PDF-1.4 fake content")
    attachment = LifecycleEventAttachment(
        event_id=event.id, filename="justificatif.pdf", file_path=str(file_path)
    )
    db_session.add(attachment)
    db_session.commit()

    response = client.get(
        f"/api/ihm/invoices/{invoice['id']}/lifecycle-events/{event.id}/attachments/{attachment.id}/download"
    )
    assert response.status_code == 200
    assert response.content == b"%PDF-1.4 fake content"


def test_download_lifecycle_event_attachment_missing_file_returns_404(client, db_session):
    from app.models.lifecycle import EventDirection, LifecycleEvent, LifecycleEventAttachment

    invoice = _make_invoice_via_api(client)
    event = LifecycleEvent(
        invoice_id=invoice["id"], company_id=invoice["company_id"], status="approved", direction=EventDirection.IN
    )
    db_session.add(event)
    db_session.commit()
    attachment = LifecycleEventAttachment(event_id=event.id, filename="missing.pdf", file_path=None)
    db_session.add(attachment)
    db_session.commit()

    response = client.get(
        f"/api/ihm/invoices/{invoice['id']}/lifecycle-events/{event.id}/attachments/{attachment.id}/download"
    )
    assert response.status_code == 404


def test_retry_afnor_flow_resends_after_a_failure(client, db_session, monkeypatch):
    from unittest.mock import patch

    from app.config import settings
    from app.models.lifecycle import AfnorFlow, AfnorFlowState

    monkeypatch.setattr(settings, "certified_platform_client_mode", "pyfrctc")
    invoice = _make_invoice_via_api(client)

    with patch("app.afnor.client.adapter.afnor_client_adapter.send_cdar") as mock_send:
        mock_send.side_effect = RuntimeError("SuperPDP unreachable")
        create_resp = client.post(
            f"/api/ihm/invoices/{invoice['id']}/lifecycle-events",
            json={"status": "suspended", "reason": "SIRET_ERR"},
        )
    event = create_resp.json()
    flow_id = event["afnor_flow"]["id"]
    assert event["afnor_flow"]["state"] == AfnorFlowState.ERROR.value

    with patch("app.afnor.client.adapter.afnor_client_adapter.send_cdar") as mock_send:
        mock_send.return_value = {"id": "superpdp-flow-99"}
        retry_resp = client.post(f"/api/ihm/invoices/{invoice['id']}/afnor-flows/{flow_id}/retry")

    assert retry_resp.status_code == 200
    retried = retry_resp.json()
    assert retried["afnor_flow"]["state"] == AfnorFlowState.SENT.value
    flow = db_session.get(AfnorFlow, flow_id)
    assert flow.flow_id == "superpdp-flow-99"


def test_retry_afnor_flow_with_overrides_updates_the_detail(client, monkeypatch):
    from unittest.mock import patch

    from app.config import settings
    from app.models.lifecycle import AfnorFlowState

    monkeypatch.setattr(settings, "certified_platform_client_mode", "pyfrctc")
    invoice = _make_invoice_via_api(client)

    with patch("app.afnor.client.adapter.afnor_client_adapter.send_cdar") as mock_send:
        mock_send.side_effect = RuntimeError("SuperPDP unreachable")
        create_resp = client.post(
            f"/api/ihm/invoices/{invoice['id']}/lifecycle-events",
            json={"status": "suspended", "reason": "SIRET_ERR"},
        )
    event = create_resp.json()
    flow_id = event["afnor_flow"]["id"]

    with patch("app.afnor.client.adapter.afnor_client_adapter.send_cdar") as mock_send:
        mock_send.return_value = {"id": "superpdp-flow-99"}
        retry_resp = client.post(
            f"/api/ihm/invoices/{invoice['id']}/afnor-flows/{flow_id}/retry",
            json={"reason": "SIRET_ERR", "comment": "corrigé"},
        )

    assert retry_resp.status_code == 200
    retried = retry_resp.json()
    assert retried["afnor_flow"]["state"] == AfnorFlowState.SENT.value
    assert retried["details"][0]["reason"] == "SIRET_ERR"
    assert retried["details"][0]["comment"] == "corrigé"


def test_retry_afnor_flow_rejects_a_flow_that_was_never_in_error(client, monkeypatch):
    from unittest.mock import patch

    from app.config import settings

    monkeypatch.setattr(settings, "certified_platform_client_mode", "pyfrctc")
    invoice = _make_invoice_via_api(client)

    with patch("app.afnor.client.adapter.afnor_client_adapter.send_cdar") as mock_send:
        mock_send.return_value = {"id": "superpdp-flow-1"}
        create_resp = client.post(
            f"/api/ihm/invoices/{invoice['id']}/lifecycle-events",
            json={"status": "approved"},
        )
    event = create_resp.json()
    flow_id = event["afnor_flow"]["id"]

    retry_resp = client.post(f"/api/ihm/invoices/{invoice['id']}/afnor-flows/{flow_id}/retry")
    assert retry_resp.status_code == 422
