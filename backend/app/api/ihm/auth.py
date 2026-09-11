"""Authentification IHM (spec.md NF3, lot 7) : connexion OIDC réelle (Entra ID),
mode `dev` (sans IdP réel, pour exercer le périmètre d'accès en développement), et
no-op tant que `settings.oidc_mode == "disabled"` (comportement des lots 0-6)."""

import time

import jwt
from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import oidc
from app.auth.session import JWT_ALGORITHM, get_current_user, issue_session_token
from app.config import settings
from app.db.session import get_db
from app.models.referential import User
from app.schemas.auth import CurrentUserRead, CurrentUserStatus
from app.services.user_service import get_or_create_user

router = APIRouter()

OIDC_STATE_COOKIE = "router_oidc_state"


def _to_user_read(user: User) -> CurrentUserRead:
    return CurrentUserRead(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        company_ids=[c.id for c in user.companies],
    )


@router.get("/me", response_model=CurrentUserStatus)
def me(user: User | None = Depends(get_current_user)):
    return CurrentUserStatus(
        oidc_mode=settings.oidc_mode,
        authenticated=user is not None,
        user=_to_user_read(user) if user else None,
    )


@router.get("/login")
def login(
    email: str = Query(default="dev@example.com"),
    name: str = Query(default="Dev User"),
    db: Session = Depends(get_db),
):
    if settings.oidc_mode == "disabled":
        raise HTTPException(status_code=404, detail="Authentication is disabled")

    if settings.oidc_mode == "dev":
        user = get_or_create_user(db, oidc_subject=f"dev:{email}", email=email, name=name)
        response = RedirectResponse(url=settings.frontend_base_url)
        response.set_cookie(
            settings.session_cookie_name,
            issue_session_token(user),
            httponly=True,
            max_age=settings.session_expiry_seconds,
            samesite="lax",
        )
        return response

    # entra_id : redirige vers Microsoft, en conservant state/code_verifier dans un
    # cookie signé de courte durée (pas de session serveur, § architecture stateless).
    state = jwt.encode({"nonce": time.time()}, settings.jwt_secret, algorithm=JWT_ALGORITHM)
    code_verifier, code_challenge = oidc.generate_pkce_pair()
    authorization_url = oidc.build_authorization_url(state=state, code_challenge=code_challenge)

    response = RedirectResponse(url=authorization_url)
    response.set_cookie(
        OIDC_STATE_COOKIE,
        jwt.encode(
            {"state": state, "code_verifier": code_verifier},
            settings.jwt_secret,
            algorithm=JWT_ALGORITHM,
        ),
        httponly=True,
        max_age=600,
        samesite="lax",
    )
    return response


@router.get("/callback")
def callback(
    code: str = Query(...),
    state: str = Query(...),
    oidc_state_cookie: str | None = Cookie(default=None, alias=OIDC_STATE_COOKIE),
    db: Session = Depends(get_db),
):
    if settings.oidc_mode != "entra_id":
        raise HTTPException(status_code=404, detail="Not found")
    if not oidc_state_cookie:
        raise HTTPException(status_code=400, detail="Missing OIDC state")

    try:
        stashed = jwt.decode(oidc_state_cookie, settings.jwt_secret, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=400, detail="Invalid OIDC state") from exc
    if stashed["state"] != state:
        raise HTTPException(status_code=400, detail="OIDC state mismatch")

    id_token = oidc.exchange_code_for_id_token(code=code, code_verifier=stashed["code_verifier"])
    claims = oidc.validate_id_token(id_token)

    user = get_or_create_user(
        db,
        oidc_subject=claims["sub"],
        email=claims.get("email") or claims.get("preferred_username"),
        name=claims.get("name", claims.get("email", "")),
    )

    response = RedirectResponse(url=settings.frontend_base_url)
    response.delete_cookie(OIDC_STATE_COOKIE)
    response.set_cookie(
        settings.session_cookie_name,
        issue_session_token(user),
        httponly=True,
        max_age=settings.session_expiry_seconds,
        samesite="lax",
    )
    return response


@router.post("/logout", status_code=204)
def logout(response: Response):
    response.delete_cookie(settings.session_cookie_name)
