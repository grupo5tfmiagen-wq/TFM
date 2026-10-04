"""Minimizacion y anonimizacion de los datos del candidato antes de enviarlos al LLM.

`payload_builder.py` ya deja fuera del grafo el sexo y el ano de nacimiento,
pero el bloque `candidate` del payload sigue conteniendo datos que permiten
inferirlos o que no son necesarios para valorar el encaje con el puesto:

- el nombre (indicador de sexo y de origen; ver Wilson y Caliskan, 2024),
- el texto completo del CV, con el nombre, el correo, el telefono y fechas,
- los anos de fin de estudios y las fechas de cada empleo (indicadores de edad),
- la institucion educativa.

`candidate_view_for_llm` construye una vista reducida con solo lo necesario
para la evaluacion. El payload original del caso NO se modifica: se sigue
guardando completo en `cases.payload` para la interfaz y la auditoria; solo
cambia lo que sale hacia el proveedor del LLM (y lo que se guarda como
`prompt` en `llm_decisions`).

Limitacion conocida: no se neutraliza el genero gramatical del texto
("Ingeniera"/"Ingeniero"), que sigue siendo un indicador de sexo.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

NAME_PLACEHOLDER = "[CANDIDATO]"
EMAIL_PLACEHOLDER = "[EMAIL]"
PHONE_PLACEHOLDER = "[TELEFONO]"
YEAR_PLACEHOLDER = "[AÑO]"
URL_PLACEHOLDER = "[URL]"
INSTITUTION_PLACEHOLDER = "[INSTITUCION]"

# Particulas de apellidos que no deben tratarse como parte identificable del
# nombre por si solas (se redactarian en cualquier frase).
_NAME_STOPWORDS = {"de", "del", "la", "las", "los", "y", "i", "da", "do", "dos", "van", "von", "der", "di"}

# Palabras genericas de los nombres de instituciones que no identifican a
# ninguna en concreto y que no deben redactarse por si solas.
_GENERIC_INSTITUTION_WORDS = {
    "universidad", "university", "universitat", "universidade", "universite", "instituto",
    "institute", "institut", "escuela", "school", "college", "facultad", "faculty", "centro",
    "center", "centre", "superior", "tecnica", "technical", "nacional", "national", "estudios",
}

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_URL_RE = re.compile(r"(?:https?://|www\.)\S+|(?:linkedin|github)\.com/\S+", re.IGNORECASE)
# Telefonos: al menos 9 digitos, con prefijo internacional, espacios, puntos o guiones opcionales.
_PHONE_RE = re.compile(r"(?<!\w)(?:\+\d{1,3}[\s.-]?)?(?:\d[\s.-]?){8,}\d(?!\w)")
# Anos plausibles en un CV (1940-2039).
_YEAR_RE = re.compile(r"(?<!\d)(?:19[4-9]\d|20[0-3]\d)(?!\d)")


def _name_patterns(name: str | None) -> list[re.Pattern[str]]:
    """Patrones para el nombre completo y para cada parte significativa del nombre."""
    if not name:
        return []
    parts = [part for part in re.split(r"\s+", name.strip()) if part]
    candidates = [name.strip()] + [
        part for part in parts if len(part) >= 3 and part.lower() not in _NAME_STOPWORDS
    ]
    # El nombre completo primero, para que se sustituya de una vez.
    return [re.compile(rf"(?<!\w){re.escape(item)}(?!\w)", re.IGNORECASE) for item in candidates]


def redact_text(
    text: str | None, name: str | None = None, institutions: list[str] | None = None
) -> str | None:
    """Sustituye nombre, correos, URLs, telefonos, instituciones educativas y anos por marcadores."""
    if not text:
        return text
    redacted = _EMAIL_RE.sub(EMAIL_PLACEHOLDER, text)
    for institution in sorted(set(institutions or []), key=len, reverse=True):
        redacted = re.sub(rf"(?<!\w){re.escape(institution)}(?!\w)", INSTITUTION_PLACEHOLDER, redacted, flags=re.IGNORECASE)
    redacted = _URL_RE.sub(URL_PLACEHOLDER, redacted)
    redacted = _PHONE_RE.sub(PHONE_PLACEHOLDER, redacted)
    for pattern in _name_patterns(name):
        redacted = pattern.sub(NAME_PLACEHOLDER, redacted)
    redacted = _YEAR_RE.sub(YEAR_PLACEHOLDER, redacted)
    # Varios marcadores seguidos (p. ej. nombre y dos apellidos) -> uno solo.
    redacted = re.sub(rf"(?:{re.escape(NAME_PLACEHOLDER)}\s*){{2,}}", NAME_PLACEHOLDER + " ", redacted)
    return redacted


def _parse_year_month(value: str | None) -> date | None:
    if not value or value in ("present", "actualidad"):
        return None
    try:
        year, month = str(value).split("-")[:2]
        return date(int(year), int(month), 1)
    except (ValueError, TypeError):
        return None


def _duration_years(start: str | None, end: str | None, today: date | None = None) -> float | None:
    """Duracion en anos de un periodo "YYYY-MM" (fin "present" = hoy)."""
    start_date = _parse_year_month(start)
    if start_date is None:
        return None
    if end in (None, "present", "actualidad"):
        end_date = today or date.today()
    else:
        end_date = _parse_year_month(end)
        if end_date is None:
            return None
    months = max(0, (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month))
    return round(months / 12, 1)


def candidate_view_for_llm(candidate: dict[str, Any] | None, today: date | None = None) -> dict[str, Any]:
    """Vista minimizada del candidato para el prompt del LLM.

    - Sin identificador ni nombre.
    - Experiencia como puesto, empresa, duracion en anos y si es el puesto
      actual, sin fechas.
    - Formacion como titulo, sin institucion ni ano de finalizacion.
    - Habilidades, idiomas y certificaciones tal cual.
    - Texto libre del CV anonimizado con `redact_text` (incluidas las
      menciones a las instituciones educativas del CV).
    """
    candidate = candidate or {}
    cv = candidate.get("cv") or {}
    name = candidate.get("name")
    # Instituciones del CV: el nombre completo y cada palabra distintiva
    # ("Complutense", "Politecnica"), para cubrir menciones abreviadas en el
    # texto libre ("por la Complutense").
    institutions: list[str] = []
    for entry in cv.get("education") or []:
        institution = (entry.get("institution") or "").strip()
        if not institution:
            continue
        institutions.append(institution)
        institutions.extend(
            word for word in re.split(r"[\s,.;()]+", institution)
            if len(word) >= 4 and word.lower() not in _GENERIC_INSTITUTION_WORDS
        )

    experience = [
        {
            "role": entry.get("role"),
            "company": entry.get("company"),
            "duration_years": _duration_years(entry.get("start_date"), entry.get("end_date"), today),
            "current": entry.get("end_date") in (None, "present", "actualidad"),
            "description": redact_text(entry.get("description"), name, institutions),
        }
        for entry in cv.get("experience") or []
    ]
    education = [{"degree": entry.get("degree")} for entry in cv.get("education") or [] if entry.get("degree")]

    return {
        "cv": {
            "experience": experience,
            "education": education,
            "technical_skills": list(cv.get("technical_skills") or []),
            "languages": list(cv.get("languages") or []),
            "certifications": list(cv.get("certifications") or []),
            "extracted_text": redact_text(cv.get("extracted_text"), name, institutions),
        }
    }
