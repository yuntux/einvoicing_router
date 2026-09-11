from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.referential import PartnerDirectoryCreate, PartnerDirectoryRead
from app.services import directory_service

router = APIRouter()


@router.get("", response_model=list[PartnerDirectoryRead])
def list_partners(db: Session = Depends(get_db)):
    return directory_service.list_partners(db)


@router.post("", response_model=PartnerDirectoryRead, status_code=201)
def create_partner(payload: PartnerDirectoryCreate, db: Session = Depends(get_db)):
    return directory_service.create_partner(
        db, siren=payload.siren, name=payload.name, siret=payload.siret
    )
