"""UserService — résolution des utilisateurs à la connexion (spec.md § 6.1/NF3/NF4,
lot 7)."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.referential import User


class UnknownUserError(Exception):
    """Aucun compte pré-provisionné (par email) ne correspond à cette connexion —
    levée sauf pour la toute première connexion jamais effectuée (amorçage, cf.
    `resolve_login_user`)."""


class InactiveUserError(Exception):
    """Le compte existe mais a été désactivé par un administrateur (§ NF4)."""


class EmailConflictError(Exception):
    """`email` a changé côté IdP depuis la dernière connexion (cas réel : mariage,
    changement de raison sociale…) mais la nouvelle valeur appartient déjà à un autre
    compte du routeur — resynchroniser aveuglément casserait l'unicité de `email`."""


def resolve_login_user(db: Session, *, oidc_subject: str, email: str, name: str) -> User:
    """Résout l'utilisateur d'une connexion réussie côté IdP (Entra ID ou mode `dev`).

    Ne crée **plus** de compte à la volée pour un email inconnu : les comptes sont
    pré-provisionnés (email seul) par un administrateur depuis l'IHM (§ NF4,
    `POST /api/ihm/users`), avant la première connexion de leur titulaire.

    - Trouvé par `oidc_subject` (connexions suivantes) → `name` et `email` sont
      resynchronisés à **chaque** connexion depuis les claims OIDC (source de vérité
      côté IdP — un nom ou une adresse email peut changer dans le temps pour un même
      compte).
    - Sinon trouvé par `email` (première connexion d'un compte pré-provisionné) →
      `oidc_subject` est rattaché à cette ligne, `name` est renseigné.
    - Sinon, **exception** : `UnknownUserError`, sauf amorçage — si la table `users`
      est entièrement vide, la toute première connexion crée son propre compte
      `admin` (sans lui, aucun administrateur n'existerait pour pré-provisionner qui
      que ce soit).
    - Un compte trouvé (par l'une ou l'autre voie) mais `is_active=False` lève
      `InactiveUserError`.
    - Resynchroniser `email` sur un compte déjà lié (`oidc_subject` trouvé) vers une
      valeur déjà prise par un **autre** compte lève `EmailConflictError` plutôt que
      d'échouer silencieusement ou de violer l'unicité de `email` en base.
    """
    user = db.query(User).filter(User.oidc_subject == oidc_subject).first()

    if user is not None:
        user.name = name
        user.email = email
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise EmailConflictError(email) from exc
        db.refresh(user)
    else:
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
        user.name = name
        db.commit()
        db.refresh(user)

    if not user.is_active:
        raise InactiveUserError(email)

    return user
