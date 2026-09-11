"""DirectoryService — annuaire des émetteurs connus du routeur (spec.md § 6.1, § 4.4)."""

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.referential import PartnerDirectory


def list_partners(db: Session) -> list[PartnerDirectory]:
    return list(db.query(PartnerDirectory).order_by(PartnerDirectory.id).all())


def create_partner(
    db: Session, *, siren: str, name: str, siret: str | None = None
) -> PartnerDirectory:
    partner = PartnerDirectory(siren=siren, siret=siret, name=name)
    db.add(partner)
    db.commit()
    db.refresh(partner)
    return partner


def get_or_create_partner(
    db: Session, *, siren: str, name: str, siret: str | None = None
) -> tuple[PartnerDirectory, bool]:
    """Retourne l'entrée d'annuaire existante pour ce SIREN, ou la crée si absente
    (comportement "auto-création à la consultation d'annuaire", § 4.4).

    Retourne (partner, created).
    """
    existing = db.query(PartnerDirectory).filter(PartnerDirectory.siren == siren).first()
    if existing:
        return existing, False
    partner = PartnerDirectory(
        siren=siren, siret=siret, name=name, first_seen_at=datetime.utcnow()
    )
    db.add(partner)
    db.commit()
    db.refresh(partner)
    return partner, True
