"""LifecycleService — saisie manuelle des messages de cycle de vie (spec.md § 4.2/§ 6.2).

Lot 3 : la génération CDAR réelle (pyfrctc) n'est pas encore branchée — `AfnorFlow` est
créé pour matérialiser le suivi technique mais reste à l'état `created` (le lot 6
ajoutera la génération/transmission effective).

Note de conception : seul le sens "achat" (`side="purchase"`) est accessible depuis
cet écran, car il n'existe qu'un point d'entrée IHM — la fiche d'une facture *reçue*
(§ 6.1 : les factures émises ne sont pas stockées). Le statut `completed` (réservé aux
factures de vente) reste donc défini dans le catalogue mais inatteignable tant qu'un
écran dédié aux factures émises n'existe pas (probablement au lot 6, avec le proxy
d'émission Odoo).
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.invoicing import Invoice
from app.models.lifecycle import (
    AfnorFlow,
    AfnorFlowType,
    EventDirection,
    LifecycleEvent,
    LifecycleEventDetail,
)
from app.services.lifecycle_catalog import STATUS_CATALOG, ManualSide


class LifecycleValidationError(ValueError):
    pass


@dataclass
class ManualEventInput:
    status: str
    reason: str | None = None
    action: str | None = None
    comment: str | None = None
    confirmed: bool = False


_FLOW_TYPE_BY_SIDE: dict[ManualSide, AfnorFlowType] = {
    "purchase": AfnorFlowType.SUPPLIER_INVOICE_LC,
    "sale": AfnorFlowType.CUSTOMER_INVOICE_LC,
}


def create_manual_event(
    db: Session, *, invoice: Invoice, side: ManualSide, data: ManualEventInput
) -> LifecycleEvent:
    info = STATUS_CATALOG.get(data.status)
    if info is None or info.manual_side is None:
        raise LifecycleValidationError(
            f"Le statut '{data.status}' n'est pas saisissable manuellement."
        )
    if info.manual_side != side:
        raise LifecycleValidationError(
            f"Le statut '{data.status}' est réservé aux factures de "
            f"{'vente' if info.manual_side == 'sale' else 'achat'}."
        )
    if info.requires_detail and not data.reason:
        raise LifecycleValidationError(f"Un motif est requis pour le statut '{data.status}'.")
    if info.requires_confirmation and not data.confirmed:
        raise LifecycleValidationError(
            f"Une confirmation explicite est requise pour le statut '{data.status}'."
        )

    flow = AfnorFlow(
        invoice_id=invoice.id,
        direction=EventDirection.OUT,
        flow_type=_FLOW_TYPE_BY_SIDE[side],
        processing_rule=invoice.processing_rule,
    )
    db.add(flow)
    db.flush()  # obtient flow.id sans committer

    event = LifecycleEvent(
        invoice_id=invoice.id,
        company_id=invoice.company_id,
        status=data.status,
        direction=EventDirection.OUT,
        afnor_flow_id=flow.id,
    )
    if data.reason or data.action or data.comment:
        event.details.append(
            LifecycleEventDetail(reason=data.reason, action=data.action, comment=data.comment)
        )
    db.add(event)

    invoice.lifecycle_status = data.status

    db.commit()
    db.refresh(event)
    return event
