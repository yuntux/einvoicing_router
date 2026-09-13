"""Routes communes à toutes les versions de l'API AFNOR exposée à Odoo (§ 4.4/§ 4.8).

Le routeur **émule un PDP** vis-à-vis d'Odoo (§ 4.4) : ces routes implémentent, avec
une correspondance précise chemin/verbe/paramètres, les deux contrats officiels
(`backend/docs/afnor-contracts/`) — "AFNOR Flow Service" (4 opérations, sous
`/afnor-flow`, comme sur le vrai serveur SuperPDP `.../afnor-flow/v1/...`) et
"AFNOR Directory Service" (9 opérations, sous `/afnor-directory`).

Principe de conception (le seul filtrage/interprétation qui a du sens pour un
routeur qui ne gère QUE les factures reçues, § 4.3) :
- `POST /afnor-flow/flows/search` et `GET /afnor-flow/flows/{flowId}` : **parsés** —
  restreints aux factures effectivement routées vers ce consommateur (NF2).
- `POST /afnor-flow/flows` (émission) : le `flowSyntax` de `flowInfo` distingue une
  facture (proxy transparent vers SuperPDP, jamais stockée, § 4.1) d'un message de
  cycle de vie CDAR (idem, avec la limitation documentée sur `create_flow`).
- **Tout le reste — healthchecks, annuaire (siren/siret/routing-code/directory-line)
  — est un pur passe-plat vers SuperPDP** (`AfnorClientAdapter.raw_passthrough`),
  statut HTTP et corps renvoyés tels quels, sans réinterprétation ni filtrage NF2 :
  ces ressources ne concernent jamais les factures reçues par le routeur.

Limites connues (documentées, pas silencieuses) :
- `GET /afnor-directory/{siren,siret}/code-insee:...` passent par les wrappers
  `pyfrctc` existants (validation incluse) plutôt que par `raw_passthrough` : les
  paramètres `fields`/`include` du contrat ne sont pas relayés (cf. docstrings) ;
- **Webhooks (`/afnor-flow/flows/webhooks`)** : non implémentés — le fichier
  `afnor-flow-openapi-v1.3.0.json` fourni déclare les schémas (`Webhook`,
  `WebhookParams`...) mais les chemins `/v1/webhooks` et `/v1/webhooks/{webhookUid}`
  sont des objets vides (`{}`, aucune opération HTTP définie) : le contrat ne fixe
  donc ni verbes ni requêtes/réponses pour cette ressource dans cette version du
  fichier. Inventer une forme REST plausible (POST/GET/DELETE à partir des seuls noms
  de schémas) serait deviner un contrat non fourni — la notification webhook déjà
  existante côté routeur (§ 4.4, format propre au routeur) reste donc en l'état tant
  qu'une version plus complète du contrat n'est pas disponible."""

import json
import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.afnor.client.adapter import afnor_client_adapter
from app.afnor.server import afnor_server_controller
from app.afnor.server.afnor_server_controller import call_certified_platform
from app.auth.oauth import get_current_target_application
from app.config import settings
from app.db.session import get_db
from app.models.referential import Company, TargetApplication
from app.schemas.afnor_flow import FlowInfoIn, SearchFlowContentOut, SearchFlowParamsIn
from app.services import audit_trace_service

_UPLOAD_CHUNK_SIZE = 64 * 1024

# Chemins réutilisés à la fois par le décorateur `@router...` et par le libellé de
# trace (`endpoint=`, § NF1) des quelques endpoints qui n'utilisent pas `passthrough`
# (lequel dérive déjà son libellé de `method`/`service`/`path`, cf. plus bas) — source
# unique plutôt que de recopier le même chemin à la main aux deux endroits. Absents
# ici : `GET /afnor-flow/flows/{flow_id}` (le libellé de contrat AFNOR utilise
# `{flowId}`, différent du nom de paramètre Python — pas mécaniquement dérivable sans
# changer le texte déjà stocké dans les `FlowTrace` existants).
_FLOWS_PATH = "/afnor-flow/flows"
_FLOWS_SEARCH_PATH = "/afnor-flow/flows/search"
_LOOKUP_SIREN_PATH = "/afnor-directory/siren/code-insee:{siren}"
_LOOKUP_SIRET_PATH = "/afnor-directory/siret/code-insee:{siret}"


def company_for(db: Session, oauth_app: TargetApplication) -> Company:
    company = db.get(Company, oauth_app.company_id)
    if company is None:
        raise HTTPException(status_code=500, detail="Application OAuth sans entreprise associée")
    return company


async def read_upload_capped(file: UploadFile, *, max_bytes: int | None = None) -> bytes:
    """Lit `file` par blocs jusqu'à `max_bytes` (par défaut `settings.
    max_upload_size_bytes`) et lève 413 dès que la limite est dépassée, sans jamais
    charger en mémoire plus que ce plafond — contrairement à `await file.read()`, qui
    tamponnerait la totalité d'un envoi disproportionné avant qu'on puisse seulement
    en constater la taille (§ 4.4, `POST /afnor-flow/flows`)."""
    limit = max_bytes if max_bytes is not None else settings.max_upload_size_bytes
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_UPLOAD_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise HTTPException(status_code=413, detail="File too large")
        chunks.append(chunk)
    return b"".join(chunks)


def register_common_routes(router: APIRouter, afnor_api_version: str) -> None:
    # Le vrai contrat AFNOR place le numéro de version APRÈS le nom du service
    # (`.../afnor-flow/v1/...`, `.../afnor-directory/v1/...` — cf. `pyfrctc.PLATFORMS`
    # et `send_flow`/`get_directory_siren`, qui construisent l'URL ainsi), jamais
    # comme préfixe global avant les deux services. `app.main` monte ce router sous
    # `/api/afnor` (sans version), donc les chemins ci-dessous doivent l'inclure
    # eux-mêmes à la bonne position pour qu'un client `pyfrctc` inchangé (ou tout
    # client suivant le même contrat, ex. un consommateur Odoo `l10n_fr_einvoicing`)
    # pointé sur `afnor_base_url=".../api/afnor"` retrouve exactement les mêmes URLs
    # que contre le vrai SuperPDP — un ancien préfixe `/api/afnor/{version}` plaçait
    # la version AVANT le nom du service, incompatible avec ce que `pyfrctc` reconstruit
    # lui-même (§ incident : 404 sur `.../afnor-directory/v1/siren/...` avec la version
    # dupliquée/mal placée).
    flows_path = f"/afnor-flow/{afnor_api_version}/flows"
    flows_search_path = f"/afnor-flow/{afnor_api_version}/flows/search"
    flows_healthcheck_path = f"/afnor-flow/{afnor_api_version}/healthcheck"
    lookup_siren_path = f"/afnor-directory/{afnor_api_version}/siren/code-insee:{{siren}}"
    lookup_siret_path = f"/afnor-directory/{afnor_api_version}/siret/code-insee:{{siret}}"

    def passthrough(
        request: Request,
        oauth_app: TargetApplication,
        db: Session,
        *,
        method: str,
        service: str,
        path: str,
        endpoint_label: str | None = None,
        json_body: dict | None = None,
        params: dict | None = None,
        extra_trace_fields: dict | None = None,
    ) -> Response:
        """Passe-plat générique (cf. docstring du module) : le statut et le corps
        renvoyés par SuperPDP sont retransmis à l'identique, jamais réinterprétés.

        `endpoint_label` ne doit être fourni explicitement que lorsque `path` contient
        des valeurs réellement interpolées (identifiants réels, pour l'appel HTTP) —
        le libellé de trace doit alors rester au gabarit du contrat (`{routing-
        identifier}`...), pas à la valeur. Sans ça, il est dérivé de `method`/
        `service`/`path` (identiques dans ce cas), évitant de le répéter à la main."""
        endpoint_label = endpoint_label or f"{method} /{service}/{path}"
        company = company_for(db, oauth_app)
        status_code, body = afnor_client_adapter.raw_passthrough(
            db,
            company=company,
            method=method,
            service=service,
            path=path,
            json_body=json_body,
            params=params,
            afnor_api_version=afnor_api_version,
        )
        audit_trace_service.record_odoo_flow_trace(
            db,
            request,
            afnor_api_version=afnor_api_version,
            endpoint=endpoint_label,
            client_id=oauth_app.client_id,
            response=body,
            http_status=status_code,
            **(extra_trace_fields or {}),
        )
        return Response(
            content=json.dumps(body), media_type="application/json", status_code=status_code
        )

    # ---------------------------------------------------------------- Flow Service

    @router.post(flows_path, status_code=202)
    async def create_flow(
        request: Request,
        file: UploadFile,
        flowInfo: str = Form(...),
        oauth_app: TargetApplication = Depends(get_current_target_application),
        db: Session = Depends(get_db),
    ):
        """Soumission d'un flux (§ 4.4) : proxy transparent vers SuperPDP, jamais
        stocké côté routeur (§ 4.1, seules les factures *reçues* sont indexées) —
        seul le `FlowTrace` de l'échange est conservé. Le `flowSyntax` déclaré dans
        `flowInfo` détermine s'il s'agit d'une facture (`send_invoice`) ou d'un
        message de cycle de vie CDAR (`send_cdar`, `flowSyntax="CDAR"`).

        Limitation connue pour la branche CDAR : contrairement aux messages saisis
        manuellement dans l'IHM du routeur (§ 4.2, sens achat uniquement), ce proxy ne
        mémorise pas le message comme `LifecycleEvent` — il concerne potentiellement
        des factures de vente qu'`Invoice` ne modélise pas (§ 6.1, factures reçues
        uniquement), cf. note dans `lifecycle_service.py`."""
        try:
            flow_info = FlowInfoIn.model_validate_json(flowInfo)
        except (ValidationError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"Invalid flowInfo: {exc}") from exc

        company = company_for(db, oauth_app)
        correlation_id = str(uuid.uuid4())
        file_bin = await read_upload_capped(file)
        filename = file.filename or flow_info.name

        audit_trace_service.record_odoo_flow_trace(
            db,
            request,
            afnor_api_version=afnor_api_version,
            endpoint=f"POST {_FLOWS_PATH}",
            filename=filename,
            flow_syntax=flow_info.flowSyntax,
            processing_rule=flow_info.processingRule,
            client_id=oauth_app.client_id,
            response={"status": "forwarding"},
            http_status=202,
            correlation_id=correlation_id,
        )

        if flow_info.flowSyntax == "CDAR":
            return call_certified_platform(
                lambda: afnor_client_adapter.send_cdar(
                    db,
                    company=company,
                    cdar_bytes=file_bin,
                    filename=filename,
                    correlation_id=correlation_id,
                )
            )
        return call_certified_platform(
            lambda: afnor_client_adapter.send_invoice(
                db,
                company=company,
                file_bin=file_bin,
                filename=filename,
                flow_syntax=flow_info.flowSyntax,
                processing_rule=flow_info.processingRule or "B2B",
                correlation_id=correlation_id,
            )
        )

    @router.post(
        flows_search_path,
        response_model=SearchFlowContentOut,
        response_model_exclude_none=True,
    )
    def search_flows(
        params: SearchFlowParamsIn,
        request: Request,
        oauth_app: TargetApplication = Depends(get_current_target_application),
        db: Session = Depends(get_db),
    ):
        """Recherche de flux (§ 4.4) : ne retourne que les factures flaggées comme
        destinées à ce consommateur (NF2) — seul `flowType=SupplierInvoice`/
        `flowDirection=In` est réellement émulé à ce jour (factures reçues par le
        routeur et routées vers Odoo) ; les autres critères de `where` sont acceptés
        pour rester conformes au contrat mais n'ont pas d'effet filtrant tant qu'aucun
        autre type de flux n'est exposé. Pas de pagination réelle (`nextCursor` toujours
        `null`) : tous les résultats sont retournés en une page."""
        invoices = afnor_server_controller.list_invoices_for_consumer(db, target_application=oauth_app)
        results = [afnor_server_controller.flow_from_invoice(invoice) for invoice in invoices]

        audit_trace_service.record_odoo_flow_trace(
            db,
            request,
            afnor_api_version=afnor_api_version,
            endpoint=f"POST {_FLOWS_SEARCH_PATH}",
            client_id=oauth_app.client_id,
            response={"count": len(results)},
            http_status=200,
        )
        return SearchFlowContentOut(results=results, filters=params.where, limit=params.limit)

    @router.get(f"/afnor-flow/{afnor_api_version}/flows/{{flow_id}}")
    def get_flow(
        flow_id: str,
        request: Request,
        docType: str = "Metadata",
        oauth_app: TargetApplication = Depends(get_current_target_application),
        db: Session = Depends(get_db),
    ):
        """Téléchargement d'un flux par identifiant (§ 4.4) — `docType=Metadata`
        (défaut) renvoie la ressource `Flow`, `docType=Original` le fichier reçu
        (l'un et l'autre servis depuis les données déjà persistées lors du polling,
        § 4.1, sans nouvel appel à SuperPDP). `Converted`/`ReadableView` sont, eux,
        systématiquement relayés en direct vers SuperPDP (`AfnorClientAdapter.get_flow_document`)
        au moment de l'appel — le routeur ne conserve aucune version convertie/lisible
        (§ 4.1, seul `Original` est téléchargé au polling) — puis renvoyés tels quels
        (passe-plat, comme l'émission `POST /flows`), une fois l'autorisation NF2
        vérifiée ci-dessous.

        Restreint aux factures routées vers ce consommateur (NF2, comme
        `POST /flows/search`) : ce contrôle est fait une seule fois, avant de
        distinguer les `docType`, et s'applique donc identiquement à `Converted`/
        `ReadableView` qu'à `Metadata`/`Original`."""
        invoice = afnor_server_controller.find_invoice_for_consumer_by_flow_id(
            db, target_application=oauth_app, flow_id=flow_id
        )
        if invoice is None:
            raise HTTPException(status_code=404, detail="Flow not found")

        if docType in ("Converted", "ReadableView"):
            company = company_for(db, oauth_app)
            file_bin = call_certified_platform(
                lambda: afnor_client_adapter.get_flow_document(
                    db, company=company, flow_id=flow_id, doc_type=docType
                )
            )
            audit_trace_service.record_odoo_flow_trace(
                db,
                request,
                afnor_api_version=afnor_api_version,
                endpoint="GET /afnor-flow/flows/{flowId}",
                flow_id=flow_id,
                doc_type=docType,
                client_id=oauth_app.client_id,
                response={"status": "ok", "size": len(file_bin)},
                http_status=200,
            )
            return Response(content=file_bin, media_type="application/octet-stream")

        audit_trace_service.record_odoo_flow_trace(
            db,
            request,
            afnor_api_version=afnor_api_version,
            endpoint="GET /afnor-flow/flows/{flowId}",
            flow_id=flow_id,
            doc_type=docType,
            client_id=oauth_app.client_id,
            response={"status": "ok"},
            http_status=200,
        )

        if docType == "Original":
            return FileResponse(
                invoice.file_path,
                filename=invoice.flow_name or f"{flow_id}.xml",
                media_type="application/octet-stream",
            )
        flow = afnor_server_controller.flow_from_invoice(invoice)
        return Response(
            content=flow.model_dump_json(exclude_none=True), media_type="application/json"
        )

    @router.get(flows_healthcheck_path)
    def flow_healthcheck(
        request: Request,
        oauth_app: TargetApplication = Depends(get_current_target_application),
        db: Session = Depends(get_db),
    ):
        return passthrough(
            request,
            oauth_app,
            db,
            method="GET",
            service="afnor-flow",
            path="healthcheck",
        )

    # ----------------------------------------------------------- Directory Service

    @router.get(lookup_siren_path)
    def lookup_siren(
        siren: str,
        request: Request,
        oauth_app: TargetApplication = Depends(get_current_target_application),
        db: Session = Depends(get_db),
    ):
        """Proxy transparent de consultation d'annuaire par SIREN (§ 4.4) — aucune
        création de `PartnerDirectory` ni de règle de routage implicite, l'annuaire
        consulté par Odoo concerne ses propres clients, pas les fournisseurs dont le
        routeur gère le routage (§ 4.3).

        Limite connue : passe par le wrapper `pyfrctc.get_directory_siren` (brut,
        validation SIREN incluse), qui ne relaie pas les paramètres `fields`/
        `include` du contrat — contrairement aux autres endpoints de ce module, qui
        utilisent `raw_passthrough` et les transmettent tels quels. Brut et non
        `_parsed` (cf. `AfnorClientAdapter.lookup_directory_siren`) : un consommateur
        appelle lui-même `get_directory_siren_parsed` sur CE que ce endpoint renvoie,
        laquelle attend les clés brutes du contrat (`entityType`/
        `administrativeStatus`/`businessName`), pas une forme déjà réinterprétée."""
        company = company_for(db, oauth_app)
        result = call_certified_platform(
            lambda: afnor_client_adapter.lookup_directory_siren(
                db, company=company, siren=siren, afnor_api_version=afnor_api_version
            )
        )
        if result is False:
            # Reflète la réponse 404/NOT_FOUND réelle de SuperPDP (`pyfrctc.
            # get_directory_siren` avale déjà ce cas en renvoyant `False` plutôt que
            # de lever) — un `consommateur` (Odoo) doit voir un vrai 404, jamais un
            # corps JSON `false` qui ferait planter son propre parsing de la réponse.
            audit_trace_service.record_odoo_flow_trace(
                db,
                request,
                afnor_api_version=afnor_api_version,
                endpoint=f"GET {_LOOKUP_SIREN_PATH}",
                siren=siren,
                client_id=oauth_app.client_id,
                response={"errorCode": "NOT_FOUND"},
                http_status=404,
            )
            raise HTTPException(status_code=404, detail={"errorCode": "NOT_FOUND"})
        audit_trace_service.record_odoo_flow_trace(
            db,
            request,
            afnor_api_version=afnor_api_version,
            endpoint=f"GET {_LOOKUP_SIREN_PATH}",
            siren=siren,
            client_id=oauth_app.client_id,
            response=result,
            http_status=200,
        )
        return result

    @router.post(f"/afnor-directory/{afnor_api_version}/siren/search")
    def search_siren(
        body: dict,
        request: Request,
        oauth_app: TargetApplication = Depends(get_current_target_application),
        db: Session = Depends(get_db),
    ):
        return passthrough(
            request,
            oauth_app,
            db,
            method="POST",
            service="afnor-directory",
            path="siren/search",
            json_body=body,
        )

    @router.get(lookup_siret_path)
    def lookup_siret(
        siret: str,
        request: Request,
        oauth_app: TargetApplication = Depends(get_current_target_application),
        db: Session = Depends(get_db),
    ):
        """Symétrique de `lookup_siren` pour un SIRET — même absence d'interprétation
        (§ 4.3/§ 4.4) et même limite connue (`fields`/`include` non relayés, cf.
        docstring de `lookup_siren`)."""
        company = company_for(db, oauth_app)
        result = call_certified_platform(
            lambda: afnor_client_adapter.lookup_directory_siret(
                db, company=company, siret=siret, afnor_api_version=afnor_api_version
            )
        )
        if result is False:
            audit_trace_service.record_odoo_flow_trace(
                db,
                request,
                afnor_api_version=afnor_api_version,
                endpoint=f"GET {_LOOKUP_SIRET_PATH}",
                siret=siret,
                client_id=oauth_app.client_id,
                response={"errorCode": "NOT_FOUND"},
                http_status=404,
            )
            raise HTTPException(status_code=404, detail={"errorCode": "NOT_FOUND"})
        audit_trace_service.record_odoo_flow_trace(
            db,
            request,
            afnor_api_version=afnor_api_version,
            endpoint=f"GET {_LOOKUP_SIRET_PATH}",
            siret=siret,
            client_id=oauth_app.client_id,
            response=result,
            http_status=200,
        )
        return result

    @router.post(f"/afnor-directory/{afnor_api_version}/siret/search")
    def search_siret(
        body: dict,
        request: Request,
        oauth_app: TargetApplication = Depends(get_current_target_application),
        db: Session = Depends(get_db),
    ):
        return passthrough(
            request,
            oauth_app,
            db,
            method="POST",
            service="afnor-directory",
            path="siret/search",
            json_body=body,
        )

    @router.get(
        f"/afnor-directory/{afnor_api_version}/routing-code/siret:{{siret}}/code:{{routing_identifier}}"
    )
    def lookup_routing_code(
        siret: str,
        routing_identifier: str,
        request: Request,
        oauth_app: TargetApplication = Depends(get_current_target_application),
        db: Session = Depends(get_db),
    ):
        return passthrough(
            request,
            oauth_app,
            db,
            method="GET",
            service="afnor-directory",
            path=f"routing-code/siret:{siret}/code:{routing_identifier}",
            endpoint_label="GET /afnor-directory/routing-code/siret:{siret}/code:{routing-identifier}",
            extra_trace_fields={"siret": siret, "routing_identifier": routing_identifier},
        )

    @router.post(f"/afnor-directory/{afnor_api_version}/routing-code/search")
    def search_routing_code(
        body: dict,
        request: Request,
        oauth_app: TargetApplication = Depends(get_current_target_application),
        db: Session = Depends(get_db),
    ):
        return passthrough(
            request,
            oauth_app,
            db,
            method="POST",
            service="afnor-directory",
            path="routing-code/search",
            json_body=body,
        )

    @router.get(f"/afnor-directory/{afnor_api_version}/directory-line/code:{{addressing_identifier}}")
    def lookup_directory_line(
        addressing_identifier: str,
        request: Request,
        oauth_app: TargetApplication = Depends(get_current_target_application),
        db: Session = Depends(get_db),
    ):
        return passthrough(
            request,
            oauth_app,
            db,
            method="GET",
            service="afnor-directory",
            path=f"directory-line/code:{addressing_identifier}",
            endpoint_label="GET /afnor-directory/directory-line/code:{addressing-identifier}",
            params=dict(request.query_params),
            extra_trace_fields={"addressing_identifier": addressing_identifier},
        )

    @router.post(f"/afnor-directory/{afnor_api_version}/directory-line/search")
    def search_directory_line(
        body: dict,
        request: Request,
        oauth_app: TargetApplication = Depends(get_current_target_application),
        db: Session = Depends(get_db),
    ):
        return passthrough(
            request,
            oauth_app,
            db,
            method="POST",
            service="afnor-directory",
            path="directory-line/search",
            json_body=body,
        )

    @router.get(f"/afnor-directory/{afnor_api_version}/healthcheck")
    def directory_healthcheck(
        request: Request,
        oauth_app: TargetApplication = Depends(get_current_target_application),
        db: Session = Depends(get_db),
    ):
        return passthrough(
            request,
            oauth_app,
            db,
            method="GET",
            service="afnor-directory",
            path="healthcheck",
        )
