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
