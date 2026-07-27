"""Modelo ORM para la tabla `dag_definitions`.

La topología del DAG en sí se define en código Python mediante el
`StateGraph` de LangGraph, no se gestiona desde la base de datos. Esta tabla
solo guarda un registro documental opcional (nombre/versión/descripción y
una exportación JSON opcional del grafo compilado) para trazabilidad en la
memoria.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class DagDefinition(Base):
    __tablename__ = "dag_definitions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    graph_export: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
