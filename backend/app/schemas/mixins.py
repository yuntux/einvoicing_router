"""Contrepartie schéma de `app.models.mixins.AuditColumnsMixin` — exposée par les
schémas `*Read` qui en héritent, pour affichage éventuel côté IHM (« créé par ... le
... »). Les emails ne sont pas résolus ici (cf. `app.api.ihm.audit` pour le pattern
de résolution par jointure) : seuls les identifiants bruts sont exposés."""

from datetime import datetime

from pydantic import BaseModel


class AuditColumnsRead(BaseModel):
    create_user_id: int | None
    create_datetime: datetime
    write_user_id: int | None
    write_datetime: datetime
