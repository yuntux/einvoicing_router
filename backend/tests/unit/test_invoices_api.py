from stdnum.fr import siren as siren_stdnum


def _valid_siren(prefix8: str) -> str:
    """Complète un préfixe de 8 chiffres par la clé Luhn qui en fait un SIREN valide
    (les tests ont besoin de SIREN distincts mais valides, pas de vrais SIREN)."""
    for check_digit in range(10):
        candidate = f"{prefix8}{check_digit}"
        if siren_stdnum.is_valid(candidate):
            return candidate
    raise AssertionError(f"Aucune clé Luhn valide pour {prefix8!r}")


def test_simulate_reception_and_list_with_filters(client):
    company_resp = client.post(
        "/api/ihm/companies", json={"siren": "333333334", "name": "Ma Société"}
    )
    company = company_resp.json()

    simulate_resp = client.post(
        "/api/test/invoices/simulate",
        json={
            "company_id": company["id"],
            "emitter_siren": "444444442",
            "invoice_number": "F-2026-042",
            "invoice_date": "2026-03-01",
            "amount_total": 1200.50,
            "currency": "EUR",
        },
    )
    assert simulate_resp.status_code == 201
    invoice = simulate_resp.json()
    assert invoice["emitter_siren"] == "444444442"
    assert invoice["amount_total"] == 1200.50

    list_resp = client.get("/api/ihm/invoices", params={"emitter_siren": "444444442"})
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


def test_list_invoices_filter_by_emitter_name(client):
    company_siren = _valid_siren("33333399")
    emitter_siren = _valid_siren("44444499")
    company = client.post(
        "/api/ihm/companies", json={"siren": company_siren, "name": "Ma Société"}
    ).json()
    client.post(
        "/api/ihm/partners", json={"siren": emitter_siren, "name": "Fournisseur Alpha SAS"}
    )
    simulate_resp = client.post(
        "/api/test/invoices/simulate",
        json={
            "company_id": company["id"],
            "emitter_siren": emitter_siren,
            "invoice_number": "F-ALPHA-1",
            "invoice_date": "2026-03-01",
        },
    )
    assert simulate_resp.status_code == 201

    # Recherche partielle, insensible à la casse (§ 8.3).
    match_resp = client.get("/api/ihm/invoices", params={"emitter_name": "alpha"})
    assert match_resp.status_code == 200
    matched = match_resp.json()
    assert len(matched) == 1
    assert matched[0]["invoice_number"] == "F-ALPHA-1"

    no_match_resp = client.get("/api/ihm/invoices", params={"emitter_name": "Beta"})
    assert no_match_resp.json() == []


def test_get_invoice_not_found(client):
    response = client.get("/api/ihm/invoices/999999")
    assert response.status_code == 404
