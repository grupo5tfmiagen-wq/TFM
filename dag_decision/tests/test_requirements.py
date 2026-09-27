"""Tests unitarios de `src/graph/requirements.py` (idiomas y formacion)."""
import pytest

from src.graph.requirements import (
    check_education,
    check_languages,
    education_level,
    language_level_rank,
    normalize_language,
)


@pytest.mark.parametrize(
    "name, expected",
    [("Inglés", "english"), ("ingles", "english"), ("English", "english"), ("Castellano", "spanish"), ("Español", "spanish")],
)
def test_normalize_language(name, expected):
    assert normalize_language(name) == expected


@pytest.mark.parametrize(
    "level, expected",
    [("A1", 1), ("b2", 4), ("C1 - avanzado", 5), ("C2", 6), ("nativo", 7), ("Bilingüe", 7), ("fluido", None), (None, None)],
)
def test_language_level_rank(level, expected):
    assert language_level_rank(level) == expected


def test_languages_met_when_level_is_equal_or_higher():
    result = check_languages([{"language": "inglés", "min_level": "B2"}], [{"language": "English", "level": "C1"}])
    assert result == {"met": True, "missing": [], "unverified": []}


def test_languages_missing_when_level_is_lower():
    result = check_languages([{"language": "english", "min_level": "B2"}], [{"language": "english", "level": "B1"}])
    assert result["met"] is False
    assert result["missing"] == [{"language": "english", "required": "B2", "candidate": "B1"}]


def test_languages_missing_when_candidate_lacks_language():
    result = check_languages([{"language": "english", "min_level": "B2"}], [{"language": "spanish", "level": "nativo"}])
    assert result["met"] is False
    assert result["missing"][0]["candidate"] is None


def test_languages_unverified_when_level_cannot_be_parsed():
    result = check_languages([{"language": "english", "min_level": "B2"}], [{"language": "english", "level": "fluido"}])
    assert result["met"] is True
    assert result["unverified"] == [{"language": "english", "required": "B2", "candidate": "fluido"}]


def test_no_language_requirements_is_met():
    assert check_languages([], [])["met"] is True


@pytest.mark.parametrize(
    "title, expected",
    [
        ("Licenciatura en Ingeniería Informática", 3),
        ("Ingeniería Informática", 3),
        ("Ingeniero Técnico en Informática", 3),
        ("Grado en Ingeniería Informática o equivalente", 3),
        ("BSc in Computer Engineering", 3),
        ("Degree in Computer Science or equivalent", 3),
        ("Técnico Superior en DAM (Ciclo Formativo de Grado Superior)", 2),
        ("Máster en Inteligencia Artificial", 4),
        ("Posgrado en Ciencia de Datos", 4),
        ("PhD in Physics", 5),
        ("Doctora en Física", 5),
        ("Bachillerato", 1),
        ("Curso de procesos industriales", None),
        (None, None),
    ],
)
def test_education_level(title, expected):
    assert education_level(title) == expected


def test_education_met_with_equal_or_higher_level():
    result = check_education("Grado en Ingeniería Informática o equivalente", [{"degree": "Máster en IA"}])
    assert result["met"] is True
    assert result["unverified"] is False


def test_education_not_met_with_lower_level():
    result = check_education("Grado en Ingeniería Informática", [{"degree": "Técnico Superior (Ciclo Formativo de Grado Superior)"}])
    assert result["met"] is False


def test_education_not_met_without_degrees():
    assert check_education("Grado", [])["met"] is False


def test_education_unverified_when_degree_is_unrecognised():
    result = check_education("Grado", [{"degree": "Curso de procesos industriales"}])
    assert result["met"] is True
    assert result["unverified"] is True


def test_education_met_when_not_required():
    assert check_education(None, [])["met"] is True
