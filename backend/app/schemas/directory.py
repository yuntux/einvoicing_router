"""Recherche dans l'annuaire AFNOR exposé par SuperPDP, côté routeur = CLIENT pour
ses propres utilisateurs IHM — distinct du passthrough Odoo déjà existant
(`app/api/afnor/_common.py`, routeur = serveur vis-à-vis d'Odoo) qui relaie les mêmes
ressources SuperPDP mais initiées par Odoo, jamais par un utilisateur du routeur."""

from typing import Literal

from pydantic import BaseModel

DirectoryResource = Literal["siren", "siret", "routing-code"]

# Chemin AFNOR (`POST /afnor-directory/{version}/{resource}/search`) par ressource —
# cf. `backend/docs/afnor-contracts/afnor-directory-openapi-v1.3.0.json`.
_SEARCH_PATH_BY_RESOURCE: dict[DirectoryResource, str] = {
    "siren": "siren/search",
    "siret": "siret/search",
    "routing-code": "routing-code/search",
}


class DirectorySearchRequest(BaseModel):
    """Un seul type de recherche à la fois (`resource`) — les champs non pertinents
    pour ce type sont ignorés s'ils sont fournis. Tous les champs de filtre sont
    optionnels ; au moins un doit être renseigné (validé par l'appelant), sinon
    SuperPDP renverrait l'intégralité de l'annuaire."""

    company_id: int
    resource: DirectoryResource

    # Filtres "siren"
    siren: str | None = None
    business_name: str | None = None

    # Filtres "siret" (+ `name`/`postal_code`/`locality` réutilisables par
    # "routing-code", qui partage les mêmes champs d'établissement, cf. contrat)
    siret: str | None = None
    name: str | None = None
    postal_code: str | None = None
    locality: str | None = None

    # Filtres "routing-code"
    routing_identifier: str | None = None
    routing_code_name: str | None = None

    def search_path(self) -> str:
        return _SEARCH_PATH_BY_RESOURCE[self.resource]

    def build_body(self) -> dict:
        """Traduit les champs du formulaire IHM vers le corps JSON attendu par
        SuperPDP (`filters.<champ>.{op,value}`, § contrat) — une correspondance
        `contains` sur les champs texte libres (nom), `strict` sur les identifiants
        (SIREN/SIRET/code de routage), comme documenté sur chaque filtre du
        contrat."""
        filters: dict = {}
        if self.resource == "siren":
            if self.siren:
                filters["siren"] = {"op": "strict", "value": self.siren}
            if self.business_name:
                filters["businessName"] = {"op": "contains", "value": self.business_name}
        elif self.resource == "siret":
            if self.siret:
                filters["siret"] = {"op": "strict", "value": self.siret}
            if self.name:
                filters["name"] = {"op": "contains", "value": self.name}
            if self.postal_code:
                filters["postalCode"] = {"op": "strict", "value": self.postal_code}
            if self.locality:
                filters["locality"] = {"op": "contains", "value": self.locality}
        else:  # routing-code
            if self.routing_identifier:
                filters["routingIdentifier"] = {"op": "strict", "value": self.routing_identifier}
            if self.routing_code_name:
                filters["routingCodeName"] = {"op": "contains", "value": self.routing_code_name}
            if self.siret:
                filters["siret"] = {"op": "strict", "value": self.siret}

        body: dict = {"filters": filters, "limit": 50}
        if self.resource == "siret":
            body["include"] = ["siren"]
        elif self.resource == "routing-code":
            body["include"] = ["siren", "siret"]
        return body

    def has_any_filter(self) -> bool:
        return bool(self.build_body()["filters"])


class PeppolCheckRequest(BaseModel):
    """Vérification directe d'un identifiant dans l'annuaire Peppol (§ bouton
    "Rechercher sur l'annuaire Peppol") — indépendante de SuperPDP (pas de
    `company_id` : une résolution DNS n'a besoin d'aucun jeton), et de tout résultat
    préalable de recherche DGFIP (contrairement à l'enrichissement des lignes
    d'annuaire dans `list_directory_lines`, qui ne fait ce check qu'APRÈS avoir
    trouvé une entité côté SuperPDP)."""

    identifier: str


class DirectoryLinesRequest(BaseModel):
    """Lignes d'annuaire (routage) d'une entité déjà identifiée — § page de détail,
    tableau sous le cartouche d'en-tête. Filtre toujours par SIREN et/ou SIRET exact
    (jamais de recherche libre ici), comme `pyfrctc.get_directory_lines`."""

    company_id: int
    siren: str | None = None
    siret: str | None = None

    def build_body(self) -> dict:
        filters: dict = {}
        if self.siren:
            filters["siren"] = {"op": "strict", "value": self.siren}
        if self.siret:
            filters["siret"] = {"op": "strict", "value": self.siret}
        # `siren`/`siret` inclus en plus de `routingCode` (§ contrat) : sans eux,
        # chaque ligne ne porte que des identifiants bruts, pas de libellé lisible
        # (`legalUnit.businessName`/`facility.name`) — le tableau "Lignes d'annuaire"
        # de l'IHM n'affichait alors aucun nom, seulement des SIREN/SIRET/codes.
        return {"filters": filters, "include": ["siren", "siret", "routingCode"], "limit": 100}
