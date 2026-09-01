"""Tests del adaptador ES->EN (`src/graph/payload_builder.py`).

No tocan Postgres: los `CVDocument`/`JobPosting` se instancian en memoria,
sin pasar por una sesion (igual que el resto de tests unitarios del
proyecto, ver `conftest.py`).
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.db.models.cv_document import CVDocument  # noqa: E402
from src.db.models.job_posting import JobPosting  # noqa: E402
from src.graph.payload_builder import (  # noqa: E402
    build_case_payload,
    cv_document_to_candidate,
    job_posting_to_job_profile,
)


def _cv(**overrides) -> CVDocument:
    defaults = dict(
        candidate_id="cand-001",
        candidate_name="Marta Suárez Delgado",
        original_format="pdf",
        idioma="es",
        texto_extraido="...",
        experiencia=[
            {
                "empresa": "Observatorio Técnico Atlántico",
                "puesto": "Ingeniera de Software",
                "fecha_inicio": "2023-07",
                "fecha_fin": "actualidad",
                "descripcion": "Control de instrumentacion cientifica.",
            }
        ],
        formacion=[{"titulo": "Grado en Ingeniería Informática", "institucion": "ULL", "anio_fin": 2019}],
        habilidades_tecnicas=["Python", "Docker"],
        idiomas=[{"idioma": "Español", "nivel": "nativo"}],
        certificaciones=[],
    )
    defaults.update(overrides)
    return CVDocument(**defaults)


def _job(**overrides) -> JobPosting:
    defaults = dict(
        external_id="job-backend-senior-2026",
        titulo="Senior Backend Engineer",
        descripcion="...",
        requisitos_minimos={
            "experiencia_anios": 5,
            "formacion": "Grado en Ingeniería Informática",
            "habilidades_obligatorias": ["Python", "PostgreSQL"],
            "idiomas": [{"idioma": "Inglés", "nivel": "B2"}],
        },
        requisitos_deseables={
            "habilidades_valorables": ["Kubernetes"],
            "experiencia_sector": "astrofisica",
        },
        habilidades_requeridas=["Python", "PostgreSQL"],
        idiomas_requeridos=[{"idioma": "Inglés", "nivel": "B2"}],
        experiencia_minima_anios=5,
        formacion_minima="Grado en Ingeniería Informática",
    )
    defaults.update(overrides)
    return JobPosting(**defaults)


def test_cv_document_to_candidate_maps_fields():
    candidate = cv_document_to_candidate(_cv())

    assert candidate["id"] == "cand-001"
    assert candidate["name"] == "Marta Suárez Delgado"
    assert candidate["cv"]["technical_skills"] == ["Python", "Docker"]
    assert candidate["cv"]["languages"] == [{"language": "Español", "level": "nativo"}]
    assert candidate["cv"]["education"] == [
        {"degree": "Grado en Ingeniería Informática", "institution": "ULL", "end_year": 2019}
    ]


def test_cv_document_maps_actualidad_to_present():
    candidate = cv_document_to_candidate(_cv())

    assert candidate["cv"]["experience"][0]["end_date"] == "present"
    assert candidate["cv"]["experience"][0]["start_date"] == "2023-07"


def test_cv_document_handles_missing_optional_fields():
    cv = _cv(experiencia=None, formacion=None, idiomas=None, certificaciones=None, habilidades_tecnicas=None)

    candidate = cv_document_to_candidate(cv)

    assert candidate["cv"]["experience"] == []
    assert candidate["cv"]["education"] == []
    assert candidate["cv"]["languages"] == []
    assert candidate["cv"]["technical_skills"] == []
    assert candidate["cv"]["certifications"] == []


def test_job_posting_to_job_profile_reads_nested_jsonb():
    job_profile = job_posting_to_job_profile(_job())

    assert job_profile["job_id"] == "job-backend-senior-2026"
    assert job_profile["mandatory_requirements"] == {
        "min_years_experience": 5,
        "min_education": "Grado en Ingeniería Informática",
        "technical_skills": ["Python", "PostgreSQL"],
        "languages": [{"language": "Inglés", "min_level": "B2"}],
    }
    assert job_profile["desired_requirements"] == {
        "technical_skills": ["Kubernetes"],
        "industry_experience": ["astrofisica"],
        "certifications": [],
    }


def test_job_posting_falls_back_to_top_level_columns_when_jsonb_missing_keys():
    job = _job(requisitos_minimos={}, requisitos_deseables=None)

    job_profile = job_posting_to_job_profile(job)

    assert job_profile["mandatory_requirements"]["min_years_experience"] == 5
    assert job_profile["mandatory_requirements"]["technical_skills"] == ["Python", "PostgreSQL"]
    assert job_profile["mandatory_requirements"]["languages"] == [{"language": "Inglés", "min_level": "B2"}]
    assert job_profile["desired_requirements"]["technical_skills"] == []
    assert job_profile["desired_requirements"]["industry_experience"] == []


def test_build_case_payload_combines_both_blocks():
    payload = build_case_payload(_cv(), _job())

    assert set(payload.keys()) == {"candidate", "job_profile"}
    assert payload["candidate"]["id"] == "cand-001"
    assert payload["job_profile"]["job_id"] == "job-backend-senior-2026"
