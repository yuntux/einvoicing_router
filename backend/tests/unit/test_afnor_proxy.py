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
            "/api/afnor/v1/directory/999999999",
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
    odoo_traces = [t for t in traces if t.request.get("endpoint") == "GET /directory/{siren}"]
    assert len(odoo_traces) == 1


def test_lookup_directory_superpdp_failure_returns_502(client, db_session):
    company = _make_company(db_session)
    oauth_app = _make_oauth_app(db_session, company, client_secret="secret-4")
    token = _token(client, oauth_app, "secret-4")

    with patch("app.afnor.client.adapter.afnor_client_adapter.lookup_directory_siren") as mock_lookup:
        mock_lookup.side_effect = RuntimeError("unreachable")
        response = client.get(
            "/api/afnor/v1/directory/999999999",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 502


def test_emit_invoice_rejects_oversized_file(client, db_session, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "max_upload_size_bytes", 10)
    company = _make_company(db_session)
    oauth_app = _make_oauth_app(db_session, company, client_secret="secret-5")
    token = _token(client, oauth_app, "secret-5")

    with patch("app.afnor.client.adapter.afnor_client_adapter.send_invoice") as mock_send:
        response = client.post(
            "/api/afnor/v1/invoices/emit",
            headers={"Authorization": f"Bearer {token}"},
            data={"flow_syntax": "Factur-X", "processing_rule": "B2B"},
            files={"file": ("invoice.xml", b"x" * 1000, "application/xml")},
        )

    assert response.status_code == 413
    mock_send.assert_not_called()


def test_emit_lifecycle_event_rejects_oversized_file(client, db_session, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "max_upload_size_bytes", 10)
    company = _make_company(db_session)
    oauth_app = _make_oauth_app(db_session, company, client_secret="secret-6")
    token = _token(client, oauth_app, "secret-6")

    with patch("app.afnor.client.adapter.afnor_client_adapter.send_cdar") as mock_send:
        response = client.post(
            "/api/afnor/v1/lifecycle-events/emit",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("cdar.xml", b"x" * 1000, "application/xml")},
        )

    assert response.status_code == 413
    mock_send.assert_not_called()
