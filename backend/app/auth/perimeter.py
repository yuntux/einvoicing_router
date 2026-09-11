"""Périmètre d'accès par entreprise (spec.md § 6.1/NF4, lot 7).

`None` signifie systématiquement "aucune restriction" — que ce soit parce que
l'authentification est désactivée (`get_current_user` retourne toujours `None` dans ce
cas, cf. `app.auth.session`) ou parce que l'utilisateur est `admin` (§ 6.1 : l'
"AccessScope" d'un admin couvre toutes les entreprises gérées)."""

from fastapi import HTTPException
from sqlalchemy.orm import Query

from app.models.referential import User


def allowed_company_ids(user: User | None) -> list[int] | None:
    if user is None or user.role == "admin":
        return None
    return [company.id for company in user.companies]


def apply_company_scope(query: Query, *, user: User | None, company_id_column) -> Query:
    """Filtre `query` sur `company_id_column` selon le périmètre de `user` — no-op si
    `allowed_company_ids` retourne `None`."""
    ids = allowed_company_ids(user)
    if ids is None:
        return query
    return query.filter(company_id_column.in_(ids))


def ensure_company_in_scope(user: User | None, company_id: int | None) -> None:
    """Lève 403 si `company_id` est hors du périmètre de `user`. Ne bloque jamais une
    ressource sans entreprise associée (`company_id is None`, ex. application cible
    mail partagée) : seule une association explicite à une entreprise hors périmètre
    est un refus d'accès."""
    if company_id is None:
        return
    ids = allowed_company_ids(user)
    if ids is not None and company_id not in ids:
        raise HTTPException(status_code=403, detail="Company outside of your access scope")
