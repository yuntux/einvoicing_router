"""Stockage des fichiers de factures sur le système de fichiers (spec.md § 4.1/NF8)."""

from datetime import datetime
from pathlib import Path

from app.config import settings


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
    directory = root / company_siren / month_folder / flow_id
    directory.mkdir(parents=True, exist_ok=True)
    file_path = directory / file_name
    file_path.write_bytes(content)
    return str(file_path)
