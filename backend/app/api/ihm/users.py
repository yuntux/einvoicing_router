"""Gestion des accès (spec.md § 6.1/NF4, lot 7) — réservée aux administrateurs."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.session import require_admin
from app.db.session import get_db
from app.models.referential import User
from app.schemas.user import UserAccessUpdate, UserRead
from app.services import user_access_service

router = APIRouter()


def _to_read(user: User) -> UserRead:
    return UserRead(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        company_ids=[c.id for c in user.companies],
    )


@router.get("", response_model=list[UserRead], dependencies=[Depends(require_admin)])
def list_users(db: Session = Depends(get_db)):
    return [_to_read(user) for user in user_access_service.list_users(db)]


@router.put("/{user_id}/access", response_model=UserRead, dependencies=[Depends(require_admin)])
def update_user_access(user_id: int, payload: UserAccessUpdate, db: Session = Depends(get_db)):
    user = user_access_service.update_access(
        db, user_id=user_id, role=payload.role, company_ids=payload.company_ids
    )
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return _to_read(user)
