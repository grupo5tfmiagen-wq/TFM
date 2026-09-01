"""Adaptador que traduce los modelos ORM en español (`CVDocument`, `JobPosting`)
al `payload` en inglés que esperan `rule_evaluator_node`/`llm_decision_node`
(ver la forma documentada al inicio de `nodes.py`).

Las tablas `cv_documents`/`job_postings` guardan sus campos estructurados en
español (algunos, como `requisitos_minimos`/`requisitos_deseables`, en
columnas JSONB sin esquema forzado por la BD), mientras que el pipeline del
grafo se escribió contra las claves en inglés de `data/case.json` y
`data/job_profile.json`. Este módulo es el único punto que conoce ambas
formas a la vez.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..db.models.cv_document import CVDocument
    from ..db.models.job_posting import JobPosting


def _map_end_date(value: str | None) -> str | None:
    """`"actualidad"` (formato español de "puesto en curso") -> `"present"`."""
    return "present" if value == "actualidad" else value


def cv_document_to_candidate(cv: "CVDocument") -> dict[str, Any]:
    """Traduce un `CVDocument` al bloque `payload["candidate"]` esperado por el grafo."""
    experience = [
        {
            "company": entry.get("empresa"),
            "role": entry.get("puesto"),
            "start_date": entry.get("fecha_inicio"),
            "end_date": _map_end_date(entry.get("fecha_fin")),
            "description": entry.get("descripcion"),
        }
        for entry in (cv.experiencia or [])
    ]
    education = [
        {
            "degree": entry.get("titulo"),
            "institution": entry.get("institucion"),
            "end_year": entry.get("anio_fin"),
        }
        for entry in (cv.formacion or [])
    ]
    languages = [
        {"language": entry.get("idioma"), "level": entry.get("nivel")}
        for entry in (cv.idiomas or [])
    ]

    return {
        "id": cv.candidate_id,
        "name": cv.candidate_name,
        "cv": {
            "original_format": cv.original_format,
            "language": cv.idioma,
            "extracted_text": cv.texto_extraido,
            "experience": experience,
            "education": education,
            "technical_skills": list(cv.habilidades_tecnicas or []),
            "languages": languages,
            "certifications": list(cv.certificaciones or []),
        },
    }


def job_posting_to_job_profile(job: "JobPosting") -> dict[str, Any]:
    """Traduce un `JobPosting` al `payload["job_profile"]` esperado por el grafo.

    `requisitos_minimos`/`requisitos_deseables` son JSONB sin esquema
    validado por la BD, así que cada clave se lee de forma defensiva y, si
    falta, se recurre a la columna equivalente de nivel superior (rellenada
    por `scripts/load_job_posting.py`).
    """
    minimos = job.requisitos_minimos or {}
    deseables = job.requisitos_deseables or {}

    idiomas_minimos = minimos.get("idiomas") or job.idiomas_requeridos or []
    languages = [
        {"language": entry.get("idioma"), "min_level": entry.get("nivel")}
        for entry in idiomas_minimos
    ]

    industry_experience = deseables.get("experiencia_sector")
    if isinstance(industry_experience, str):
        industry_experience = [industry_experience]

    return {
        "job_id": job.external_id,
        "title": job.titulo,
        "description": job.descripcion,
        "mandatory_requirements": {
            "min_years_experience": minimos.get("experiencia_anios", job.experiencia_minima_anios),
            "min_education": minimos.get("formacion", job.formacion_minima),
            "technical_skills": list(
                minimos.get("habilidades_obligatorias") or job.habilidades_requeridas or []
            ),
            "languages": languages,
        },
        "desired_requirements": {
            "technical_skills": list(deseables.get("habilidades_valorables") or []),
            "industry_experience": industry_experience or [],
            "certifications": list(deseables.get("certificaciones") or []),
        },
    }


def build_case_payload(cv: "CVDocument", job: "JobPosting") -> dict[str, Any]:
    """Payload completo `{"candidate": ..., "job_profile": ...}` para un `Case` nuevo."""
    return {
        "candidate": cv_document_to_candidate(cv),
        "job_profile": job_posting_to_job_profile(job),
    }
