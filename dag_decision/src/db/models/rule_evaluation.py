"""Modelo ORM para la tabla `rule_evaluations`: resultados del módulo Rule Evaluator."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base

if TYPE_CHECKING:
    from .node_execution import CaseNodeExecution


class RuleEvaluation(Base):
    __tablename__ = "rule_evaluations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    node_execution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("case_node_executions.id"), nullable=False
    )
    rule_name: Mapped[str] = mapped_column(String(150), nullable=False)
    result_bool: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    score: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    label: Mapped[str | None] = mapped_column(String(150), nullable=True)
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    node_execution: Mapped["CaseNodeExecution"] = relationship(back_populates="rule_evaluations")
