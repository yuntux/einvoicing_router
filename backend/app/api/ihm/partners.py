from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.auth.session import get_current_user
from app.db.session import get_db
from app.models.referential import User
from app.schemas.referential import PartnerDirectoryCreate, PartnerDirectoryRead
from app.services import audit_trace_service, directory_service

router = APIRouter()


@router.get("", response_model=list[PartnerDirectoryRead])
def list_partners(db: Session = Depends(get_db)):
    return directory_service.list_partners(db)


@router.post("", response_model=PartnerDirectoryRead, status_code=201)
def create_partner(
    payload: PartnerDirectoryCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    partner = directory_service.create_partner(
        db,
        siren=payload.siren,
        name=payload.name,
        siret=payload.siret,
        actor_user_id=user.id if user else None,
    )
    audit_trace_service.record_user_action(
        db, request, user, action="partner_create", target=str(partner.id)
    )
    return partner
