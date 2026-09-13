"""Statut PEPPOL d'une ligne d'annuaire AFNOR (§ page de détail "Annuaire") —
complètement indépendant de SuperPDP : `pyfrctc.check_directory_line_peppol_status`
ne fait aucun appel HTTP à la plateforme certifiée, seulement une résolution DNS
NAPTR contre le SML (Service Metadata Locator) du réseau PEPPOL, pour savoir si un
SIRET (schéma d'adressage "0225") y est enregistré et par quel Access Point il est
géré."""

from concurrent.futures import ThreadPoolExecutor

from pyfrctc.peppol import check_directory_line_peppol_status

# Une entité comme le SIREN de l'État agrège des centaines de lignes d'annuaire :
# résoudre leur statut Peppol une par une (DNS synchrone, § docstring) rendrait la
# page de détail inutilisable. `_MAX_WORKERS` borne le parallélisme (pas de sens à
# ouvrir des milliers de requêtes DNS simultanées) ; `_LOOKUP_TIMEOUT_SECONDS` évite
# qu'une seule résolution DNS anormalement lente (réseau, SML indisponible) ne
# bloque l'affichage de toutes les autres lignes.
_MAX_WORKERS = 20
_LOOKUP_TIMEOUT_SECONDS = 3.0


def check_peppol_status(directory_line_identifier: str | None) -> dict:
    """Renvoie `{"active": bool, "access_point": str | None, "error": str | None}` —
    ne lève jamais : une erreur DNS (réseau, résolution) est rapportée dans `error`
    plutôt que de faire échouer tout l'affichage des lignes d'annuaire pour une seule
    ligne dont le statut PEPPOL n'a pas pu être déterminé."""
    if not directory_line_identifier:
        return {"active": False, "access_point": None, "error": "Identifiant manquant"}
    try:
        result = check_directory_line_peppol_status(directory_line_identifier)
    except Exception as exc:  # noqa: BLE001 — résolution DNS tierce, cause imprévisible
        return {"active": False, "access_point": None, "error": str(exc)}
    if result is False:
        return {"active": False, "access_point": None, "error": None}
    return {"active": True, "access_point": result, "error": None}


def check_peppol_statuses_bulk(directory_line_identifiers: list[str | None]) -> list[dict]:
    """Version parallélisée de `check_peppol_status` pour une liste de lignes
    d'annuaire (§ page de détail "Annuaire", `list_directory_lines`) — résout les
    identifiants en parallèle (`_MAX_WORKERS` résolutions DNS à la fois) plutôt
    qu'une boucle séquentielle, et borne chaque résolution à
    `_LOOKUP_TIMEOUT_SECONDS` : au-delà, la ligne est rapportée en erreur plutôt que
    de laisser une seule résolution DNS lente retarder l'affichage de toutes les
    autres. L'ordre du résultat correspond à celui de `directory_line_identifiers`."""
    if not directory_line_identifiers:
        return []
    with ThreadPoolExecutor(max_workers=min(_MAX_WORKERS, len(directory_line_identifiers))) as executor:
        futures = [executor.submit(check_peppol_status, identifier) for identifier in directory_line_identifiers]
        results = []
        for future in futures:
            try:
                results.append(future.result(timeout=_LOOKUP_TIMEOUT_SECONDS))
            except TimeoutError:
                results.append({"active": False, "access_point": None, "error": "Délai de résolution Peppol dépassé"})
        return results
