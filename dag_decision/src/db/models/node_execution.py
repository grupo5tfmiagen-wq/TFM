"""Modelo ORM para la tabla `case_node_executions`.

Una fila por cada nodo ejecutado por el motor DAG para un caso dado: qué
entró, qué salió y cuándo. Es la columna vertebral de la capa de
trazabilidad (quién hizo qué, en qué orden) que complementa los propios
checkpoints de LangGraph.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base

if TYPE_CHECKING:
    from .case import Case
    from .human_escalation import HumanEscalation
    from .llm_decision import LlmDecision
    from .rule_evaluation import RuleEvaluation
    from .validation import Validation


class CaseNodeExecution(Base):
    __tablename__ = "case_node_executions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id"), nullable=False)
    node_key: Mapped[str] = mapped_column(String(150), nullable=False)
    input_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    output_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    case: Mapped["Case"] = relationship(back_populates="node_executions")
    rule_evaluations: Mapped[list["RuleEvaluation"]] = relationship(back_populates="node_execution")
    llm_decisions: Mapped[list["LlmDecision"]] = relationship(back_populates="node_execution")
    validations: Mapped[list["Validation"]] = relationship(back_populates="node_execution")
    human_escalations: Mapped[list["HumanEscalation"]] = relationship(back_populates="node_execution")
