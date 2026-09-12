"""Proxy émission (POST /flows) / cycle de vie / annuaire, Odoo -> SuperPDP
(spec.md § 4.4). Depuis la convergence vers le vrai contrat AFNOR Flow Service,
l'émission de facture et de message de cycle de vie CDAR passent par le même
endpoint `POST /flows`, distingués par `flowInfo.flowSyntax` ("CDAR" pour un
cycle de vie, tout le reste pour une facture)."""

import json
from unittest.mock import patch

from app.auth.oauth import generate_client_credentials, hash_secret
from app.models.audit import FlowTrace
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


def _token(client, oauth_app, secret):
    response = client.post(
        "/api/afnor/v1/oauth/token",
        data={"grant_type": "client_credentials", "client_id": oauth_app.client_id, "client_secret": secret},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _post_flow(client, token, *, flow_info: dict, content: bytes = b"<invoice/>", filename="invoice.xml"):
    return client.post(
        "/api/afnor/v1/afnor-flow/flows",
        headers={"Authorization": f"Bearer {token}"},
        data={"flowInfo": json.dumps(flow_info)},
        files={"file": (filename, content, "application/xml")},
    )


def test_create_flow_invoice_proxies_and_traces_without_storing_invoice(client, db_session):
    company = _make_company(db_session)
    oauth_app = _make_oauth_app(db_session, company, client_secret="secret-1")
    token = _token(client, oauth_app, "secret-1")

    with patch("app.afnor.client.adapter.afnor_client_adapter.send_invoice") as mock_send:
        mock_send.return_value = {"id": "superpdp-flow-1", "state": "sent"}
        response = _post_flow(
            client, token, flow_info={"flowSyntax": "Factur-X", "name": "invoice.xml", "processingRule": "B2B"}
        )

    assert response.status_code == 202
    assert response.json() == {"id": "superpdp-flow-1", "state": "sent"}
    mock_send.assert_called_once()
    _, kwargs = mock_send.call_args
    assert kwargs["company"].id == company.id
    assert kwargs["flow_syntax"] == "Factur-X"

    from app.models.invoicing import Invoice

    assert db_session.query(Invoice).count() == 0

    traces = db_session.query(FlowTrace).all()
    odoo_traces = [t for t in traces if t.request.get("endpoint") == "POST /afnor-flow/flows"]
    assert len(odoo_traces) == 1


def test_create_flow_invoice_superpdp_failure_returns_502(client, db_session):
    company = _make_company(db_session)
    oauth_app = _make_oauth_app(db_session, company, client_secret="secret-1")
    token = _token(client, oauth_app, "secret-1")

    with patch("app.afnor.client.adapter.afnor_client_adapter.send_invoice") as mock_send:
        mock_send.side_effect = RuntimeError("unreachable")
        response = _post_flow(
            client, token, flow_info={"flowSyntax": "Factur-X", "name": "invoice.xml", "processingRule": "B2B"}
        )

    assert response.status_code == 502


def test_create_flow_cdar_proxies_and_traces(client, db_session):
    company = _make_company(db_session)
    oauth_app = _make_oauth_app(db_session, company, client_secret="secret-2")
    token = _token(client, oauth_app, "secret-2")

    with patch("app.afnor.client.adapter.afnor_client_adapter.send_cdar") as mock_send:
        mock_send.return_value = {"id": "superpdp-flow-2"}
        response = _post_flow(
            client,
            token,
            flow_info={"flowSyntax": "CDAR", "name": "cdar.xml"},
            content=b"<CrossDomainAcknowledgementAndResponse/>",
            filename="cdar.xml",
        )

    assert response.status_code == 202
    assert response.json() == {"id": "superpdp-flow-2"}
    mock_send.assert_called_once()

    traces = db_session.query(FlowTrace).all()
    odoo_traces = [t for t in traces if t.request.get("endpoint") == "POST /afnor-flow/flows"]
    assert len(odoo_traces) == 1


def test_create_flow_rejects_missing_token(client, db_session):
    response = client.post(
        "/api/afnor/v1/afnor-flow/flows",
        data={"flowInfo": json.dumps({"flowSyntax": "Factur-X", "name": "invoice.xml"})},
        files={"file": ("invoice.xml", b"<invoice/>", "application/xml")},
    )
    assert response.status_code == 401


def test_create_flow_rejects_invalid_flow_info(client, db_session):
    company = _make_company(db_session)
    oauth_app = _make_oauth_app(db_session, company, client_secret="secret-x")
    token = _token(client, oauth_app, "secret-x")

    response = client.post(
        "/api/afnor/v1/afnor-flow/flows",
        headers={"Authorization": f"Bearer {token}"},
        data={"flowInfo": json.dumps({"flowSyntax": "NotAValidSyntax", "name": "invoice.xml"})},
        files={"file": ("invoice.xml", b"<invoice/>", "application/xml")},
    )
    assert response.status_code == 400


def test_lookup_directory_proxies_and_traces_without_creating_partner(client, db_session):
    """Proxy transparent (§ 4.4) : la consultation d'annuaire ne doit plus créer de
    `PartnerDirectory` ni de `RoutingRule` implicite — l'annuaire consulté par Odoo
    concerne ses propres clients, pas les fournisseurs du routeur (§ 4.3)."""
    company = _make_company(db_session)
    oauth_app = _make_oauth_app(db_session, company, client_secret="secret-3")
    token = _token(client, oauth_app, "secret-3")

    with patch("app.afnor.client.adapter.afnor_client_adapter.lookup_directory_siren") as mock_lookup:
        mock_lookup.return_value = {
            "siren": "999999999",
            "name": "Nouveau Tiers",
            "closed": False,
            "entity_type": "private",
        }
        response = client.get(
            "/api/afnor/v1/afnor-directory/siren/code-insee:999999999",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "siren": "999999999",
        "name": "Nouveau Tiers",
        "closed": False,
        "entity_type": "private",
    }
    mock_lookup.assert_called_once()
    _, kwargs = mock_lookup.call_args
    assert kwargs["company"].id == company.id
    assert kwargs["siren"] == "999999999"

    from app.models.referential import PartnerDirectory, RoutingRule

    assert db_session.query(PartnerDirectory).count() == 0
    assert db_session.query(RoutingRule).count() == 0

    traces = db_session.query(FlowTrace).all()
    odoo_traces = [
        t for t in traces if t.request.get("endpoint") == "GET /afnor-directory/siren/code-insee:{siren}"
    ]
    assert len(odoo_traces) == 1


def test_lookup_directory_superpdp_failure_returns_502(client, db_session):
    company = _make_company(db_session)
    oauth_app = _make_oauth_app(db_session, company, client_secret="secret-4")
    token = _token(client, oauth_app, "secret-4")

    with patch("app.afnor.client.adapter.afnor_client_adapter.lookup_directory_siren") as mock_lookup:
        mock_lookup.side_effect = RuntimeError("unreachable")
        response = client.get(
            "/api/afnor/v1/afnor-directory/siren/code-insee:999999999",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 502


def test_create_flow_rejects_oversized_file(client, db_session, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "max_upload_size_bytes", 10)
    company = _make_company(db_session)
    oauth_app = _make_oauth_app(db_session, company, client_secret="secret-5")
    token = _token(client, oauth_app, "secret-5")

    with patch("app.afnor.client.adapter.afnor_client_adapter.send_invoice") as mock_send:
        response = _post_flow(
            client,
            token,
            flow_info={"flowSyntax": "Factur-X", "name": "invoice.xml", "processingRule": "B2B"},
            content=b"x" * 1000,
        )

    assert response.status_code == 413
    mock_send.assert_not_called()


def test_create_flow_cdar_rejects_oversized_file(client, db_session, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "max_upload_size_bytes", 10)
    company = _make_company(db_session)
    oauth_app = _make_oauth_app(db_session, company, client_secret="secret-6")
    token = _token(client, oauth_app, "secret-6")

    with patch("app.afnor.client.adapter.afnor_client_adapter.send_cdar") as mock_send:
        response = _post_flow(
            client,
            token,
            flow_info={"flowSyntax": "CDAR", "name": "cdar.xml"},
            content=b"x" * 1000,
            filename="cdar.xml",
        )

    assert response.status_code == 413
    mock_send.assert_not_called()
