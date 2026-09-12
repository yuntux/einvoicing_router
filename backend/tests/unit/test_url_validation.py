"""app.services.url_validation — garde-fou anti-SSRF (CWE-918) sur les URLs de
webhook saisies dans l'IHM et appelées par le routeur lui-même (§ 4.4/§ 4.7)."""

from unittest.mock import patch

import pytest

from app.services.url_validation import UnsafeWebhookUrlError, validate_webhook_url


def test_rejects_non_http_scheme():
    with pytest.raises(UnsafeWebhookUrlError):
        validate_webhook_url("file:///etc/passwd")


def test_rejects_ftp_scheme():
    with pytest.raises(UnsafeWebhookUrlError):
        validate_webhook_url("ftp://example.com/hook")


def test_rejects_missing_host():
    with pytest.raises(UnsafeWebhookUrlError):
        validate_webhook_url("https:///no-host")


def test_rejects_ipv4_loopback():
    with pytest.raises(UnsafeWebhookUrlError):
        validate_webhook_url("http://127.0.0.1:8000/admin")


def test_rejects_ipv6_loopback():
    with pytest.raises(UnsafeWebhookUrlError):
        validate_webhook_url("http://[::1]/admin")


def test_rejects_private_rfc1918_address():
    with pytest.raises(UnsafeWebhookUrlError):
        validate_webhook_url("http://10.0.0.5/hook")
    with pytest.raises(UnsafeWebhookUrlError):
        validate_webhook_url("http://192.168.1.1/hook")
    with pytest.raises(UnsafeWebhookUrlError):
        validate_webhook_url("http://172.16.0.1/hook")


def test_rejects_link_local_cloud_metadata_address():
    """169.254.169.254 : endpoint de métadonnées cloud (AWS/GCP/Azure) — vecteur
    classique de vol d'identifiants IAM via SSRF."""
    with pytest.raises(UnsafeWebhookUrlError):
        validate_webhook_url("http://169.254.169.254/latest/meta-data/")


def test_rejects_unresolvable_host():
    """`.invalid` (RFC 2606) est garanti de ne jamais résoudre — utilisé ici plutôt
    qu'un vrai nom d'hôte pour ne pas dépendre du réseau dans ce test."""
    with pytest.raises(UnsafeWebhookUrlError):
        validate_webhook_url("https://this-host-does-not-exist.invalid/hook")


def test_accepts_public_address():
    with patch(
        "app.services.url_validation.socket.getaddrinfo",
        return_value=[(2, 1, 6, "", ("93.184.216.34", 0))],
    ):
        validate_webhook_url("https://example.com/hook")  # ne lève pas
