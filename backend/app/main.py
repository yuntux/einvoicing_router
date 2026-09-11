from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.afnor.v1 import router as afnor_v1_router
from app.api.ihm.companies import router as companies_router
from app.api.ihm.invoices import router as invoices_router
from app.api.ihm.lifecycle import router as lifecycle_router
from app.api.ihm.partners import router as partners_router
from app.api.ihm.routing_rules import router as routing_rules_router
from app.api.ihm.target_applications import router as target_applications_router


def create_app() -> FastAPI:
    app = FastAPI(title="Routeur de factures électroniques")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(companies_router, prefix="/api/ihm/companies", tags=["companies"])
    app.include_router(partners_router, prefix="/api/ihm/partners", tags=["partners"])
    app.include_router(
        target_applications_router,
        prefix="/api/ihm/target-applications",
        tags=["target-applications"],
    )
    app.include_router(
        routing_rules_router, prefix="/api/ihm/routing-rules", tags=["routing-rules"]
    )
    app.include_router(invoices_router, prefix="/api/ihm/invoices", tags=["invoices"])
    app.include_router(
        lifecycle_router, prefix="/api/ihm/lifecycle-catalog", tags=["lifecycle"]
    )
    app.include_router(afnor_v1_router, prefix="/api/afnor/v1", tags=["afnor-v1"])
    return app


app = create_app()
