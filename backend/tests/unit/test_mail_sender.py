"""SmtpMailSender — construction du message SMTP (spec.md § 4.9.1). `mail_router_service`
et les tests de plus haut niveau (`test_mail_routing.py`) passent par un
`MailSenderProtocol` de substitution ; celui-ci vérifie directement la seule logique
propre à `SmtpMailSender` : la résolution de l'en-tête `From`."""

import socket
from unittest.mock import MagicMock, patch

from app.services.mail_sender import Ipv4SmtpConnection, OutgoingMail, SmtpMailSender


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
    with patch("app.services.mail_sender.Ipv4SmtpConnection") as mock_smtp_cls:
        mock_smtp = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_smtp

        SmtpMailSender().send(
            _mail(from_address="factures@ma-societe.example"), router_settings=_FakeRouterSettings()
        )

    sent_message = mock_smtp.send_message.call_args.args[0]
    assert sent_message["From"] == "factures@ma-societe.example"


def test_from_header_falls_back_to_global_setting_when_not_set():
    with patch("app.services.mail_sender.Ipv4SmtpConnection") as mock_smtp_cls:
        mock_smtp = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_smtp

        SmtpMailSender().send(_mail(), router_settings=_FakeRouterSettings())

    sent_message = mock_smtp.send_message.call_args.args[0]
    assert sent_message["From"] == "routeur@example.com"


def test_ipv4_smtp_connection_resolves_and_connects_over_ipv4_only():
    """Régression (Exchange Online `4.7.25` : IPv6 sans PTR rejetée) — la résolution
    DNS est explicitement restreinte à `AF_INET`, et le socket se connecte à
    l'adresse IPv4 résolue, jamais à l'hôte brut (qui pourrait re-résoudre en IPv6)."""
    smtp = Ipv4SmtpConnection.__new__(Ipv4SmtpConnection)
    smtp.source_address = None
    smtp.debuglevel = 0

    with (
        patch("app.services.mail_sender.socket.getaddrinfo") as mock_getaddrinfo,
        patch("app.services.mail_sender.socket.create_connection") as mock_create_connection,
    ):
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("203.0.113.10", 587)),
        ]
        smtp._get_socket("smtp.example.com", 587, 10)

    mock_getaddrinfo.assert_called_once_with(
        "smtp.example.com", 587, socket.AF_INET, socket.SOCK_STREAM
    )
    mock_create_connection.assert_called_once_with(("203.0.113.10", 587), 10, None)


def test_ipv4_smtp_connection_preserves_original_hostname_for_tls_sni():
    """`self._host` (utilisé par `starttls()` pour la validation TLS/SNI du
    certificat) doit rester le nom d'hôte d'origine, jamais l'IPv4 résolue —
    sinon la validation du certificat échouerait (un certificat n'est jamais émis
    pour une adresse IP littérale)."""
    with patch("app.services.mail_sender.socket.getaddrinfo") as mock_getaddrinfo:
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("203.0.113.10", 587)),
        ]
        with patch("app.services.mail_sender.socket.create_connection"):
            with patch.object(Ipv4SmtpConnection, "getreply", return_value=(220, b"ok")):
                smtp = Ipv4SmtpConnection("smtp.example.com", 587)

    assert smtp._host == "smtp.example.com"
