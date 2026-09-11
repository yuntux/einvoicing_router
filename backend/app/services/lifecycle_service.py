"""LifecycleService — saisie manuelle des messages de cycle de vie (spec.md § 4.2/§ 6.2).

Lot 3 : la génération CDAR réelle (pyfrctc) n'était pas encore branchée — `AfnorFlow`
restait à l'état `created`. Lot 6 : en mode `settings.superpdp_client_mode ==
"pyfrctc"`, le flux est réellement généré (`cdar_service`, validé XSD) puis transmis à
SuperPDP (`AfnorClientAdapter.send_cdar`) ; en mode `"fake"` (défaut dev/tests), le
comportement du lot 3 est conservé à l'identique. Un échec de génération/transmission
ne fait pas échouer la saisie manuelle elle-même (l'événement métier reste enregistré,
`AfnorFlow.state` passe à `error` — rejeu non automatisé à ce stade, cf. § 4.7 qui ne
couvre que le routage mail/API, pas la transmission CDAR).

Note de conception : seul le sens "achat" (`side="purchase"`) est accessible depuis
cet écran, car il n'existe qu'un point d'entrée IHM — la fiche d'une facture *reçue*
(§ 6.1 : les factures émises ne sont pas stockées). Le statut `completed` (réservé aux
factures de vente) reste donc défini dans le catalogue mais inatteignable tant qu'un
écran dédié aux factures émises n'existe pas.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.config import settings
from app.models.invoicing import Invoice
from app.models.lifecycle import (
    AfnorFlow,
    AfnorFlowState,
    AfnorFlowType,
    EventDirection,
    LifecycleEvent,
    LifecycleEventDetail,
)
from app.services import cdar_service, webhook_notification_service
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

    if settings.superpdp_client_mode == "pyfrctc":
        _generate_and_send_cdar(db, invoice=invoice, flow=flow, data=data)

    # Notification best-effort vers Odoo (§ 4.4/§ 4.7) — un échec ici est sans
    # conséquence, le contenu reste consultable par Odoo au prochain polling.
    try:
        webhook_notification_service.notify_lifecycle_event(
            db, invoice=invoice, status=data.status
        )
    except Exception:
        pass

    return event


def _generate_and_send_cdar(db: Session, *, invoice: Invoice, flow: AfnorFlow, data: ManualEventInput) -> None:
    from app.afnor.client.adapter import afnor_client_adapter

    try:
        data_dict = cdar_service.build_data_dict(
            invoice=invoice,
            buyer_company=invoice.company,
            status=data.status,
            reason=data.reason,
            action=data.action,
            comment=data.comment,
        )
        cdar_bytes = cdar_service.generate(data_dict)
        flow.file_bin = cdar_bytes
        flow.data_dict = cdar_service.to_json_safe(data_dict)
        flow.state = AfnorFlowState.GENERATED
        db.commit()

        result = afnor_client_adapter.send_cdar(
            db, company=invoice.company, cdar_bytes=cdar_bytes, filename=f"cdar-{flow.id}.xml"
        )
        flow.flow_id = result.get("id") or result.get("flowId")
        flow.state = AfnorFlowState.SENT
        db.commit()
    except Exception:
        # La saisie métier (LifecycleEvent) reste valide même si la génération/
        # transmission CDAR échoue — seul le suivi technique (`AfnorFlow`) le reflète.
        flow.state = AfnorFlowState.ERROR
        db.commit()
