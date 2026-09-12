from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.referential import PartnerDirectory, TargetApplication
from app.schemas.referential import (
    RoutingRuleCreate,
    RoutingRuleRead,
    RoutingRuleUpsert,
    TargetApplicationRead,
)
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


@router.put(
    "/{partner_directory_id}/{target_application_id}",
    response_model=RoutingRuleRead,
)
def upsert_routing_rule(
    partner_directory_id: int,
    target_application_id: int,
    payload: RoutingRuleUpsert,
    db: Session = Depends(get_db),
):
    """Crée ou met à jour la règle d'un couple (fournisseur, application cible) —
    matrice éditable de la page Règles de routage (§ 4.3)."""
    if db.get(PartnerDirectory, partner_directory_id) is None:
        raise HTTPException(status_code=404, detail="Partner not found")
    if db.get(TargetApplication, target_application_id) is None:
        raise HTTPException(status_code=404, detail="Target application not found")
    return routing_rule_service.upsert_rule(
        db,
        partner_directory_id=partner_directory_id,
        target_application_id=target_application_id,
        start_date=payload.start_date,
        end_date=payload.end_date,
    )


@router.get("/resolve", response_model=list[TargetApplicationRead])
def resolve_routing(
    siren: str = Query(..., min_length=9, max_length=9),
    reference_date: date = Query(default_factory=date.today),
    company_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """Résout les applications cibles pour un émetteur/date donnés (§ 4.3). `company_id`
    (optionnel) restreint aux applications `afnor_api` de cette entreprise — sans lui,
    prévisualisation toutes entreprises confondues (cf. NF2/routing_rule_service.resolve)."""
    return routing_rule_service.resolve(
        db, siren=siren, reference_date=reference_date, company_id=company_id
    )
