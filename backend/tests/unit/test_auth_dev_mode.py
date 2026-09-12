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
    # Toute première connexion : pas de connexion précédente à afficher.
    assert body["user"]["previous_login_at"] is None


def test_me_previous_login_at_reflects_login_before_the_current_one(client, monkeypatch):
    """`/auth/me` doit exposer l'avant-dernière connexion, jamais celle en cours
    (sans intérêt puisque toujours "maintenant") — cf. `get_previous_login`."""
    monkeypatch.setattr(settings, "oidc_mode", "dev")

    client.get("/api/ihm/auth/login", params={"email": "dana@example.com"}, follow_redirects=False)
    first_login_at = client.get("/api/ihm/auth/me").json()["user"]["previous_login_at"]
    assert first_login_at is None
    client.post("/api/ihm/auth/logout")

    client.get("/api/ihm/auth/login", params={"email": "dana@example.com"}, follow_redirects=False)
    body = client.get("/api/ihm/auth/me").json()
    # La connexion en cours (la 2e) n'est pas celle renvoyée : c'est la 1re.
    assert body["user"]["previous_login_at"] is not None


def test_login_dev_mode_resyncs_name_on_repeat_login(client, monkeypatch):
    """`name` reflète toujours la dernière connexion (source de vérité IdP), pas
    seulement la première (cf. resolve_login_user)."""
    monkeypatch.setattr(settings, "oidc_mode", "dev")

    client.get(
        "/api/ihm/auth/login",
        params={"email": "renamed@example.com", "name": "Ancien Nom"},
        follow_redirects=False,
    )
    client.post("/api/ihm/auth/logout")

    client.get(
        "/api/ihm/auth/login",
        params={"email": "renamed@example.com", "name": "Nouveau Nom"},
        follow_redirects=False,
    )
    body = client.get("/api/ihm/auth/me").json()
    assert body["user"]["name"] == "Nouveau Nom"


def test_login_dev_mode_redirects_to_next_path(client, monkeypatch):
    monkeypatch.setattr(settings, "oidc_mode", "dev")
    monkeypatch.setattr(settings, "frontend_base_url", "https://router.example.com")

    response = client.get(
        "/api/ihm/auth/login",
        params={"email": "carol@example.com", "next": "/invoices/42"},
        follow_redirects=False,
    )
    assert response.status_code in (302, 307)
    assert response.headers["location"] == "https://router.example.com/invoices/42"


def test_login_dev_mode_rejects_absolute_url_as_next(client, monkeypatch):
    """`next` doit rester un chemin interne — jamais une redirection ouverte vers un
    domaine arbitraire (cf. _safe_next_path)."""
    monkeypatch.setattr(settings, "oidc_mode", "dev")
    monkeypatch.setattr(settings, "frontend_base_url", "https://router.example.com")

    response = client.get(
        "/api/ihm/auth/login",
        params={"email": "mallory@example.com", "next": "https://evil.example/phishing"},
        follow_redirects=False,
    )
    assert response.headers["location"] == "https://router.example.com/"


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
    # Pré-provisionne le second compte (§ NF4) — sans ça sa connexion serait refusée.
    client.post("/api/ihm/users", json={"email": "restricted@example.com"})
    client.post("/api/ihm/auth/logout")

    company_a = _make_company(db_session, siren="111111111", name="Société A")
    company_b = _make_company(db_session, siren="222222222", name="Société B")

    client.get("/api/ihm/auth/login", params={"email": "restricted@example.com"}, follow_redirects=False)

    from app.models.referential import User

    restricted_user = db_session.query(User).filter(User.email == "restricted@example.com").one()
    assert restricted_user.role == "user"
    restricted_user.companies = [company_a]
    db_session.commit()

    # Page Entreprises réservée aux admins (§ 5.1) — un utilisateur restreint n'y a
    # plus accès du tout, même filtré à son périmètre.
    response = client.get("/api/ihm/companies")
    assert response.status_code == 403

    # La référence minimale (id+nom, non filtrée par périmètre) reste accessible :
    # des pages non admin-only (ex. Règles de routage) en ont besoin pour l'affichage.
    lookup = client.get("/api/ihm/companies/lookup")
    assert lookup.status_code == 200
    names = {c["name"] for c in lookup.json()}
    assert names == {"Société A", "Société B"}

    # Consultation d'une facture hors périmètre -> 403 (pas 404, la ressource existe).
    from datetime import date

    from app.models.invoicing import Invoice

    invoice = Invoice(
        company_id=company_b.id,
        emitter_siren="333333333",
        invoice_number="F-1",
        invoice_date=date(2026, 1, 1),
        file_path="/tmp/x.pdf",
        certified_platform_flow_id="flow-1",
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


def test_login_unknown_email_redirects_to_login_error(client, monkeypatch):
    """Sauf amorçage (premier compte, cf. UserService), un email sans compte
    pré-provisionné (§ NF4) est refusé — pas de création à la volée."""
    monkeypatch.setattr(settings, "oidc_mode", "dev")
    monkeypatch.setattr(settings, "frontend_base_url", "https://router.example.com")

    # Amorce un premier compte pour sortir du cas "table vide".
    client.get("/api/ihm/auth/login", params={"email": "admin8@example.com"}, follow_redirects=False)
    client.post("/api/ihm/auth/logout")

    response = client.get(
        "/api/ihm/auth/login",
        params={"email": "inconnu@example.com"},
        follow_redirects=False,
    )
    assert response.headers["location"] == "https://router.example.com/login-error?reason=unknown"
    assert "router_session" not in response.cookies

    me = client.get("/api/ihm/auth/me")
    assert me.json()["authenticated"] is False


def test_login_preprovisioned_user_attaches_subject_on_first_login(client, monkeypatch):
    monkeypatch.setattr(settings, "oidc_mode", "dev")
    client.get("/api/ihm/auth/login", params={"email": "admin9@example.com"}, follow_redirects=False)
    client.post("/api/ihm/users", json={"email": "preprovisioned@example.com"})
    client.post("/api/ihm/auth/logout")

    response = client.get(
        "/api/ihm/auth/login",
        params={"email": "preprovisioned@example.com", "name": "Nom Réel"},
        follow_redirects=False,
    )
    assert "router_session" in response.cookies

    me = client.get("/api/ihm/auth/me").json()
    assert me["authenticated"] is True
    assert me["user"]["email"] == "preprovisioned@example.com"
    assert me["user"]["name"] == "Nom Réel"
    assert me["user"]["role"] == "user"


def test_login_inactive_user_redirects_to_login_error(client, monkeypatch):
    monkeypatch.setattr(settings, "oidc_mode", "dev")
    monkeypatch.setattr(settings, "frontend_base_url", "https://router.example.com")

    client.get("/api/ihm/auth/login", params={"email": "admin10@example.com"}, follow_redirects=False)
    created = client.post("/api/ihm/users", json={"email": "banned@example.com"}).json()
    client.put(
        f"/api/ihm/users/{created['id']}/access",
        json={"role": "user", "company_ids": [], "is_active": False},
    )
    client.post("/api/ihm/auth/logout")

    response = client.get(
        "/api/ihm/auth/login",
        params={"email": "banned@example.com"},
        follow_redirects=False,
    )
    assert response.headers["location"] == "https://router.example.com/login-error?reason=inactive"
    assert "router_session" not in response.cookies
