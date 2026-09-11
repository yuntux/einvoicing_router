"""BillingManagerContactService — adresses email des Gestionnaires de facturation
(spec.md § 4.7), paramétrées globalement (pas par entreprise)."""

from sqlalchemy.orm import Session

from app.models.settings import BillingManagerContact


def list_contacts(db: Session) -> list[BillingManagerContact]:
    return list(db.query(BillingManagerContact).order_by(BillingManagerContact.id).all())


def create_contact(db: Session, *, email: str) -> BillingManagerContact:
    contact = BillingManagerContact(email=email)
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return contact


def delete_contact(db: Session, *, contact_id: int) -> None:
    contact = db.get(BillingManagerContact, contact_id)
    if contact is not None:
        db.delete(contact)
        db.commit()
