from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.ihm.companies import router as companies_router


def create_app() -> FastAPI:
    app = FastAPI(title="Routeur de factures électroniques")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(companies_router, prefix="/api/ihm/companies", tags=["companies"])
    return app


app = create_app()
