"""Allowlist IPv4/IPv6 (spec.md NF6, lot 7) — configurable séparément pour les deux
surfaces exposées par le routeur (§ 3) : l'IHM (`/api/ihm/*`, hors `/api/ihm/auth/*`,
qui doit rester joignable pour se connecter) et l'API AFNOR (`/api/afnor/*`)."""

import ipaddress

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.db.session import SessionLocal
from app.services import router_settings_service


def is_ip_allowed(ip: str, allowlist: str | None) -> bool:
    """Une allowlist vide/`None` signifie "aucune restriction" (comportement par
    défaut, dev/tests) — sinon `ip` doit appartenir à l'une des adresses/CIDR listées,
    séparées par des virgules."""
    if not allowlist or not allowlist.strip():
        return True
    try:
        candidate = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for entry in allowlist.split(","):
        entry = entry.strip()
        if not entry:
            continue
        try:
            network = ipaddress.ip_network(entry, strict=False)
        except ValueError:
            continue
        if candidate in network:
            return True
    return False


class IPAllowlistMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        allowlist_field: str | None = None
        if path.startswith("/api/ihm/") and not path.startswith("/api/ihm/auth/"):
            allowlist_field = "ihm_ip_allowlist"
        elif path.startswith("/api/afnor/"):
            allowlist_field = "afnor_api_ip_allowlist"

        if allowlist_field is not None:
            client_ip = request.client.host if request.client else None
            db = SessionLocal()
            try:
                router_settings = router_settings_service.get_settings(db)
                allowlist = getattr(router_settings, allowlist_field)
            finally:
                db.close()
            if client_ip is None or not is_ip_allowed(client_ip, allowlist):
                return JSONResponse(status_code=403, content={"detail": "IP address not allowed"})

        return await call_next(request)
