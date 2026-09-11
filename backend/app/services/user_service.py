"""UserService — provisionnement des utilisateurs authentifiés (spec.md § 6.1/NF3/NF4,
lot 7)."""

from sqlalchemy.orm import Session

from app.models.referential import User


def get_or_create_user(db: Session, *, oidc_subject: str, email: str, name: str) -> User:
    """Retrouve l'utilisateur par `oidc_subject`, à défaut par `email` (cas d'un
    utilisateur pré-provisionné côté périmètre avant sa première connexion), sinon le
    crée. Le tout premier utilisateur créé devient automatiquement `admin` (amorçage :
    sans lui, personne ne pourrait attribuer de périmètre à qui que ce soit)."""
    user = db.query(User).filter(User.oidc_subject == oidc_subject).first()
    if user is not None:
        return user

    user = db.query(User).filter(User.email == email).first()
    if user is not None:
        user.oidc_subject = oidc_subject
        db.commit()
        db.refresh(user)
        return user

    is_first_user = db.query(User).count() == 0
    user = User(
        oidc_subject=oidc_subject,
        email=email,
        name=name,
        role="admin" if is_first_user else "user",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
