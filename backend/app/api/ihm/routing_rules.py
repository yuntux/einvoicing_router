from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.auth.session import get_current_user, require_write
from app.db.session import get_db
from app.models.referential import PartnerDirectory, TargetApplication, User
from app.schemas.referential import RoutingRuleRead, RoutingRuleSetActive, TargetApplicationRead
from app.services import audit_trace_service, invoice_ingestion_service, routing_rule_service

router = APIRouter()


@router.get("", response_model=list[RoutingRuleRead])
def list_routing_rules(partner_id: int | None = None, db: Session = Depends(get_db)):
    return routing_rule_service.list_rules(db, partner_id=partner_id)


@router.put(
    "/{partner_directory_id}/{target_application_id}",
    response_model=RoutingRuleRead | None,
    dependencies=[Depends(require_write)],
)
def set_routing_rule_active(
    partner_directory_id: int,
    target_application_id: int,
    payload: RoutingRuleSetActive,
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    """Coche/décoche la case d'un couple (fournisseur, application cible) — matrice
    éditable de la page Règles de routage (§ 4.3). Crée la règle si `active=True` et
    qu'elle n'existe pas encore, la supprime si `active=False`."""
    if db.get(PartnerDirectory, partner_directory_id) is None:
        raise HTTPException(status_code=404, detail="Partner not found")
    if db.get(TargetApplication, target_application_id) is None:
        raise HTTPException(status_code=404, detail="Target application not found")
    rule = routing_rule_service.set_rule_active(
        db,
        partner_directory_id=partner_directory_id,
        target_application_id=target_application_id,
        active=payload.active,
        actor_user_id=user.id if user else None,
    )
    if payload.active and payload.reroute_existing:
        # Rejoue immédiatement les factures déjà reçues de ce fournisseur qui n'ont
        # pas encore de routage vers cette cible (§ 4.3) — sans ça, il faudrait
        # attendre le prochain cycle de polling (jusqu'à 15 min) pour qu'elles soient
        # enfin routées. L'utilisateur peut désactiver ce rejeu (payload.reroute_existing
        # = False) pour ne router que les prochaines factures reçues.
        invoice_ingestion_service.reroute_unrouted_invoices_for_partner(
            db,
            partner_directory_id=partner_directory_id,
            target_application_id=target_application_id,
        )
    audit_trace_service.record_user_action(
        db,
        request,
        user,
        action="routing_rule_activate" if payload.active else "routing_rule_deactivate",
        target=f"{partner_directory_id}:{target_application_id}",
    )
    return rule


@router.get("/resolve", response_model=list[TargetApplicationRead])
def resolve_routing(
    siren: str = Query(..., min_length=9, max_length=9),
    company_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """Résout les applications cibles pour un émetteur donné (§ 4.3). `company_id`
    (optionnel) restreint aux applications de cette entreprise — sans lui,
    prévisualisation toutes entreprises confondues (cf. NF2/routing_rule_service.resolve)."""
    return routing_rule_service.resolve(db, siren=siren, company_id=company_id)
