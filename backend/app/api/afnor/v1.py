"""API AFNOR XP Z12-013 exposée à Odoo — version v1 (spec.md § 4.4/§ 4.8).

Seule version existante à ce jour (la norme XP Z12-013 n'a pas encore de v2
publiée) — point d'entrée du registre de versions
(`app/afnor/versioning/registry.py`), qui permettra d'en monter une future sur un
autre préfixe sans toucher à celui-ci ni aux services qu'il appelle. Les routes
métier communes à toute future version (`POST /flows`, `POST /flows/search`,
`GET /flows/{flowId}`, `GET /siren/code-insee:{siren}`) sont factorisées dans
`_common.py` ; seule `/oauth/token` (infrastructure non versionnée, § 4.10) est
propre à ce module."""

import base64
import binascii

from fastapi import APIRouter, Depends, Form, Header, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.afnor.versioning.registry import register_version
from app.api.afnor._common import register_common_routes
from app.auth.oauth import issue_token_response
from app.auth.rate_limit import rate_limit
from app.db.session import get_db
from app.services import audit_trace_service

AFNOR_API_VERSION = "v1"

router = APIRouter()
register_common_routes(router, AFNOR_API_VERSION)


def _client_credentials_from_basic_auth(authorization: str | None) -> tuple[str, str] | None:
    """RFC 6749 § 2.3.1 recommande `client_secret_basic` (en-tête `Authorization:
    Basic base64(client_id:client_secret)`) — et c'est en réalité ce qu'envoie
    `requests_oauthlib.OAuth2Session.fetch_token(client_id=..., client_secret=...)`
    par défaut (utilisé tel quel par `pyfrctc.get_session`, donc par Odoo
    `l10n_fr_einvoicing` pour s'authentifier auprès de ce routeur), pas
    `client_secret_post` comme supposé initialement (§ 4.10) — d'où le
    "(missing_token) Missing access token parameter" côté Odoo : sa requête de jeton
    échouait silencieusement (422, `client_id`/`client_secret` absents du corps)."""
    if not authorization or not authorization.startswith("Basic "):
        return None
    try:
        decoded = base64.b64decode(authorization.removeprefix("Basic ")).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=401, detail="Invalid Basic authorization header") from exc
    if ":" not in decoded:
        raise HTTPException(status_code=401, detail="Invalid Basic authorization header")
    client_id, _, client_secret = decoded.partition(":")
    return client_id, client_secret


@router.post("/oauth/token", dependencies=[Depends(rate_limit(scope="oauth_token"))])
def issue_token(
    request: Request,
    response: Response,
    grant_type: str = Form(...),
    client_id: str | None = Form(default=None),
    client_secret: str | None = Form(default=None),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """Conformité RFC 6749 (authentification client, validation du grant, erreurs
    normalisées) déléguée à Authlib — cf. `app.auth.oauth.issue_token_response`.
    `client_id`/`client_secret` : `client_secret_basic` (en-tête `Authorization`) si
    présent, sinon `client_secret_post` (corps du formulaire, § 4.10)."""
    from_basic_auth = _client_credentials_from_basic_auth(authorization)
    if from_basic_auth is not None:
        client_id, client_secret = from_basic_auth
    if not client_id or not client_secret:
        raise HTTPException(status_code=400, detail="Missing client_id/client_secret")

    status_code, body = issue_token_response(
        db, grant_type=grant_type, client_id=client_id, client_secret=client_secret
    )
    response.status_code = status_code
    audit_trace_service.record_odoo_flow_trace(
        db,
        request,
        afnor_api_version=AFNOR_API_VERSION,
        endpoint="POST /oauth/token",
        client_id=client_id,
        response={"status": "issued" if status_code == 200 else body.get("error")},
        http_status=status_code,
    )
    return body


register_version(AFNOR_API_VERSION, router)
