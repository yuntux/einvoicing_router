"""Validation des URLs saisies par l'IHM et destinées à être appelées par le routeur
lui-même (webhooks, § 4.4/§ 4.7) — garde-fou anti-SSRF (CWE-918) : le serveur ne doit
jamais pouvoir être détourné, sur la seule foi d'une valeur saisie par un utilisateur
authentifié (même non-admin, même simplement scopé à sa propre entreprise), vers son
réseau interne ou des services cloud sensibles (métadonnées AWS/GCP/Azure).

Limite connue : la résolution DNS a lieu à la validation (création/modification),
pas à chaque appel du webhook (`app/services/webhook_sender.py`) — un hôte public au
moment de l'enregistrement qui serait ensuite re-pointé vers une IP interne ("DNS
rebinding") contournerait ce contrôle. Hors périmètre de ce correctif ; blocage
efficace contre la classe d'attaque la plus commune (IP interne/privée saisie
directement ou via un nom d'hôte qui y résout déjà)."""

import ipaddress
import socket
from urllib.parse import urlparse


class UnsafeWebhookUrlError(ValueError):
    """URL de webhook refusée (schéma non http(s), hôte manquant/non résolvable, ou
    résolvant vers une adresse IP privée/loopback/link-local/réservée)."""


def validate_webhook_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeWebhookUrlError("L'URL de webhook doit utiliser http:// ou https://")
    if not parsed.hostname:
        raise UnsafeWebhookUrlError("URL de webhook invalide (hôte manquant)")

    try:
        addr_infos = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror as exc:
        raise UnsafeWebhookUrlError(
            f"Impossible de résoudre l'hôte du webhook ({parsed.hostname!r}) : {exc}"
        ) from exc

    for _family, _type, _proto, _canonname, sockaddr in addr_infos:
        ip = ipaddress.ip_address(sockaddr[0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise UnsafeWebhookUrlError(
                f"L'hôte du webhook ({parsed.hostname!r}) résout vers une adresse "
                f"non autorisée ({ip}) — les adresses privées/internes sont refusées"
            )
