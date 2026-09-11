"""UserService — résolution des utilisateurs à la connexion (spec.md § 6.1/NF3/NF4,
lot 7)."""

from sqlalchemy.orm import Session

from app.models.referential import User


class UnknownUserError(Exception):
    """Aucun compte pré-provisionné (par email) ne correspond à cette connexion —
    levée sauf pour la toute première connexion jamais effectuée (amorçage, cf.
    `resolve_login_user`)."""


class InactiveUserError(Exception):
    """Le compte existe mais a été désactivé par un administrateur (§ NF4)."""


def resolve_login_user(db: Session, *, oidc_subject: str, email: str, name: str) -> User:
    """Résout l'utilisateur d'une connexion réussie côté IdP (Entra ID ou mode `dev`).

    Ne crée **plus** de compte à la volée pour un email inconnu : les comptes sont
    pré-provisionnés (email seul) par un administrateur depuis l'IHM (§ NF4,
    `POST /api/ihm/users`), avant la première connexion de leur titulaire.

    - Trouvé par `oidc_subject` (connexions suivantes) → retourné tel quel (après
      contrôle `is_active`).
    - Sinon trouvé par `email` (première connexion d'un compte pré-provisionné) →
      `oidc_subject` est rattaché à cette ligne ; `name` est complété depuis les
      claims OIDC s'il n'avait pas déjà été saisi par l'admin.
    - Sinon, **exception** : `UnknownUserError`, sauf amorçage — si la table `users`
      est entièrement vide, la toute première connexion crée son propre compte
      `admin` (sans lui, aucun administrateur n'existerait pour pré-provisionner qui
      que ce soit).
    - Un compte trouvé (par l'une ou l'autre voie) mais `is_active=False` lève
      `InactiveUserError`.
    """
    user = db.query(User).filter(User.oidc_subject == oidc_subject).first()

    if user is None:
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            if db.query(User).count() == 0:
                user = User(oidc_subject=oidc_subject, email=email, name=name, role="admin")
                db.add(user)
                db.commit()
                db.refresh(user)
                return user
            raise UnknownUserError(email)

        user.oidc_subject = oidc_subject
        if not user.name:
            user.name = name
        db.commit()
        db.refresh(user)

    if not user.is_active:
        raise InactiveUserError(email)

    return user
