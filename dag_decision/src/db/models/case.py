"""Modelo ORM para la tabla `cases`: el estado de negocio persistido de cada caso.

Es la contrapartida consultable y legible del concepto "Estado del Caso" del
documento de arquitectura. Es intencionadamente más simple que el estado
completo de checkpoint de LangGraph: guarda los campos necesarios para
informes y consultas entre casos, no una instantánea completa reproducible.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base

if TYPE_CHECKING:
    from .cv_document import CVDocument
    from .final_decision import FinalDecision
    from .human_escalation import HumanEscalation
    from .job_posting import JobPosting
    from .node_execution import CaseNodeExecution


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    current_node_key: Mapped[str | None] = mapped_column(String(150), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    
    # Foreign keys a CV y oferta laboral
    cv_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cv_documents.id"), nullable=True
    )
    job_posting_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job_postings.id"), nullable=True
    )
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relaciones
    cv_document: Mapped["CVDocument | None"] = relationship(back_populates="cases")
    job_posting: Mapped["JobPosting | None"] = relationship(back_populates="cases")
    node_executions: Mapped[list["CaseNodeExecution"]] = relationship(back_populates="case")
    human_escalations: Mapped[list["HumanEscalation"]] = relationship(back_populates="case")
    final_decision: Mapped["FinalDecision | None"] = relationship(back_populates="case")
