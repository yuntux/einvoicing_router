"""Limitation de débit (spec.md NF6) sur `POST /oauth/token` et `GET /auth/login` —
désactivée par défaut dans la suite de tests (cf. conftest.py), réactivée
explicitement ici."""

from app.auth.oauth import generate_client_credentials, hash_secret
from app.auth.rate_limit import reset_rate_limits
from app.config import settings
from app.models.referential import Company, RoutingMethod, TargetApplication


def _make_oauth_app(db, client_secret="s3cret-value"):
    """Une application `afnor_api` EST le "client" OAuth (§ 4.9.2/§ 4.10)."""
    company = Company(siren="123456789", name="Ma Société")
    db.add(company)
    db.commit()
    db.refresh(company)

    target = TargetApplication(
        name="Odoo",
        routing_method=RoutingMethod.AFNOR_API,
        company_id=company.id,
        parameters={
            "client_id": generate_client_credentials()[0],
            "client_secret_hash": hash_secret(client_secret),
            "app_type": "confidential",
        },
    )
    db.add(target)
    db.commit()
    db.refresh(target)
    return target


def test_oauth_token_endpoint_is_rate_limited(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_max_requests", 3)
    monkeypatch.setattr(settings, "rate_limit_window_seconds", 60)
    reset_rate_limits()
    oauth_app = _make_oauth_app(db_session)

    data = {
        "grant_type": "client_credentials",
        "client_id": oauth_app.client_id,
        "client_secret": "wrong-secret",
    }
    for _ in range(3):
        response = client.post("/api/afnor/oauth/token", data=data)
        assert response.status_code == 400  # invalid_client, requête acceptée

    response = client.post("/api/afnor/oauth/token", data=data)
    assert response.status_code == 429


def test_ihm_login_endpoint_is_rate_limited(client, monkeypatch):
    monkeypatch.setattr(settings, "oidc_mode", "dev")
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_max_requests", 3)
    monkeypatch.setattr(settings, "rate_limit_window_seconds", 60)
    reset_rate_limits()

    for _ in range(3):
        response = client.get(
            "/api/ihm/auth/login", params={"email": "user@example.com"}, follow_redirects=False
        )
        assert response.status_code != 429

    response = client.get(
        "/api/ihm/auth/login", params={"email": "user@example.com"}, follow_redirects=False
    )
    assert response.status_code == 429


def test_rate_limit_is_per_client_ip(client, db_session, monkeypatch):
    """Deux fenêtres distinctes (`scope`) ne se gênent pas — vérifie que
    `oauth_token` et `ihm_login` sont comptés indépendamment."""
    monkeypatch.setattr(settings, "oidc_mode", "dev")
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_max_requests", 2)
    monkeypatch.setattr(settings, "rate_limit_window_seconds", 60)
    reset_rate_limits()
    oauth_app = _make_oauth_app(db_session)

    data = {
        "grant_type": "client_credentials",
        "client_id": oauth_app.client_id,
        "client_secret": "wrong-secret",
    }
    for _ in range(2):
        assert client.post("/api/afnor/oauth/token", data=data).status_code == 400
    assert client.post("/api/afnor/oauth/token", data=data).status_code == 429

    # Le budget de `ihm_login` est indépendant de celui de `oauth_token`.
    response = client.get(
        "/api/ihm/auth/login", params={"email": "user@example.com"}, follow_redirects=False
    )
    assert response.status_code != 429
