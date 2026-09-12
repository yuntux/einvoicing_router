"""AFNOR Directory Service + healthchecks — endpoints en pur passe-plat vers
SuperPDP (spec.md § 4.4/§ 4.3) : aucun de ces endpoints ne concerne les factures
reçues par le routeur, donc aucun filtrage NF2, aucune interprétation du corps —
seul le statut HTTP et le corps réellement renvoyés par SuperPDP comptent.

Un seul jeu de mocks bas niveau (`_mock_session`, qui patche directement la méthode
`requests.Session.request` de la session pyfrctc mise en cache) est réutilisé pour
tous les endpoints passe-plat, afin de vérifier systématiquement les mêmes
invariants pour chacun : méthode HTTP et URL exacts, statut ET corps transmis tels
quels (y compris les statuts d'erreur du contrat), authentification requise, aucune
écriture en base (`PartnerDirectory`/`RoutingRule`/`Invoice`)."""

from unittest.mock import MagicMock, patch

import pytest

from app.auth.oauth import generate_client_credentials, hash_secret
from app.models.audit import FlowTrace
from app.models.referential import (
    Company,
    OAuthAppType,
    OAuthApplication,
    OAuthScope,
    PartnerDirectory,
    RoutingRule,
)


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


def _fake_response(status_code: int, json_body: dict | list | None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.content = b"{}" if json_body is not None else b""
    resp.json.return_value = json_body
    resp.request = MagicMock(headers={})
    resp.headers = {}
    return resp


# Les 8 endpoints qui passent réellement par `raw_passthrough` (méthode HTTP
# générique `session.request`, mockable uniformément). `GET /siret/code-insee:...`
# passe par le wrapper `pyfrctc` dédié (comme `GET /siren/code-insee:...`) et est
# donc testé séparément ci-dessous (`test_lookup_siret_*`), avec un mock différent.
PASSTHROUGH_ENDPOINTS = [
    ("POST", "/api/afnor/v1/afnor-directory/siren/search", {"where": {"siren": {"op": "strict", "value": "702042755"}}}),
    ("POST", "/api/afnor/v1/afnor-directory/siret/search", {"where": {}}),
    (
        "GET",
        "/api/afnor/v1/afnor-directory/routing-code/siret:70204275500240/code:702042755",
        None,
    ),
    ("POST", "/api/afnor/v1/afnor-directory/routing-code/search", {"where": {}}),
    (
        "GET",
        "/api/afnor/v1/afnor-directory/directory-line/code:dcsc456sdcsdcs556",
        None,
    ),
    ("POST", "/api/afnor/v1/afnor-directory/directory-line/search", {"where": {}}),
    ("GET", "/api/afnor/v1/afnor-flow/healthcheck", None),
    ("GET", "/api/afnor/v1/afnor-directory/healthcheck", None),
]


def _make_request(client, method, path, token, body):
    headers = {"Authorization": f"Bearer {token}"}
    if method == "GET":
        return client.get(path, headers=headers)
    return client.post(path, json=body, headers=headers)


@pytest.mark.parametrize("method,path,body", PASSTHROUGH_ENDPOINTS)
def test_passthrough_forwards_success_body_and_status_verbatim(client, db_session, method, path, body):
    company = _make_company(db_session)
    oauth_app = _make_oauth_app(db_session, company, client_secret="secret-1")
    token = _token(client, oauth_app, "secret-1")

    fake_body = {"results": [{"siren": "702042755"}], "totalNumberOfResults": 1}
    with patch("app.afnor.client.adapter.core.get_session") as mock_get_session, patch(
        "app.afnor.client.adapter.core._get_plateform", return_value="superpdp"
    ), patch(
        "app.services.superpdp_credentials_service.get_credentials_application"
    ) as mock_creds, patch(
        "app.services.superpdp_credentials_service.get_decrypted_secret", return_value="secret"
    ):
        mock_creds.return_value = MagicMock(platform="superpdp", client_id="cid", token_cache=None)
        session = MagicMock()
        session.hooks = {}
        session.request.return_value = _fake_response(200, fake_body)
        mock_get_session.return_value = session

        response = _make_request(client, method, path, token, body)

    assert response.status_code == 200
    assert response.json() == fake_body
    session.request.assert_called_once()
    called_method = session.request.call_args.args[0]
    assert called_method == method

    # Aucune écriture métier : un passe-plat ne doit jamais créer de données.
    assert db_session.query(PartnerDirectory).count() == 0
    assert db_session.query(RoutingRule).count() == 0

    traces = db_session.query(FlowTrace).filter(FlowTrace.direction == "router_to_superpdp").all()
    assert len(traces) == 1
    assert traces[0].http_status == 200


@pytest.mark.parametrize("method,path,body", PASSTHROUGH_ENDPOINTS)
def test_passthrough_forwards_upstream_error_status_verbatim(client, db_session, method, path, body):
    """Rigueur du passe-plat : un 404/403/... renvoyé par SuperPDP doit ressortir
    identique à Odoo — jamais aplati sur un 502 générique (réservé aux pannes
    réseau réelles, cf. test suivant)."""
    company = _make_company(db_session)
    oauth_app = _make_oauth_app(db_session, company, client_secret="secret-2")
    token = _token(client, oauth_app, "secret-2")

    error_body = {"errorCode": "MISSING_RESOURCE", "errorMessage": "Requested resource is Not Found"}
    with patch("app.afnor.client.adapter.core.get_session") as mock_get_session, patch(
        "app.afnor.client.adapter.core._get_plateform", return_value="superpdp"
    ), patch(
        "app.services.superpdp_credentials_service.get_credentials_application"
    ) as mock_creds, patch(
        "app.services.superpdp_credentials_service.get_decrypted_secret", return_value="secret"
    ):
        mock_creds.return_value = MagicMock(platform="superpdp", client_id="cid", token_cache=None)
        session = MagicMock()
        session.hooks = {}
        session.request.return_value = _fake_response(404, error_body)
        mock_get_session.return_value = session

        response = _make_request(client, method, path, token, body)

    assert response.status_code == 404
    assert response.json() == error_body


@pytest.mark.parametrize("method,path,body", PASSTHROUGH_ENDPOINTS)
def test_passthrough_network_failure_returns_502_with_afnor_error_envelope(
    client, db_session, method, path, body
):
    company = _make_company(db_session)
    oauth_app = _make_oauth_app(db_session, company, client_secret="secret-3")
    token = _token(client, oauth_app, "secret-3")

    with patch("app.afnor.client.adapter.core.get_session") as mock_get_session, patch(
        "app.afnor.client.adapter.core._get_plateform", return_value="superpdp"
    ), patch(
        "app.services.superpdp_credentials_service.get_credentials_application"
    ) as mock_creds, patch(
        "app.services.superpdp_credentials_service.get_decrypted_secret", return_value="secret"
    ):
        mock_creds.return_value = MagicMock(platform="superpdp", client_id="cid", token_cache=None)
        session = MagicMock()
        session.hooks = {}
        session.request.side_effect = ConnectionError("network down")
        mock_get_session.return_value = session

        response = _make_request(client, method, path, token, body)

    assert response.status_code == 502
    body_json = response.json()
    assert body_json["errorCode"] == "INTERNAL_ERROR"
    assert "network down" in body_json["errorMessage"]


@pytest.mark.parametrize("method,path,body", PASSTHROUGH_ENDPOINTS)
def test_passthrough_rejects_missing_token(client, db_session, method, path, body):
    if method == "GET":
        response = client.get(path)
    else:
        response = client.post(path, json=body)
    assert response.status_code == 401
    assert response.json()["errorCode"] == "MISSING_TOKEN"


@pytest.mark.parametrize("method,path,body", PASSTHROUGH_ENDPOINTS)
def test_passthrough_rejects_invalid_token(client, db_session, method, path, body):
    headers = {"Authorization": "Bearer not-a-real-token"}
    if method == "GET":
        response = client.get(path, headers=headers)
    else:
        response = client.post(path, json=body, headers=headers)
    assert response.status_code == 401


def test_lookup_siret_uses_pyfrctc_wrapper_without_creating_partner(client, db_session):
    """`GET /siret/code-insee:{siret}` passe par le wrapper `pyfrctc` dédié (comme
    `GET /siren/code-insee:{siren}`, déjà couvert par `test_afnor_proxy.py`) plutôt
    que par `raw_passthrough` — vérifié séparément car mocké différemment."""
    company = _make_company(db_session)
    oauth_app = _make_oauth_app(db_session, company, client_secret="secret-4")
    token = _token(client, oauth_app, "secret-4")

    with patch("app.afnor.client.adapter.afnor_client_adapter.lookup_directory_siret") as mock_lookup:
        mock_lookup.return_value = {"siret": "70204275500240", "name": "Tiers"}
        response = client.get(
            "/api/afnor/v1/afnor-directory/siret/code-insee:70204275500240",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    assert response.json() == {"siret": "70204275500240", "name": "Tiers"}
    mock_lookup.assert_called_once()
    _, kwargs = mock_lookup.call_args
    assert kwargs["siret"] == "70204275500240"

    assert db_session.query(PartnerDirectory).count() == 0
    assert db_session.query(RoutingRule).count() == 0


def test_lookup_siret_superpdp_failure_returns_502(client, db_session):
    company = _make_company(db_session)
    oauth_app = _make_oauth_app(db_session, company, client_secret="secret-5")
    token = _token(client, oauth_app, "secret-5")

    with patch("app.afnor.client.adapter.afnor_client_adapter.lookup_directory_siret") as mock_lookup:
        mock_lookup.side_effect = RuntimeError("unreachable")
        response = client.get(
            "/api/afnor/v1/afnor-directory/siret/code-insee:70204275500240",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 502
