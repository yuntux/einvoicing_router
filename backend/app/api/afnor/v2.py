"""API AFNOR XP Z12-013 exposée à Odoo — version v2 (spec.md § 4.4/§ 4.8, lot 8).

Preuve du registre de versions (`app/afnor/versioning/registry.py`) : ce module monte
un nouveau router sur un préfixe distinct (`/api/afnor/v2`, § 4.8 : "routage par
préfixe d'URL") en réutilisant les routes communes de `_common.py`, sans qu'aucun
service (`AfnorServerController`, `AfnorClientAdapter`, `AuditTraceService`...) n'ait
besoin d'être dupliqué ou modifié pour l'occasion. En pratique, tant que la norme
XP Z12-013 n'a pas de v2 publiée, ce module expose la même surface que v1 (moins
`/oauth/token` et les endpoints d'émission, propres à v1) ; il matérialise le point
d'extension plutôt qu'un changement de comportement réel."""

from fastapi import APIRouter

from app.afnor.versioning.registry import register_version
from app.api.afnor._common import register_common_routes

AFNOR_API_VERSION = "v2"

router = APIRouter()
register_common_routes(router, AFNOR_API_VERSION)

register_version(AFNOR_API_VERSION, router)
