"""Registre de versions de l'API AFNOR exposée à Odoo (spec.md § 4.8).

Seule `v1` (`app/api/afnor/v1.py`) existe aujourd'hui — la norme XP Z12-013 n'a pas
encore de v2 publiée, et exposer par avance un router `v2` qui ne ferait que copier
`v1` serait anticiper inutilement (§ 4.8 met en garde contre ce travers pour une
décision voisine : "sans que cette extraction future ne soit anticipée
prématurément"). Ce module est le dispositif qui permettra d'ajouter une vraie
version future sans rien modifier ailleurs : un nouveau module `app/api/afnor/v2.py`
n'aurait qu'à construire son router via `register_common_routes` (`_common.py`) et
l'enregistrer ici avec `register_version` ; `app/main.py` le monterait alors
automatiquement sous `/api/afnor/v2`, dès qu'il est ajouté à
`settings.afnor_api_enabled_versions` — sans qu'aucun service
(`AfnorServerController`, `AfnorClientAdapter`, `AuditTraceService`...) n'ait besoin
d'être modifié ni dupliqué (mécanisme prouvé, sans v2 réelle, par
`tests/unit/test_afnor_versioning.py`). Une version pourra de la même façon être
dépréciée puis retirée sans supprimer son code, en l'omettant simplement de
`afnor_api_enabled_versions`."""

from fastapi import APIRouter

_REGISTRY: dict[str, APIRouter] = {}


def register_version(version: str, router: APIRouter) -> None:
    _REGISTRY[version] = router


def get_router(version: str) -> APIRouter | None:
    return _REGISTRY.get(version)


def registered_versions() -> list[str]:
    return sorted(_REGISTRY.keys())
