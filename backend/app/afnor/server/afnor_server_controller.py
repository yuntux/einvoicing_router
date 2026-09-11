"""AfnorServerController — émulation de PDP vis-à-vis d'Odoo (spec.md § 4.4).

Module de service, pensé pour rester isolé/testable (§ 4.8) même s'il reste, au lot 4,
un module interne du routeur plutôt qu'une bibliothèque séparée (cf. § 4.8, décision
d'architecture déjà actée)."""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.invoicing import Invoice, InvoiceRouting
from app.models.referential import OAuthApplication, TargetApplication
from app.services import directory_service, routing_rule_service


def _target_applications_for(db: Session, oauth_app: OAuthApplication) -> list[TargetApplication]:
    return (
        db.query(TargetApplication)
        .filter(TargetApplication.oauth_application_id == oauth_app.id)
        .all()
    )


def list_invoices_for_consumer(db: Session, *, oauth_app: OAuthApplication) -> list[Invoice]:
    """Consultation des factures (§ 4.4) : ne retourne que les factures flaggées comme
    destinées à ce consommateur, via les `InvoiceRouting` de ses applications cibles."""
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
    return db.query(Invoice).filter(Invoice.id.in_(ids)).order_by(Invoice.id).all()


@dataclass
class DirectoryLookupResult:
    partner_id: int
    siren: str
    name: str
    created: bool


def lookup_or_create_directory_entry(
    db: Session, *, oauth_app: OAuthApplication, siren: str, name: str | None
) -> DirectoryLookupResult:
    """Consultation d'annuaire (§ 4.4) : crée l'entrée `PartnerDirectory` si elle
    n'existe pas encore, et déclare automatiquement une règle de routage implicite
    vers les applications cibles de ce consommateur."""
    partner, created = directory_service.get_or_create_partner(
        db, siren=siren, name=name or siren
    )
    if created:
        for target in _target_applications_for(db, oauth_app):
            routing_rule_service.create_rule(
                db, partner_directory_id=partner.id, target_application_id=target.id
            )
    return DirectoryLookupResult(
        partner_id=partner.id, siren=partner.siren, name=partner.name, created=created
    )
