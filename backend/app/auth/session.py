"""Session IHM (spec.md NF3/NF4, lot 7) — jeton bearer JWT signé HS256, distinct du
jeton émis pour l'API AFNOR (`app.auth.oauth`, applications OAuth par entreprise) :
celui-ci identifie un **utilisateur humain**, avec son rôle et son périmètre
d'entreprises (§ 6.1)."""

import time

import jwt
from fastapi import Cookie, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import get_db
from app.models.referential import User

JWT_ALGORITHM = "HS256"

# Claim `typ` distinguant ce jeton du jeton OAuth émis pour les applications
# consommatrices (§ 4.10, `app.auth.oauth`) — signés avec des secrets déjà distincts
# (`session_secret` vs `jwt_secret`), cette claim est une seconde barrière : même si
# les deux secrets venaient un jour à être confondus par erreur, un jeton de l'un ne
# serait jamais accepté à la place de l'autre.
_TOKEN_TYPE = "ihm_session"


def issue_session_token(user: User) -> str:
    now = int(time.time())
    payload = {
        "sub": str(user.id),
        "role": user.role,
        "typ": _TOKEN_TYPE,
        "iat": now,
        "exp": now + settings.session_expiry_seconds,
    }
    return jwt.encode(payload, settings.session_secret, algorithm=JWT_ALGORITHM)


def _decode_session_token(token: str) -> dict:
    payload = jwt.decode(token, settings.session_secret, algorithms=[JWT_ALGORITHM])
    if payload.get("typ") != _TOKEN_TYPE:
        raise jwt.InvalidTokenError("Unexpected token type")
    return payload


def get_current_user(
    session_token: str | None = Cookie(default=None, alias=settings.session_cookie_name),
    db: Session = Depends(get_db),
) -> User | None:
    """Résout l'utilisateur courant depuis le cookie de session.

    Retourne `None` sans erreur tant que `settings.oidc_mode == "disabled"` (défaut
    dev/tests, comportement des lots 0-6 inchangé — aucune authentification requise).
    Dès que l'authentification est activée (`dev` ou `entra_id`), une session absente
    ou invalide est encore tolérée ici (routes publiques comme `/auth/me`) ; c'est
    `require_current_user` qui impose la présence d'une session valide."""
    if settings.oidc_mode == "disabled":
        return None
    if not session_token:
        return None
    try:
        payload = _decode_session_token(session_token)
    except jwt.PyJWTError:
        return None
    user = db.get(User, int(payload["sub"]))
    return user


def require_current_user(
    user: User | None = Depends(get_current_user),
) -> User | None:
    """Dépendance à poser sur les routes IHM protégées (§ NF3) : lève 401 si
    l'authentification est activée et qu'aucune session valide n'est présente.
    Ne bloque jamais rien tant que `oidc_mode == "disabled"` (retourne `None`)."""
    if settings.oidc_mode == "disabled":
        return None
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def require_admin(
    user: User | None = Depends(require_current_user),
) -> User | None:
    """Réservé à la gestion des accès (§ NF4) : lève 403 si un utilisateur authentifié
    n'est pas `admin`. Comme les autres dépendances de ce module, ne bloque rien tant
    que `oidc_mode == "disabled"`."""
    if settings.oidc_mode == "disabled":
        return None
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return user
