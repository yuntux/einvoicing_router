"""API IHM RouterSettings + BillingManagerContact (spec.md § 6.1/§ 4.7, lot 5)."""


def test_get_router_settings_returns_defaults(client):
    response = client.get("/api/ihm/settings")
    assert response.status_code == 200
    body = response.json()
    assert body["technical_log_retention_days"] == 15 * 365
    assert body["smtp_port"] == 587


def test_update_router_settings(client):
    response = client.put(
        "/api/ihm/settings",
        json={
            "smtp_host": "smtp.example.com",
            "smtp_port": 25,
            "smtp_from_address": "routeur@example.com",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["smtp_host"] == "smtp.example.com"
    assert body["smtp_port"] == 25
    assert body["smtp_from_address"] == "routeur@example.com"

    # Persisté : un GET ultérieur voit la même valeur.
    response = client.get("/api/ihm/settings")
    assert response.json()["smtp_host"] == "smtp.example.com"


def test_billing_manager_contacts_crud(client):
    response = client.post(
        "/api/ihm/settings/billing-manager-contacts", json={"email": "gestion@example.com"}
    )
    assert response.status_code == 201
    contact_id = response.json()["id"]

    response = client.get("/api/ihm/settings/billing-manager-contacts")
    assert response.status_code == 200
    assert [c["email"] for c in response.json()] == ["gestion@example.com"]

    response = client.delete(f"/api/ihm/settings/billing-manager-contacts/{contact_id}")
    assert response.status_code == 204

    response = client.get("/api/ihm/settings/billing-manager-contacts")
    assert response.json() == []
