"""Abstraction d'envoi de notification webhook (spec.md § 4.4/§ 4.7, lot 6).

Symétrique à `mail_sender.py` : `WebhookNotificationService` et
`RetrySchedulerService` dépendent de `WebhookSenderProtocol`, pas directement de
`requests`, pour rester testables sans point de terminaison HTTP réel."""

from dataclasses import dataclass
from typing import Protocol

import requests

from app.config import settings


@dataclass
class OutgoingWebhook:
    url: str
    payload: dict


class WebhookSenderProtocol(Protocol):
    def send(self, webhook: OutgoingWebhook) -> None:
        """Envoie la notification ; lève une exception en cas d'échec (statut HTTP
        non-2xx ou erreur réseau, interprétée comme un échec par l'appelant)."""
        ...


class HttpWebhookSender:
    def send(self, webhook: OutgoingWebhook) -> None:
        response = requests.post(
            webhook.url, json=webhook.payload, timeout=settings.webhook_timeout_seconds
        )
        response.raise_for_status()
