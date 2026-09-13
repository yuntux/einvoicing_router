"""AfnorClientAdapter — orchestration DB pour le client AFNOR réel (spec.md § 7.3,
lot 6) : résolution des identifiants par entreprise (§ 4.10), cache de session/jeton
pyfrctc, et traçabilité (`FlowTrace`, NF1) de chaque appel sortant vers SuperPDP.

`PyfrctcCertifiedPlatformClient` (module frère) reste, lui, indépendant de la base de données —
c'est cet adaptateur qui fait le pont, comme le prévoit le diagramme de composants
(§ 7.3 : `InvoiceIngestionService --> AfnorClientAdapter`, `AfnorServerController -->
AfnorClientAdapter : proxy émission vers SuperPDP`)."""

import contextlib
import json
from typing import Callable

from fastapi import HTTPException
from pyfrctc import pyfrctc as core
from sqlalchemy.orm import Session

from app.afnor.client.pyfrctc_client import PyfrctcCertifiedPlatformClient, _json_safe
from app.config import settings
from app.models.referential import Company
from app.services import audit_trace_service, certified_platform_credentials_service


@contextlib.contextmanager
def _capture_last_exchange_headers(session):
    """pyfrctc n'expose que le JSON parsé de la réponse SuperPDP, jamais l'objet HTTP
    brut — on capture les en-têtes de la dernière requête/réponse de la session via un
    hook `requests` le temps de l'appel, pour les faire remonter au `FlowTrace` (NF1)
    sans avoir à modifier pyfrctc."""
    captured: dict[str, dict[str, str] | None] = {"request": None, "response": None}

    def _on_response(response, *args, **kwargs):
        captured["request"] = dict(response.request.headers)
        captured["response"] = dict(response.headers)

    hooks = session.hooks.setdefault("response", [])
    hooks.append(_on_response)
    try:
        yield captured
    finally:
        hooks.remove(_on_response)


class AfnorClientAdapter:
    """Reconstruit une session `pyfrctc` à chaque appel plutôt que de la garder en
    cache mémoire pour la durée du process : `core.get_session` lit déjà le jeton
    depuis `Company.certified_platform_token_cache` (persisté en base, survit à un
    redémarrage) et ne fait un vrai aller-retour réseau que s'il est expiré — pas de
    coût réel à l'appeler à chaque fois. Un cache en mémoire d'un objet
    `OAuth2Session` déjà construit, lui, retient un jeton figé au moment de sa
    création : passé son expiration (~1h), toute requête ultérieure déclenche le
    rafraîchissement automatique de `requests_oauthlib`, qui n'a — pour le grant
    `client_credentials` — jamais reçu `client_id`/`client_secret` (`pyfrctc` gère
    l'expiration lui-même en amont, cf. commentaire dans `_get_session_client_
    credentials` : "we can't use OAuth2Session() to automate the retreival of a new
    access_token"), d'où un rafraîchissement sans identifiants envoyé à SuperPDP
    ("Client credentials missing or malformed") — régression constatée en presque
    une heure d'inactivité du process sur une même entreprise."""

    def _get_or_build_session(self, db: Session, company: Company):
        application = certified_platform_credentials_service.get_credentials_application(
            db, company_id=company.id
        )
        if application is None:
            raise ValueError(
                f"Aucun identifiant SuperPDP configuré pour l'entreprise {company.id} "
                "(§ 4.10) — à saisir depuis l'IHM avant d'activer le client réel."
            )
        client_secret = certified_platform_credentials_service.get_decrypted_secret(application)
        platform = application.certified_platform or settings.certified_platform

        def get_token_method(grant_type: str) -> dict:
            cache = json.loads(application.certified_platform_token_cache) if application.certified_platform_token_cache else {}
            return {"access_token": cache.get("access_token"), "expires_at": cache.get("expires_at")}

        def update_token_method(token: dict) -> None:
            application.certified_platform_token_cache = json.dumps(token)
            db.commit()

        session = core.get_session(
            platform=platform,
            auth_method="client_credentials",
            company_ident4log=company.siren,
            get_token_method=get_token_method,
            update_token_method=update_token_method,
            client_id=application.certified_platform_client_id,
            client_secret=client_secret,
        )
        return session

    def get_client_for_company(self, db: Session, company: Company) -> PyfrctcCertifiedPlatformClient:
        return PyfrctcCertifiedPlatformClient(self._get_or_build_session(db, company))

    def _send_flow_and_trace(
        self,
        db: Session,
        session,
        *,
        request_payload: dict,
        afnor_api_version: str,
        correlation_id: str | None,
        send: Callable[[], dict],
    ) -> dict:
        """Appelle `send` (un envoi pyfrctc vers SuperPDP), trace l'échange
        (`router_to_superpdp`, NF1) qu'il réussisse ou échoue, et propage l'exception
        telle quelle en cas d'échec (traduite en 502 par l'appelant, cf.
        `afnor_server_controller.call_certified_platform`) — factorise `send_invoice`/`send_cdar`,
        identiques hormis l'appel pyfrctc et le contenu de `request_payload`."""
        with _capture_last_exchange_headers(session) as headers:
            try:
                result = send()
            except Exception as exc:
                audit_trace_service.record_flow_trace(
                    db,
                    direction="router_to_superpdp",
                    afnor_api_version=afnor_api_version,
                    request=request_payload,
                    response={"error": str(exc)},
                    http_status=502,
                    correlation_id=correlation_id,
                    request_headers=headers["request"],
                    response_headers=headers["response"],
                )
                raise
            audit_trace_service.record_flow_trace(
                db,
                direction="router_to_superpdp",
                afnor_api_version=afnor_api_version,
                request=request_payload,
                # `_parse_flow_dict` (appelé par `send_flow_parsed`) enrichit `result` de
                # `datetime` dérivés en plus des chaînes ISO d'origine — non sérialisables
                # tels quels dans la colonne JSON `FlowTrace.response` (§ NF1).
                response=_json_safe({k: v for k, v in result.items() if not isinstance(v, bytes)}),
                http_status=200,
                correlation_id=correlation_id,
                request_headers=headers["request"],
                response_headers=headers["response"],
            )
        return result

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
        stockée en base (les factures émises ne sont pas indexées, § 4.1).

        `core.send_flow` (brut), pas `_parsed` : ce dernier ajoute des clés
        pythonic supplémentaires (`submitted_at`/`updated_at`/`state`...) absentes
        du schéma `FullFlowInfo` du contrat AFNOR — additives seulement (jamais de
        clé du contrat perdue ni renommée, contrairement au bug corrigé sur
        `lookup_directory_siren`/`siret`), mais un consommateur (Odoo) doit recevoir
        exactement la réponse `POST /afnor-flow/flows` telle que SuperPDP l'a émise."""
        session = self._get_or_build_session(db, company)
        return self._send_flow_and_trace(
            db,
            session,
            request_payload={
                "filename": filename,
                "flow_syntax": flow_syntax,
                "processing_rule": processing_rule,
            },
            afnor_api_version=afnor_api_version,
            correlation_id=correlation_id,
            send=lambda: core.send_flow(session, file_bin, filename, flow_syntax, processing_rule),
        )

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
        messages émis par Odoo. `processing_rule="NotApplicable"` : un CDAR n'est pas
        une facture (pas de règle B2B/B2G à appliquer) — `pyfrctc.send_flow` valide
        cet argument côté client contre une liste fermée avant tout appel réseau
        (`"LifeCycle"` n'en fait pas partie et faisait échouer systématiquement
        l'envoi, indépendamment de SuperPDP)."""
        session = self._get_or_build_session(db, company)
        return self._send_flow_and_trace(
            db,
            session,
            request_payload={"filename": filename},
            afnor_api_version=afnor_api_version,
            correlation_id=correlation_id,
            send=lambda: core.send_flow(session, cdar_bytes, filename, "CDAR", "NotApplicable"),
        )

    def get_flow_document(
        self,
        db: Session,
        *,
        company: Company,
        flow_id: str,
        doc_type: str,
        afnor_api_version: str = "v1",
        correlation_id: str | None = None,
    ) -> bytes:
        """Relit à la volée un document déjà connu de SuperPDP pour un flux existant
        (`docType=Converted`/`ReadableView`, § 4.4) — contrairement à `send_invoice`/
        `send_cdar`, aucune émission n'a lieu : on ne fait que rappeler SuperPDP au
        moment où Odoo le demande. L'appelant (`GET /flows/{flowId}` dans
        `_common.py`) a déjà vérifié que le flux est routé vers ce consommateur (NF2,
        même filtre `InvoiceRouting` que `POST /flows/search`) avant d'invoquer cette
        méthode — elle ne refait aucun contrôle d'autorisation.

        Le contenu binaire renvoyé n'est jamais consigné dans `FlowTrace` (NF1 ne
        trace que sa taille), à l'image de ce que fait `_send_flow_and_trace` pour les
        réponses de `send_invoice`/`send_cdar`."""
        session = self._get_or_build_session(db, company)
        request_payload = {"flow_id": flow_id, "doc_type": doc_type}
        with _capture_last_exchange_headers(session) as headers:
            try:
                file_bin = core.get_flow(session, flow_id, doc_type=doc_type)
            except Exception as exc:
                audit_trace_service.record_flow_trace(
                    db,
                    direction="router_to_superpdp",
                    afnor_api_version=afnor_api_version,
                    request=request_payload,
                    response={"error": str(exc)},
                    http_status=502,
                    correlation_id=correlation_id,
                    request_headers=headers["request"],
                    response_headers=headers["response"],
                )
                raise
            audit_trace_service.record_flow_trace(
                db,
                direction="router_to_superpdp",
                afnor_api_version=afnor_api_version,
                request=request_payload,
                response={"size": len(file_bin)},
                http_status=200,
                correlation_id=correlation_id,
                request_headers=headers["request"],
                response_headers=headers["response"],
            )
        return file_bin

    def _lookup_directory_and_trace(
        self,
        db: Session,
        session,
        *,
        request_payload: dict,
        afnor_api_version: str,
        lookup: Callable[[], dict | bool],
    ) -> dict | bool:
        """Appelle `lookup` (une consultation d'annuaire pyfrctc, § brut — pas
        `_parsed`, cf. `lookup_directory_siren`/`lookup_directory_siret`) et trace
        l'échange (`router_to_superpdp`, NF1) — factorise les deux, identiques hormis
        l'appel pyfrctc et le contenu de `request_payload` (à l'image de
        `_send_flow_and_trace` pour `send_invoice`/`send_cdar`). `lookup` renvoie
        `False` (pas une exception) quand SuperPDP répond 404/NOT_FOUND — reflété ici
        par `http_status=404` dans la trace, à charge de l'appelant (`_common.py`) de
        traduire ça en une vraie 404 HTTP plutôt que de renvoyer `false` en JSON."""
        with _capture_last_exchange_headers(session) as headers:
            result = lookup()
            audit_trace_service.record_flow_trace(
                db,
                direction="router_to_superpdp",
                afnor_api_version=afnor_api_version,
                request=request_payload,
                response=result if result is not False else {"found": False},
                http_status=200 if result is not False else 404,
                request_headers=headers["request"],
                response_headers=headers["response"],
            )
        return result

    def lookup_directory_siren(
        self, db: Session, *, company: Company, siren: str, afnor_api_version: str = "v1"
    ) -> dict | bool:
        """Résultat BRUT de SuperPDP (`pyfrctc.get_directory_siren`, pas `_parsed`) :
        ce proxy doit relayer exactement la forme du contrat AFNOR (clés `siren`/
        `businessName`/`entityType`/`administrativeStatus`...) — un consommateur
        (Odoo `l10n_fr_einvoicing`) appelle lui-même `get_directory_siren_parsed`
        *sur la réponse de ce endpoint*, laquelle réinterprète ces clés brutes ; lui
        renvoyer une forme déjà "parsée" (`name`/`closed`/`entity_type`) fait
        disparaître silencieusement `entityType`, que `_parsed` retombe alors sur
        "no" — d'où un partenaire pourtant bien réel signalé comme absent de
        l'annuaire côté Odoo, malgré une entreprise trouvée côté SuperPDP."""
        session = self._get_or_build_session(db, company)
        return self._lookup_directory_and_trace(
            db,
            session,
            request_payload={"siren": siren},
            afnor_api_version=afnor_api_version,
            lookup=lambda: core.get_directory_siren(session, siren),
        )

    def lookup_directory_siret(
        self, db: Session, *, company: Company, siret: str, afnor_api_version: str = "v1"
    ) -> dict | bool:
        """Symétrique de `lookup_directory_siren` pour un SIRET — même raison de
        rester sur le résultat brut (`get_directory_siret`, pas `_parsed`)."""
        session = self._get_or_build_session(db, company)
        return self._lookup_directory_and_trace(
            db,
            session,
            request_payload={"siret": siret},
            afnor_api_version=afnor_api_version,
            lookup=lambda: core.get_directory_siret(session, siret),
        )

    def raw_passthrough(
        self,
        db: Session,
        *,
        company: Company,
        method: str,
        service: str,
        path: str,
        json_body: dict | None = None,
        params: dict | None = None,
        afnor_api_version: str = "v1",
        correlation_id: str | None = None,
    ) -> tuple[int, dict]:
        """Proxy HTTP générique et transparent vers un endpoint AFNOR
        (`service="afnor-flow"` ou `"afnor-directory"`) que ni pyfrctc ni ce module
        n'interprètent (§ 4.4) — le routeur ne fait que transmettre tel quel, sans
        filtrage ni stockage, contrairement à `POST /flows/search`/`GET /flows/{id}`
        (restreints aux factures routées vers le consommateur, NF2).

        Retourne `(status_code, body)` en préservant le statut HTTP réel renvoyé par
        SuperPDP (jamais aplati sur un 502 générique comme `call_certified_platform`, sauf
        échec réseau où aucun statut réel n'existe)."""
        session = self._get_or_build_session(db, company)
        platform = core._get_plateform(session)
        base_url = core.PLATFORMS[platform]["afnor_base_url"]
        url = f"{base_url}/{service}/{core.AFNOR_API_VERSION}/{path}"
        request_payload = {"method": method, "url": url, "body": json_body, "params": params}

        with _capture_last_exchange_headers(session) as headers:
            try:
                response = session.request(
                    method, url, json=json_body, params=params, timeout=core.TIMEOUT
                )
            except Exception as exc:
                audit_trace_service.record_flow_trace(
                    db,
                    direction="router_to_superpdp",
                    afnor_api_version=afnor_api_version,
                    request=request_payload,
                    response={"error": str(exc)},
                    http_status=502,
                    correlation_id=correlation_id,
                    request_headers=headers["request"],
                    response_headers=headers["response"],
                )
                raise HTTPException(
                    status_code=502, detail=f"SuperPDP unreachable: {exc}"
                ) from exc

            try:
                body = response.json() if response.content else {}
            except ValueError:
                body = {"raw": response.text}

            audit_trace_service.record_flow_trace(
                db,
                direction="router_to_superpdp",
                afnor_api_version=afnor_api_version,
                request=request_payload,
                response=body,
                http_status=response.status_code,
                correlation_id=correlation_id,
                request_headers=headers["request"],
                response_headers=headers["response"],
            )
        return response.status_code, body


# Instance partagée par le process (cache de session), à l'image du pattern
# `SessionLocal` de `app/db/session.py`.
afnor_client_adapter = AfnorClientAdapter()
