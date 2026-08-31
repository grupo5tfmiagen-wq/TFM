"""Modelo ORM para la tabla `job_postings`: ofertas laborales a las que aplican los candidatos.

Almacena la información estructurada de las ofertas de trabajo, incluyendo
requisitos, habilidades y condiciones. Permite relacionar múltiples casos
(candidaturas) con una misma oferta.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base

if TYPE_CHECKING:
    from .case import Case


class JobPosting(Base):
    __tablename__ = "job_postings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    external_id: Mapped[str] = mapped_column(String(150), unique=True, nullable=False, index=True)
    titulo: Mapped[str] = mapped_column(String(300), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Requisitos estructurados
    requisitos_minimos: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    requisitos_deseables: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    habilidades_requeridas: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    idiomas_requeridos: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    
    # Criterios de filtrado
    experiencia_minima_anios: Mapped[int | None] = mapped_column(Integer, nullable=True)
    formacion_minima: Mapped[str | None] = mapped_column(String(200), nullable=True)
    
    # Condiciones laborales
    ubicacion: Mapped[str | None] = mapped_column(String(200), nullable=True)
    tipo_contrato: Mapped[str | None] = mapped_column(String(100), nullable=True)
    salario_min: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    salario_max: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    
    # Estado y fechas
    activa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    fecha_publicacion: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fecha_cierre: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relaciones
    cases: Mapped[list["Case"]] = relationship(back_populates="job_posting")
