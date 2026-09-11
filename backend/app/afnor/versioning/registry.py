"""Registre de versions de l'API AFNOR exposée à Odoo (spec.md § 4.8, lot 8).

Chaque version (`app/api/afnor/v1.py`, `v2.py`, …) enregistre son propre router
FastAPI via `register_version` ; `app/main.py` monte dynamiquement toutes les
versions activées (`settings.afnor_api_enabled_versions`) sous `/api/afnor/{version}`
— routage par préfixe d'URL, cf. § 4.8. Aucun service (`AfnorServerController`,
`AfnorClientAdapter`, `AuditTraceService`...) n'a besoin d'être modifié pour ajouter
une version : ils sont simplement réutilisés par le nouveau router, jamais dupliqués
(preuve dans `tests/unit/test_afnor_versioning.py`). Une version peut être retirée du
service sans supprimer son code, en l'omettant de `afnor_api_enabled_versions`
(dépréciation progressive, § 4.8) — son router reste enregistré, seul le montage change."""

from fastapi import APIRouter

_REGISTRY: dict[str, APIRouter] = {}


def register_version(version: str, router: APIRouter) -> None:
    _REGISTRY[version] = router


def get_router(version: str) -> APIRouter | None:
    return _REGISTRY.get(version)


def registered_versions() -> list[str]:
    return sorted(_REGISTRY.keys())
