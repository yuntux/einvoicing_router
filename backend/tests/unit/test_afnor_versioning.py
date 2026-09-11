"""Registre de versions AFNOR (spec.md § 4.8, lot 8) — preuve qu'une v2 s'ajoute sans
toucher aux services existants."""

from app.afnor.versioning.registry import registered_versions
from app.auth.oauth import generate_client_credentials, hash_secret
from app.models.referential import Company, OAuthAppType, OAuthApplication, OAuthScope


def _make_company(db, siren="123456789"):
    company = Company(siren=siren, name="Ma Société")
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


def _make_oauth_app(db, company, client_secret="s3cret-value"):
    oauth_app = OAuthApplication(
        company_id=company.id,
        client_id=generate_client_credentials()[0],
        client_secret_hash=hash_secret(client_secret),
        app_type=OAuthAppType.CONFIDENTIAL,
        scope=OAuthScope.CONSUMER_TO_ROUTER,
    )
    db.add(oauth_app)
    db.commit()
    db.refresh(oauth_app)
    return oauth_app


def test_registry_contains_v1_and_v2():
    assert registered_versions() == ["v1", "v2"]


def test_v2_reuses_same_service_modules_as_v1_not_duplicated_logic():
    """La preuve architecturale du § 4.8 : v2 importe exactement les mêmes objets
    module que v1 pour afnor_server_controller/audit_trace_service — aucune logique
    dupliquée, aucun service modifié pour ajouter la version."""
    import app.api.afnor.v1 as v1
    import app.api.afnor.v2 as v2

    assert v1.afnor_server_controller is v2.afnor_server_controller
    assert v1.audit_trace_service is v2.audit_trace_service


def test_v1_and_v2_endpoints_both_work_independently(client, db_session):
    company = _make_company(db_session)
    oauth_app = _make_oauth_app(db_session, company, client_secret="secret-1")

    token_response = client.post(
        "/api/afnor/v1/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": oauth_app.client_id,
            "client_secret": "secret-1",
        },
    )
    assert token_response.status_code == 200
    token = token_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    v1_response = client.get("/api/afnor/v1/invoices", headers=headers)
    assert v1_response.status_code == 200

    v2_response = client.get("/api/afnor/v2/invoices", headers=headers)
    assert v2_response.status_code == 200

    from app.models.audit import FlowTrace

    traces = db_session.query(FlowTrace).all()
    versions_traced = {t.afnor_api_version for t in traces if t.request.get("endpoint") == "GET /invoices"}
    assert versions_traced == {"v1", "v2"}


def test_v2_has_no_own_token_endpoint(client):
    """L'émission de jeton reste une infrastructure non versionnée (§ 4.10) — seule
    la surface métier (factures, annuaire) est dupliquée par version."""
    response = client.post(
        "/api/afnor/v2/oauth/token",
        data={"grant_type": "client_credentials", "client_id": "x", "client_secret": "y"},
    )
    assert response.status_code == 404
