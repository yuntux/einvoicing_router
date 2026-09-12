"""Écritures globales réservées aux administrateurs (§ NF4) : configuration générale
(SMTP, allowlist IP), gestionnaires de facturation, création d'entreprise — aucune de
ces actions n'est cantonnée au périmètre d'un utilisateur restreint, donc aucune
d'elles ne doit lui être ouverte."""

from app.config import settings


def _login_as_first_admin(client, email="admin@example.com"):
    """Premier compte connecté en mode dev -> admin (amorçage, cf. test_users_api.py)."""
    client.get("/api/ihm/auth/login", params={"email": email}, follow_redirects=False)


def _login_as_regular_user(client, admin_email, user_email):
    _login_as_first_admin(client, admin_email)
    client.post("/api/ihm/users", json={"email": user_email})
    client.post("/api/ihm/auth/logout")
    client.get("/api/ihm/auth/login", params={"email": user_email}, follow_redirects=False)


def test_update_router_settings_requires_admin(client, monkeypatch):
    monkeypatch.setattr(settings, "oidc_mode", "dev")
    _login_as_regular_user(client, "admin1@example.com", "user1@example.com")

    response = client.put("/api/ihm/settings", json={"smtp_host": "smtp.example.com"})
    assert response.status_code == 403


def test_update_router_settings_works_for_admin(client, monkeypatch):
    monkeypatch.setattr(settings, "oidc_mode", "dev")
    _login_as_first_admin(client, "admin2@example.com")

    response = client.put("/api/ihm/settings", json={"smtp_host": "smtp.example.com"})
    assert response.status_code == 200


def test_create_billing_manager_contact_requires_admin(client, monkeypatch):
    monkeypatch.setattr(settings, "oidc_mode", "dev")
    _login_as_regular_user(client, "admin3@example.com", "user3@example.com")

    response = client.post("/api/ihm/settings/billing-manager-contacts", json={"email": "x@example.com"})
    assert response.status_code == 403


def test_delete_billing_manager_contact_requires_admin(client, monkeypatch, db_session):
    monkeypatch.setattr(settings, "oidc_mode", "dev")
    _login_as_first_admin(client, "admin4@example.com")
    contact = client.post(
        "/api/ihm/settings/billing-manager-contacts", json={"email": "y@example.com"}
    ).json()
    # Pré-provisionné pendant que admin4 est encore connecté (§ NF4) : sinon sa
    # propre connexion serait refusée (compte inconnu), cf. test_auth_dev_mode.py.
    client.post("/api/ihm/users", json={"email": "user4@example.com"})
    client.post("/api/ihm/auth/logout")

    client.get("/api/ihm/auth/login", params={"email": "user4@example.com"}, follow_redirects=False)
    response = client.delete(f"/api/ihm/settings/billing-manager-contacts/{contact['id']}")
    assert response.status_code == 403


def test_create_company_requires_admin(client, monkeypatch):
    monkeypatch.setattr(settings, "oidc_mode", "dev")
    _login_as_regular_user(client, "admin5@example.com", "user5@example.com")

    response = client.post("/api/ihm/companies", json={"siren": "123456782", "name": "Acme"})
    assert response.status_code == 403


def test_create_company_works_for_admin(client, monkeypatch):
    monkeypatch.setattr(settings, "oidc_mode", "dev")
    _login_as_first_admin(client, "admin6@example.com")

    response = client.post("/api/ihm/companies", json={"siren": "123456782", "name": "Acme"})
    assert response.status_code == 201


def test_get_router_settings_requires_admin(client, monkeypatch):
    """Page Configuration réservée aux admins, lecture comme écriture (§ 5.1) — ces
    réglages (SMTP, allowlist IP...) sont sensibles, pas de lecture pour un
    utilisateur restreint contrairement à d'autres pages IHM."""
    monkeypatch.setattr(settings, "oidc_mode", "dev")
    _login_as_regular_user(client, "admin7@example.com", "user7@example.com")

    response = client.get("/api/ihm/settings")
    assert response.status_code == 403
