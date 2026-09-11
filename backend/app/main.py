from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

import app.api.afnor.v1  # noqa: F401  (s'enregistre auprès du registre de versions)
import app.api.afnor.v2  # noqa: F401  (idem — cf. app/afnor/versioning/registry.py)
from app.afnor.versioning.registry import get_router
from app.api.ihm.auth import router as auth_router
from app.api.ihm.companies import router as companies_router
from app.api.ihm.invoice_routings import router as invoice_routings_router
from app.api.ihm.invoices import router as invoices_router
from app.api.ihm.lifecycle import router as lifecycle_router
from app.api.ihm.partners import router as partners_router
from app.api.ihm.routing_rules import router as routing_rules_router
from app.api.ihm.settings import router as settings_router
from app.api.ihm.target_applications import router as target_applications_router
from app.api.ihm.users import router as users_router
from app.auth.ip_allowlist import IPAllowlistMiddleware
from app.auth.session import require_current_user
from app.config import settings
from app.scheduler.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def _lifespan(app: FastAPI):
    if settings.scheduler_enabled:
        start_scheduler()
    yield
    stop_scheduler()


def create_app() -> FastAPI:
    app = FastAPI(title="Routeur de factures électroniques", lifespan=_lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
        # Requis pour que le cookie de session IHM (§ NF3, lot 7) soit transmis par le
        # navigateur : allow_origins ne peut alors pas être "*" (déjà le cas ici).
        allow_credentials=True,
    )
    if settings.ip_allowlist_enabled:
        app.add_middleware(IPAllowlistMiddleware)
    # Requis par Authlib (authlib.integrations.starlette_client) pour stocker le
    # state/nonce OIDC côté serveur pendant le flux Entra ID (§ NF3, app/auth/oidc.py).
    app.add_middleware(SessionMiddleware, secret_key=settings.jwt_secret)

    # Authentification requise sur toutes les routes IHM (NF3) dès que
    # `settings.oidc_mode != "disabled"` — `require_current_user` ne bloque jamais
    # rien tant que ce n'est pas le cas (comportement des lots 0-6 inchangé par
    # défaut). `/auth/*` reste hors de cette dépendance : il faut pouvoir s'y
    # connecter avant d'avoir une session.
    ihm_auth = [Depends(require_current_user)]

    app.include_router(auth_router, prefix="/api/ihm/auth", tags=["auth"])
    app.include_router(
        companies_router, prefix="/api/ihm/companies", tags=["companies"], dependencies=ihm_auth
    )
    app.include_router(
        partners_router, prefix="/api/ihm/partners", tags=["partners"], dependencies=ihm_auth
    )
    app.include_router(
        target_applications_router,
        prefix="/api/ihm/target-applications",
        tags=["target-applications"],
        dependencies=ihm_auth,
    )
    app.include_router(
        routing_rules_router,
        prefix="/api/ihm/routing-rules",
        tags=["routing-rules"],
        dependencies=ihm_auth,
    )
    app.include_router(
        invoices_router, prefix="/api/ihm/invoices", tags=["invoices"], dependencies=ihm_auth
    )
    app.include_router(
        lifecycle_router,
        prefix="/api/ihm/lifecycle-catalog",
        tags=["lifecycle"],
        dependencies=ihm_auth,
    )
    # Registre de versions AFNOR (§ 4.8) : chaque version activée dans
    # `settings.afnor_api_enabled_versions` est montée sous son propre préfixe, sans
    # qu'ajouter/retirer une version ne touche aux autres routers ici.
    for version in settings.afnor_api_enabled_versions.split(","):
        version = version.strip()
        version_router = get_router(version)
        if version_router is not None:
            app.include_router(
                version_router, prefix=f"/api/afnor/{version}", tags=[f"afnor-{version}"]
            )
    app.include_router(
        invoice_routings_router,
        prefix="/api/ihm/invoice-routings",
        tags=["invoice-routings"],
        dependencies=ihm_auth,
    )
    app.include_router(
        settings_router, prefix="/api/ihm/settings", tags=["settings"], dependencies=ihm_auth
    )
    app.include_router(users_router, prefix="/api/ihm/users", tags=["users"])

    return app


app = create_app()
