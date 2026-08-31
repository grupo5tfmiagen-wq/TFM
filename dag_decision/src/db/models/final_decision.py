"""Modelo ORM para la tabla `final_decisions`: la decisión oficial de cierre de cada caso."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base

if TYPE_CHECKING:
    from .case import Case


class FinalDecision(Base):
    __tablename__ = "final_decisions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id"), nullable=False, unique=True
    )
    outcome: Mapped[str] = mapped_column(String(100), nullable=False)
    consolidated_from: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    decided_by: Mapped[str | None] = mapped_column(String(150), nullable=True)

    case: Mapped["Case"] = relationship(back_populates="final_decision")
