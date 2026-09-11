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
        if payload.company_id is None:
            raise HTTPException(
                status_code=422,
                detail="company_id est requis pour la méthode afnor_api (§ 4.9.2).",
            )
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
