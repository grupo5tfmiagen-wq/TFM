"""Modelo ORM para la tabla `llm_decisions`: salidas del módulo LLM Decision Nodes."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base

if TYPE_CHECKING:
    from .node_execution import CaseNodeExecution
    from .validation import Validation


class LlmDecision(Base):
    __tablename__ = "llm_decisions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    node_execution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("case_node_executions.id"), nullable=False
    )
    model_name: Mapped[str] = mapped_column(String(150), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    raw_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    structured_output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    node_execution: Mapped["CaseNodeExecution"] = relationship(back_populates="llm_decisions")
    validations: Mapped[list["Validation"]] = relationship(back_populates="llm_decision")
