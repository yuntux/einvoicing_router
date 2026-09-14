"""API IHM RouterSettings + BillingManagerContact (spec.md § 6.1/§ 4.7, lot 5)."""

from unittest.mock import MagicMock, patch

from app.models.audit import TechnicalLog


def test_get_router_settings_returns_defaults(client):
    response = client.get("/api/ihm/settings")
    assert response.status_code == 200
    body = response.json()
    assert body["technical_log_retention_days"] == 15 * 365
    assert body["smtp_port"] == 587


def test_update_router_settings(client):
    response = client.put(
        "/api/ihm/settings",
        json={
            "smtp_host": "smtp.example.com",
            "smtp_port": 25,
            "smtp_from_address": "routeur@example.com",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["smtp_host"] == "smtp.example.com"
    assert body["smtp_port"] == 25
    assert body["smtp_from_address"] == "routeur@example.com"

    # Persisté : un GET ultérieur voit la même valeur.
    response = client.get("/api/ihm/settings")
    assert response.json()["smtp_host"] == "smtp.example.com"


def test_smtp_test_connection_uses_saved_settings_when_overrides_blank(client):
    client.put("/api/ihm/settings", json={"smtp_host": "smtp.example.com", "smtp_port": 25})

    with patch("app.services.router_settings_service.Ipv4SmtpConnection") as mock_smtp_cls:
        mock_smtp = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_smtp
        response = client.post("/api/ihm/settings/smtp/test-connection", json={})

    assert response.status_code == 200
    assert response.json() == {"ok": True, "error": None}
    mock_smtp_cls.assert_called_once_with("smtp.example.com", 25, timeout=10)


def test_smtp_test_connection_override_without_saving(client):
    """Un champ fourni dans le corps de la requête prime sur la valeur enregistrée
    (jamais persisté) — permet de tester avant d'enregistrer."""
    client.put("/api/ihm/settings", json={"smtp_host": "smtp.example.com", "smtp_port": 25})

    with patch("app.services.router_settings_service.Ipv4SmtpConnection") as mock_smtp_cls:
        mock_smtp = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_smtp
        response = client.post(
            "/api/ihm/settings/smtp/test-connection",
            json={"smtp_host": "smtp.other.example.com"},
        )

    assert response.status_code == 200
    mock_smtp_cls.assert_called_once_with("smtp.other.example.com", 25, timeout=10)

    # Non persisté.
    assert client.get("/api/ihm/settings").json()["smtp_host"] == "smtp.example.com"


def test_smtp_test_connection_reports_failure(client):
    client.put("/api/ihm/settings", json={"smtp_host": "smtp.example.com", "smtp_port": 25})

    with patch("app.services.router_settings_service.Ipv4SmtpConnection") as mock_smtp_cls:
        mock_smtp_cls.side_effect = OSError("Connection refused")
        response = client.post("/api/ihm/settings/smtp/test-connection", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert "Connection refused" in body["error"]


def test_smtp_test_connection_without_host_configured(client):
    response = client.post("/api/ihm/settings/smtp/test-connection", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["error"]


def test_smtp_send_test_email_uses_saved_settings(client):
    client.put(
        "/api/ihm/settings",
        json={
            "smtp_host": "smtp.example.com",
            "smtp_port": 25,
            "smtp_from_address": "routeur@example.com",
        },
    )

    with patch("app.services.mail_sender.Ipv4SmtpConnection") as mock_smtp_cls:
        mock_smtp = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_smtp
        response = client.post(
            "/api/ihm/settings/smtp/send-test-email",
            json={"to_address": "destinataire@example.com"},
        )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "error": None}
    mock_smtp.send_message.assert_called_once()
    sent_message = mock_smtp.send_message.call_args.args[0]
    assert sent_message["From"] == "routeur@example.com"
    assert sent_message["To"] == "destinataire@example.com"


def test_smtp_send_test_email_without_from_address_returns_clear_error(client):
    """Régression : sans adresse expéditeur configurée, `EmailMessage["From"] = None`
    sérialisait littéralement la chaîne "None" comme expéditeur, rejetée par le
    serveur distant (ex. Exchange Online, 5.1.7 Invalid address) sans qu'on sache que
    la vraie cause est une adresse expéditeur manquante. Doit être détecté avant tout
    envoi, sans même tenter la connexion SMTP."""
    client.put("/api/ihm/settings", json={"smtp_host": "smtp.example.com", "smtp_port": 25})

    with patch("app.services.mail_sender.Ipv4SmtpConnection") as mock_smtp_cls:
        response = client.post(
            "/api/ihm/settings/smtp/send-test-email",
            json={"to_address": "destinataire@example.com"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert "expéditeur" in body["error"]
    mock_smtp_cls.assert_not_called()


def test_smtp_test_connection_success_recorded_in_technical_log(client, db_session):
    client.put("/api/ihm/settings", json={"smtp_host": "smtp.example.com", "smtp_port": 25})

    with patch("app.services.router_settings_service.Ipv4SmtpConnection") as mock_smtp_cls:
        mock_smtp = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_smtp
        client.post("/api/ihm/settings/smtp/test-connection", json={})

    log = db_session.query(TechnicalLog).filter(TechnicalLog.log_type == "smtp_test_connection").one()
    assert log.origin == "ihm_settings_smtp"
    assert log.status == "success"


def test_smtp_test_connection_failure_recorded_in_technical_log_with_detail(client, db_session):
    client.put("/api/ihm/settings", json={"smtp_host": "smtp.example.com", "smtp_port": 25})

    with patch("app.services.router_settings_service.Ipv4SmtpConnection") as mock_smtp_cls:
        mock_smtp_cls.side_effect = OSError("Connection refused")
        client.post("/api/ihm/settings/smtp/test-connection", json={})

    log = db_session.query(TechnicalLog).filter(TechnicalLog.log_type == "smtp_test_connection").one()
    assert log.status == "error"
    assert "Connection refused" in log.details


def test_smtp_send_test_email_failure_recorded_in_technical_log_with_detail(client, db_session):
    client.put(
        "/api/ihm/settings",
        json={
            "smtp_host": "smtp.example.com",
            "smtp_port": 25,
            "smtp_from_address": "routeur@example.com",
        },
    )

    with patch("app.services.mail_sender.Ipv4SmtpConnection") as mock_smtp_cls:
        mock_smtp_cls.side_effect = OSError("Connection refused")
        client.post(
            "/api/ihm/settings/smtp/send-test-email",
            json={"to_address": "destinataire@example.com"},
        )

    log = db_session.query(TechnicalLog).filter(TechnicalLog.log_type == "smtp_send_test_email").one()
    assert log.status == "error"
    assert "destinataire@example.com" in log.details
    assert "Connection refused" in log.details


def test_smtp_send_test_email_reports_failure(client):
    client.put(
        "/api/ihm/settings",
        json={
            "smtp_host": "smtp.example.com",
            "smtp_port": 25,
            "smtp_from_address": "routeur@example.com",
        },
    )

    with patch("app.services.mail_sender.Ipv4SmtpConnection") as mock_smtp_cls:
        mock_smtp_cls.side_effect = OSError("Connection refused")
        response = client.post(
            "/api/ihm/settings/smtp/send-test-email",
            json={"to_address": "destinataire@example.com"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert "Connection refused" in body["error"]


def test_billing_manager_contacts_crud(client):
    response = client.post(
        "/api/ihm/settings/billing-manager-contacts", json={"email": "gestion@example.com"}
    )
    assert response.status_code == 201
    contact_id = response.json()["id"]

    response = client.get("/api/ihm/settings/billing-manager-contacts")
    assert response.status_code == 200
    assert [c["email"] for c in response.json()] == ["gestion@example.com"]

    response = client.delete(f"/api/ihm/settings/billing-manager-contacts/{contact_id}")
    assert response.status_code == 204

    response = client.get("/api/ihm/settings/billing-manager-contacts")
    assert response.json() == []
