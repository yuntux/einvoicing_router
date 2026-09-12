from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth.perimeter import ensure_company_in_scope
from app.auth.session import get_current_user
from app.db.session import get_db
from app.models.referential import Company, User
from app.schemas.company import CompanyCreate, CompanyLookup, CompanyRead
from app.schemas.certified_platform_credentials import (
    AfnorPlatform,
    CertifiedPlatformCredentialsCreate,
    CertifiedPlatformCredentialsStatus,
)
from app.scheduler.polling_job import run_polling_cycle
from app.services import audit_trace_service, certified_platform_credentials_service

# `router` : ouvert à tout utilisateur authentifié (`dependencies=ihm_auth` dans
# `app/main.py`) — uniquement la référence minimale id+nom (`/lookup`), dont ont
# besoin des pages non admin-only (ex. Règles de routage) pour afficher un nom
# d'entreprise, sans exposer la page Entreprises elle-même (§ NF4).
# `admin_router` : réservé aux administrateurs — la liste complète (SIREN, colonnes
# d'audit), la création, et les identifiants de plateforme certifiée (sensibles) de
# n'importe quelle entreprise.
router = APIRouter()
admin_router = APIRouter()


@router.get("/lookup", response_model=list[CompanyLookup])
def list_company_lookups(db: Session = Depends(get_db)) -> list[Company]:
    """Référence minimale (id + nom), toutes entreprises confondues, sans filtrage de
    périmètre : c'est une donnée non sensible utilisée pour l'affichage croisé sur
    des pages accessibles à un utilisateur restreint (ex. Règles de routage)."""
    return list(db.query(Company).order_by(Company.id).all())


@admin_router.get("", response_model=list[CompanyRead])
def list_companies(db: Session = Depends(get_db)) -> list[Company]:
    return list(db.query(Company).order_by(Company.id).all())


@admin_router.post("/run-polling-cycle", status_code=204)
def run_polling_cycle_endpoint(db: Session = Depends(get_db)) -> None:
    """Force immédiatement un passage du cycle de polling AFNOR/plateforme certifiée
    (§ 4.1, toutes entreprises confondues — `run_polling_cycle` n'est pas paramétrable
    par entreprise), sans attendre le prochain déclenchement du scheduler (jusqu'à
    `polling_interval_minutes`)."""
    run_polling_cycle(db)


@admin_router.get("/afnor-platforms", response_model=list[AfnorPlatform])
def list_afnor_platforms() -> list[dict[str, str]]:
    """Plateformes AFNOR connues de `pyfrctc` (§ 4.10) — alimente le sélecteur de
    plateforme par entreprise, plutôt qu'une URL libre non validée."""
    return certified_platform_credentials_service.list_platforms()


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


@admin_router.get(
    "/{company_id}/certified-platform-credentials", response_model=CertifiedPlatformCredentialsStatus
)
def get_certified_platform_credentials_status(
    company_id: int,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    """Ne renvoie jamais le secret (chiffré ou non) — seulement s'il est configuré."""
    ensure_company_in_scope(user, company_id)
    application = certified_platform_credentials_service.get_credentials_application(
        db, company_id=company_id
    )
    if application is None:
        return CertifiedPlatformCredentialsStatus(configured=False)
    return CertifiedPlatformCredentialsStatus(
        configured=True, client_id=application.certified_platform_client_id, platform=application.certified_platform
    )


@admin_router.put(
    "/{company_id}/certified-platform-credentials", response_model=CertifiedPlatformCredentialsStatus
)
def set_certified_platform_credentials(
    company_id: int,
    payload: CertifiedPlatformCredentialsCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    ensure_company_in_scope(user, company_id)
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")

    connection_ok, connection_error = certified_platform_credentials_service.test_connection(
        company_siren=company.siren,
        client_id=payload.client_id,
        client_secret=payload.client_secret,
        platform=payload.platform,
    )
    if not connection_ok:
        raise HTTPException(
            status_code=422, detail=f"Test de connexion à l'API AFNOR échoué : {connection_error}"
        )

    application = certified_platform_credentials_service.set_credentials(
        db,
        company_id=company_id,
        client_id=payload.client_id,
        client_secret=payload.client_secret,
        platform=payload.platform,
        actor_user_id=user.id if user else None,
    )
    audit_trace_service.record_user_action(
        db, request, user, action="certified_platform_credentials_update", target=str(company_id)
    )
    return CertifiedPlatformCredentialsStatus(
        configured=True, client_id=application.certified_platform_client_id, platform=application.certified_platform
    )
