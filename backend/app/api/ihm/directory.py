"""Recherche dans l'annuaire AFNOR exposé par SuperPDP, pour les utilisateurs du
routeur (§ nouvel écran "Annuaire") — le routeur agit ici en CLIENT, avec les
identifiants SuperPDP d'une entreprise gérée choisie explicitement (chaque
entreprise a son propre jeton, § 4.10), contrairement au passthrough Odoo déjà
existant (`app/api/afnor/_common.py`) où le routeur est SERVEUR vis-à-vis d'Odoo.

Réutilise `AfnorClientAdapter.raw_passthrough` (déjà utilisé par ce passthrough
Odoo) plutôt que d'ajouter de nouveaux wrappers `pyfrctc` : `raw_passthrough` est
déjà générique (méthode/service/chemin) et trace l'échange (`FlowTrace`, NF1)
comme tout appel sortant vers SuperPDP."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.afnor.client.adapter import afnor_client_adapter
from app.afnor.server.afnor_server_controller import call_certified_platform
from app.auth.perimeter import ensure_company_in_scope
from app.auth.session import get_current_user
from app.db.session import get_db
from app.models.referential import Company, User
from app.schemas.directory import DirectoryLinesRequest, DirectorySearchRequest, PeppolCheckRequest
from app.services.peppol_service import check_peppol_status, check_peppol_statuses_bulk

router = APIRouter()


def _company_in_scope(db: Session, company_id: int, user: User | None) -> Company:
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    ensure_company_in_scope(user, company.id)
    return company


@router.post("/search")
def search_directory(
    payload: DirectorySearchRequest,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
) -> dict:
    """Relaie `POST /afnor-directory/{version}/{siren,siret,routing-code}/search`
    vers SuperPDP avec les identifiants de `payload.company_id` — corps de réponse
    SuperPDP renvoyé tel quel (`results`/`totalNumberOfResults`/`search`, § contrat),
    jamais réinterprété : le formulaire de recherche IHM ne fait que traduire ses
    champs en filtres du contrat (`DirectorySearchRequest.build_body`)."""
    if not payload.has_any_filter():
        raise HTTPException(status_code=422, detail="At least one search field is required")
    company = _company_in_scope(db, payload.company_id, user)
    status_code, body = call_certified_platform(
        lambda: afnor_client_adapter.raw_passthrough(
            db,
            company=company,
            method="POST",
            service="afnor-directory",
            path=payload.search_path(),
            json_body=payload.build_body(),
        )
    )
    if status_code >= 400:
        raise HTTPException(status_code=502, detail=body)
    return body


@router.post("/peppol-check")
def peppol_check(payload: PeppolCheckRequest) -> dict:
    """Vérification directe dans l'annuaire Peppol (§ bouton "Rechercher sur
    l'annuaire Peppol") — sur l'identifiant tel que saisi dans le formulaire (SIREN,
    SIRET ou identifiant de routage selon le mode de recherche actif), sans passer
    par une recherche SuperPDP au préalable : couvre le cas d'une entité connue de
    Peppol mais absente de l'annuaire DGFIP (§ spec.md § 4.11)."""
    identifier = payload.identifier.strip()
    if not identifier:
        raise HTTPException(status_code=422, detail="identifier is required")
    return check_peppol_status(identifier)


@router.post("/lines")
def list_directory_lines(
    payload: DirectoryLinesRequest,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
) -> dict:
    """Lignes d'annuaire (routage) d'une entité déjà identifiée (SIREN et/ou SIRET),
    pour le tableau sous le cartouche d'en-tête de la page de détail — même
    passthrough que `search_directory`, ressource `directory-line/search`.

    Chaque ligne est enrichie d'un champ `peppol` (§ colonne "Annuaire Peppol") —
    ajouté ici, jamais dans le corps SuperPDP lui-même : une résolution DNS contre le
    réseau PEPPOL (`peppol_service.check_peppol_status`), indépendante de SuperPDP,
    donc pas un champ du contrat AFNOR."""
    if not payload.siren and not payload.siret:
        raise HTTPException(status_code=422, detail="siren or siret is required")
    company = _company_in_scope(db, payload.company_id, user)
    status_code, body = call_certified_platform(
        lambda: afnor_client_adapter.raw_passthrough(
            db,
            company=company,
            method="POST",
            service="afnor-directory",
            path="directory-line/search",
            json_body=payload.build_body(),
        )
    )
    if status_code >= 400:
        raise HTTPException(status_code=502, detail=body)
    lines = body.get("results", [])
    identifiers = [line.get("addressingIdentifier") or line.get("siret") for line in lines]
    for line, peppol_status in zip(lines, check_peppol_statuses_bulk(identifiers)):
        line["peppol"] = peppol_status
    return body
