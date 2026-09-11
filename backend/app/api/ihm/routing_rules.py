from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.referential import RoutingRuleCreate, RoutingRuleRead, TargetApplicationRead
from app.services import routing_rule_service

router = APIRouter()


@router.get("", response_model=list[RoutingRuleRead])
def list_routing_rules(partner_id: int | None = None, db: Session = Depends(get_db)):
    return routing_rule_service.list_rules(db, partner_id=partner_id)


@router.post("", response_model=RoutingRuleRead, status_code=201)
def create_routing_rule(payload: RoutingRuleCreate, db: Session = Depends(get_db)):
    return routing_rule_service.create_rule(
        db,
        partner_directory_id=payload.partner_directory_id,
        target_application_id=payload.target_application_id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        active=payload.active,
    )


@router.get("/resolve", response_model=list[TargetApplicationRead])
def resolve_routing(
    siren: str = Query(..., min_length=9, max_length=9),
    reference_date: date = Query(default_factory=date.today),
    db: Session = Depends(get_db),
):
    """Résout les applications cibles pour un émetteur/date donnés (§ 4.3)."""
    return routing_rule_service.resolve(db, siren=siren, reference_date=reference_date)
