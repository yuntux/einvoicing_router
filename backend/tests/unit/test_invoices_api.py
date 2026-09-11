def test_simulate_reception_and_list_with_filters(client):
    company_resp = client.post(
        "/api/ihm/companies", json={"siren": "333333333", "name": "Ma Société"}
    )
    company = company_resp.json()

    simulate_resp = client.post(
        "/api/ihm/invoices/simulate",
        json={
            "company_id": company["id"],
            "emitter_siren": "444444444",
            "invoice_number": "F-2026-042",
            "invoice_date": "2026-03-01",
            "amount_total": 1200.50,
            "currency": "EUR",
        },
    )
    assert simulate_resp.status_code == 201
    invoice = simulate_resp.json()
    assert invoice["emitter_siren"] == "444444444"
    assert invoice["amount_total"] == 1200.50

    list_resp = client.get(
        "/api/ihm/invoices", params={"emitter_siren": "444444444", "currency": "EUR"}
    )
    assert list_resp.status_code == 200
    invoices = list_resp.json()
    assert len(invoices) == 1
    assert invoices[0]["invoice_number"] == "F-2026-042"

    detail_resp = client.get(f"/api/ihm/invoices/{invoice['id']}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["routings"] == []
    assert detail["emitter_name"] is None  # pas d'entrée PartnerDirectory pour cet émetteur


def test_list_invoices_filter_no_match(client):
    response = client.get("/api/ihm/invoices", params={"emitter_siren": "999999999"})
    assert response.status_code == 200
    assert response.json() == []


def test_get_invoice_not_found(client):
    response = client.get("/api/ihm/invoices/999999")
    assert response.status_code == 404
