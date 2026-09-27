"""Comprobacion determinista de los requisitos obligatorios de idioma y formacion.

Complementa las dos reglas originales de `rule_evaluator_node` (habilidades
tecnicas y anos de experiencia). Las funciones son puras (sin BD ni LLM) para
poder probarlas de forma aislada.

Criterio comun: un requisito solo descarta al candidato cuando se puede
comprobar con certeza que NO lo cumple. Si el dato no se puede interpretar
(p. ej. un nivel de idioma "fluido" o un titulo que no encaja en ningun
nivel conocido), el requisito se marca como "no verificable" en lugar de
rechazar: una regla automatica no debe descartar a nadie por un dato mal
extraido del CV. Los requisitos no verificables fuerzan la revision humana
(ver `validation_node`).
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

# ---------------------------------------------------------------------------
# Idiomas
# ---------------------------------------------------------------------------

# Niveles del Marco Comun Europeo de Referencia (MCER), de menor a mayor.
# "nativo"/"bilingue" se situan por encima de C2.
_CEFR_RANK = {"A1": 1, "A2": 2, "B1": 3, "B2": 4, "C1": 5, "C2": 6}
_NATIVE_LEVELS = {"nativo", "nativa", "native", "bilingue", "bilingual", "lengua materna", "mother tongue"}
_NATIVE_RANK = 7

# Nombres de idioma en espanol normalizados a su nombre en ingles, para poder
# comparar CVs y ofertas que vienen en idiomas distintos (el catalogo de la
# demo esta en espanol; los JSON de `data/` en ingles).
_LANGUAGE_ALIASES = {
    "ingles": "english",
    "espanol": "spanish",
    "castellano": "spanish",
    "frances": "french",
    "aleman": "german",
    "italiano": "italian",
    "portugues": "portuguese",
    "catalan": "catalan",
    "euskera": "basque",
    "vasco": "basque",
    "gallego": "galician",
    "chino": "chinese",
    "japones": "japanese",
    "arabe": "arabic",
    "ruso": "russian",
}


def _normalize_text(value: str | None) -> str:
    """Minusculas, sin tildes y sin espacios sobrantes."""
    if not value:
        return ""
    decomposed = unicodedata.normalize("NFKD", str(value))
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(without_accents.lower().split())


def normalize_language(name: str | None) -> str:
    """Nombre de idioma canonico (en ingles, minusculas): "Inglés" -> "english"."""
    normalized = _normalize_text(name)
    return _LANGUAGE_ALIASES.get(normalized, normalized)


def language_level_rank(level: str | None) -> int | None:
    """Posicion ordinal de un nivel de idioma, o `None` si no se puede interpretar.

    Acepta niveles MCER ("B2", "b2", "C1 - avanzado") y nativo/bilingue.
    """
    normalized = _normalize_text(level)
    if not normalized:
        return None
    if normalized in _NATIVE_LEVELS:
        return _NATIVE_RANK
    code = normalized[:2].upper()
    return _CEFR_RANK.get(code)


def check_languages(required: list[dict[str, Any]], candidate: list[dict[str, Any]]) -> dict[str, Any]:
    """Comprueba los idiomas obligatorios de la oferta frente a los del CV.

    `required` usa la forma del payload del grafo (`{"language", "min_level"}`)
    y `candidate` la del CV (`{"language", "level"}`).

    Devuelve `{"met", "missing", "unverified"}`:
    - `missing`: idiomas que el candidato no tiene o con nivel insuficiente
      (descartan al candidato).
    - `unverified`: idiomas cuyo nivel no se puede interpretar (fuerzan
      revision humana, no descartan).
    """
    candidate_levels: dict[str, str | None] = {}
    for entry in candidate or []:
        language = normalize_language(entry.get("language"))
        if language:
            candidate_levels[language] = entry.get("level")

    missing: list[dict[str, Any]] = []
    unverified: list[dict[str, Any]] = []
    for requirement in required or []:
        language = normalize_language(requirement.get("language"))
        if not language:
            continue
        required_level = requirement.get("min_level")
        required_rank = language_level_rank(required_level)
        if language not in candidate_levels:
            missing.append({"language": language, "required": required_level, "candidate": None})
            continue
        candidate_level = candidate_levels[language]
        candidate_rank = language_level_rank(candidate_level)
        if required_rank is None or candidate_rank is None:
            unverified.append({"language": language, "required": required_level, "candidate": candidate_level})
        elif candidate_rank < required_rank:
            missing.append({"language": language, "required": required_level, "candidate": candidate_level})

    return {"met": not missing, "missing": missing, "unverified": unverified}


# ---------------------------------------------------------------------------
# Formacion
# ---------------------------------------------------------------------------

EDUCATION_LEVEL_NAMES = {
    1: "educacion secundaria",
    2: "formacion profesional",
    3: "titulo universitario (grado o equivalente)",
    4: "master",
    5: "doctorado",
}

# Palabras clave por nivel, en espanol e ingles, ya normalizadas (sin tildes).
# Se buscan como palabras completas y en este orden: primero los niveles
# altos (asi "Master en Ingenieria" es master y no grado) y la formacion
# profesional antes que el grado universitario, porque los titulos de FP
# contienen la palabra "grado" ("Ciclo Formativo de Grado Superior").
_EDUCATION_KEYWORDS: list[tuple[int, tuple[str, ...]]] = [
    (5, ("doctorado", "doctor", "doctora", "phd", "ph.d", "doctoral")),
    (4, ("master", "msc", "m.sc", "mba", "maestria", "posgrado", "postgrado", "postgraduate")),
    (2, (
        "formacion profesional", "ciclo formativo", "grado superior", "grado medio",
        "tecnico superior", "fp", "vocational", "associate degree",
    )),
    (3, (
        "grado", "licenciatura", "licenciado", "licenciada", "ingenieria", "ingeniero",
        "ingeniera", "diplomatura", "diplomado", "diplomada", "arquitectura",
        "bachelor", "bachelors", "bsc", "b.sc", "degree", "universitario", "universitaria",
    )),
    (1, ("bachillerato", "eso", "high school", "secondary", "secundaria")),
]
_EDUCATION_PATTERNS = [
    (level, [re.compile(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])") for keyword in keywords])
    for level, keywords in _EDUCATION_KEYWORDS
]


def education_level(title: str | None) -> int | None:
    """Nivel ordinal de un titulo o de un requisito de formacion, o `None`.

    Solo se clasifica el NIVEL (grado, master...), no la disciplina: saber si
    "Ingenieria de Telecomunicaciones" es "equivalente" a "Ingenieria
    Informatica" es un juicio que se deja al LLM y al revisor humano.
    """
    normalized = _normalize_text(title)
    if not normalized:
        return None
    for level, patterns in _EDUCATION_PATTERNS:
        if any(pattern.search(normalized) for pattern in patterns):
            return level
    return None


def check_education(min_education: str | None, education: list[dict[str, Any]]) -> dict[str, Any]:
    """Comprueba que el candidato tiene al menos el nivel de formacion exigido.

    Devuelve `{"met", "required_level", "candidate_level", "unverified", "reason"}`.
    Si la oferta no exige formacion, se considera cumplido. Si no se puede
    interpretar el requisito o ningun titulo del candidato, el requisito
    queda como no verificable (no descarta, fuerza revision humana).
    """
    if not min_education:
        return {"met": True, "required_level": None, "candidate_level": None, "unverified": False, "reason": None}

    required_level = education_level(min_education)
    if required_level is None:
        return {
            "met": True,
            "required_level": None,
            "candidate_level": None,
            "unverified": True,
            "reason": f"No se reconoce el nivel del requisito de formacion: {min_education!r}",
        }

    degrees = [entry.get("degree") for entry in education or [] if entry.get("degree")]
    if not degrees:
        return {
            "met": False,
            "required_level": EDUCATION_LEVEL_NAMES[required_level],
            "candidate_level": None,
            "unverified": False,
            "reason": "El CV no incluye ninguna titulacion.",
        }

    candidate_levels = [level for level in (education_level(degree) for degree in degrees) if level is not None]
    if not candidate_levels:
        return {
            "met": True,
            "required_level": EDUCATION_LEVEL_NAMES[required_level],
            "candidate_level": None,
            "unverified": True,
            "reason": f"No se reconoce el nivel de las titulaciones del CV: {degrees}",
        }

    best = max(candidate_levels)
    met = best >= required_level
    return {
        "met": met,
        "required_level": EDUCATION_LEVEL_NAMES[required_level],
        "candidate_level": EDUCATION_LEVEL_NAMES[best],
        "unverified": False,
        "reason": None if met else "Nivel de formacion inferior al exigido.",
    }
