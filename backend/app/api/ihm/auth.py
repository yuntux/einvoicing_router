"""Authentification IHM (spec.md NF3, lot 7) : connexion OIDC réelle (Entra ID, via
Authlib — cf. `app.auth.oidc`), mode `dev` (sans IdP réel, pour exercer le périmètre
d'accès en développement), et no-op tant que `settings.oidc_mode == "disabled"`
(comportement des lots 0-6)."""

from authlib.integrations.base_client.errors import OAuthError
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth.oidc import entra_id_client
from app.auth.session import get_current_user, issue_session_token
from app.config import settings
from app.db.session import get_db
from app.models.referential import User
from app.schemas.auth import CurrentUserRead, CurrentUserStatus
from app.services.user_service import get_or_create_user

router = APIRouter()


def _to_user_read(user: User) -> CurrentUserRead:
    return CurrentUserRead(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        company_ids=[c.id for c in user.companies],
    )


def _set_session_cookie(response: Response, user: User) -> None:
    response.set_cookie(
        settings.session_cookie_name,
        issue_session_token(user),
        httponly=True,
        max_age=settings.session_expiry_seconds,
        samesite="lax",
    )


@router.get("/me", response_model=CurrentUserStatus)
def me(user: User | None = Depends(get_current_user)):
    return CurrentUserStatus(
        oidc_mode=settings.oidc_mode,
        authenticated=user is not None,
        user=_to_user_read(user) if user else None,
    )


@router.get("/login")
async def login(
    request: Request,
    email: str = Query(default="dev@example.com"),
    name: str = Query(default="Dev User"),
    db: Session = Depends(get_db),
):
    if settings.oidc_mode == "disabled":
        raise HTTPException(status_code=404, detail="Authentication is disabled")

    if settings.oidc_mode == "dev":
        user = get_or_create_user(db, oidc_subject=f"dev:{email}", email=email, name=name)
        response = RedirectResponse(url=settings.frontend_base_url)
        _set_session_cookie(response, user)
        return response

    # entra_id : Authlib gère la découverte OIDC, PKCE et le state/nonce (stockés
    # côté serveur via SessionMiddleware, cf. app.main) — cf. app.auth.oidc.
    client = entra_id_client()
    return await client.authorize_redirect(request, settings.oidc_redirect_uri)


@router.get("/callback")
async def callback(request: Request, db: Session = Depends(get_db)):
    if settings.oidc_mode != "entra_id":
        raise HTTPException(status_code=404, detail="Not found")

    client = entra_id_client()
    try:
        token = await client.authorize_access_token(request)
    except OAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    claims = token.get("userinfo") or {}
    if not claims.get("sub"):
        raise HTTPException(status_code=400, detail="Missing ID token claims")

    user = get_or_create_user(
        db,
        oidc_subject=claims["sub"],
        email=claims.get("email") or claims.get("preferred_username"),
        name=claims.get("name", claims.get("email", "")),
    )

    response = RedirectResponse(url=settings.frontend_base_url)
    _set_session_cookie(response, user)
    return response


@router.post("/logout", status_code=204)
def logout(response: Response):
    response.delete_cookie(settings.session_cookie_name)
