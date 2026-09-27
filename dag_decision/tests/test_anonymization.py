"""Tests unitarios de `src/graph/anonymization.py` (datos que salen hacia el LLM)."""
from datetime import date

from src.graph.anonymization import NAME_PLACEHOLDER, candidate_view_for_llm, redact_text


CANDIDATE = {
    "id": "cand-001",
    "name": "Marina Etxeberria Zubizarreta",
    "cv": {
        "original_format": "pdf",
        "language": "es",
        "extracted_text": (
            "Marina Etxeberria Zubizarreta\n"
            "Bilbao · marina.etxeberria@correo-ejemplo.com · +34 600 000 000 · linkedin.com/in/marina\n"
            "Ingeniera de software. Licenciada en 1986 por la Universidad Complutense."
        ),
        "experience": [
            {"company": "IAC", "role": "Tech Lead", "start_date": "2015-03", "end_date": "present", "description": "Lidera el equipo."},
            {"company": "Empresa B", "role": "Backend", "start_date": "2005-01", "end_date": "2015-02", "description": "Servicios Python."},
        ],
        "education": [{"degree": "Licenciatura en Ingeniería Informática", "institution": "Universidad Complutense de Madrid", "end_year": 1986}],
        "technical_skills": ["Python", "Docker"],
        "languages": [{"language": "Inglés", "level": "C1"}],
        "certifications": ["CKA"],
    },
}


def test_redact_text_removes_name_contact_and_years():
    text = redact_text(CANDIDATE["cv"]["extracted_text"], CANDIDATE["name"])
    for personal in ("Marina", "Etxeberria", "Zubizarreta", "@correo-ejemplo.com", "600 000 000", "linkedin", "1986"):
        assert personal not in text
    assert NAME_PLACEHOLDER in text
    assert "Ingeniera de software" in text


def test_redact_text_does_not_remove_name_particles_elsewhere():
    text = redact_text("Experiencia de la empresa", "Ana de la Fuente")
    assert text == "Experiencia de la empresa"


def test_view_excludes_identity_dates_and_institution():
    view = candidate_view_for_llm(CANDIDATE, today=date(2026, 9, 1))
    rendered = str(view)
    for personal in ("cand-001", "Marina", "Complutense", "1986", "2015-03", "2005-01"):
        assert personal not in rendered
    assert "id" not in view and "name" not in view


def test_view_keeps_information_needed_for_the_assessment():
    view = candidate_view_for_llm(CANDIDATE, today=date(2026, 9, 1))
    cv = view["cv"]
    assert cv["technical_skills"] == ["Python", "Docker"]
    assert cv["languages"] == [{"language": "Inglés", "level": "C1"}]
    assert cv["certifications"] == ["CKA"]
    assert cv["education"] == [{"degree": "Licenciatura en Ingeniería Informática"}]
    assert cv["experience"][0] == {
        "role": "Tech Lead", "company": "IAC", "duration_years": 11.5, "current": True, "description": "Lidera el equipo.",
    }
    assert cv["experience"][1]["duration_years"] == 10.1
    assert cv["experience"][1]["current"] is False


def test_view_does_not_modify_original_payload():
    original = str(CANDIDATE)
    candidate_view_for_llm(CANDIDATE)
    assert str(CANDIDATE) == original


def test_view_handles_empty_candidate():
    assert candidate_view_for_llm(None)["cv"]["experience"] == []
