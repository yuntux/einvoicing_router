"""Stockage des fichiers de factures sur le système de fichiers (spec.md § 4.1/NF8)."""

from datetime import datetime
from pathlib import Path

from app.config import settings


def _safe_path_component(value: str, *, fallback: str) -> str:
    """Neutralise une traversée de chemin (CWE-22) : `flow_id`/`file_name` viennent de
    métadonnées SuperPDP externes (assignées par la plateforme d'interopérabilité,
    en dernier ressort potentiellement influencées par le fournisseur émetteur de la
    facture) — jamais des identifiants que le routeur choisit lui-même. `Path.name`
    ne garde que le dernier segment (neutralise `../..` et, propriété moins connue
    de pathlib, un composant absolu comme `/etc/passwd` qui sinon remplacerait
    entièrement le chemin de base via l'opérateur `/`)."""
    name = Path(value).name
    if not name or name in (".", ".."):
        return fallback
    return name


def save_invoice_file(
    *, company_siren: str, flow_id: str, file_name: str, content: bytes, received_at: datetime
) -> str:
    """Écrit le fichier de facture et retourne son chemin (relatif à la racine de
    stockage configurée). Les fichiers sont répartis dans un sous-dossier mensuel
    (`YYMM`, ex. "2609" pour septembre 2026) sous celui de l'entreprise, créé à la
    volée à la première facture reçue pour ce mois — évite d'accumuler tous les flux
    d'une entreprise dans un seul répertoire au fil des années."""
    root = Path(settings.invoice_storage_root)
    month_folder = received_at.strftime("%y%m")
    safe_flow_id = _safe_path_component(flow_id, fallback="unknown-flow")
    directory = root / company_siren / month_folder / safe_flow_id
    directory.mkdir(parents=True, exist_ok=True)
    safe_file_name = _safe_path_component(file_name, fallback=f"{safe_flow_id}.xml")
    file_path = directory / safe_file_name
    file_path.write_bytes(content)
    return str(file_path)


def save_lifecycle_attachment(*, company_siren: str, event_id: int, file_name: str, content: bytes) -> str:
    """Écrit une pièce jointe de message de cycle de vie CDAR (norme XP Z12-013 § 4.2,
    MDT-96) — entrante (nom de fichier assigné par la contrepartie via SuperPDP) ou
    sortante (saisie manuelle IHM). Classée par `event_id` (identifiant interne,
    jamais influencé de l'extérieur) plutôt que par `flow_id` : un événement sortant
    n'a pas encore de `flow_id` externe au moment de la saisie."""
    root = Path(settings.invoice_storage_root)
    directory = root / company_siren / "lifecycle-attachments" / str(event_id)
    directory.mkdir(parents=True, exist_ok=True)
    safe_file_name = _safe_path_component(file_name, fallback=f"attachment-{event_id}.bin")
    file_path = directory / safe_file_name
    file_path.write_bytes(content)
    return str(file_path)


def save_afnor_flow_file(*, company_siren: str, flow_id: int, content: bytes) -> str:
    """Écrit le fichier d'un flux AFNOR (CDAR entrant ou sortant, § 6.2) — classé par
    `flow_id` **interne** (`AfnorFlow.id`, jamais influencé de l'extérieur), pas par
    l'identifiant technique externe (`AfnorFlow.flow_id`, absent tant qu'un flux
    sortant n'a pas encore été transmis) — même principe que `save_lifecycle_
    attachment`. Toujours nommé `cdar.xml` : un seul fichier par flux, le dossier
    (`flow_id` interne) suffit à le distinguer des autres."""
    root = Path(settings.invoice_storage_root)
    directory = root / company_siren / "afnor-flows" / str(flow_id)
    directory.mkdir(parents=True, exist_ok=True)
    file_path = directory / "cdar.xml"
    file_path.write_bytes(content)
    return str(file_path)
