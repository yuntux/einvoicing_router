"""Recherche annuaire AFNOR côté IHM (§ nouvel écran "Annuaire") — le routeur agit en
CLIENT de l'annuaire SuperPDP pour ses propres utilisateurs, avec les identifiants
d'une entreprise gérée choisie explicitement (`company_id`), via
`AfnorClientAdapter.raw_passthrough` — même mécanique bas niveau que le passthrough
Odoo déjà testé dans `test_afnor_directory_passthrough.py`, mais exposée sous
`/api/ihm/directory/*` et scopée par périmètre utilisateur (NF4) plutôt que par
application OAuth."""

from unittest.mock import MagicMock, patch

from app.models.audit import FlowTrace
from app.models.referential import Company


def _make_company(db, siren="123456789", name="Ma Société"):
    company = Company(siren=siren, name=name)
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


def _fake_response(status_code: int, json_body: dict):
    resp = MagicMock()
    resp.status_code = status_code
    resp.content = b"{}"
    resp.json.return_value = json_body
    resp.request = MagicMock(headers={})
    resp.headers = {}
    return resp


def test_search_siren_relays_filters_and_response(client, db_session):
    company = _make_company(db_session)
    fake_body = {
        "results": [{"siren": "702042755", "businessName": "ACME", "entityType": "COMPANY"}],
        "totalNumberOfResults": 1,
    }

    with (
        patch("app.afnor.client.adapter.core.get_session") as mock_get_session,
        patch("app.afnor.client.adapter.core._get_plateform", return_value="superpdp"),
        patch(
            "app.services.certified_platform_credentials_service.get_credentials_application"
        ) as mock_creds,
        patch(
            "app.services.certified_platform_credentials_service.get_decrypted_secret",
            return_value="secret",
        ),
    ):
        mock_creds.return_value = MagicMock(platform="superpdp", client_id="cid", token_cache=None)
        session = MagicMock()
        session.hooks = {}
        session.request.return_value = _fake_response(200, fake_body)
        mock_get_session.return_value = session

        response = client.post(
            "/api/ihm/directory/search",
            json={"company_id": company.id, "resource": "siren", "business_name": "ACME"},
        )

    assert response.status_code == 200
    assert response.json() == fake_body

    called_kwargs = session.request.call_args
    assert called_kwargs.args[0] == "POST"
    assert called_kwargs.args[1].endswith("/afnor-directory/v1/siren/search")
    sent_json = called_kwargs.kwargs["json"]
    assert sent_json["filters"] == {"businessName": {"op": "contains", "value": "ACME"}}

    traces = db_session.query(FlowTrace).filter(FlowTrace.direction == "router_to_superpdp").all()
    assert len(traces) == 1


def test_search_requires_at_least_one_filter(client, db_session):
    company = _make_company(db_session)

    response = client.post(
        "/api/ihm/directory/search",
        json={"company_id": company.id, "resource": "siren"},
    )

    assert response.status_code == 422


def test_directory_lines_forwards_siren_filter(client, db_session):
    company = _make_company(db_session)
    fake_body = {"results": [], "totalNumberOfResults": 0}

    with (
        patch("app.afnor.client.adapter.core.get_session") as mock_get_session,
        patch("app.afnor.client.adapter.core._get_plateform", return_value="superpdp"),
        patch(
            "app.services.certified_platform_credentials_service.get_credentials_application"
        ) as mock_creds,
        patch(
            "app.services.certified_platform_credentials_service.get_decrypted_secret",
            return_value="secret",
        ),
    ):
        mock_creds.return_value = MagicMock(platform="superpdp", client_id="cid", token_cache=None)
        session = MagicMock()
        session.hooks = {}
        session.request.return_value = _fake_response(200, fake_body)
        mock_get_session.return_value = session

        response = client.post(
            "/api/ihm/directory/lines",
            json={"company_id": company.id, "siren": "702042755"},
        )

    assert response.status_code == 200
    assert response.json() == fake_body
    sent_json = session.request.call_args.kwargs["json"]
    assert sent_json["filters"] == {"siren": {"op": "strict", "value": "702042755"}}


def test_peppol_check_relays_identifier_without_company(client, db_session):
    """§ bouton "Rechercher sur l'annuaire Peppol" — pas de `company_id` requis, pas
    d'appel SuperPDP : une résolution DNS pure sur l'identifiant tel quel."""
    with patch(
        "app.services.peppol_service.check_directory_line_peppol_status",
        return_value="ap.example.com",
    ):
        response = client.post("/api/ihm/directory/peppol-check", json={"identifier": "844191981"})

    assert response.status_code == 200
    assert response.json() == {"active": True, "access_point": "ap.example.com", "error": None}


def test_peppol_check_rejects_blank_identifier(client, db_session):
    response = client.post("/api/ihm/directory/peppol-check", json={"identifier": "   "})

    assert response.status_code == 422


def test_directory_lines_enriches_each_result_with_peppol_status(client, db_session):
    """§ colonne "Annuaire Peppol" — chaque ligne renvoyée par SuperPDP est enrichie
    d'un statut PEPPOL (résolution DNS indépendante, § peppol_service), jamais
    fourni par SuperPDP lui-même."""
    company = _make_company(db_session)
    fake_body = {
        "results": [
            {"addressingIdentifier": "70204275500013", "siret": "70204275500013"},
            {"addressingIdentifier": "70204275500021", "siret": "70204275500021"},
        ],
        "totalNumberOfResults": 2,
    }

    def fake_peppol_check(dir_line):
        if dir_line == "70204275500013":
            return "ap.example.com"
        return False

    with (
        patch("app.afnor.client.adapter.core.get_session") as mock_get_session,
        patch("app.afnor.client.adapter.core._get_plateform", return_value="superpdp"),
        patch(
            "app.services.certified_platform_credentials_service.get_credentials_application"
        ) as mock_creds,
        patch(
            "app.services.certified_platform_credentials_service.get_decrypted_secret",
            return_value="secret",
        ),
        patch(
            "app.services.peppol_service.check_directory_line_peppol_status",
            side_effect=fake_peppol_check,
        ),
    ):
        mock_creds.return_value = MagicMock(platform="superpdp", client_id="cid", token_cache=None)
        session = MagicMock()
        session.hooks = {}
        session.request.return_value = _fake_response(200, fake_body)
        mock_get_session.return_value = session

        response = client.post(
            "/api/ihm/directory/lines",
            json={"company_id": company.id, "siren": "702042755"},
        )

    assert response.status_code == 200
    results = response.json()["results"]
    assert results[0]["peppol"] == {"active": True, "access_point": "ap.example.com", "error": None}
    assert results[1]["peppol"] == {"active": False, "access_point": None, "error": None}


def test_directory_lines_requires_siren_or_siret(client, db_session):
    company = _make_company(db_session)

    response = client.post("/api/ihm/directory/lines", json={"company_id": company.id})

    assert response.status_code == 422


def test_search_unknown_company_returns_404(client, db_session):
    response = client.post(
        "/api/ihm/directory/search",
        json={"company_id": 999999, "resource": "siren", "siren": "702042755"},
    )

    assert response.status_code == 404
