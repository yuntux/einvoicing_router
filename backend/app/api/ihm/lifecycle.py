from fastapi import APIRouter

from app.schemas.lifecycle import LifecycleCatalogRead, StatusCatalogEntry
from app.services.lifecycle_catalog import ACTIONS, REASONS, STATUS_CATALOG

router = APIRouter()


@router.get("", response_model=LifecycleCatalogRead)
def get_lifecycle_catalog():
    """Expose le catalogue de statuts (§ 4.2) pour que l'IHM construise un formulaire
    dynamique sans dupliquer les règles métier côté frontend."""
    return LifecycleCatalogRead(
        statuses=[
            StatusCatalogEntry(
                key=key,
                label=info.label,
                cdar_code=info.cdar_code,
                mdt88_code=info.mdt88_code,
                manual_side=info.manual_side,
                requires_detail=info.requires_detail,
                requires_confirmation=info.requires_confirmation,
            )
            for key, info in STATUS_CATALOG.items()
        ],
        reasons=REASONS,
        actions=ACTIONS,
    )
