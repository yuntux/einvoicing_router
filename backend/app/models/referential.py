"""Référentiel, applications cibles et accès (spec.md § 6.1 / § 7.1.1)."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Company(Base):
    """Entreprise gérée (spec.md § 6.1)."""

    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    siren: Mapped[str] = mapped_column(String(9), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
