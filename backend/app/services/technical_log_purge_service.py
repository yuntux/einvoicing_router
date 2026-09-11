"""Purge de `TechnicalLog` selon `RouterSettings.technical_log_retention_days`
(spec.md § 6.1, lot 8) — 15 ans par défaut, sans remise en cause du mécanisme si la
durée est amenée à changer (paramétrable depuis l'IHM, cf. § 4.9.1/settings)."""

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.audit import TechnicalLog
from app.services import router_settings_service


def purge_technical_logs(db: Session, *, now: datetime | None = None) -> int:
    now = now or datetime.utcnow()
    router_settings = router_settings_service.get_settings(db)
    cutoff = now - timedelta(days=router_settings.technical_log_retention_days)

    deleted = (
        db.query(TechnicalLog)
        .filter(TechnicalLog.created_at < cutoff)
        .delete(synchronize_session=False)
    )
    db.commit()
    return deleted
