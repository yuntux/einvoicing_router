"""Registre de versions AFNOR (spec.md § 4.8) — preuve que le dispositif permet
d'ajouter une future version sans toucher aux services existants, sans qu'une v2
fictive ne soit pour autant montée en permanence tant qu'elle ne correspond à rien
de réel (§ 4.8 met justement en garde contre une anticipation prématurée)."""

from fastapi import APIRouter
from fastapi.testclient import TestClient

from app.afnor.versioning import registry
from app.afnor.versioning.registry import register_version, registered_versions
from app.api.afnor._common import register_common_routes
from app.auth.oauth import generate_client_credentials, hash_secret
from app.config import settings
from app.db.session import get_db
from app.main import create_app
from app.models.referential import Company, RoutingMethod, TargetApplication


def _make_company(db, siren="123456789"):
    company = Company(siren=siren, name="Ma Société")
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


def _make_oauth_app(db, company, client_secret="s3cret-value"):
    """Une application `afnor_api` EST le "client" OAuth (§ 4.9.2/§ 4.10)."""
    target = TargetApplication(
        name="Odoo",
        routing_method=RoutingMethod.AFNOR_API,
        company_id=company.id,
        parameters={
            "client_id": generate_client_credentials()[0],
            "client_secret_hash": hash_secret(client_secret),
            "app_type": "confidential",
        },
    )
    db.add(target)
    db.commit()
    db.refresh(target)
    return target


def test_registry_contains_only_v1_today():
    assert registered_versions() == ["v1"]


def test_a_future_version_reuses_same_service_modules_not_duplicated_logic():
    """Enregistre une version hypothétique ("v2-future") via le même mécanisme que
    v1 (`register_common_routes`) — preuve que l'ajout d'une vraie v2 le jour venu
    réutiliserait le même `__code__` compilé, sans dupliquer la logique métier."""
    import app.api.afnor.v1 as v1

    future_router = APIRouter()
    register_common_routes(future_router, "v2-future")

    def endpoint_for(router, path: str):
        return next(route.endpoint for route in router.routes if route.path == path)

    assert (
        endpoint_for(v1.router, "/afnor-flow/v1/flows/search").__code__
        is endpoint_for(future_router, "/afnor-flow/v2-future/flows/search").__code__
    )
    assert (
        endpoint_for(v1.router, "/afnor-directory/v1/siren/code-insee:{siren}").__code__
        is endpoint_for(
            future_router, "/afnor-directory/v2-future/siren/code-insee:{siren}"
        ).__code__
    )


def test_enabling_a_future_version_mounts_it_without_touching_main(db_session):
    """Bout-en-bout : active une version hypothétique via
    `afnor_api_enabled_versions` et prouve qu'elle répond, sans avoir modifié
    `app/main.py` ni aucun service pour l'occasion."""
    future_router = APIRouter()
    register_common_routes(future_router, "v2-future")
    register_version("v2-future", future_router)

    original = settings.afnor_api_enabled_versions
    settings.afnor_api_enabled_versions = "v1,v2-future"
    try:
        app = create_app()
    finally:
        settings.afnor_api_enabled_versions = original
        registry._REGISTRY.pop("v2-future", None)

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    company = _make_company(db_session)
    oauth_app = _make_oauth_app(db_session, company, client_secret="secret-1")

    with TestClient(app, base_url="https://testserver") as client:
        token_response = client.post(
            "/api/afnor/oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": oauth_app.client_id,
                "client_secret": "secret-1",
            },
        )
        assert token_response.status_code == 200
        token = token_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        search_body = {"where": {}}
        v1_response = client.post(
            "/api/afnor/afnor-flow/v1/flows/search", json=search_body, headers=headers
        )
        assert v1_response.status_code == 200

        future_response = client.post(
            "/api/afnor/afnor-flow/v2-future/flows/search", json=search_body, headers=headers
        )
        assert future_response.status_code == 200


def test_v1_has_the_only_token_endpoint():
    """L'émission de jeton reste une infrastructure non versionnée (§ 4.10) — seule
    la surface métier (factures, annuaire) serait dupliquée par une future version,
    via `register_common_routes` (cf. tests ci-dessus)."""
    import app.api.afnor.v1 as v1

    paths = {route.path for route in v1.router.routes}
    assert "/oauth/token" in paths
