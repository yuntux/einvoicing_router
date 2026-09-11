"""Authentification par application OAuth (spec.md § 4.4/§ 4.9.2/§ 4.10).

Flux `client_credentials` minimal : un consommateur (Odoo) échange son
`client_id`/`client_secret` contre un jeton bearer (JWT signé HS256, § 4.10 — un
jeton par entreprise). Le secret n'est jamais stocké en clair : seul un hash est
conservé, comparé lors de l'émission du jeton.
"""

import hashlib
import hmac
import secrets
import time

import jwt
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import get_db
from app.models.referential import OAuthApplication

JWT_ALGORITHM = "HS256"


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


def issue_access_token(oauth_app: OAuthApplication) -> str:
    now = int(time.time())
    payload = {
        "sub": oauth_app.client_id,
        "company_id": oauth_app.company_id,
        "scope": oauth_app.scope,
        "iat": now,
        "exp": now + settings.jwt_expiry_seconds,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def get_current_oauth_application(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> OAuthApplication:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.removeprefix("Bearer ")
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc

    oauth_app = (
        db.query(OAuthApplication).filter(OAuthApplication.client_id == payload["sub"]).first()
    )
    if oauth_app is None:
        raise HTTPException(status_code=401, detail="Unknown client")
    return oauth_app
