from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.oauth import generate_client_credentials, hash_secret
from app.db.session import get_db
from app.models.referential import (
    OAuthApplication,
    OAuthAppType,
    OAuthScope,
    RoutingMethod,
    TargetApplication,
)
from app.schemas.referential import (
    TargetApplicationCreate,
    TargetApplicationCreated,
    TargetApplicationRead,
    TargetApplicationStatusUpdate,
    TargetApplicationUpdate,
)

router = APIRouter()


@router.get("", response_model=list[TargetApplicationRead])
def list_target_applications(db: Session = Depends(get_db)):
    return list(db.query(TargetApplication).order_by(TargetApplication.id).all())


@router.post("", response_model=TargetApplicationCreated, status_code=201)
def create_target_application(payload: TargetApplicationCreate, db: Session = Depends(get_db)):
    oauth_client_id: str | None = None
    oauth_client_secret: str | None = None
    oauth_application_id: int | None = None

    if payload.routing_method == RoutingMethod.AFNOR_API:
        oauth_client_id, oauth_client_secret = generate_client_credentials()
        oauth_app = OAuthApplication(
            company_id=payload.company_id,
            client_id=oauth_client_id,
            client_secret_hash=hash_secret(oauth_client_secret),
            app_type=payload.parameters.get("app_type", OAuthAppType.CONFIDENTIAL),
            scope=OAuthScope.CONSUMER_TO_ROUTER,
            redirect_urls=",".join(payload.parameters.get("redirect_urls", []) or []) or None,
            preferred_conversion_format=payload.parameters.get("preferred_conversion_format"),
            webhook_url=payload.parameters.get("webhook_url"),
        )
        db.add(oauth_app)
        db.flush()
        oauth_application_id = oauth_app.id

    target_application = TargetApplication(
        name=payload.name,
        routing_method=payload.routing_method,
        company_id=payload.company_id,
        oauth_application_id=oauth_application_id,
        parameters=payload.parameters if payload.routing_method == RoutingMethod.MAIL else {},
    )
    db.add(target_application)
    db.commit()
    db.refresh(target_application)

    return TargetApplicationCreated(
        **TargetApplicationRead.model_validate(target_application).model_dump(),
        oauth_client_id=oauth_client_id,
        oauth_client_secret=oauth_client_secret,
    )


@router.put("/{target_application_id}", response_model=TargetApplicationRead)
def update_target_application(
    target_application_id: int, payload: TargetApplicationUpdate, db: Session = Depends(get_db)
):
    """Modifie le nom et les paramètres propres à la méthode de routage déjà choisie
    (§ 4.9.1/4.9.2) — destinataires mail, ou URLs de redirection/format préféré de
    conversion/type d'application/URL de webhook pour une application OAuth
    (portés par l'`OAuthApplication` liée, jamais par `TargetApplication.parameters`
    pour cette méthode, cf. § 6.1)."""
    target_application = db.get(TargetApplication, target_application_id)
    if target_application is None:
        raise HTTPException(status_code=404, detail="Target application not found")

    target_application.name = payload.name
    if target_application.routing_method == RoutingMethod.MAIL:
        target_application.parameters = payload.parameters
    else:
        oauth_app = target_application.oauth_application
        if oauth_app is not None:
            oauth_app.redirect_urls = (
                ",".join(payload.parameters.get("redirect_urls", []) or []) or None
            )
            oauth_app.preferred_conversion_format = payload.parameters.get(
                "preferred_conversion_format"
            )
            oauth_app.app_type = payload.parameters.get("app_type", oauth_app.app_type)
            oauth_app.webhook_url = payload.parameters.get("webhook_url")

    db.commit()
    db.refresh(target_application)
    return target_application


@router.put("/{target_application_id}/status", response_model=TargetApplicationRead)
def update_target_application_status(
    target_application_id: int, payload: TargetApplicationStatusUpdate, db: Session = Depends(get_db)
):
    """Activation/désactivation sans suppression (§ 6.1) : une application désactivée
    n'est plus retenue par RoutingRuleService.resolve pour de nouvelles factures,
    mais son historique de routage reste intact."""
    target_application = db.get(TargetApplication, target_application_id)
    if target_application is None:
        raise HTTPException(status_code=404, detail="Target application not found")
    target_application.is_active = payload.is_active
    db.commit()
    db.refresh(target_application)
    return target_application
