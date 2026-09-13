"""Conformité mécanique aux schémas JSON des contrats officiels (§ 4.4) — valide les
réponses RÉELLEMENT produites par les endpoints contre `#/components/schemas/...`
des fichiers `backend/docs/afnor-contracts/*.json`, via `jsonschema` (cf.
`tests/afnor_contracts.py`). Complète `test_afnor_server.py`/`test_afnor_proxy.py`
(qui vérifient le comportement métier) par une garantie structurelle : si le contrat
change de forme (champ renommé, enum étendue...) ou si notre mapping s'en écarte, ces
tests le détectent sans qu'il faille se souvenir de relire le schéma à la main."""

from datetime import date

from app.auth.oauth import generate_client_credentials, hash_secret
from app.models.invoicing import Invoice, InvoiceRouting
from app.models.referential import Company, PartnerDirectory, RoutingMethod, TargetApplication
from tests.afnor_contracts import FLOW_CONTRACT, assert_matches_schema


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


def _make_invoice(db, company, partner, flow_id="flow-1", **overrides):
    invoice = Invoice(
        company_id=company.id,
        partner_directory_id=partner.id,
        emitter_siren=partner.siren,
        invoice_number="INV-1",
        invoice_date=date(2026, 1, 1),
        file_path="/tmp/fake.pdf",
        certified_platform_flow_id=flow_id,
        **overrides,
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


def _authenticate(client, oauth_app, secret):
    response = client.post(
        "/api/afnor/oauth/token",
        data={"grant_type": "client_credentials", "client_id": oauth_app.client_id, "client_secret": secret},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _setup_routed_invoice(db, *, flow_id: str, **invoice_overrides):
    company = _make_company(db, siren="111111111")
    target = _make_oauth_app(db, company, client_secret="secret-contract")
    partner = PartnerDirectory(siren="987654321", name="Fournisseur")
    db.add(partner)
    db.commit()
    db.refresh(partner)
    invoice = _make_invoice(db, company, partner, flow_id=flow_id, **invoice_overrides)
    _route(db, invoice, target)
    return target, invoice


def test_search_flows_response_matches_search_flow_content_schema(client, db_session):
    oauth_app, _invoice = _setup_routed_invoice(db_session, flow_id="flow-contract-1")
    token = _authenticate(client, oauth_app, "secret-contract")

    response = client.post(
        "/api/afnor/afnor-flow/v1/flows/search",
        json={"where": {}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200

    assert_matches_schema(
        response.json(), filename=FLOW_CONTRACT, schema_name="SearchFlowContent"
    )
    for flow in response.json()["results"]:
        assert_matches_schema(flow, filename=FLOW_CONTRACT, schema_name="Flow")


def test_search_flows_response_matches_schema_even_with_minimal_invoice_fields(client, db_session):
    """Cas limite : une facture dont les champs d'enveloppe optionnels
    (flow_profile, tracking_id, ack_status...) sont tous `None` — les valeurs par
    défaut de `flow_from_invoice` doivent rester conformes au schéma (ex.
    `flowProfile="Undefined"` est une valeur d'enum valide, pas juste une chaîne
    arbitraire qui « passerait »)."""
    oauth_app, _invoice = _setup_routed_invoice(
        db_session,
        flow_id="flow-contract-2",
        syntax=None,
        flow_profile=None,
        processing_rule=None,
        processing_rule_source=None,
        tracking_id=None,
        flow_name=None,
        ack_status=None,
    )
    token = _authenticate(client, oauth_app, "secret-contract")

    response = client.post(
        "/api/afnor/afnor-flow/v1/flows/search",
        json={"where": {}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    for flow in response.json()["results"]:
        assert_matches_schema(flow, filename=FLOW_CONTRACT, schema_name="Flow")


def test_get_flow_metadata_response_matches_flow_schema(client, db_session):
    oauth_app, invoice = _setup_routed_invoice(db_session, flow_id="flow-contract-3")
    token = _authenticate(client, oauth_app, "secret-contract")

    response = client.get(
        f"/api/afnor/afnor-flow/v1/flows/{invoice.certified_platform_flow_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert_matches_schema(response.json(), filename=FLOW_CONTRACT, schema_name="Flow")


def test_assert_matches_schema_actually_detects_a_violation():
    """Garde-fou sur le garde-fou : si `assert_matches_schema` ne détectait plus
    jamais rien (schéma mal résolu, validateur no-op...), tous les tests
    ci-dessus passeraient à tort. Vérifie qu'une réponse non conforme est bien
    rejetée, avec un message qui identifie le champ fautif."""
    invalid_flow = {
        "flowId": "x",
        "submittedAt": "2026-01-01T00:00:00Z",
        "flowSyntax": "NOT_A_VALID_SYNTAX",
        "name": "f.xml",
        "flowProfile": "Basic",
        "processingRule": "B2B",
        "processingRuleSource": "Computed",
        "flowDirection": "In",
        "flowType": "SupplierInvoice",
        "acknowledgement": {"status": "Pending"},
        "updatedAt": "2026-01-01T00:00:00Z",
    }
    try:
        assert_matches_schema(invalid_flow, filename=FLOW_CONTRACT, schema_name="Flow")
    except AssertionError as exc:
        assert "flowSyntax" in str(exc)
    else:
        raise AssertionError("assert_matches_schema aurait dû rejeter flowSyntax invalide")
