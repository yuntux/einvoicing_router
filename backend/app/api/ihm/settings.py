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


@router.get("", response_model=RouterSettingsRead)
def get_router_settings(db: Session = Depends(get_db)):
    return router_settings_service.get_settings(db)


@router.put("", response_model=RouterSettingsRead)
def update_router_settings(payload: RouterSettingsUpdate, db: Session = Depends(get_db)):
    return router_settings_service.update_settings(db, **payload.model_dump())


@router.get("/billing-manager-contacts", response_model=list[BillingManagerContactRead])
def list_billing_manager_contacts(db: Session = Depends(get_db)):
    return billing_manager_contact_service.list_contacts(db)


@router.post(
    "/billing-manager-contacts", response_model=BillingManagerContactRead, status_code=201
)
def create_billing_manager_contact(
    payload: BillingManagerContactCreate, db: Session = Depends(get_db)
):
    return billing_manager_contact_service.create_contact(db, email=payload.email)


@router.delete("/billing-manager-contacts/{contact_id}", status_code=204)
def delete_billing_manager_contact(contact_id: int, db: Session = Depends(get_db)):
    billing_manager_contact_service.delete_contact(db, contact_id=contact_id)
