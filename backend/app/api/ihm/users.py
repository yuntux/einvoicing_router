"""Gestion des accès (spec.md § 6.1/NF4, lot 7) — réservée aux administrateurs.

Toutes les routes de ce router sont admin-only : le contrôle est posé une seule fois,
sur `include_router()` (cf. `app/main.py`), plutôt que répété sur chaque décorateur."""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth.session import get_current_user
from app.db.session import get_db
from app.models.referential import User
from app.schemas.user import UserAccessUpdate, UserCreate, UserRead
from app.services import audit_trace_service, user_access_service
from app.services.user_access_service import EmailAlreadyExistsError

router = APIRouter()


def _to_read(user: User) -> UserRead:
    return UserRead(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        company_ids=[c.id for c in user.companies],
        is_active=user.is_active,
        has_logged_in=user.oidc_subject is not None,
        create_user_id=user.create_user_id,
        create_datetime=user.create_datetime,
        write_user_id=user.write_user_id,
        write_datetime=user.write_datetime,
    )


@router.get("", response_model=list[UserRead])
def list_users(db: Session = Depends(get_db)):
    return [_to_read(user) for user in user_access_service.list_users(db)]


@router.post("", response_model=UserRead, status_code=201)
def create_user(
    payload: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
):
    """Pré-provisionne un compte par email (§ NF4) : sa première connexion OIDC
    rattachera automatiquement `oidc_subject` à cette ligne (cf.
    `user_service.resolve_login_user`) plutôt que d'être rejetée comme inconnue."""
    try:
        user = user_access_service.create_user(
            db, email=payload.email, name=payload.name, actor_user_id=actor.id if actor else None
        )
    except EmailAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail="A user with this email already exists") from exc
    audit_trace_service.record_audit_log(
        db,
        action="user_create",
        target=str(user.id),
        user_id=actor.id if actor else None,
        ip_address=request.client.host if request.client else None,
    )
    return _to_read(user)


@router.put("/{user_id}/access", response_model=UserRead)
def update_user_access(
    user_id: int,
    payload: UserAccessUpdate,
    request: Request,
    db: Session = Depends(get_db),
    actor: User | None = Depends(get_current_user),
):
    user = user_access_service.update_access(
        db,
        user_id=user_id,
        role=payload.role,
        company_ids=payload.company_ids,
        is_active=payload.is_active,
        actor_user_id=actor.id if actor else None,
    )
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    audit_trace_service.record_audit_log(
        db,
        action="user_access_update",
        target=str(user.id),
        user_id=actor.id if actor else None,
        ip_address=request.client.host if request.client else None,
    )
    return _to_read(user)
