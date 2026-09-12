"""Enveloppe d'erreur AFNOR (`app/api/afnor/errors.py`) — vérifie le mapping complet
`errorCode` par statut HTTP (repris tel quel des exemples des deux contrats
officiels) et que les routes IHM restent en format `HTTPException` standard,
inchangé (§ NF... : l'enveloppe ne doit affecter QUE `/api/afnor/`)."""

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.afnor.errors import _ERROR_CODE_BY_STATUS, register_afnor_error_handlers
from tests.afnor_contracts import DIRECTORY_CONTRACT, FLOW_CONTRACT, error_codes_from_contract


def _make_test_app() -> FastAPI:
    app = FastAPI()
    register_afnor_error_handlers(app)

    @app.get("/api/afnor/v1/boom/{status_code}")
    def afnor_boom(status_code: int):
        raise HTTPException(status_code=status_code, detail="something went wrong")

    @app.get("/api/afnor/v1/boom-preformatted")
    def afnor_boom_preformatted():
        raise HTTPException(
            status_code=404,
            detail={"errorCode": "CUSTOM_CODE", "errorMessage": "already shaped"},
        )

    @app.get("/api/ihm/boom/{status_code}")
    def ihm_boom(status_code: int):
        raise HTTPException(status_code=status_code, detail="ihm error")

    return app


@pytest.fixture()
def error_client():
    return TestClient(_make_test_app(), raise_server_exceptions=False)


@pytest.mark.parametrize("status_code,expected_code", sorted(_ERROR_CODE_BY_STATUS.items()))
def test_afnor_routes_use_error_envelope_for_every_documented_status(
    error_client, status_code, expected_code
):
    response = error_client.get(f"/api/afnor/v1/boom/{status_code}")
    assert response.status_code == status_code
    body = response.json()
    assert body == {"errorCode": expected_code, "errorMessage": "something went wrong"}


def test_afnor_route_unmapped_status_falls_back_to_internal_error(error_client):
    response = error_client.get("/api/afnor/v1/boom/418")
    assert response.status_code == 418
    assert response.json()["errorCode"] == "INTERNAL_ERROR"


def test_afnor_route_preserves_already_shaped_error_detail(error_client):
    """Un passe-plat qui relaie tel quel une erreur JSON de SuperPDP (déjà au format
    `{errorCode, errorMessage}`) ne doit pas être re-enveloppé une deuxième fois."""
    response = error_client.get("/api/afnor/v1/boom-preformatted")
    assert response.status_code == 404
    assert response.json() == {"errorCode": "CUSTOM_CODE", "errorMessage": "already shaped"}


def test_ihm_routes_are_not_affected_by_the_afnor_error_envelope(error_client):
    response = error_client.get("/api/ihm/boom/404")
    assert response.status_code == 404
    assert response.json() == {"detail": "ihm error"}


def test_error_code_mapping_matches_both_official_contracts():
    """Ne compare PAS `_ERROR_CODE_BY_STATUS` à une copie retapée de mémoire dans le
    test (ça ne prouverait que la cohérence du test avec lui-même) : le recalcule à
    partir des exemples `errorCode` réellement déclarés dans les deux fichiers
    `backend/docs/afnor-contracts/*.json`, et vérifie qu'aucun des deux contrats ne
    contredit `_ERROR_CODE_BY_STATUS` — celle-ci devant couvrir l'union des deux
    (Flow et Directory ne documentent pas exactement le même sous-ensemble de
    statuts : ex. 413 seulement côté Flow, qui accepte des uploads ; 408/501
    seulement côté Directory)."""
    flow_codes = error_codes_from_contract(FLOW_CONTRACT)
    directory_codes = error_codes_from_contract(DIRECTORY_CONTRACT)

    assert flow_codes, "le contrat Flow doit déclarer au moins un errorCode d'exemple"
    assert directory_codes, "le contrat Directory doit déclarer au moins un errorCode d'exemple"

    for contract_name, codes in (("Flow", flow_codes), ("Directory", directory_codes)):
        for status, expected_code in codes.items():
            assert _ERROR_CODE_BY_STATUS.get(status) == expected_code, (
                f"contrat {contract_name} : statut {status} doit mapper vers "
                f"{expected_code!r}, _ERROR_CODE_BY_STATUS a "
                f"{_ERROR_CODE_BY_STATUS.get(status)!r}"
            )

    union = {**flow_codes, **directory_codes}
    assert set(_ERROR_CODE_BY_STATUS) == set(union), (
        "_ERROR_CODE_BY_STATUS doit couvrir exactement l'union des statuts "
        "documentés par les deux contrats, ni plus ni moins"
    )
