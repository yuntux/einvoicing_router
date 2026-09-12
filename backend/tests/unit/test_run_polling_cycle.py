"""Relevé manuel des nouvelles factures depuis la page Entreprises (§ 4.1) : force un
passage du cycle de polling sans attendre le prochain déclenchement du scheduler —
même principe que le bouton « Forcer un cycle d'envoi » de la page Échecs de routage
(cf. `test_invoice_routings_api.py`), mais pour le polling plutôt que le retry."""

from datetime import datetime

from app.config import settings
from app.models.referential import Company


def test_run_polling_cycle_updates_last_polled_at(client, db_session, monkeypatch):
    # `settings.certified_platform_client_mode` doit valoir "fake" (défaut du code)
    # pour ce test — forcé explicitement car un `.env` de dev présent dans le
    # répertoire d'exécution peut le surcharger (`pydantic-settings` charge `.env`
    # relatif au cwd, indépendamment de pytest).
    monkeypatch.setattr(settings, "certified_platform_client_mode", "fake")
    company = Company(siren="123456782", name="Acme SAS")
    db_session.add(company)
    db_session.commit()
    db_session.refresh(company)
    assert company.last_polled_at is None

    response = client.post("/api/ihm/companies/run-polling-cycle")
    assert response.status_code == 204

    db_session.refresh(company)
    assert company.last_polled_at is not None
    assert company.last_polled_at <= datetime.utcnow()


def test_run_polling_cycle_requires_admin(client, monkeypatch):
    """Endpoint monté sur `admin_router` (§ 5.1, page Entreprises) : un utilisateur
    restreint ou lecture seule n'y a pas plus accès qu'aux autres actions de cette
    page (cf. `test_admin_only_pages_scope.py`)."""
    monkeypatch.setattr(settings, "oidc_mode", "dev")
    client.get("/api/ihm/auth/login", params={"email": "admin@example.com"}, follow_redirects=False)
    client.post("/api/ihm/users", json={"email": "user@example.com"})
    client.post("/api/ihm/auth/logout")
    client.get("/api/ihm/auth/login", params={"email": "user@example.com"}, follow_redirects=False)

    response = client.post("/api/ihm/companies/run-polling-cycle")
    assert response.status_code == 403
