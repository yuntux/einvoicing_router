"""Traçabilité "qui/quand" par ligne (`AuditColumnsMixin`) + extension du journal
d'audit (`AuditLog`, NF9) aux actions IHM au-delà du seul téléchargement de facture."""

from app.config import settings
from app.models.audit import AuditLog
from app.models.referential import Company


def test_login_and_logout_are_audited(client, monkeypatch, db_session):
    monkeypatch.setattr(settings, "oidc_mode", "dev")
    client.get("/api/ihm/auth/login", params={"email": "alice@example.com"}, follow_redirects=False)
    client.post("/api/ihm/auth/logout")

    actions = [log.action for log in db_session.query(AuditLog).order_by(AuditLog.id).all()]
    assert actions == ["login", "logout"]


def test_create_company_sets_audit_columns_and_logs_action(client, monkeypatch, db_session):
    monkeypatch.setattr(settings, "oidc_mode", "dev")
    client.get("/api/ihm/auth/login", params={"email": "admin@example.com"}, follow_redirects=False)
    admin_id = client.get("/api/ihm/auth/me").json()["user"]["id"]

    response = client.post("/api/ihm/companies", json={"siren": "123456782", "name": "Acme"})
    assert response.status_code == 201
    company_id = response.json()["id"]

    company = db_session.get(Company, company_id)
    assert company.create_user_id == admin_id
    assert company.write_user_id == admin_id
    assert company.create_datetime is not None
    assert company.write_datetime is not None

    log = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "company_create")
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert log is not None
    assert log.target == str(company_id)
    assert log.user_id == admin_id


def test_update_router_settings_sets_write_user_and_logs_action(client, monkeypatch, db_session):
    monkeypatch.setattr(settings, "oidc_mode", "dev")
    client.get("/api/ihm/auth/login", params={"email": "admin2@example.com"}, follow_redirects=False)
    admin_id = client.get("/api/ihm/auth/me").json()["user"]["id"]

    response = client.put("/api/ihm/settings", json={"smtp_host": "smtp.example.com"})
    assert response.status_code == 200

    from app.services import router_settings_service

    router_settings = router_settings_service.get_settings(db_session)
    assert router_settings.write_user_id == admin_id

    log = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "settings_update")
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert log is not None
    assert log.user_id == admin_id


def test_partner_created_manually_has_create_user_id_but_auto_created_does_not(
    client, monkeypatch, db_session
):
    """Un fournisseur créé via le formulaire IHM porte `create_user_id` ; un
    fournisseur auto-créé à la réception d'une facture (§ 4.4) reste à `None` — ce
    n'est pas une action utilisateur."""
    monkeypatch.setattr(settings, "oidc_mode", "dev")
    client.get("/api/ihm/auth/login", params={"email": "admin3@example.com"}, follow_redirects=False)
    admin_id = client.get("/api/ihm/auth/me").json()["user"]["id"]

    response = client.post("/api/ihm/partners", json={"siren": "100000009", "name": "Fournisseur A"})
    assert response.status_code == 201
    partner_id = response.json()["id"]

    from app.models.referential import PartnerDirectory

    partner = db_session.get(PartnerDirectory, partner_id)
    assert partner.create_user_id == admin_id

    from app.services import directory_service

    auto_partner, created = directory_service.get_or_create_partner(
        db_session, siren="111222338", name="Fournisseur auto-détecté"
    )
    assert created is True
    assert auto_partner.create_user_id is None


def test_last_login_derived_from_audit_log_reflects_most_recent_login(
    client, monkeypatch, db_session
):
    """`last_login_at` (§ NF4/NF9, `UsersView`) n'est pas une colonne dédiée sur
    `User` — il est dérivé du journal d'audit (action "login") pour ne pas dupliquer
    un événement déjà tracé là, cf. `audit_trace_service.get_last_login(s)`."""
    from datetime import timedelta

    from app.services import audit_trace_service

    monkeypatch.setattr(settings, "oidc_mode", "dev")
    client.get("/api/ihm/auth/login", params={"email": "bob@example.com"}, follow_redirects=False)
    user_id = client.get("/api/ihm/auth/me").json()["user"]["id"]

    first_login_log = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "login", AuditLog.user_id == user_id)
        .first()
    )
    # Pas encore de login pour un autre utilisateur -> absent du dict, get() renvoie None.
    assert audit_trace_service.get_last_logins(db_session, [user_id, 999999]) == {
        user_id: first_login_log.created_at
    }
    # Une seule connexion à ce stade -> pas d'"avant-dernière" à renvoyer.
    assert audit_trace_service.get_previous_login(db_session, user_id) is None
    # Recule artificiellement le 1er login pour simuler un vrai écart temporel, puis
    # ajoute un 2e login plus récent : `get_last_login` doit refléter le plus récent.
    first_login_log.created_at -= timedelta(days=1)
    db_session.commit()

    client.post("/api/ihm/auth/logout")
    client.get("/api/ihm/auth/login", params={"email": "bob@example.com"}, follow_redirects=False)

    logs = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "login", AuditLog.user_id == user_id)
        .order_by(AuditLog.id)
        .all()
    )
    assert len(logs) == 2
    assert audit_trace_service.get_last_login(db_session, user_id) == logs[1].created_at
    assert audit_trace_service.get_last_login(db_session, user_id) != logs[0].created_at

    # `get_previous_login` (utilisé par /auth/me pour la sidebar) doit renvoyer la
    # connexion *avant* la dernière, jamais la dernière elle-même.
    assert audit_trace_service.get_previous_login(db_session, user_id) == logs[0].created_at
    assert audit_trace_service.get_previous_login(db_session, user_id) != logs[1].created_at
