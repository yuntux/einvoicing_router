"""Attribut `Secure` du cookie de session IHM (spec.md § NF3) — présent dès que
`oidc_mode != "dev"` (déploiement réel, toujours HTTPS), absent en mode `dev` (usage
HTTP local simple)."""

from unittest.mock import AsyncMock, patch

from app.config import settings


def test_session_cookie_is_not_secure_in_dev_mode(client, monkeypatch):
    monkeypatch.setattr(settings, "oidc_mode", "dev")

    response = client.get(
        "/api/ihm/auth/login",
        params={"email": "alice@example.com", "name": "Alice"},
        follow_redirects=False,
    )

    set_cookie = response.headers.get("set-cookie", "")
    assert "router_session=" in set_cookie
    assert "Secure" not in set_cookie


def test_session_cookie_is_secure_in_entra_id_mode(client, monkeypatch):
    monkeypatch.setattr(settings, "oidc_mode", "entra_id")
    monkeypatch.setattr(settings, "oidc_tenant_id", "tenant")
    monkeypatch.setattr(settings, "oidc_client_id", "client-123")

    fake_token = {
        "access_token": "irrelevant",
        "userinfo": {
            "sub": "entra-subject-secure-test",
            "email": "secure-cookie@example.com",
            "name": "Secure Cookie",
        },
    }
    with patch(
        "authlib.integrations.starlette_client.StarletteOAuth2App.authorize_access_token",
        new=AsyncMock(return_value=fake_token),
    ):
        response = client.get(
            "/api/ihm/auth/callback",
            params={"code": "auth-code", "state": "whatever-authlib-manages-this"},
            follow_redirects=False,
        )

    set_cookie = response.headers.get("set-cookie", "")
    assert "router_session=" in set_cookie
    assert "Secure" in set_cookie
