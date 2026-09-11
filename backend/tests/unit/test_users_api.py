"""Gestion des accès (spec.md § 6.1/NF4, lot 7) — réservée aux administrateurs."""

from app.config import settings
from app.models.referential import Company


def _make_company(db, siren="123456789", name="Société A"):
    company = Company(siren=siren, name=name)
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


def test_list_users_works_unauthenticated_when_disabled(client, monkeypatch):
    monkeypatch.setattr(settings, "oidc_mode", "dev")
    client.get("/api/ihm/auth/login", params={"email": "admin@example.com"}, follow_redirects=False)
    monkeypatch.setattr(settings, "oidc_mode", "disabled")

    response = client.get("/api/ihm/users")
    assert response.status_code == 200


def test_list_users_requires_admin_when_enabled(client, monkeypatch):
    monkeypatch.setattr(settings, "oidc_mode", "dev")
    # Premier utilisateur -> admin (amorçage).
    client.get("/api/ihm/auth/login", params={"email": "admin@example.com"}, follow_redirects=False)
    response = client.get("/api/ihm/users")
    assert response.status_code == 200

    # Pré-provisionne le second compte avant sa première connexion (§ NF4) — sans
    # cela, sa connexion serait refusée (cf. test_auth_dev_mode.py).
    client.post("/api/ihm/users", json={"email": "regular@example.com"})
    client.post("/api/ihm/auth/logout")

    # Second utilisateur -> role "user", refusé sur la liste des accès.
    client.get("/api/ihm/auth/login", params={"email": "regular@example.com"}, follow_redirects=False)
    response = client.get("/api/ihm/users")
    assert response.status_code == 403


def test_update_user_access_sets_role_and_company_scope(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "oidc_mode", "dev")
    client.get("/api/ihm/auth/login", params={"email": "admin3@example.com"}, follow_redirects=False)

    company = _make_company(db_session)

    users = client.get("/api/ihm/users").json()
    admin_user_id = [u["id"] for u in users if u["email"] == "admin3@example.com"][0]

    response = client.put(
        f"/api/ihm/users/{admin_user_id}/access",
        json={"role": "user", "company_ids": [company.id], "is_active": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "user"
    assert body["company_ids"] == [company.id]
    assert body["is_active"] is True


def test_create_user_preprovisions_by_email(client, monkeypatch):
    monkeypatch.setattr(settings, "oidc_mode", "dev")
    client.get("/api/ihm/auth/login", params={"email": "admin4@example.com"}, follow_redirects=False)

    response = client.post("/api/ihm/users", json={"email": "future@example.com", "name": "Future User"})
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "future@example.com"
    assert body["name"] == "Future User"
    assert body["role"] == "user"
    assert body["is_active"] is True
    assert body["has_logged_in"] is False


def test_create_user_rejects_duplicate_email(client, monkeypatch):
    monkeypatch.setattr(settings, "oidc_mode", "dev")
    client.get("/api/ihm/auth/login", params={"email": "admin5@example.com"}, follow_redirects=False)

    client.post("/api/ihm/users", json={"email": "dup@example.com"})
    response = client.post("/api/ihm/users", json={"email": "dup@example.com"})
    assert response.status_code == 409


def test_create_user_requires_admin(client, monkeypatch):
    monkeypatch.setattr(settings, "oidc_mode", "dev")
    client.get("/api/ihm/auth/login", params={"email": "admin6@example.com"}, follow_redirects=False)
    client.post("/api/ihm/users", json={"email": "someone@example.com"})
    client.post("/api/ihm/auth/logout")

    client.get("/api/ihm/auth/login", params={"email": "someone@example.com"}, follow_redirects=False)
    response = client.post("/api/ihm/users", json={"email": "other@example.com"})
    assert response.status_code == 403


def test_deactivating_user_flags_has_logged_in_and_is_active(client, monkeypatch):
    monkeypatch.setattr(settings, "oidc_mode", "dev")
    client.get("/api/ihm/auth/login", params={"email": "admin7@example.com"}, follow_redirects=False)
    client.post("/api/ihm/users", json={"email": "toban@example.com"})
    client.post("/api/ihm/auth/logout")
    client.get("/api/ihm/auth/login", params={"email": "toban@example.com"}, follow_redirects=False)
    client.post("/api/ihm/auth/logout")

    client.get("/api/ihm/auth/login", params={"email": "admin7@example.com"}, follow_redirects=False)
    users = client.get("/api/ihm/users").json()
    target = [u for u in users if u["email"] == "toban@example.com"][0]
    assert target["has_logged_in"] is True

    response = client.put(
        f"/api/ihm/users/{target['id']}/access",
        json={"role": "user", "company_ids": [], "is_active": False},
    )
    assert response.status_code == 200
    assert response.json()["is_active"] is False
