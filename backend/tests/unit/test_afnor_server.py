"""Module serveur AFNOR — API exposée à Odoo (spec.md § 4.4/§ 4.8, lot 4)."""

from datetime import date

from app.auth.oauth import generate_client_credentials, hash_secret
from app.models.audit import FlowTrace
from app.models.invoicing import Invoice, InvoiceRouting
from app.models.referential import (
    Company,
    OAuthAppType,
    OAuthScope,
    OAuthApplication,
    PartnerDirectory,
    RoutingMethod,
    TargetApplication,
)

def _make_company(db, siren="123456789", name="Ma Société"):
    company = Company(siren=siren, name=name)
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


def _make_oauth_app(db, company, client_id=None, client_secret="s3cret-value"):
    client_id = client_id or generate_client_credentials()[0]
    oauth_app = OAuthApplication(
        company_id=company.id,
        client_id=client_id,
        client_secret_hash=hash_secret(client_secret),
        app_type=OAuthAppType.CONFIDENTIAL,
        scope=OAuthScope.CONSUMER_TO_ROUTER,
    )
    db.add(oauth_app)
    db.commit()
    db.refresh(oauth_app)
    return oauth_app


def _make_target(db, company, oauth_app=None, name="Odoo"):
    target = TargetApplication(
        name=name,
        routing_method=RoutingMethod.AFNOR_API,
        company_id=company.id,
        oauth_application_id=oauth_app.id if oauth_app else None,
    )
    db.add(target)
    db.commit()
    db.refresh(target)
    return target


def _make_partner(db, siren="987654321", name="Fournisseur"):
    partner = PartnerDirectory(siren=siren, name=name)
    db.add(partner)
    db.commit()
    db.refresh(partner)
    return partner


def _make_invoice(db, company, partner, flow_id="flow-1"):
    invoice = Invoice(
        company_id=company.id,
        partner_directory_id=partner.id,
        emitter_siren=partner.siren,
        invoice_number="INV-1",
        invoice_date=date(2026, 1, 1),
        file_path="/tmp/fake.pdf",
        superpdp_flow_id=flow_id,
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    return invoice


def _route(db, invoice, target):
    routing = InvoiceRouting(invoice_id=invoice.id, target_application_id=target.id)
    db.add(routing)
    db.commit()
    return routing


def test_token_issuance_success(client, db_session):
    company = _make_company(db_session)
    oauth_app = _make_oauth_app(db_session, company, client_secret="s3cret-value")

    response = client.post(
        "/api/afnor/v1/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": oauth_app.client_id,
            "client_secret": "s3cret-value",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    # RFC 6749 : "bearer" est insensible à la casse (RFC 6750 § 7.1) — Authlib émet
    # "Bearer", capitalisé, ce qui est tout aussi conforme.
    assert body["token_type"].lower() == "bearer"

    traces = db_session.query(FlowTrace).all()
    assert len(traces) == 1
    assert traces[0].direction == "odoo_to_router"


def test_token_issuance_wrong_secret(client, db_session):
    company = _make_company(db_session)
    oauth_app = _make_oauth_app(db_session, company, client_secret="s3cret-value")

    response = client.post(
        "/api/afnor/v1/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": oauth_app.client_id,
            "client_secret": "wrong-secret",
        },
    )

    # RFC 6749 § 5.2 : 401 n'est requis que si le client a tenté de s'authentifier
    # via l'en-tête Authorization ; en client_secret_post (notre cas, § 4.10),
    # Authlib retourne 400 invalid_client, conformément à la norme.
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_client"


def test_token_issuance_unknown_client(client, db_session):
    response = client.post(
        "/api/afnor/v1/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": "unknown-client",
            "client_secret": "whatever",
        },
    )

    assert response.status_code == 400
    assert response.json()["error"] == "invalid_client"


def test_token_issuance_wrong_grant_type(client, db_session):
    company = _make_company(db_session)
    oauth_app = _make_oauth_app(db_session, company, client_secret="s3cret-value")

    response = client.post(
        "/api/afnor/v1/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": oauth_app.client_id,
            "client_secret": "s3cret-value",
        },
    )

    assert response.status_code == 400


def _authenticate(client, oauth_app, secret):
    response = client.post(
        "/api/afnor/v1/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": oauth_app.client_id,
            "client_secret": secret,
        },
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_list_invoices_scoped_to_consumer(client, db_session):
    company_a = _make_company(db_session, siren="111111111", name="Société A")
    company_b = _make_company(db_session, siren="222222222", name="Société B")

    oauth_app_a = _make_oauth_app(db_session, company_a, client_secret="secret-a")
    oauth_app_b = _make_oauth_app(db_session, company_b, client_secret="secret-b")

    target_a = _make_target(db_session, company_a, oauth_app=oauth_app_a, name="Odoo A")
    target_b = _make_target(db_session, company_b, oauth_app=oauth_app_b, name="Odoo B")

    partner = _make_partner(db_session)
    invoice_a = _make_invoice(db_session, company_a, partner, flow_id="flow-a")
    invoice_b = _make_invoice(db_session, company_b, partner, flow_id="flow-b")

    _route(db_session, invoice_a, target_a)
    _route(db_session, invoice_b, target_b)

    token_a = _authenticate(client, oauth_app_a, "secret-a")

    response = client.get(
        "/api/afnor/v1/invoices", headers={"Authorization": f"Bearer {token_a}"}
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == invoice_a.id


def test_list_invoices_excludes_invoice_of_another_company_even_if_routed_there(
    client, db_session
):
    """Garde-fou NF2 (défense en profondeur, cf. list_invoices_for_consumer) : même si
    un `InvoiceRouting` erroné existe (donnée historique désynchronisée, bug amont...),
    l'API ne doit jamais exposer une facture d'une autre entreprise que celle du
    consommateur authentifié."""
    company_a = _make_company(db_session, siren="111111111", name="Société A")
    company_b = _make_company(db_session, siren="222222222", name="Société B")

    oauth_app_a = _make_oauth_app(db_session, company_a, client_secret="secret-a")
    target_a = _make_target(db_session, company_a, oauth_app=oauth_app_a, name="Odoo A")

    partner = _make_partner(db_session)
    invoice_b = _make_invoice(db_session, company_b, partner, flow_id="flow-b")

    # Routage (à tort) de la facture de l'entreprise B vers la cible de l'entreprise A.
    _route(db_session, invoice_b, target_a)

    token_a = _authenticate(client, oauth_app_a, "secret-a")
    response = client.get(
        "/api/afnor/v1/invoices", headers={"Authorization": f"Bearer {token_a}"}
    )

    assert response.status_code == 200
    assert response.json() == []


def test_list_invoices_no_target_returns_empty(client, db_session):
    company = _make_company(db_session)
    oauth_app = _make_oauth_app(db_session, company, client_secret="s3cret-value")
    token = _authenticate(client, oauth_app, "s3cret-value")

    response = client.get(
        "/api/afnor/v1/invoices", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    assert response.json() == []


def test_list_invoices_rejects_missing_token(client, db_session):
    response = client.get("/api/afnor/v1/invoices")
    assert response.status_code == 401


def test_list_invoices_rejects_invalid_token(client, db_session):
    response = client.get(
        "/api/afnor/v1/invoices", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert response.status_code == 401
