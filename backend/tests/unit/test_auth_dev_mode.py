"""Authentification IHM en mode `dev` (spec.md NF3/NF4, lot 7) — sans IdP réel."""

from app.config import settings
from app.models.referential import Company


def _make_company(db, siren="123456789", name="Société A"):
    company = Company(siren=siren, name=name)
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


def test_me_unauthenticated_when_disabled(client):
    response = client.get("/api/ihm/auth/me")
    assert response.status_code == 200
    body = response.json()
    assert body == {"oidc_mode": "disabled", "authenticated": False, "user": None}


def test_protected_route_not_blocked_when_disabled(client, db_session):
    _make_company(db_session)
    response = client.get("/api/ihm/companies")
    assert response.status_code == 200


def test_login_dev_mode_sets_session_and_me_reflects_user(client, monkeypatch):
    monkeypatch.setattr(settings, "oidc_mode", "dev")

    response = client.get(
        "/api/ihm/auth/login",
        params={"email": "alice@example.com", "name": "Alice"},
        follow_redirects=False,
    )
    assert response.status_code in (302, 307)
    assert "router_session" in response.cookies

    me = client.get("/api/ihm/auth/me")
    body = me.json()
    assert body["oidc_mode"] == "dev"
    assert body["authenticated"] is True
    assert body["user"]["email"] == "alice@example.com"
    # Premier utilisateur créé -> admin (amorçage, cf. UserService).
    assert body["user"]["role"] == "admin"


def test_protected_route_requires_session_when_enabled(client, monkeypatch):
    monkeypatch.setattr(settings, "oidc_mode", "dev")
    response = client.get("/api/ihm/companies")
    assert response.status_code == 401


def test_logout_clears_session(client, monkeypatch):
    monkeypatch.setattr(settings, "oidc_mode", "dev")
    client.get("/api/ihm/auth/login", params={"email": "bob@example.com"}, follow_redirects=False)
    assert client.get("/api/ihm/auth/me").json()["authenticated"] is True

    logout = client.post("/api/ihm/auth/logout")
    assert logout.status_code == 204

    assert client.get("/api/ihm/auth/me").json()["authenticated"] is False


def test_restricted_user_sees_only_their_company_scope(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "oidc_mode", "dev")

    # Amorce un admin d'abord (premier utilisateur), pour que le second reste "user".
    client.get("/api/ihm/auth/login", params={"email": "admin@example.com"}, follow_redirects=False)
    client.post("/api/ihm/auth/logout")

    company_a = _make_company(db_session, siren="111111111", name="Société A")
    company_b = _make_company(db_session, siren="222222222", name="Société B")

    client.get("/api/ihm/auth/login", params={"email": "restricted@example.com"}, follow_redirects=False)

    from app.models.referential import User

    restricted_user = db_session.query(User).filter(User.email == "restricted@example.com").one()
    assert restricted_user.role == "user"
    restricted_user.companies = [company_a]
    db_session.commit()

    response = client.get("/api/ihm/companies")
    assert response.status_code == 200
    names = [c["name"] for c in response.json()]
    assert names == ["Société A"]

    # Consultation d'une facture hors périmètre -> 403 (pas 404, la ressource existe).
    from datetime import date

    from app.models.invoicing import Invoice

    invoice = Invoice(
        company_id=company_b.id,
        emitter_siren="333333333",
        invoice_number="F-1",
        invoice_date=date(2026, 1, 1),
        file_path="/tmp/x.pdf",
        superpdp_flow_id="flow-1",
    )
    db_session.add(invoice)
    db_session.commit()
    db_session.refresh(invoice)

    response = client.get(f"/api/ihm/invoices/{invoice.id}")
    assert response.status_code == 403


def test_admin_sees_all_companies(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "oidc_mode", "dev")
    _make_company(db_session, siren="444444444", name="Société C")
    _make_company(db_session, siren="555555555", name="Société D")

    client.get("/api/ihm/auth/login", params={"email": "admin2@example.com"}, follow_redirects=False)
    response = client.get("/api/ihm/companies")
    assert response.status_code == 200
    assert len(response.json()) == 2
