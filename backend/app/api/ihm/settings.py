"""Configuration générale du routeur (spec.md § 6.1) — lecture ouverte à tout
utilisateur authentifié, écriture réservée aux administrateurs (§ NF4) : ces
réglages (SMTP, allowlist IP, gestionnaires de facturation) s'appliquent à tout le
routeur, jamais à une seule entreprise, donc pas de notion de périmètre ici.

Deux routers distincts, montés au même préfixe dans `app/main.py` : `router` (lecture,
`dependencies=ihm_auth`) et `admin_router` (écriture, `dependencies=ihm_auth +
[Depends(require_admin)]`) — le contrôle d'accès se lit à l'endroit où les routes sont
câblées, pas dispersé sur chaque décorateur."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.settings import (
    BillingManagerContactCreate,
    BillingManagerContactRead,
    RouterSettingsRead,
    RouterSettingsUpdate,
)
from app.services import billing_manager_contact_service, router_settings_service

router = APIRouter()
admin_router = APIRouter()


@router.get("", response_model=RouterSettingsRead)
def get_router_settings(db: Session = Depends(get_db)):
    return router_settings_service.get_settings(db)


@router.get("/billing-manager-contacts", response_model=list[BillingManagerContactRead])
def list_billing_manager_contacts(db: Session = Depends(get_db)):
    return billing_manager_contact_service.list_contacts(db)


@admin_router.put("", response_model=RouterSettingsRead)
def update_router_settings(payload: RouterSettingsUpdate, db: Session = Depends(get_db)):
    return router_settings_service.update_settings(db, **payload.model_dump())


@admin_router.post(
    "/billing-manager-contacts", response_model=BillingManagerContactRead, status_code=201
)
def create_billing_manager_contact(
    payload: BillingManagerContactCreate, db: Session = Depends(get_db)
):
    return billing_manager_contact_service.create_contact(db, email=payload.email)


@admin_router.delete("/billing-manager-contacts/{contact_id}", status_code=204)
def delete_billing_manager_contact(contact_id: int, db: Session = Depends(get_db)):
    billing_manager_contact_service.delete_contact(db, contact_id=contact_id)
