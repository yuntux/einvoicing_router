"""Configuration générale du routeur (spec.md § 6.1) — page et API réservées aux
administrateurs (§ NF4/§ 5.1) : ces réglages (SMTP, allowlist IP, gestionnaires de
facturation) s'appliquent à tout le routeur, jamais à une seule entreprise, et
touchent des paramètres sensibles (identifiants SMTP) — pas d'accès en lecture pour
un utilisateur restreint, contrairement à d'autres pages IHM.

Un seul router, monté dans `app/main.py` avec `dependencies=ihm_admin_only`."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.auth.session import get_current_user
from app.db.session import get_db
from app.models.referential import User
from app.schemas.settings import (
    BillingManagerContactCreate,
    BillingManagerContactRead,
    RouterSettingsRead,
    RouterSettingsUpdate,
)
from app.services import audit_trace_service, billing_manager_contact_service, router_settings_service

router = APIRouter()


@router.get("", response_model=RouterSettingsRead)
def get_router_settings(db: Session = Depends(get_db)):
    return router_settings_service.get_settings(db)


@router.get("/billing-manager-contacts", response_model=list[BillingManagerContactRead])
def list_billing_manager_contacts(db: Session = Depends(get_db)):
    return billing_manager_contact_service.list_contacts(db)


@router.put("", response_model=RouterSettingsRead)
def update_router_settings(
    payload: RouterSettingsUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    result = router_settings_service.update_settings(
        db, **payload.model_dump(), write_user_id=user.id if user else None
    )
    audit_trace_service.record_user_action(db, request, user, action="settings_update", target="router_settings")
    return result


@router.post(
    "/billing-manager-contacts", response_model=BillingManagerContactRead, status_code=201
)
def create_billing_manager_contact(
    payload: BillingManagerContactCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    contact = billing_manager_contact_service.create_contact(
        db, email=payload.email, actor_user_id=user.id if user else None
    )
    audit_trace_service.record_user_action(
        db, request, user, action="billing_manager_contact_create", target=str(contact.id)
    )
    return contact


@router.delete("/billing-manager-contacts/{contact_id}", status_code=204)
def delete_billing_manager_contact(
    contact_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    billing_manager_contact_service.delete_contact(db, contact_id=contact_id)
    audit_trace_service.record_user_action(
        db, request, user, action="billing_manager_contact_delete", target=str(contact_id)
    )
