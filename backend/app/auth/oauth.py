"""Authentification par application OAuth (spec.md § 4.4/§ 4.9.2/§ 4.10).

Flux `client_credentials` : un consommateur (Odoo) échange son `client_id`/
`client_secret` contre un jeton bearer (JWT signé HS256, § 4.10 — un jeton par
entreprise). La conformité RFC 6749 (authentification client, validation de la
requête de jeton, erreurs normalisées) est déléguée à **Authlib**
(`authlib.oauth2.rfc6749`) plutôt que réimplémentée à la main — nous ne fournissons
que la résolution du client depuis notre base et la génération du jeton lui-même
(JWT via PyJWT). Le secret n'est jamais stocké en clair : seul un hash est conservé,
comparé par Authlib lors de l'authentification du client.

Le "client" OAuth est directement une `TargetApplication` de méthode `afnor_api` —
`client_id`/`client_secret_hash` vivent dans son JSON `parameters` (cf.
`app.models.referential.TargetApplication`), pas dans une table dédiée."""

import contextvars
import hashlib
import hmac
import secrets
import time

import jwt
from authlib.oauth2.rfc6749 import AuthorizationServer as _AuthorizationServer
from authlib.oauth2.rfc6749 import ClientMixin, OAuth2Payload, OAuth2Request
from authlib.oauth2.rfc6749.grants import ClientCredentialsGrant
from fastapi import Depends, Header, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import get_db
from app.models.referential import RoutingMethod, TargetApplication

JWT_ALGORITHM = "HS256"

# Claim `typ` distinguant ce jeton du jeton de session IHM (§ NF3, `app.auth.session`)
# — signés avec des secrets déjà distincts (`jwt_secret` vs `session_secret`), cette
# claim est une seconde barrière contre toute confusion entre les deux (cf. commentaire
# symétrique dans `app.auth.session`).
_TOKEN_TYPE = "oauth_client_credentials"

# Authlib n'a pas d'intégration officielle FastAPI/Starlette côté serveur OAuth2
# (contrairement à Flask/Django) — `query_client`/`save_token` sont de simples
# fonctions, sans accès direct à la session SQLAlchemy de la requête FastAPI en
# cours ; on la transporte via une contextvar, le temps de l'appel à
# `create_token_response` (cf. `issue_token_response`).
_current_db: contextvars.ContextVar[Session] = contextvars.ContextVar("current_db")


def generate_client_credentials() -> tuple[str, str]:
    """Retourne (client_id, client_secret_en_clair) — le secret n'est jamais
    reconstructible ensuite, seul son hash est conservé (cf. `hash_secret`)."""
    client_id = secrets.token_hex(16)
    client_secret = secrets.token_urlsafe(32)
    return client_id, client_secret


def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def verify_secret(secret: str, secret_hash: str) -> bool:
    return hmac.compare_digest(hash_secret(secret), secret_hash)


def _find_target_application_by_client_id(db: Session, client_id: str) -> TargetApplication | None:
    """`client_id` vit dans le JSON `parameters` (pas une colonne dédiée, cf.
    docstring du module) — recherché via `json_extract` (SQLite) plutôt que chargé
    et filtré côté Python, pour rester correct si le nombre d'applications `afnor_api`
    grandit."""
    return (
        db.query(TargetApplication)
        .filter(
            TargetApplication.routing_method == RoutingMethod.AFNOR_API,
            func.json_extract(TargetApplication.parameters, "$.client_id") == client_id,
        )
        .first()
    )


class _ClientWrapper(ClientMixin):
    """Adapte `TargetApplication` à l'interface `ClientMixin` attendue par Authlib."""

    def __init__(self, model: TargetApplication) -> None:
        self.model = model

    def get_client_id(self) -> str:
        return self.model.client_id

    def get_default_redirect_uri(self):
        return None

    def get_allowed_scope(self, scope):
        return scope or ""

    def check_redirect_uri(self, redirect_uri):
        return True

    def check_client_secret(self, client_secret: str) -> bool:
        return verify_secret(client_secret, self.model.client_secret_hash or "")

    def check_endpoint_auth_method(self, method, endpoint):
        return method == "client_secret_post"

    def check_response_type(self, response_type):
        return False

    def check_grant_type(self, grant_type):
        return grant_type == "client_credentials"


class _FormPayload(OAuth2Payload):
    def __init__(self, data: dict) -> None:
        self._data = data

    @property
    def data(self):
        return self._data

    @property
    def datalist(self):
        return {key: [value] for key, value in self._data.items()}


class _FormRequest(OAuth2Request):
    """`OAuth2Request` construite depuis les champs de formulaire déjà validés par
    FastAPI (`Form(...)`), plutôt que reparser le corps de la requête HTTP."""

    def __init__(self, data: dict) -> None:
        # Authlib exige un schéma "https" (RFC 6749 § 3.2) — cette URI est purement
        # interne (jamais résolue en réseau), le schéma https satisfait juste ce
        # contrôle sans désactiver la vérification via AUTHLIB_INSECURE_TRANSPORT.
        super().__init__(method="POST", uri="https://router.internal/oauth/token", headers={})
        self.payload = _FormPayload(data)

    @property
    def form(self):
        return self.payload.data

    @property
    def args(self):
        return {}


def _query_client(client_id: str) -> _ClientWrapper | None:
    db = _current_db.get()
    model = _find_target_application_by_client_id(db, client_id)
    return _ClientWrapper(model) if model else None


def _save_token(token: dict, request) -> None:
    # Jetons auto-porteurs (JWT signé, § 4.10) : rien à persister côté serveur.
    pass


def _generate_bearer_token(
    grant_type,
    client: _ClientWrapper,
    user=None,
    scope=None,
    expires_in=None,
    include_refresh_token=True,
) -> dict:
    now = int(time.time())
    expires_in = expires_in or settings.jwt_expiry_seconds
    payload = {
        "sub": client.model.client_id,
        "company_id": client.model.company_id,
        "typ": _TOKEN_TYPE,
        "iat": now,
        "exp": now + expires_in,
    }
    access_token = jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)
    return {"access_token": access_token, "token_type": "Bearer", "expires_in": expires_in}


class _RouterAuthorizationServer(_AuthorizationServer):
    def __init__(self, query_client, save_token) -> None:
        super().__init__()
        # Attributs d'instance (pas de méthodes de classe) : la base appelle
        # `self.query_client(client_id)`/`self.save_token(token, request)` tels quels.
        self.query_client = query_client
        self.save_token = save_token

    def create_oauth2_request(self, request):
        return request  # déjà une `_FormRequest` (cf. `issue_token_response`)

    def handle_response(self, status_code, payload, headers):
        return status_code, payload, headers

    def send_signal(self, name, *args, **kwargs):
        pass  # pas de système de signaux côté FastAPI


class _ClientCredentialsGrant(ClientCredentialsGrant):
    # Odoo transmet client_id/client_secret dans le corps du formulaire (§ 4.10),
    # pas via l'en-tête Authorization Basic (seule méthode par défaut d'Authlib).
    TOKEN_ENDPOINT_AUTH_METHODS = ["client_secret_post"]


_server = _RouterAuthorizationServer(query_client=_query_client, save_token=_save_token)
_server.register_grant(_ClientCredentialsGrant)
_server.register_token_generator("client_credentials", _generate_bearer_token)


def issue_token_response(
    db: Session, *, grant_type: str, client_id: str, client_secret: str
) -> tuple[int, dict]:
    """Point d'entrée pour la route FastAPI `POST /oauth/token` : délègue à Authlib
    l'authentification du client et la validation de la requête de jeton (RFC 6749),
    retourne `(status_code, corps_json)` prêt à renvoyer tel quel."""
    reset_token = _current_db.set(db)
    try:
        request = _FormRequest(
            {"grant_type": grant_type, "client_id": client_id, "client_secret": client_secret}
        )
        status_code, body, _headers = _server.create_token_response(request)
        return status_code, body
    finally:
        _current_db.reset(reset_token)


def get_current_target_application(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> TargetApplication:
    """Authentifie une requête Odoo -> routeur (§ 4.4) via son jeton bearer et
    retourne directement la `TargetApplication` `afnor_api` correspondante (plus
    d'objet `OAuthApplication` intermédiaire : chaque application `afnor_api` est
    déjà, en elle-même, le "client" OAuth)."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.removeprefix("Bearer ")
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALGORITHM])
        if payload.get("typ") != _TOKEN_TYPE:
            raise jwt.InvalidTokenError("Unexpected token type")
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc

    target_application = _find_target_application_by_client_id(db, payload["sub"])
    if target_application is None:
        raise HTTPException(status_code=401, detail="Unknown client")
    return target_application
