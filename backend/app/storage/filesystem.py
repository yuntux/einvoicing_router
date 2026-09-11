"""Stockage des fichiers de factures sur le système de fichiers (spec.md § 4.1/NF8)."""

from pathlib import Path

from app.config import settings


def save_invoice_file(
    *, company_siren: str, flow_id: str, file_name: str, content: bytes
) -> str:
    """Écrit le fichier de facture et retourne son chemin (relatif à la racine de
    stockage configurée)."""
    root = Path(settings.invoice_storage_root)
    directory = root / company_siren / flow_id
    directory.mkdir(parents=True, exist_ok=True)
    file_path = directory / file_name
    file_path.write_bytes(content)
    return str(file_path)
