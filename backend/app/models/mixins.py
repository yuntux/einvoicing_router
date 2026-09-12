"""Traçabilité "qui/quand" portée par la ligne elle-même (spec.md § NF9) —
complémentaire à `AuditLog` (`app.models.audit`), pas un remplacement : ce mixin ne
garde qu'un instantané (qui a créé/modifié cette ligne, et quand), pas l'historique
des actions intermédiaires ni les suppressions. `AuditLog` reste la seule source pour
un historique complet ; ces colonnes servent à un affichage rapide sur la fiche
elle-même (« créé par ... le ... »), sans jointure sur le journal.

`create_user_id`/`write_user_id` restent `None` pour une ligne créée par le système
plutôt que par un utilisateur IHM (ex. `PartnerDirectory` détecté à la réception
d'une facture) ou hors authentification (`settings.oidc_mode == "disabled"`, § NF3)."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column


class AuditColumnsMixin:
    create_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    create_datetime: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    write_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    write_datetime: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
