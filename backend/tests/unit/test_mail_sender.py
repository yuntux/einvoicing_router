"""SmtpMailSender — construction du message SMTP (spec.md § 4.9.1). `mail_router_service`
et les tests de plus haut niveau (`test_mail_routing.py`) passent par un
`MailSenderProtocol` de substitution ; celui-ci vérifie directement la seule logique
propre à `SmtpMailSender` : la résolution de l'en-tête `From`."""

from unittest.mock import MagicMock, patch

from app.services.mail_sender import OutgoingMail, SmtpMailSender


class _FakeRouterSettings:
    smtp_host = "smtp.example.com"
    smtp_port = 587
    smtp_username = None
    smtp_password = None
    smtp_use_tls = False
    smtp_from_address = "routeur@example.com"


def _mail(**overrides) -> OutgoingMail:
    defaults = dict(to=["dest@example.com"], cc=[], bcc=[], subject="F-1", body="corps")
    defaults.update(overrides)
    return OutgoingMail(**defaults)


def test_from_header_uses_target_override_when_set():
    with patch("app.services.mail_sender.smtplib.SMTP") as mock_smtp_cls:
        mock_smtp = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_smtp

        SmtpMailSender().send(
            _mail(from_address="factures@ma-societe.example"), router_settings=_FakeRouterSettings()
        )

    sent_message = mock_smtp.send_message.call_args.args[0]
    assert sent_message["From"] == "factures@ma-societe.example"


def test_from_header_falls_back_to_global_setting_when_not_set():
    with patch("app.services.mail_sender.smtplib.SMTP") as mock_smtp_cls:
        mock_smtp = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_smtp

        SmtpMailSender().send(_mail(), router_settings=_FakeRouterSettings())

    sent_message = mock_smtp.send_message.call_args.args[0]
    assert sent_message["From"] == "routeur@example.com"
