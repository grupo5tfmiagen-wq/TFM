"""Script de ejemplo para cargar ofertas laborales en la base de datos.

Uso:
    python scripts/load_job_posting.py
"""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.db.base import SessionLocal
from src.db.models import JobPosting


def crear_oferta_ejemplo() -> None:
    """Crea una oferta laboral de ejemplo para testing."""
    db = SessionLocal()
    try:
        # Verificar si ya existe
        existing = db.query(JobPosting).filter(
            JobPosting.external_id == "puesto-backend-senior-2026"
        ).first()
        
        if existing:
            print(f"La oferta 'puesto-backend-senior-2026' ya existe (ID: {existing.id})")
            return
        
        oferta = JobPosting(
            external_id="puesto-backend-senior-2026",
            titulo="Backend Senior - Python y Sistemas Distribuidos",
            descripcion="""
            Buscamos un/a ingeniero/a de software senior con experiencia en desarrollo backend
            para unirse a nuestro equipo de plataforma. Trabajarás en el diseño e implementación
            de APIs REST, microservicios y sistemas distribuidos de alta disponibilidad.
            """.strip(),
            requisitos_minimos={
                "experiencia_anios": 5,
                "formacion": "Grado en Ingeniería Informática o similar",
                "habilidades_obligatorias": ["Python", "PostgreSQL", "Docker", "Git"],
                "idiomas": [{"idioma": "Inglés", "nivel": "B2"}],
            },
            requisitos_deseables={
                "habilidades_valorables": ["Kubernetes", "Redis", "RabbitMQ", "AWS"],
                "experiencia_sector": "Experiencia en sistemas de control o instrumentación",
            },
            habilidades_requeridas=["Python", "PostgreSQL", "Docker", "Git", "Linux"],
            idiomas_requeridos=[
                {"idioma": "Español", "nivel": "nativo"},
                {"idioma": "Inglés", "nivel": "B2"},
            ],
            experiencia_minima_anios=5,
            formacion_minima="Grado en Ingeniería Informática",
            ubicacion="Tenerife, España (híbrido)",
            tipo_contrato="Indefinido",
            salario_min=45000,
            salario_max=55000,
            activa=True,
            fecha_publicacion=datetime.now(timezone.utc),
        )
        
        db.add(oferta)
        db.commit()
        db.refresh(oferta)
        
        print(f"✓ Oferta creada exitosamente:")
        print(f"  ID: {oferta.id}")
        print(f"  External ID: {oferta.external_id}")
        print(f"  Título: {oferta.titulo}")
        
    finally:
        db.close()


if __name__ == "__main__":
    crear_oferta_ejemplo()
