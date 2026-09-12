"""LifecycleService — saisie manuelle des messages de cycle de vie (spec.md § 4.2/§ 6.2).

Lot 3 : la génération CDAR réelle (pyfrctc) n'était pas encore branchée — `AfnorFlow`
restait à l'état `created`. Lot 6 : en mode `settings.certified_platform_client_mode ==
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
from datetime import date, datetime

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
    LifecycleEventPayment,
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

    if settings.certified_platform_client_mode == "pyfrctc":
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


def _to_payment_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    return datetime.utcnow().date()


_STATE_FLOW_TYPES = {AfnorFlowType.STATE_SUPPLIER_INVOICE_LC.value, AfnorFlowType.STATE_CUSTOMER_INVOICE_LC.value}


def create_incoming_event(
    db: Session,
    *,
    invoice: Invoice,
    flow_id: str,
    xml_bytes: bytes,
    parsed: dict | None = None,
    flow_type: str | None = None,
) -> LifecycleEvent | None:
    """Traite un CDAR entrant déjà rattaché à `invoice` (§ 4.2, reçu de SuperPDP) —
    cf. `app.services.lifecycle_ingestion_service` pour le rattachement par numéro de
    facture. Idempotent : un `flow_id` déjà traité (entrant ou sortant) ne recrée
    jamais d'événement — le polling repasse sur la même fenêtre `since` par
    tolérance (§ 4.1), et interroge désormais les deux sens `flow_direction`
    (`in`/`out`) côté SuperPDP pour ne rater aucun statut technique (cf. l'incident
    du statut ap_received exposé en `flow_direction=out`) : filtrer uniquement sur
    `direction == IN` ici laisserait passer un flux qu'on a nous-mêmes déjà envoyé
    (`AfnorFlow(direction=OUT)`) s'il ressort du même `flow_id` côté recherche.

    Retourne `None` si le CDAR a déjà été traité, ou si son statut (MDT-105) n'est pas
    reconnu dans `STATUS_CATALOG` — dans ce dernier cas, l'`AfnorFlow` technique est
    quand même conservé (trace brute pour investigation), mais aucun `LifecycleEvent`
    métier n'est créé avec un statut inventé."""
    existing = db.query(AfnorFlow).filter(AfnorFlow.flow_id == flow_id).first()
    if existing is not None:
        return None

    if parsed is None:
        parsed = cdar_service.parse(xml_bytes)

    flow = AfnorFlow(
        invoice_id=invoice.id,
        flow_id=flow_id,
        direction=EventDirection.IN,
        flow_type=(
            AfnorFlowType.STATE_SUPPLIER_INVOICE_LC
            if flow_type in _STATE_FLOW_TYPES
            else AfnorFlowType.SUPPLIER_INVOICE_LC
        ),
        syntax="CDAR",
        processing_rule=invoice.processing_rule,
        state=AfnorFlowState.DONE,
        file_bin=xml_bytes,
        data_dict=cdar_service.to_json_safe(parsed),
    )
    db.add(flow)
    db.flush()  # obtient flow.id sans committer

    status_code = parsed.get("status_code")
    status_key = cdar_service.resolve_status_key(status_code) if status_code else None
    if status_key is None:
        db.commit()
        return None

    event = LifecycleEvent(
        invoice_id=invoice.id,
        company_id=invoice.company_id,
        status=status_key,
        direction=EventDirection.IN,
        afnor_flow_id=flow.id,
        event_datetime=parsed.get("lc_datetime") or datetime.utcnow(),
    )

    doc_statuses = parsed.get("doc_status") or []
    first_doc_status = doc_statuses[0] if doc_statuses else {}
    reason = first_doc_status.get("reason_code")
    action = first_doc_status.get("action_code")
    comment = first_doc_status.get("comment")
    # Les codes (motif/action fermés, cf. REASONS/ACTIONS) tiennent dans les colonnes
    # `reason`/`action` (String(30)/String(10)) — le texte libre correspondant, quand
    # il n'y a pas de code, part dans `comment` (Text, non borné) plutôt que d'être
    # tronqué silencieusement.
    if not reason and first_doc_status.get("reason_txt"):
        comment = f"{comment + ' — ' if comment else ''}Motif : {first_doc_status['reason_txt']}"
    if not action and first_doc_status.get("action_txt"):
        comment = f"{comment + ' — ' if comment else ''}Action : {first_doc_status['action_txt']}"
    if reason or action or comment:
        event.details.append(LifecycleEventDetail(reason=reason, action=action, comment=comment))

    for characteristic in first_doc_status.get("doc_characteristics") or []:
        amount = characteristic.get("amount")
        payment_date = characteristic.get("date")
        if isinstance(amount, dict) and amount.get("float") is not None and payment_date is not None:
            event.payments.append(
                LifecycleEventPayment(
                    amount=amount["float"],
                    currency=amount.get("currency") or "EUR",
                    payment_date=_to_payment_date(payment_date),
                )
            )

    db.add(event)
    invoice.lifecycle_status = status_key
    db.commit()
    db.refresh(event)

    try:
        webhook_notification_service.notify_lifecycle_event(db, invoice=invoice, status=status_key)
    except Exception:
        pass

    return event
