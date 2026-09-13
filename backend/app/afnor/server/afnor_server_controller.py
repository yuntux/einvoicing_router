"""AfnorServerController — émulation de PDP vis-à-vis d'Odoo (spec.md § 4.4).

Module de service, pensé pour rester isolé/testable (§ 4.8) même s'il reste, au lot 4,
un module interne du routeur plutôt qu'une bibliothèque séparée (cf. § 4.8, décision
d'architecture déjà actée)."""

from typing import Callable, TypeVar

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.invoicing import Invoice, InvoiceRouting
from app.models.referential import TargetApplication
from app.schemas.afnor_flow import Acknowledgement, Flow

T = TypeVar("T")

# `Invoice.ack_status` porte la valeur déjà remappée par pyfrctc (`state`, cf.
# `pyfrctc._parse_flow_dict` : "sent"/"done"/"error"/"ap_unknown"), pas l'énumération
# officielle `FlowAckStatus` ("Pending"/"Ok"/"Error") — on la restitue ici pour ne
# jamais exposer à Odoo une valeur hors contrat. "ap_unknown" (ou absent) est
# remappé sur "Pending" plutôt que sur une valeur définitive non garantie.
_ACK_STATUS_FROM_PYFRCTC_STATE = {"sent": "Pending", "done": "Ok", "error": "Error"}


def call_certified_platform(fn: Callable[[], T]) -> T:
    """Exécute un appel à `AfnorClientAdapter` et transforme toute exception en 502
    (§ 4.4) — évite de répéter le même try/except à chaque endpoint proxy `v1`/`v2`."""
    try:
        return fn()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"SuperPDP unreachable: {exc}") from exc


def _routed_invoice_ids(db: Session, target_application: TargetApplication):
    """Sous-requête des `Invoice.id` réellement routés vers cette application cible
    (§ 4.4) — factorise le filtre commun à `list_invoices_for_consumer`/
    `find_invoice_for_consumer_by_flow_id`.

    `InvoiceRouting` est une décision persistée (créée soit à la réception par
    `InvoiceIngestionService._route_invoice` contre les `RoutingRule` actives à ce
    moment-là, soit rétroactivement via le rétro-routage explicite du § 4.3), jamais
    recalculée depuis les `RoutingRule` courantes : une facture reçue avant
    l'activation d'une règle pour son émetteur ne doit apparaître que si ce
    rétro-routage a été explicitement demandé, jamais simplement parce que la règle
    est active aujourd'hui — d'où l'interrogation de `InvoiceRouting` et jamais de
    `RoutingRule` ici. Retournée sans `.all()` : reste une sous-requête SQL, jamais
    matérialisée en liste Python, pour que `Invoice.id.in_(...)` s'exécute en une
    seule requête côté base."""
    return (
        db.query(InvoiceRouting.invoice_id)
        .filter(InvoiceRouting.target_application_id == target_application.id)
        .distinct()
    )


def list_invoices_for_consumer(
    db: Session, *, target_application: TargetApplication
) -> list[Invoice]:
    """Consultation des factures (§ 4.4) : ne retourne que les factures flaggées comme
    destinées à ce consommateur, via les `InvoiceRouting` de cette application cible
    (chaque application `afnor_api` est elle-même le "client" OAuth authentifié —
    plus d'indirection par un `OAuthApplication` séparé, § 4.9.2/§ 4.10).

    Filtre aussi explicitement `Invoice.company_id == target_application.company_id`
    (NF2, cloisonnement strict entre entreprises gérées) : garde-fou redondant avec le
    filtre déjà appliqué en amont par `RoutingRuleService.resolve` au moment du
    routage — en cas de désynchronisation, une facture d'une autre entreprise ne doit
    jamais être exposée à ce consommateur."""
    return (
        db.query(Invoice)
        .filter(
            Invoice.id.in_(_routed_invoice_ids(db, target_application)),
            Invoice.company_id == target_application.company_id,
        )
        .order_by(Invoice.id)
        .all()
    )


def find_invoice_for_consumer_by_flow_id(
    db: Session, *, target_application: TargetApplication, flow_id: str
) -> Invoice | None:
    """Comme `list_invoices_for_consumer`, mais pour un seul flux identifié par son
    `flowId` d'origine (`Invoice.certified_platform_flow_id`) — utilisé par `GET /flows/{flowId}`
    (§ 4.4). Mêmes garde-fous NF2 : jamais de facture hors du périmètre autorisé."""
    return (
        db.query(Invoice)
        .filter(
            Invoice.id.in_(_routed_invoice_ids(db, target_application)),
            Invoice.company_id == target_application.company_id,
            Invoice.certified_platform_flow_id == flow_id,
        )
        .first()
    )


def flow_from_invoice(invoice: Invoice) -> Flow:
    """Traduit une `Invoice` (modèle interne) en ressource `Flow` du contrat AFNOR
    (§ 4.4, "émulation de PDP") — une facture reçue par le routeur et routée vers
    Odoo est, du point de vue d'Odoo, un flux entrant (`flowDirection="In"`, PDP vers
    OD) de type `SupplierInvoice` : seul flux réellement émulé à ce jour."""
    return Flow(
        flowId=invoice.certified_platform_flow_id,
        submittedAt=invoice.certified_platform_submitted_at or invoice.received_at,
        flowSyntax=invoice.syntax or "CII",
        name=invoice.flow_name or invoice.invoice_number,
        flowProfile=invoice.flow_profile or "Undefined",
        processingRule=invoice.processing_rule or "Undefined",
        trackingId=invoice.tracking_id,
        processingRuleSource=invoice.processing_rule_source or "Computed",
        flowDirection="In",
        flowType="SupplierInvoice",
        acknowledgement=Acknowledgement(
            status=_ACK_STATUS_FROM_PYFRCTC_STATE.get(invoice.ack_status or "", "Pending")
        ),
        updatedAt=invoice.certified_platform_updated_at or invoice.received_at,
    )
