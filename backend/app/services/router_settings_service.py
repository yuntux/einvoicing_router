"""RouterSettingsService — configuration générale du routeur, instance unique
(spec.md § 6.1)."""

from sqlalchemy.orm import Session

from app.models.settings import RouterSettings

SETTINGS_ID = 1


def get_settings(db: Session) -> RouterSettings:
    settings_row = db.get(RouterSettings, SETTINGS_ID)
    if settings_row is None:
        settings_row = RouterSettings(id=SETTINGS_ID)
        db.add(settings_row)
        db.commit()
        db.refresh(settings_row)
    return settings_row


def update_settings(db: Session, **fields) -> RouterSettings:
    settings_row = get_settings(db)
    for key, value in fields.items():
        if value is not None:
            setattr(settings_row, key, value)
    db.commit()
    db.refresh(settings_row)
    return settings_row
