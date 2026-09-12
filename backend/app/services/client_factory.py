"""Sélection du client AFNOR côté SuperPDP pour une entreprise (spec.md § 4.1/§ 4.8,
lot 6) : "fake" (fixtures, défaut dev/tests) ou "pyfrctc" (client réel), piloté par
`settings.certified_platform_client_mode` — le point d'extension prévu au lot 2."""

from sqlalchemy.orm import Session

from app.afnor.client.adapter import afnor_client_adapter
from app.afnor.client.base import CertifiedPlatformClientProtocol
from app.afnor.client.fake import FakeCertifiedPlatformClient
from app.config import settings
from app.models.referential import Company


def resolve_client_for_company(db: Session, company: Company) -> CertifiedPlatformClientProtocol:
    if settings.certified_platform_client_mode == "pyfrctc":
        return afnor_client_adapter.get_client_for_company(db, company)
    return FakeCertifiedPlatformClient()
