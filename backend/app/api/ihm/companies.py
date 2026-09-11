from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.referential import Company
from app.schemas.company import CompanyCreate, CompanyRead
from app.schemas.superpdp_credentials import SuperPDPCredentialsCreate, SuperPDPCredentialsStatus
from app.services import superpdp_credentials_service

router = APIRouter()


@router.get("", response_model=list[CompanyRead])
def list_companies(db: Session = Depends(get_db)) -> list[Company]:
    return list(db.query(Company).order_by(Company.id).all())


@router.post("", response_model=CompanyRead, status_code=201)
def create_company(payload: CompanyCreate, db: Session = Depends(get_db)) -> Company:
    company = Company(siren=payload.siren, name=payload.name)
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


@router.get(
    "/{company_id}/superpdp-credentials", response_model=SuperPDPCredentialsStatus
)
def get_superpdp_credentials_status(company_id: int, db: Session = Depends(get_db)):
    """Ne renvoie jamais le secret (chiffré ou non) — seulement s'il est configuré."""
    application = superpdp_credentials_service.get_credentials_application(
        db, company_id=company_id
    )
    if application is None:
        return SuperPDPCredentialsStatus(configured=False)
    return SuperPDPCredentialsStatus(configured=True, client_id=application.client_id)


@router.put(
    "/{company_id}/superpdp-credentials", response_model=SuperPDPCredentialsStatus
)
def set_superpdp_credentials(
    company_id: int, payload: SuperPDPCredentialsCreate, db: Session = Depends(get_db)
):
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    application = superpdp_credentials_service.set_credentials(
        db, company_id=company_id, client_id=payload.client_id, client_secret=payload.client_secret
    )
    return SuperPDPCredentialsStatus(configured=True, client_id=application.client_id)
