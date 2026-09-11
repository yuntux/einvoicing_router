from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.referential import TargetApplication
from app.schemas.referential import TargetApplicationCreate, TargetApplicationRead

router = APIRouter()


@router.get("", response_model=list[TargetApplicationRead])
def list_target_applications(db: Session = Depends(get_db)):
    return list(db.query(TargetApplication).order_by(TargetApplication.id).all())


@router.post("", response_model=TargetApplicationRead, status_code=201)
def create_target_application(payload: TargetApplicationCreate, db: Session = Depends(get_db)):
    target_application = TargetApplication(
        name=payload.name,
        routing_method=payload.routing_method,
        company_id=payload.company_id,
        parameters=payload.parameters,
    )
    db.add(target_application)
    db.commit()
    db.refresh(target_application)
    return target_application
