"""Flux OIDC réel Entra ID (spec.md NF3, lot 7) — découverte/JWKS/échange de jetons
mockés (aucun réseau, aucun tenant réel requis)."""

from unittest.mock import MagicMock, patch

import jwt as pyjwt
from cryptography.hazmat.primitives.asymmetric import rsa

from app.auth import oidc
from app.config import settings

DISCOVERY = {
    "authorization_endpoint": "https://login.microsoftonline.com/tenant/oauth2/v2.0/authorize",
    "token_endpoint": "https://login.microsoftonline.com/tenant/oauth2/v2.0/token",
    "jwks_uri": "https://login.microsoftonline.com/tenant/discovery/v2.0/keys",
    "issuer": "https://login.microsoftonline.com/tenant/v2.0",
}


def _rsa_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


def test_build_authorization_url_includes_pkce_and_state(monkeypatch):
    monkeypatch.setattr(settings, "oidc_tenant_id", "tenant")
    monkeypatch.setattr(settings, "oidc_client_id", "client-123")
    with patch("app.auth.oidc._discovery_document", return_value=DISCOVERY):
        url = oidc.build_authorization_url(state="state-abc", code_challenge="challenge-xyz")

    assert url.startswith(DISCOVERY["authorization_endpoint"])
    assert "client_id=client-123" in url
    assert "state=state-abc" in url
    assert "code_challenge=challenge-xyz" in url
    assert "code_challenge_method=S256" in url


def test_exchange_code_for_id_token(monkeypatch):
    monkeypatch.setattr(settings, "oidc_client_id", "client-123")
    monkeypatch.setattr(settings, "oidc_client_secret", "secret")

    mock_response = MagicMock()
    mock_response.json.return_value = {"id_token": "the-id-token"}
    mock_response.raise_for_status.return_value = None

    with (
        patch("app.auth.oidc._discovery_document", return_value=DISCOVERY),
        patch("app.auth.oidc.requests.post", return_value=mock_response) as mock_post,
    ):
        token = oidc.exchange_code_for_id_token(code="auth-code", code_verifier="verifier")

    assert token == "the-id-token"
    mock_post.assert_called_once()
    assert mock_post.call_args.args[0] == DISCOVERY["token_endpoint"]


def test_validate_id_token_success(monkeypatch):
    monkeypatch.setattr(settings, "oidc_client_id", "client-123")
    private_key, public_key = _rsa_keypair()

    id_token = pyjwt.encode(
        {
            "sub": "entra-subject-1",
            "email": "user@example.com",
            "name": "Entra User",
            "aud": "client-123",
            "iss": DISCOVERY["issuer"],
        },
        private_key,
        algorithm="RS256",
    )

    fake_signing_key = MagicMock()
    fake_signing_key.key = public_key

    with (
        patch("app.auth.oidc._discovery_document", return_value=DISCOVERY),
        patch.object(
            pyjwt.PyJWKClient, "get_signing_key_from_jwt", return_value=fake_signing_key
        ),
    ):
        claims = oidc.validate_id_token(id_token)

    assert claims["sub"] == "entra-subject-1"
    assert claims["email"] == "user@example.com"


def test_validate_id_token_rejects_wrong_audience(monkeypatch):
    monkeypatch.setattr(settings, "oidc_client_id", "client-123")
    private_key, public_key = _rsa_keypair()

    id_token = pyjwt.encode(
        {"sub": "s", "aud": "someone-else", "iss": DISCOVERY["issuer"]},
        private_key,
        algorithm="RS256",
    )
    fake_signing_key = MagicMock()
    fake_signing_key.key = public_key

    with (
        patch("app.auth.oidc._discovery_document", return_value=DISCOVERY),
        patch.object(
            pyjwt.PyJWKClient, "get_signing_key_from_jwt", return_value=fake_signing_key
        ),
    ):
        try:
            oidc.validate_id_token(id_token)
            assert False, "expected InvalidAudienceError"
        except pyjwt.InvalidAudienceError:
            pass


def test_login_entra_id_redirects_and_sets_state_cookie(client, monkeypatch):
    monkeypatch.setattr(settings, "oidc_mode", "entra_id")
    monkeypatch.setattr(settings, "oidc_tenant_id", "tenant")
    monkeypatch.setattr(settings, "oidc_client_id", "client-123")

    with patch("app.api.ihm.auth.oidc.build_authorization_url", return_value="https://login.example/authorize?x=1"):
        response = client.get("/api/ihm/auth/login", follow_redirects=False)

    assert response.status_code in (302, 307)
    assert response.headers["location"] == "https://login.example/authorize?x=1"
    assert "router_oidc_state" in response.cookies


def test_callback_success_creates_session(client, monkeypatch):
    monkeypatch.setattr(settings, "oidc_mode", "entra_id")
    monkeypatch.setattr(settings, "oidc_tenant_id", "tenant")
    monkeypatch.setattr(settings, "oidc_client_id", "client-123")

    with patch("app.api.ihm.auth.oidc.build_authorization_url", return_value="https://login.example/authorize?state=state-1"):
        login_response = client.get("/api/ihm/auth/login", follow_redirects=False)
    assert "router_oidc_state" in login_response.cookies

    # Le state réellement stashé est généré côté serveur (jwt.encode aléatoire) ; on le
    # récupère depuis le cookie plutôt que de le deviner.
    import jwt as pyjwt_mod

    from app.auth.session import JWT_ALGORITHM

    stashed = pyjwt_mod.decode(
        login_response.cookies["router_oidc_state"], settings.jwt_secret, algorithms=[JWT_ALGORITHM]
    )
    real_state = stashed["state"]

    with (
        patch("app.api.ihm.auth.oidc.exchange_code_for_id_token", return_value="id-token-value"),
        patch(
            "app.api.ihm.auth.oidc.validate_id_token",
            return_value={
                "sub": "entra-subject-42",
                "email": "callback@example.com",
                "name": "Callback User",
            },
        ),
    ):
        response = client.get(
            "/api/ihm/auth/callback",
            params={"code": "auth-code", "state": real_state},
            follow_redirects=False,
        )

    assert response.status_code in (302, 307)
    assert "router_session" in response.cookies

    me = client.get("/api/ihm/auth/me")
    body = me.json()
    assert body["authenticated"] is True
    assert body["user"]["email"] == "callback@example.com"


def test_callback_rejects_state_mismatch(client, monkeypatch):
    monkeypatch.setattr(settings, "oidc_mode", "entra_id")
    monkeypatch.setattr(settings, "oidc_tenant_id", "tenant")
    monkeypatch.setattr(settings, "oidc_client_id", "client-123")

    with patch("app.api.ihm.auth.oidc.build_authorization_url", return_value="https://login.example/authorize"):
        client.get("/api/ihm/auth/login", follow_redirects=False)

    response = client.get(
        "/api/ihm/auth/callback",
        params={"code": "auth-code", "state": "wrong-state"},
        follow_redirects=False,
    )
    assert response.status_code == 400
