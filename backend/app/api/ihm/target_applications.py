from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth.oauth import generate_client_credentials, hash_secret
from app.auth.perimeter import ensure_company_in_scope
from app.auth.session import get_current_user
from app.db.session import get_db
from app.models.referential import OAuthAppType, RoutingMethod, TargetApplication, User
from app.schemas.referential import (
    TargetApplicationCreate,
    TargetApplicationCreated,
    TargetApplicationLookup,
    TargetApplicationRead,
    TargetApplicationStatusUpdate,
    TargetApplicationUpdate,
    validate_target_application_parameters,
)
from app.services import audit_trace_service
from app.services.url_validation import UnsafeWebhookUrlError, validate_webhook_url

# `router` : ouvert à tout utilisateur authentifié (`dependencies=ihm_auth` dans
# `app/main.py`) — uniquement la référence minimale id+nom+entreprise (`/lookup`),
# dont a besoin la page Règles de routage (non admin-only) pour afficher ses colonnes
# sans donner accès à la page Applications cibles elle-même (§ NF4).
# `admin_router` : réservé aux administrateurs — liste complète, création,
# modification, activation/désactivation.
router = APIRouter()
admin_router = APIRouter()


def _oauth_parameters_from_payload(payload_parameters: dict) -> dict:
    """Normalise les paramètres `afnor_api` reçus de l'IHM (§ 4.9.2) — valide l'URL
    de webhook (SSRF, § garde-fou CWE-918) et rejoint la liste d'URLs de redirection
    en une chaîne stockée (même format qu'avant, cf. § 6.1)."""
    webhook_url = payload_parameters.get("webhook_url")
    if webhook_url:
        try:
            validate_webhook_url(webhook_url)
        except UnsafeWebhookUrlError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "app_type": payload_parameters.get("app_type", OAuthAppType.CONFIDENTIAL),
        "redirect_urls": ",".join(payload_parameters.get("redirect_urls", []) or []) or None,
        "preferred_conversion_format": payload_parameters.get("preferred_conversion_format"),
        "webhook_url": webhook_url,
    }


@router.get("/lookup", response_model=list[TargetApplicationLookup])
def list_target_application_lookups(db: Session = Depends(get_db)):
    """Référence minimale (id + nom + entreprise), toutes applications confondues,
    sans filtrage de périmètre ni paramètres sensibles (destinataires mail, webhook
    OAuth) : utilisée pour l'affichage croisé sur des pages accessibles à un
    utilisateur restreint (ex. Règles de routage)."""
    return list(db.query(TargetApplication).order_by(TargetApplication.id).all())


@admin_router.get("", response_model=list[TargetApplicationRead])
def list_target_applications(db: Session = Depends(get_db)):
    return list(db.query(TargetApplication).order_by(TargetApplication.id).all())


@admin_router.post("", response_model=TargetApplicationCreated, status_code=201)
def create_target_application(
    payload: TargetApplicationCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    ensure_company_in_scope(user, payload.company_id)
    actor_id = user.id if user else None
    oauth_client_id: str | None = None
    oauth_client_secret: str | None = None
    parameters = payload.parameters

    if payload.routing_method == RoutingMethod.AFNOR_API:
        oauth_client_id, oauth_client_secret = generate_client_credentials()
        parameters = {
            "client_id": oauth_client_id,
            "client_secret_hash": hash_secret(oauth_client_secret),
            **_oauth_parameters_from_payload(payload.parameters),
        }

    target_application = TargetApplication(
        name=payload.name,
        routing_method=payload.routing_method,
        company_id=payload.company_id,
        parameters=parameters,
        create_user_id=actor_id,
        write_user_id=actor_id,
    )
    db.add(target_application)
    db.commit()
    db.refresh(target_application)

    audit_trace_service.record_user_action(
        db, request, user, action="target_application_create", target=str(target_application.id)
    )

    return TargetApplicationCreated(
        **TargetApplicationRead.model_validate(target_application).model_dump(),
        oauth_client_id=oauth_client_id,
        oauth_client_secret=oauth_client_secret,
    )


@admin_router.put("/{target_application_id}", response_model=TargetApplicationRead)
def update_target_application(
    target_application_id: int,
    payload: TargetApplicationUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    """Modifie le nom et les paramètres propres à la méthode de routage déjà choisie
    (§ 4.9.1/4.9.2) — destinataires mail, ou URLs de redirection/format préféré de
    conversion/type d'application/URL de webhook pour une méthode `afnor_api`
    (`client_id`/`client_secret_hash`, eux, sont immuables après création — jamais
    touchés ici, cf. § 4.9.2)."""
    target_application = db.get(TargetApplication, target_application_id)
    if target_application is None:
        raise HTTPException(status_code=404, detail="Target application not found")
    ensure_company_in_scope(user, target_application.company_id)
    # `routing_method` est figé après création (jamais dans `TargetApplicationUpdate`, cf. sa
    # docstring) — c'est donc l'objet existant, pas le payload, qui porte la méthode à valider ici.
    try:
        validate_target_application_parameters(target_application.routing_method, payload.parameters)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    actor_id = user.id if user else None
    target_application.name = payload.name
    target_application.write_user_id = actor_id
    if target_application.routing_method == RoutingMethod.MAIL:
        target_application.parameters = payload.parameters
    else:
        target_application.parameters = {
            "client_id": target_application.client_id,
            "client_secret_hash": target_application.client_secret_hash,
            **_oauth_parameters_from_payload(payload.parameters),
        }

    db.commit()
    db.refresh(target_application)
    audit_trace_service.record_user_action(
        db, request, user, action="target_application_update", target=str(target_application_id)
    )
    return target_application


@admin_router.post("/{target_application_id}/regenerate-secret", response_model=TargetApplicationCreated)
def regenerate_target_application_secret(
    target_application_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    """Renouvelle le secret OAuth d'une application `afnor_api` (§ 4.9.2) — révoque
    immédiatement l'ancien secret (jamais conservé) : à utiliser en cas de fuite
    suspectée ou de rotation périodique. `client_id` reste inchangé (identifiant
    public déjà connu du consommateur, § 4.9.2) — seul le secret change, comme sur
    la fiche application de SuperPDP."""
    target_application = db.get(TargetApplication, target_application_id)
    if target_application is None:
        raise HTTPException(status_code=404, detail="Target application not found")
    ensure_company_in_scope(user, target_application.company_id)
    if target_application.routing_method != RoutingMethod.AFNOR_API:
        raise HTTPException(
            status_code=422, detail="Seules les applications AFNOR API ont un secret OAuth à renouveler"
        )

    actor_id = user.id if user else None
    _, new_secret = generate_client_credentials()
    target_application.parameters = {
        **target_application.parameters,
        "client_secret_hash": hash_secret(new_secret),
    }
    target_application.write_user_id = actor_id
    db.commit()
    db.refresh(target_application)

    audit_trace_service.record_user_action(
        db, request, user, action="target_application_secret_regenerate", target=str(target_application_id)
    )

    return TargetApplicationCreated(
        **TargetApplicationRead.model_validate(target_application).model_dump(),
        oauth_client_id=target_application.client_id,
        oauth_client_secret=new_secret,
    )


@admin_router.put("/{target_application_id}/status", response_model=TargetApplicationRead)
def update_target_application_status(
    target_application_id: int,
    payload: TargetApplicationStatusUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    """Activation/désactivation sans suppression (§ 6.1) : une application désactivée
    n'est plus retenue par RoutingRuleService.resolve pour de nouvelles factures,
    mais son historique de routage reste intact."""
    target_application = db.get(TargetApplication, target_application_id)
    if target_application is None:
        raise HTTPException(status_code=404, detail="Target application not found")
    ensure_company_in_scope(user, target_application.company_id)
    actor_id = user.id if user else None
    target_application.is_active = payload.is_active
    target_application.write_user_id = actor_id
    db.commit()
    db.refresh(target_application)
    audit_trace_service.record_user_action(
        db, request, user, action="target_application_status_update", target=str(target_application_id)
    )
    return target_application
