"""Validation de réponses contre les schémas déclarés dans les contrats OpenAPI
officiels AFNOR fournis par l'utilisateur (`backend/docs/afnor-contracts/*.json`).

Objectif : piloter les tests par le contrat plutôt que par la mémoire — un schéma
mal recopié (ou une réponse qui en dérive) se voit immédiatement, sans dépendre de
ce qu'un test a pensé à vérifier à la main."""

import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

_CONTRACTS_DIR = Path(__file__).resolve().parent.parent / "docs" / "afnor-contracts"

FLOW_CONTRACT = "afnor-flow-openapi-v1.3.0.json"
DIRECTORY_CONTRACT = "afnor-directory-openapi-v1.3.0.json"


@lru_cache(maxsize=None)
def _load_spec(filename: str) -> dict:
    return json.loads((_CONTRACTS_DIR / filename).read_text())


@lru_cache(maxsize=None)
def _registry_for(filename: str) -> Registry:
    resource = Resource.from_contents(_load_spec(filename), default_specification=DRAFT202012)
    return Registry().with_resource(uri=filename, resource=resource)


def schema_validator(filename: str, schema_name: str) -> Draft202012Validator:
    """Validateur JSON Schema pour `#/components/schemas/{schema_name}` du contrat
    `filename` (un des deux fichiers ci-dessus)."""
    schema = {"$ref": f"{filename}#/components/schemas/{schema_name}"}
    return Draft202012Validator(schema, registry=_registry_for(filename))


def assert_matches_schema(instance: dict, *, filename: str, schema_name: str) -> None:
    """Lève une `AssertionError` listant TOUTES les violations (pas seulement la
    première) si `instance` ne respecte pas `#/components/schemas/{schema_name}`."""
    validator = schema_validator(filename, schema_name)
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.path))
    if errors:
        details = "\n".join(f"  - {'.'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in errors)
        raise AssertionError(
            f"{instance!r}\nne respecte pas {filename}#/components/schemas/{schema_name} :\n{details}"
        )


def error_codes_from_contract(filename: str) -> dict[int, str]:
    """Extrait `{statut_http: errorCode}` des exemples `responses.ErrorXXXResponse`
    du contrat — utilisé pour vérifier que notre table `_ERROR_CODE_BY_STATUS`
    (app/api/afnor/errors.py) ne dérive jamais du contrat plutôt que de la retaper
    de mémoire dans le test lui-même."""
    responses = _load_spec(filename)["components"]["responses"]
    codes: dict[int, str] = {}
    for name, response in responses.items():
        if not name.startswith("Error") or not name.endswith("Response"):
            continue
        status = int(name.removeprefix("Error").removesuffix("Response"))
        example = response["content"]["application/json"]["example"]
        codes[status] = example["errorCode"]
    return codes
