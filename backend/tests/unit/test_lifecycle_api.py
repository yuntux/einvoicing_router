def _make_invoice_via_api(client, siren="777777777"):
    company = client.post(
        "/api/ihm/companies", json={"siren": siren, "name": "Ma Société"}
    ).json()
    invoice = client.post(
        "/api/ihm/invoices/simulate",
        json={
            "company_id": company["id"],
            "emitter_siren": "888888888",
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
