"""Pages Entreprises, Applications cibles, Configuration et Traces & journaux
réservées aux admins (spec.md § 5.1) — un utilisateur restreint n'y a plus aucun
accès, y compris en lecture, à l'exception des références minimales (`/lookup`)
utilisées par des pages non admin-only (ex. Règles de routage)."""

from stdnum.fr import siren as siren_stdnum

from app.config import settings


def _valid_siren(prefix8: str) -> str:
    for check_digit in range(10):
        candidate = f"{prefix8}{check_digit}"
        if siren_stdnum.is_valid(candidate):
            return candidate
    raise AssertionError(f"Aucune clé Luhn valide pour {prefix8!r}")


def _login_as_first_admin(client, email="admin@example.com"):
    client.get("/api/ihm/auth/login", params={"email": email}, follow_redirects=False)


def _create_restricted_user_scoped_to(client, *, admin_email, user_email, company_id):
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


def test_restricted_user_cannot_list_companies(client, monkeypatch):
    monkeypatch.setattr(settings, "oidc_mode", "dev")
    _login_as_first_admin(client, "admin1@example.com")
    company_a = _make_company(client, _valid_siren("31111111"), "Société A")

    _create_restricted_user_scoped_to(
        client, admin_email="admin1@example.com", user_email="user1@example.com", company_id=company_a
    )

    assert client.get("/api/ihm/companies").status_code == 403
    assert client.get("/api/ihm/companies/afnor-platforms").status_code == 403
    assert client.get(f"/api/ihm/companies/{company_a}/certified-platform-credentials").status_code == 403
    assert (
        client.put(
            f"/api/ihm/companies/{company_a}/certified-platform-credentials",
            json={"client_id": "x", "client_secret": "y"},
        ).status_code
        == 403
    )
    assert client.post("/api/ihm/companies", json={"siren": _valid_siren("31111112"), "name": "B"}).status_code == 403


def test_restricted_user_can_read_company_lookup(client, monkeypatch):
    monkeypatch.setattr(settings, "oidc_mode", "dev")
    _login_as_first_admin(client, "admin2@example.com")
    company_a = _make_company(client, _valid_siren("32111111"), "Société A")
    company_b = _make_company(client, _valid_siren("32111112"), "Société B")

    _create_restricted_user_scoped_to(
        client, admin_email="admin2@example.com", user_email="user2@example.com", company_id=company_a
    )

    response = client.get("/api/ihm/companies/lookup")
    assert response.status_code == 200
    body = {row["id"]: row for row in response.json()}
    assert set(body) == {company_a, company_b}
    assert body[company_a] == {"id": company_a, "name": "Société A"}
    assert "siren" not in body[company_a]


def test_restricted_user_cannot_access_settings_page(client, monkeypatch):
    monkeypatch.setattr(settings, "oidc_mode", "dev")
    _login_as_first_admin(client, "admin3@example.com")
    company_a = _make_company(client, _valid_siren("33111111"), "Société A")

    _create_restricted_user_scoped_to(
        client, admin_email="admin3@example.com", user_email="user3@example.com", company_id=company_a
    )

    assert client.get("/api/ihm/settings").status_code == 403
    assert client.get("/api/ihm/settings/billing-manager-contacts").status_code == 403
    assert client.put("/api/ihm/settings", json={"smtp_host": "x"}).status_code == 403


def test_restricted_user_cannot_access_traces_pages(client, monkeypatch):
    monkeypatch.setattr(settings, "oidc_mode", "dev")
    _login_as_first_admin(client, "admin4@example.com")
    company_a = _make_company(client, _valid_siren("34111111"), "Société A")

    _create_restricted_user_scoped_to(
        client, admin_email="admin4@example.com", user_email="user4@example.com", company_id=company_a
    )

    assert client.get("/api/ihm/audit/flow-traces").status_code == 403
    assert client.get("/api/ihm/audit/technical-logs").status_code == 403
    assert client.get("/api/ihm/audit/audit-logs").status_code == 403


def test_admin_still_has_full_access_to_admin_only_pages(client, monkeypatch):
    monkeypatch.setattr(settings, "oidc_mode", "dev")
    _login_as_first_admin(client, "admin5@example.com")
    _make_company(client, _valid_siren("35111111"), "Société A")

    assert client.get("/api/ihm/companies").status_code == 200
    assert client.get("/api/ihm/settings").status_code == 200
    assert client.get("/api/ihm/audit/flow-traces").status_code == 200
    assert client.get("/api/ihm/audit/technical-logs").status_code == 200
    assert client.get("/api/ihm/audit/audit-logs").status_code == 200
