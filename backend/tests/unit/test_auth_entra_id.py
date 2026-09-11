"""Flux OIDC réel Entra ID, construit sur Authlib (spec.md NF3, lot 7) — mocké au
niveau des méthodes publiques d'Authlib (`authorize_redirect`/`authorize_access_token`),
jamais de ses internes (découverte, PKCE, validation JWKS) : c'est le rôle d'Authlib
lui-même de les garantir correctes, pas de ce projet de les retester. Aucun réseau,
aucun tenant Entra ID réel requis."""

from unittest.mock import AsyncMock, patch

from authlib.integrations.base_client.errors import OAuthError
from fastapi.responses import RedirectResponse

from app.config import settings


def test_login_entra_id_redirects(client, monkeypatch):
    monkeypatch.setattr(settings, "oidc_mode", "entra_id")
    monkeypatch.setattr(settings, "oidc_tenant_id", "tenant")
    monkeypatch.setattr(settings, "oidc_client_id", "client-123")

    fake_redirect = RedirectResponse(url="https://login.microsoftonline.com/authorize?x=1")
    with patch(
        "authlib.integrations.starlette_client.StarletteOAuth2App.authorize_redirect",
        new=AsyncMock(return_value=fake_redirect),
    ) as mock_authorize_redirect:
        response = client.get("/api/ihm/auth/login", follow_redirects=False)

    assert response.status_code in (302, 307)
    assert response.headers["location"] == "https://login.microsoftonline.com/authorize?x=1"
    mock_authorize_redirect.assert_called_once()


def test_login_then_callback_redirects_to_next_path(client, monkeypatch):
    """`next` transite par la session Starlette (state/nonce OIDC, cf. app.main) le
    temps de l'aller-retour vers Entra ID, et détermine la redirection finale une fois
    `callback` atteint — pas seulement `frontend_base_url`."""
    monkeypatch.setattr(settings, "oidc_mode", "entra_id")
    monkeypatch.setattr(settings, "oidc_tenant_id", "tenant")
    monkeypatch.setattr(settings, "oidc_client_id", "client-123")
    monkeypatch.setattr(settings, "frontend_base_url", "https://router.example.com")

    fake_redirect = RedirectResponse(url="https://login.microsoftonline.com/authorize?x=1")
    with patch(
        "authlib.integrations.starlette_client.StarletteOAuth2App.authorize_redirect",
        new=AsyncMock(return_value=fake_redirect),
    ):
        client.get(
            "/api/ihm/auth/login",
            params={"next": "/invoices/42"},
            follow_redirects=False,
        )

    fake_token = {
        "userinfo": {"sub": "entra-subject-next", "email": "next@example.com", "name": "Next"}
    }
    with patch(
        "authlib.integrations.starlette_client.StarletteOAuth2App.authorize_access_token",
        new=AsyncMock(return_value=fake_token),
    ):
        response = client.get(
            "/api/ihm/auth/callback",
            params={"code": "auth-code", "state": "s"},
            follow_redirects=False,
        )

    assert response.headers["location"] == "https://router.example.com/invoices/42"


def test_login_disabled_mode_returns_404(client):
    response = client.get("/api/ihm/auth/login", follow_redirects=False)
    assert response.status_code == 404


def test_callback_success_creates_session(client, monkeypatch):
    monkeypatch.setattr(settings, "oidc_mode", "entra_id")
    monkeypatch.setattr(settings, "oidc_tenant_id", "tenant")
    monkeypatch.setattr(settings, "oidc_client_id", "client-123")

    fake_token = {
        "access_token": "irrelevant",
        "userinfo": {
            "sub": "entra-subject-42",
            "email": "callback@example.com",
            "name": "Callback User",
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

    assert response.status_code in (302, 307)
    assert "router_session" in response.cookies

    me = client.get("/api/ihm/auth/me")
    body = me.json()
    assert body["authenticated"] is True
    assert body["user"]["email"] == "callback@example.com"
    assert body["user"]["name"] == "Callback User"


def test_callback_reuses_existing_user_by_subject(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "oidc_mode", "entra_id")
    monkeypatch.setattr(settings, "oidc_tenant_id", "tenant")
    monkeypatch.setattr(settings, "oidc_client_id", "client-123")

    fake_token = {
        "userinfo": {"sub": "entra-subject-99", "email": "repeat@example.com", "name": "Repeat"}
    }
    with patch(
        "authlib.integrations.starlette_client.StarletteOAuth2App.authorize_access_token",
        new=AsyncMock(return_value=fake_token),
    ):
        client.get(
            "/api/ihm/auth/callback",
            params={"code": "auth-code-1", "state": "s1"},
            follow_redirects=False,
        )
        client.get(
            "/api/ihm/auth/callback",
            params={"code": "auth-code-2", "state": "s2"},
            follow_redirects=False,
        )

    from app.models.referential import User

    users = db_session.query(User).filter(User.oidc_subject == "entra-subject-99").all()
    assert len(users) == 1


def test_callback_oauth_error_returns_400(client, monkeypatch):
    monkeypatch.setattr(settings, "oidc_mode", "entra_id")
    monkeypatch.setattr(settings, "oidc_tenant_id", "tenant")
    monkeypatch.setattr(settings, "oidc_client_id", "client-123")

    with patch(
        "authlib.integrations.starlette_client.StarletteOAuth2App.authorize_access_token",
        new=AsyncMock(side_effect=OAuthError(description="mismatching_state")),
    ):
        response = client.get(
            "/api/ihm/auth/callback",
            params={"code": "auth-code", "state": "bad-state"},
            follow_redirects=False,
        )

    assert response.status_code == 400


def test_callback_disabled_when_not_entra_id_mode(client):
    response = client.get(
        "/api/ihm/auth/callback",
        params={"code": "x", "state": "y"},
        follow_redirects=False,
    )
    assert response.status_code == 404


def test_callback_unknown_email_redirects_to_login_error(client, monkeypatch):
    """Sauf amorçage (premier compte), un email sans compte pré-provisionné (§ NF4)
    est refusé — pas de création à la volée depuis les claims Entra ID."""
    monkeypatch.setattr(settings, "oidc_mode", "entra_id")
    monkeypatch.setattr(settings, "oidc_tenant_id", "tenant")
    monkeypatch.setattr(settings, "oidc_client_id", "client-123")
    monkeypatch.setattr(settings, "frontend_base_url", "https://router.example.com")

    # Amorce un premier compte pour sortir du cas "table vide".
    with patch(
        "authlib.integrations.starlette_client.StarletteOAuth2App.authorize_access_token",
        new=AsyncMock(
            return_value={"userinfo": {"sub": "bootstrap-sub", "email": "bootstrap@example.com"}}
        ),
    ):
        client.get(
            "/api/ihm/auth/callback",
            params={"code": "c0", "state": "s0"},
            follow_redirects=False,
        )
    client.post("/api/ihm/auth/logout")

    fake_token = {"userinfo": {"sub": "unknown-sub", "email": "inconnu@example.com"}}
    with patch(
        "authlib.integrations.starlette_client.StarletteOAuth2App.authorize_access_token",
        new=AsyncMock(return_value=fake_token),
    ):
        response = client.get(
            "/api/ihm/auth/callback",
            params={"code": "auth-code", "state": "s"},
            follow_redirects=False,
        )

    assert response.headers["location"] == "https://router.example.com/login-error?reason=unknown"
    assert "router_session" not in response.cookies


def test_callback_preprovisioned_email_attaches_subject(client, monkeypatch):
    monkeypatch.setattr(settings, "oidc_mode", "entra_id")
    monkeypatch.setattr(settings, "oidc_tenant_id", "tenant")
    monkeypatch.setattr(settings, "oidc_client_id", "client-123")

    # Amorce l'admin, puis pré-provisionne le compte à connecter.
    with patch(
        "authlib.integrations.starlette_client.StarletteOAuth2App.authorize_access_token",
        new=AsyncMock(
            return_value={"userinfo": {"sub": "admin-sub", "email": "admin@example.com"}}
        ),
    ):
        client.get("/api/ihm/auth/callback", params={"code": "c0", "state": "s0"}, follow_redirects=False)
    client.post("/api/ihm/users", json={"email": "preprovisioned@example.com"})
    client.post("/api/ihm/auth/logout")

    fake_token = {
        "userinfo": {
            "sub": "preprovisioned-sub",
            "email": "preprovisioned@example.com",
            "name": "Nom Réel",
        }
    }
    with patch(
        "authlib.integrations.starlette_client.StarletteOAuth2App.authorize_access_token",
        new=AsyncMock(return_value=fake_token),
    ):
        response = client.get(
            "/api/ihm/auth/callback",
            params={"code": "auth-code", "state": "s"},
            follow_redirects=False,
        )

    assert "router_session" in response.cookies
    me = client.get("/api/ihm/auth/me").json()
    assert me["user"]["email"] == "preprovisioned@example.com"
    assert me["user"]["name"] == "Nom Réel"
    assert me["user"]["role"] == "user"


def test_callback_inactive_user_redirects_to_login_error(client, monkeypatch):
    monkeypatch.setattr(settings, "oidc_mode", "entra_id")
    monkeypatch.setattr(settings, "oidc_tenant_id", "tenant")
    monkeypatch.setattr(settings, "oidc_client_id", "client-123")
    monkeypatch.setattr(settings, "frontend_base_url", "https://router.example.com")

    with patch(
        "authlib.integrations.starlette_client.StarletteOAuth2App.authorize_access_token",
        new=AsyncMock(
            return_value={"userinfo": {"sub": "admin-sub2", "email": "admin2@example.com"}}
        ),
    ):
        client.get("/api/ihm/auth/callback", params={"code": "c0", "state": "s0"}, follow_redirects=False)
    created = client.post("/api/ihm/users", json={"email": "banned@example.com"}).json()
    client.put(
        f"/api/ihm/users/{created['id']}/access",
        json={"role": "user", "company_ids": [], "is_active": False},
    )
    client.post("/api/ihm/auth/logout")

    fake_token = {"userinfo": {"sub": "banned-sub", "email": "banned@example.com"}}
    with patch(
        "authlib.integrations.starlette_client.StarletteOAuth2App.authorize_access_token",
        new=AsyncMock(return_value=fake_token),
    ):
        response = client.get(
            "/api/ihm/auth/callback",
            params={"code": "auth-code", "state": "s"},
            follow_redirects=False,
        )

    assert response.headers["location"] == "https://router.example.com/login-error?reason=inactive"
    assert "router_session" not in response.cookies
