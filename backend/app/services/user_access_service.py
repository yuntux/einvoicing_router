"""Gestion du périmètre d'accès des utilisateurs (spec.md § 6.1/NF4, lot 7)."""

from sqlalchemy.orm import Session

from app.models.referential import Company, User


def list_users(db: Session) -> list[User]:
    return list(db.query(User).order_by(User.id).all())


def update_access(db: Session, *, user_id: int, role: str, company_ids: list[int]) -> User | None:
    user = db.get(User, user_id)
    if user is None:
        return None
    user.role = role
    user.companies = (
        db.query(Company).filter(Company.id.in_(company_ids)).all() if company_ids else []
    )
    db.commit()
    db.refresh(user)
    return user
