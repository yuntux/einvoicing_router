"""Flux OIDC réel contre Microsoft Entra ID (spec.md NF3, lot 7) — authorization code
+ PKCE, adapté à une IHM SPA servie séparément du backend (§ 3).

Utilise directement `requests`/`PyJWT` (déjà des dépendances du projet, via pyfrctc et
l'API AFNOR) plutôt qu'une bibliothèque OIDC dédiée (`msal`/`authlib`), pour rester
minimal : le flux ne nécessite que la découverte OpenID Connect, l'échange
code/jetons, et la validation de signature du jeton d'ID via son JWKS."""

import base64
import hashlib
import secrets
from urllib.parse import quote

import jwt
import requests

from app.config import settings

DISCOVERY_TIMEOUT_SECONDS = 10
TOKEN_EXCHANGE_TIMEOUT_SECONDS = 10


def _authority() -> str:
    return f"https://login.microsoftonline.com/{settings.oidc_tenant_id}/v2.0"


def _discovery_document() -> dict:
    response = requests.get(
        f"{_authority()}/.well-known/openid-configuration", timeout=DISCOVERY_TIMEOUT_SECONDS
    )
    response.raise_for_status()
    return response.json()


def generate_pkce_pair() -> tuple[str, str]:
    """Retourne (code_verifier, code_challenge) — S256, RFC 7636."""
    code_verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return code_verifier, code_challenge


def build_authorization_url(*, state: str, code_challenge: str) -> str:
    discovery = _discovery_document()
    params = {
        "client_id": settings.oidc_client_id,
        "response_type": "code",
        "redirect_uri": settings.oidc_redirect_uri,
        "scope": "openid profile email",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    query = "&".join(f"{key}={quote(str(value))}" for key, value in params.items())
    return f"{discovery['authorization_endpoint']}?{query}"


def exchange_code_for_id_token(*, code: str, code_verifier: str) -> str:
    """Échange le code d'autorisation contre les jetons, et retourne l'`id_token`
    (JWT) — seul jeton dont ce routeur a besoin : il n'appelle aucune API Microsoft
    Graph pour le compte de l'utilisateur, l'identité déclarée dans l'ID token suffit."""
    discovery = _discovery_document()
    response = requests.post(
        discovery["token_endpoint"],
        data={
            "client_id": settings.oidc_client_id,
            "client_secret": settings.oidc_client_secret,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.oidc_redirect_uri,
            "code_verifier": code_verifier,
        },
        timeout=TOKEN_EXCHANGE_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()["id_token"]


def validate_id_token(id_token: str) -> dict:
    """Vérifie la signature (JWKS du tenant), l'émetteur et l'audience de l'ID token,
    et retourne ses claims (`sub`, `email`/`preferred_username`, `name`)."""
    discovery = _discovery_document()
    jwks_client = jwt.PyJWKClient(discovery["jwks_uri"])
    signing_key = jwks_client.get_signing_key_from_jwt(id_token)
    claims = jwt.decode(
        id_token,
        signing_key.key,
        algorithms=["RS256"],
        audience=settings.oidc_client_id,
        issuer=discovery["issuer"],
    )
    return claims
