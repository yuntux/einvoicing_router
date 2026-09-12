from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth.perimeter import apply_company_scope, ensure_company_in_scope
from app.auth.session import get_current_user
from app.db.session import get_db
from app.models.referential import Company, User
from app.schemas.company import CompanyCreate, CompanyRead
from app.schemas.superpdp_credentials import (
    AfnorPlatform,
    SuperPDPCredentialsCreate,
    SuperPDPCredentialsStatus,
)
from app.services import audit_trace_service, superpdp_credentials_service

# `admin_router` : réservé aux administrateurs (§ NF4), monté au même préfixe dans
# `app/main.py` avec `dependencies=ihm_auth + [Depends(require_admin)]` — créer une
# entreprise gérée n'est pas une action qu'un utilisateur restreint à son propre
# périmètre doit pouvoir déclencher. Le reste de ce router reste ouvert à tout
# utilisateur authentifié, filtré par périmètre entreprise au cas par cas
# (`ensure_company_in_scope`/`apply_company_scope`).
router = APIRouter()
admin_router = APIRouter()


@router.get("", response_model=list[CompanyRead])
def list_companies(
    db: Session = Depends(get_db), user: User | None = Depends(get_current_user)
) -> list[Company]:
    """§ NF4 : un utilisateur restreint ne voit que les entreprises de son périmètre
    (`user.companies`) — un admin, ou hors authentification, voit tout."""
    query = apply_company_scope(db.query(Company), user=user, company_id_column=Company.id)
    return list(query.order_by(Company.id).all())


@router.get("/afnor-platforms", response_model=list[AfnorPlatform])
def list_afnor_platforms() -> list[dict[str, str]]:
    """Plateformes AFNOR connues de `pyfrctc` (§ 4.10) — alimente le sélecteur de
    plateforme par entreprise, plutôt qu'une URL libre non validée."""
    return superpdp_credentials_service.list_platforms()


@admin_router.post("", response_model=CompanyRead, status_code=201)
def create_company(
    payload: CompanyCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
) -> Company:
    company = Company(
        siren=payload.siren,
        name=payload.name,
        create_user_id=user.id if user else None,
        write_user_id=user.id if user else None,
    )
    db.add(company)
    db.commit()
    db.refresh(company)
    audit_trace_service.record_user_action(
        db, request, user, action="company_create", target=str(company.id)
    )
    return company


@router.get(
    "/{company_id}/superpdp-credentials", response_model=SuperPDPCredentialsStatus
)
def get_superpdp_credentials_status(
    company_id: int,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    """Ne renvoie jamais le secret (chiffré ou non) — seulement s'il est configuré."""
    ensure_company_in_scope(user, company_id)
    application = superpdp_credentials_service.get_credentials_application(
        db, company_id=company_id
    )
    if application is None:
        return SuperPDPCredentialsStatus(configured=False)
    return SuperPDPCredentialsStatus(
        configured=True, client_id=application.client_id, platform=application.platform
    )


@router.put(
    "/{company_id}/superpdp-credentials", response_model=SuperPDPCredentialsStatus
)
def set_superpdp_credentials(
    company_id: int,
    payload: SuperPDPCredentialsCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    ensure_company_in_scope(user, company_id)
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")

    connection_ok, connection_error = superpdp_credentials_service.test_connection(
        company_siren=company.siren,
        client_id=payload.client_id,
        client_secret=payload.client_secret,
        platform=payload.platform,
    )
    if not connection_ok:
        raise HTTPException(
            status_code=422, detail=f"Test de connexion à l'API AFNOR échoué : {connection_error}"
        )

    application = superpdp_credentials_service.set_credentials(
        db,
        company_id=company_id,
        client_id=payload.client_id,
        client_secret=payload.client_secret,
        platform=payload.platform,
        actor_user_id=user.id if user else None,
    )
    audit_trace_service.record_user_action(
        db, request, user, action="superpdp_credentials_update", target=str(company_id)
    )
    return SuperPDPCredentialsStatus(
        configured=True, client_id=application.client_id, platform=application.platform
    )
