"""AfnorServerController — émulation de PDP vis-à-vis d'Odoo (spec.md § 4.4).

Module de service, pensé pour rester isolé/testable (§ 4.8) même s'il reste, au lot 4,
un module interne du routeur plutôt qu'une bibliothèque séparée (cf. § 4.8, décision
d'architecture déjà actée)."""

from sqlalchemy.orm import Session

from app.models.invoicing import Invoice, InvoiceRouting
from app.models.referential import OAuthApplication, TargetApplication


def _target_applications_for(db: Session, oauth_app: OAuthApplication) -> list[TargetApplication]:
    return (
        db.query(TargetApplication)
        .filter(TargetApplication.oauth_application_id == oauth_app.id)
        .all()
    )


def list_invoices_for_consumer(db: Session, *, oauth_app: OAuthApplication) -> list[Invoice]:
    """Consultation des factures (§ 4.4) : ne retourne que les factures flaggées comme
    destinées à ce consommateur, via les `InvoiceRouting` de ses applications cibles.

    Filtre aussi explicitement `Invoice.company_id == oauth_app.company_id` (NF2,
    cloisonnement strict entre entreprises gérées) : garde-fou redondant avec le filtre
    déjà appliqué en amont par `RoutingRuleService.resolve` au moment du routage — en
    cas de désynchronisation (ex. `InvoiceRouting` créé avant un changement ultérieur
    de rattachement d'une application cible), une facture d'une autre entreprise ne
    doit jamais être exposée à ce consommateur."""
    target_ids = [t.id for t in _target_applications_for(db, oauth_app)]
    if not target_ids:
        return []
    invoice_ids = (
        db.query(InvoiceRouting.invoice_id)
        .filter(InvoiceRouting.target_application_id.in_(target_ids))
        .distinct()
        .all()
    )
    ids = [row[0] for row in invoice_ids]
    if not ids:
        return []
    return (
        db.query(Invoice)
        .filter(Invoice.id.in_(ids), Invoice.company_id == oauth_app.company_id)
        .order_by(Invoice.id)
        .all()
    )
