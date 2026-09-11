"""Gestion du périmètre d'accès des utilisateurs (spec.md § 6.1/NF4, lot 7)."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.referential import Company, User


class EmailAlreadyExistsError(Exception):
    """Un compte existe déjà pour cet email (pré-provisionné ou déjà connecté)."""


def list_users(db: Session) -> list[User]:
    return list(db.query(User).order_by(User.id).all())


def create_user(db: Session, *, email: str, name: str | None) -> User:
    """Pré-provisionne un compte (§ NF4) : seul l'email est garanti — `oidc_subject`
    reste nul jusqu'à la première connexion de son titulaire (cf.
    `user_service.resolve_login_user`), qui le rattachera à cette ligne plutôt que
    d'en créer une nouvelle."""
    user = User(email=email, name=name, role="user", is_active=True)
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise EmailAlreadyExistsError(email) from exc
    db.refresh(user)
    return user


def update_access(
    db: Session, *, user_id: int, role: str, company_ids: list[int], is_active: bool
) -> User | None:
    user = db.get(User, user_id)
    if user is None:
        return None
    user.role = role
    user.is_active = is_active
    user.companies = (
        db.query(Company).filter(Company.id.in_(company_ids)).all() if company_ids else []
    )
    db.commit()
    db.refresh(user)
    return user
