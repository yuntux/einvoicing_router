"""Cloisonnement par entreprise sur les applications cibles (spec.md § 6.1/NF4).

Avant ce correctif, `target_applications.py` ne filtrait jamais par périmètre : un
utilisateur restreint à une entreprise pouvait lire (destinataires mail, URLs de
webhook/redirection OAuth) et modifier les applications cibles de n'importe quelle
autre entreprise — ces tests couvrent la régression."""

from stdnum.fr import siren as siren_stdnum

from app.config import settings


def _valid_siren(prefix8: str) -> str:
    """Complète un préfixe de 8 chiffres par la clé Luhn qui en fait un SIREN valide
    (les tests ont besoin de SIREN distincts mais valides, pas de vrais SIREN)."""
    for check_digit in range(10):
        candidate = f"{prefix8}{check_digit}"
        if siren_stdnum.is_valid(candidate):
            return candidate
    raise AssertionError(f"Aucune clé Luhn valide pour {prefix8!r}")


def _login_as_first_admin(client, email="admin@example.com"):
    client.get("/api/ihm/auth/login", params={"email": email}, follow_redirects=False)


def _create_restricted_user_scoped_to(client, *, admin_email, user_email, company_id):
    """Connecté en admin, pré-provisionne `user_email`, le cantonne à `company_id`,
    puis se déconnecte et connecte ce compte restreint."""
    users = client.get("/api/ihm/users").json()
    if not any(u["email"] == user_email for u in users):
        client.post("/api/ihm/users", json={"email": user_email})
    user_id = next(u["id"] for u in client.get("/api/ihm/users").json() if u["email"] == user_email)
    response = client.put(
        f"/api/ihm/users/{user_id}/access",
        json={"role": "user", "company_ids": [company_id], "is_active": True},
    )
    assert response.status_code == 200
    client.post("/api/ihm/auth/logout")
    client.get("/api/ihm/auth/login", params={"email": user_email}, follow_redirects=False)


def _make_company(client, siren, name):
    response = client.post("/api/ihm/companies", json={"siren": siren, "name": name})
    assert response.status_code == 201
    return response.json()["id"]


def _make_target_application(client, *, company_id, name="Spendesk"):
    response = client.post(
        "/api/ihm/target-applications",
        json={
            "name": name,
            "routing_method": "mail",
            "company_id": company_id,
            "parameters": {"to": ["ap@example.com"], "cc": [], "bcc": []},
        },
    )
    assert response.status_code == 201
    return response.json()


def test_restricted_user_cannot_list_target_applications_of_another_company(client, monkeypatch):
    monkeypatch.setattr(settings, "oidc_mode", "dev")
    _login_as_first_admin(client, "admin1@example.com")
    company_a = _make_company(client, _valid_siren("11111111"), "Société A")
    company_b = _make_company(client, _valid_siren("22222222"), "Société B")
    _make_target_application(client, company_id=company_b, name="Cible B")

    _create_restricted_user_scoped_to(
        client, admin_email="admin1@example.com", user_email="user1@example.com", company_id=company_a
    )

    response = client.get("/api/ihm/target-applications")
    assert response.status_code == 200
    assert response.json() == []


def test_restricted_user_cannot_create_target_application_for_another_company(client, monkeypatch):
    monkeypatch.setattr(settings, "oidc_mode", "dev")
    _login_as_first_admin(client, "admin2@example.com")
    company_a = _make_company(client, _valid_siren("11111112"), "Société A")
    company_b = _make_company(client, _valid_siren("22222223"), "Société B")

    _create_restricted_user_scoped_to(
        client, admin_email="admin2@example.com", user_email="user2@example.com", company_id=company_a
    )

    response = client.post(
        "/api/ihm/target-applications",
        json={
            "name": "Cible B",
            "routing_method": "mail",
            "company_id": company_b,
            "parameters": {"to": ["ap@example.com"], "cc": [], "bcc": []},
        },
    )
    assert response.status_code == 403


def test_restricted_user_cannot_update_target_application_of_another_company(client, monkeypatch):
    monkeypatch.setattr(settings, "oidc_mode", "dev")
    _login_as_first_admin(client, "admin3@example.com")
    company_a = _make_company(client, _valid_siren("11111113"), "Société A")
    company_b = _make_company(client, _valid_siren("22222224"), "Société B")
    target_b = _make_target_application(client, company_id=company_b, name="Cible B")

    _create_restricted_user_scoped_to(
        client, admin_email="admin3@example.com", user_email="user3@example.com", company_id=company_a
    )

    response = client.put(
        f"/api/ihm/target-applications/{target_b['id']}",
        json={"name": "Détournée", "parameters": {"to": ["attacker@evil.example"], "cc": [], "bcc": []}},
    )
    assert response.status_code == 403


def test_restricted_user_cannot_toggle_status_of_target_application_of_another_company(client, monkeypatch):
    monkeypatch.setattr(settings, "oidc_mode", "dev")
    _login_as_first_admin(client, "admin4@example.com")
    company_a = _make_company(client, _valid_siren("11111114"), "Société A")
    company_b = _make_company(client, _valid_siren("22222225"), "Société B")
    target_b = _make_target_application(client, company_id=company_b, name="Cible B")

    _create_restricted_user_scoped_to(
        client, admin_email="admin4@example.com", user_email="user4@example.com", company_id=company_a
    )

    response = client.put(
        f"/api/ihm/target-applications/{target_b['id']}/status", json={"is_active": False}
    )
    assert response.status_code == 403


def test_restricted_user_still_sees_own_company_target_applications(client, monkeypatch):
    monkeypatch.setattr(settings, "oidc_mode", "dev")
    _login_as_first_admin(client, "admin5@example.com")
    company_a = _make_company(client, _valid_siren("11111115"), "Société A")
    target_a = _make_target_application(client, company_id=company_a, name="Cible A")

    _create_restricted_user_scoped_to(
        client, admin_email="admin5@example.com", user_email="user5@example.com", company_id=company_a
    )

    response = client.get("/api/ihm/target-applications")
    assert response.status_code == 200
    assert [t["id"] for t in response.json()] == [target_a["id"]]
