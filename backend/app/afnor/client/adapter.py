"""AfnorClientAdapter — orchestration DB pour le client AFNOR réel (spec.md § 7.3,
lot 6) : résolution des identifiants par entreprise (§ 4.10), cache de session/jeton
pyfrctc, et traçabilité (`FlowTrace`, NF1) de chaque appel sortant vers SuperPDP.

`PyfrctcSuperPDPClient` (module frère) reste, lui, indépendant de la base de données —
c'est cet adaptateur qui fait le pont, comme le prévoit le diagramme de composants
(§ 7.3 : `InvoiceIngestionService --> AfnorClientAdapter`, `AfnorServerController -->
AfnorClientAdapter : proxy émission vers SuperPDP`)."""

import json

from pyfrctc import pyfrctc as core
from sqlalchemy.orm import Session

from app.afnor.client.pyfrctc_client import PyfrctcSuperPDPClient
from app.config import settings
from app.models.referential import Company
from app.services import audit_trace_service, superpdp_credentials_service


class AfnorClientAdapter:
    """Une instance vit pour la durée du process (cache de session en mémoire, par
    entreprise) — le cache de jeton lui-même est persisté en base
    (`OAuthApplication.token_cache`) pour survivre à un redémarrage."""

    def __init__(self) -> None:
        self._sessions: dict[int, object] = {}

    def _get_or_build_session(self, db: Session, company: Company):
        if company.id in self._sessions:
            return self._sessions[company.id]

        application = superpdp_credentials_service.get_credentials_application(
            db, company_id=company.id
        )
        if application is None:
            raise ValueError(
                f"Aucun identifiant SuperPDP configuré pour l'entreprise {company.id} "
                "(§ 4.10) — à saisir depuis l'IHM avant d'activer le client réel."
            )
        client_secret = superpdp_credentials_service.get_decrypted_secret(application)

        def get_token_method(grant_type: str) -> dict:
            cache = json.loads(application.token_cache) if application.token_cache else {}
            return {"access_token": cache.get("access_token"), "expires_at": cache.get("expires_at")}

        def update_token_method(token: dict) -> None:
            application.token_cache = json.dumps(token)
            db.commit()

        session = core.get_session(
            platform=settings.superpdp_platform,
            auth_method="client_credentials",
            company_ident4log=company.siren,
            get_token_method=get_token_method,
            update_token_method=update_token_method,
            client_id=application.client_id,
            client_secret=client_secret,
        )
        self._sessions[company.id] = session
        return session

    def get_client_for_company(self, db: Session, company: Company) -> PyfrctcSuperPDPClient:
        return PyfrctcSuperPDPClient(self._get_or_build_session(db, company))

    def send_invoice(
        self,
        db: Session,
        *,
        company: Company,
        file_bin: bytes,
        filename: str,
        flow_syntax: str,
        processing_rule: str,
        afnor_api_version: str = "v1",
        correlation_id: str | None = None,
    ) -> dict:
        """Émission d'une facture (proxy Odoo -> SuperPDP, § 4.4) — tracée, jamais
        stockée en base (les factures émises ne sont pas indexées, § 4.1)."""
        session = self._get_or_build_session(db, company)
        request_payload = {
            "filename": filename,
            "flow_syntax": flow_syntax,
            "processing_rule": processing_rule,
        }
        try:
            result = core.send_flow_parsed(session, file_bin, filename, flow_syntax, processing_rule)
        except Exception as exc:
            audit_trace_service.record_flow_trace(
                db,
                direction="router_to_superpdp",
                afnor_api_version=afnor_api_version,
                request=request_payload,
                response={"error": str(exc)},
                http_status=502,
                correlation_id=correlation_id,
            )
            raise
        audit_trace_service.record_flow_trace(
            db,
            direction="router_to_superpdp",
            afnor_api_version=afnor_api_version,
            request=request_payload,
            response={k: v for k, v in result.items() if not isinstance(v, bytes)},
            http_status=200,
            correlation_id=correlation_id,
        )
        return result

    def send_cdar(
        self,
        db: Session,
        *,
        company: Company,
        cdar_bytes: bytes,
        filename: str = "cdar.xml",
        afnor_api_version: str = "v1",
        correlation_id: str | None = None,
    ) -> dict:
        """Transmission d'un message de cycle de vie CDAR (§ 4.2/§ 4.4) — utilisée à la
        fois pour les événements saisis manuellement (lot 3+6) et pour le proxy des
        messages émis par Odoo."""
        session = self._get_or_build_session(db, company)
        request_payload = {"filename": filename}
        try:
            result = core.send_flow_parsed(session, cdar_bytes, filename, "CDAR", "LifeCycle")
        except Exception as exc:
            audit_trace_service.record_flow_trace(
                db,
                direction="router_to_superpdp",
                afnor_api_version=afnor_api_version,
                request=request_payload,
                response={"error": str(exc)},
                http_status=502,
                correlation_id=correlation_id,
            )
            raise
        audit_trace_service.record_flow_trace(
            db,
            direction="router_to_superpdp",
            afnor_api_version=afnor_api_version,
            request=request_payload,
            response={k: v for k, v in result.items() if not isinstance(v, bytes)},
            http_status=200,
            correlation_id=correlation_id,
        )
        return result

    def lookup_directory_siren(
        self, db: Session, *, company: Company, siren: str, afnor_api_version: str = "v1"
    ) -> dict:
        session = self._get_or_build_session(db, company)
        result = core.get_directory_siren_parsed(session, siren)
        audit_trace_service.record_flow_trace(
            db,
            direction="router_to_superpdp",
            afnor_api_version=afnor_api_version,
            request={"siren": siren},
            response=result,
            http_status=200,
        )
        return result


# Instance partagée par le process (cache de session), à l'image du pattern
# `SessionLocal` de `app/db/session.py`.
afnor_client_adapter = AfnorClientAdapter()
