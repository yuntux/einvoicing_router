from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.referential import Company
from app.schemas.company import CompanyCreate, CompanyRead

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
