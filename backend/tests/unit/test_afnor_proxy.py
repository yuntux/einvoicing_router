"""Proxy émission/cycle de vie Odoo -> SuperPDP (spec.md § 4.4, lot 6)."""

from unittest.mock import patch

from app.auth.oauth import generate_client_credentials, hash_secret
from app.models.audit import FlowTrace
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


def _token(client, oauth_app, secret):
    response = client.post(
        "/api/afnor/v1/oauth/token",
        data={"grant_type": "client_credentials", "client_id": oauth_app.client_id, "client_secret": secret},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_emit_invoice_proxies_and_traces_without_storing_invoice(client, db_session):
    company = _make_company(db_session)
    oauth_app = _make_oauth_app(db_session, company, client_secret="secret-1")
    token = _token(client, oauth_app, "secret-1")

    with patch("app.afnor.client.adapter.afnor_client_adapter.send_invoice") as mock_send:
        mock_send.return_value = {"id": "superpdp-flow-1", "state": "sent"}
        response = client.post(
            "/api/afnor/v1/invoices/emit",
            headers={"Authorization": f"Bearer {token}"},
            data={"flow_syntax": "Factur-X", "processing_rule": "B2B"},
            files={"file": ("invoice.xml", b"<invoice/>", "application/xml")},
        )

    assert response.status_code == 200
    assert response.json() == {"id": "superpdp-flow-1", "state": "sent"}
    mock_send.assert_called_once()
    _, kwargs = mock_send.call_args
    assert kwargs["company"].id == company.id
    assert kwargs["flow_syntax"] == "Factur-X"

    from app.models.invoicing import Invoice

    assert db_session.query(Invoice).count() == 0

    traces = db_session.query(FlowTrace).all()
    odoo_traces = [t for t in traces if t.request.get("endpoint") == "POST /invoices/emit"]
    assert len(odoo_traces) == 1


def test_emit_invoice_superpdp_failure_returns_502(client, db_session):
    company = _make_company(db_session)
    oauth_app = _make_oauth_app(db_session, company, client_secret="secret-1")
    token = _token(client, oauth_app, "secret-1")

    with patch("app.afnor.client.adapter.afnor_client_adapter.send_invoice") as mock_send:
        mock_send.side_effect = RuntimeError("unreachable")
        response = client.post(
            "/api/afnor/v1/invoices/emit",
            headers={"Authorization": f"Bearer {token}"},
            data={"flow_syntax": "Factur-X", "processing_rule": "B2B"},
            files={"file": ("invoice.xml", b"<invoice/>", "application/xml")},
        )

    assert response.status_code == 502


def test_emit_lifecycle_event_proxies_and_traces(client, db_session):
    company = _make_company(db_session)
    oauth_app = _make_oauth_app(db_session, company, client_secret="secret-2")
    token = _token(client, oauth_app, "secret-2")

    with patch("app.afnor.client.adapter.afnor_client_adapter.send_cdar") as mock_send:
        mock_send.return_value = {"id": "superpdp-flow-2"}
        response = client.post(
            "/api/afnor/v1/lifecycle-events/emit",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("cdar.xml", b"<CrossDomainAcknowledgementAndResponse/>", "application/xml")},
        )

    assert response.status_code == 200
    assert response.json() == {"id": "superpdp-flow-2"}
    mock_send.assert_called_once()

    traces = db_session.query(FlowTrace).all()
    odoo_traces = [
        t for t in traces if t.request.get("endpoint") == "POST /lifecycle-events/emit"
    ]
    assert len(odoo_traces) == 1


def test_emit_endpoints_reject_missing_token(client, db_session):
    response = client.post(
        "/api/afnor/v1/invoices/emit",
        data={"flow_syntax": "Factur-X", "processing_rule": "B2B"},
        files={"file": ("invoice.xml", b"<invoice/>", "application/xml")},
    )
    assert response.status_code == 401
