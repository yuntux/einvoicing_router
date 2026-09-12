"""app.storage.filesystem — garde-fou contre la traversée de chemin (CWE-22) sur
`flow_id`/`file_name`, deux valeurs issues de métadonnées SuperPDP externes plutôt
que d'identifiants choisis par le routeur lui-même."""

from datetime import datetime

from app.storage.filesystem import save_invoice_file

_RECEIVED_AT = datetime(2026, 9, 1, 10, 0, 0)


def test_save_invoice_file_writes_under_storage_root(tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "invoice_storage_root", str(tmp_path))

    path = save_invoice_file(
        company_siren="123456789",
        flow_id="flow-1",
        file_name="invoice.xml",
        content=b"<invoice/>",
        received_at=_RECEIVED_AT,
    )

    assert path.startswith(str(tmp_path))
    assert path.endswith("invoice.xml")


def test_save_invoice_file_neutralizes_path_traversal_in_file_name(tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "invoice_storage_root", str(tmp_path))

    path = save_invoice_file(
        company_siren="123456789",
        flow_id="flow-2",
        file_name="../../../../etc/cron.d/evil",
        content=b"malicious",
        received_at=_RECEIVED_AT,
    )

    assert path.startswith(str(tmp_path))


def test_save_invoice_file_neutralizes_absolute_path_in_file_name(tmp_path, monkeypatch):
    """Cas non intuitif de pathlib : `Path(a) / b` ignore entièrement `a` si `b` est
    un chemin absolu — sans neutralisation, un `file_name` valant `/etc/passwd`
    ferait écrire hors de l'arborescence de stockage prévue."""
    from app.config import settings

    monkeypatch.setattr(settings, "invoice_storage_root", str(tmp_path))

    path = save_invoice_file(
        company_siren="123456789",
        flow_id="flow-3",
        file_name="/etc/passwd",
        content=b"malicious",
        received_at=_RECEIVED_AT,
    )

    assert path.startswith(str(tmp_path))
    assert path.endswith("passwd")


def test_save_invoice_file_neutralizes_path_traversal_in_flow_id(tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "invoice_storage_root", str(tmp_path))

    path = save_invoice_file(
        company_siren="123456789",
        flow_id="../../../../etc",
        file_name="invoice.xml",
        content=b"<invoice/>",
        received_at=_RECEIVED_AT,
    )

    assert path.startswith(str(tmp_path))
