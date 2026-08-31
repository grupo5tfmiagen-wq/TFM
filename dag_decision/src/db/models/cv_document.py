"""Modelo ORM para la tabla `cv_documents`: CVs convertidos de PDF a JSON estructurado.

Almacena los currículums procesados por el script de conversión, incluyendo
tanto el texto extraído como los datos estructurados (experiencia, formación,
habilidades, etc.). Un mismo CV puede usarse en múltiples casos (aplicaciones
a diferentes ofertas).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base

if TYPE_CHECKING:
    from .case import Case


class CVDocument(Base):
    __tablename__ = "cv_documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Identificación del candidato
    candidate_id: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    candidate_name: Mapped[str] = mapped_column(String(300), nullable=False)
    
    # Metadatos del documento original
    original_filename: Mapped[str | None] = mapped_column(String(500), nullable=True)
    original_format: Mapped[str | None] = mapped_column(String(50), nullable=True)
    idioma: Mapped[str | None] = mapped_column(String(10), nullable=True)
    
    # Contenido extraído
    texto_extraido: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Datos estructurados (JSONB para flexibilidad)
    experiencia: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    formacion: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    habilidades_tecnicas: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    idiomas: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    certificaciones: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    
    # JSON completo original por si hay campos adicionales
    raw_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relaciones
    cases: Mapped[list["Case"]] = relationship(back_populates="cv_document")
