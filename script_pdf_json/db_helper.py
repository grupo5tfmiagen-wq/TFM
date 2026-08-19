"""Utilidades para guardar CVs y ofertas laborales en la base de datos.

Proporciona funciones para insertar o actualizar registros en las tablas
cv_documents y job_postings, y crear casos relacionados.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

# Añadir el path del proyecto dag_decision para importar los modelos
sys.path.insert(0, str(Path(__file__).parent.parent / "dag_decision"))

from src.db.base import SessionLocal
from src.db.models import CVDocument, JobPosting, Case


def guardar_cv_en_bbdd(caso_json: dict) -> uuid.UUID:
    """Guarda el CV del caso en la tabla cv_documents.
    
    Args:
        caso_json: Diccionario con la estructura del caso generada por cv_to_json_openai.py
        
    Returns:
        UUID del CV document creado
    """
    candidato = caso_json["candidato"]
    cv_data = candidato["cv"]
    
    db = SessionLocal()
    try:
        cv_doc = CVDocument(
            candidate_id=candidato["id"],
            candidate_name=candidato["nombre"],
            original_filename=caso_json["metadata"]["origen"].replace("pdf:", ""),
            original_format=cv_data["formato_original"],
            idioma=cv_data["idioma"],
            texto_extraido=cv_data["texto_extraido"],
            experiencia=cv_data["experiencia"],
            formacion=cv_data["formacion"],
            habilidades_tecnicas=cv_data["habilidades_tecnicas"],
            idiomas=cv_data["idiomas"],
            certificaciones=cv_data["certificaciones"],
            raw_json=cv_data,  # Guardar el JSON completo por si hay campos extra
        )
        db.add(cv_doc)
        db.commit()
        db.refresh(cv_doc)
        return cv_doc.id
    finally:
        db.close()


def buscar_o_crear_oferta(puesto_id: str, db=None) -> uuid.UUID:
    """Busca una oferta laboral por external_id o la crea si no existe.
    
    Args:
        puesto_id: ID externo de la oferta (ej. "puesto-backend-senior-2026")
        db: Sesión de base de datos opcional (si no se proporciona, crea una nueva)
        
    Returns:
        UUID de la oferta laboral
    """
    should_close = db is None
    if db is None:
        db = SessionLocal()
    
    try:
        # Buscar oferta existente
        oferta = db.query(JobPosting).filter(JobPosting.external_id == puesto_id).first()
        
        if oferta is None:
            # Crear oferta básica si no existe
            # En producción, esto debería cargarse desde una fuente de datos real
            oferta = JobPosting(
                external_id=puesto_id,
                titulo=f"Puesto {puesto_id}",  # Placeholder
                descripcion="Oferta creada automáticamente desde conversión de CV",
                activa=True,
            )
            db.add(oferta)
            db.commit()
            db.refresh(oferta)
        
        return oferta.id
    finally:
        if should_close:
            db.close()


def crear_caso_en_bbdd(caso_json: dict, cv_document_id: uuid.UUID, job_posting_id: uuid.UUID) -> uuid.UUID:
    """Crea un caso en la tabla cases relacionado con el CV y la oferta.
    
    Args:
        caso_json: Diccionario con la estructura del caso
        cv_document_id: UUID del CV document
        job_posting_id: UUID de la oferta laboral
        
    Returns:
        UUID del caso creado
    """
    db = SessionLocal()
    try:
        caso = Case(
            case_type="cv_evaluation",
            status="pending",
            payload=caso_json,
            cv_document_id=cv_document_id,
            job_posting_id=job_posting_id,
        )
        db.add(caso)
        db.commit()
        db.refresh(caso)
        return caso.id
    finally:
        db.close()


def guardar_caso_completo(caso_json: dict) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Guarda un caso completo: CV, oferta y caso relacionados.
    
    Args:
        caso_json: Diccionario con la estructura del caso generada por cv_to_json_openai.py
        
    Returns:
        Tupla con (cv_document_id, job_posting_id, case_id)
    """
    # Guardar CV
    cv_id = guardar_cv_en_bbdd(caso_json)
    
    # Buscar o crear oferta
    puesto_id = caso_json["puesto_id"]
    oferta_id = buscar_o_crear_oferta(puesto_id)
    
    # Crear caso
    caso_id = crear_caso_en_bbdd(caso_json, cv_id, oferta_id)
    
    return cv_id, oferta_id, caso_id
