"""
Convierte un CV en PDF a la estructura JSON usada como 'caso de entrada' del
DAG (el mismo formato de data/caso.json), lista para ejecutarse con
decision_engine.py.

Dos pasos:
  1. Extracción de texto del PDF con pdfplumber.
  2. Estructuración del texto libre en campos (experiencia, formación,
     habilidades, idiomas, certificaciones) con la API de OpenAI, usando
     Structured Outputs (client.chat.completions.parse) contra un esquema
     definido con modelos de Pydantic — la respuesta llega ya validada y
     tipada, sin necesidad de parsear JSON a mano.

Uso:
    python cv_to_json.py cv_ejemplo.pdf --puesto-id puesto-backend-senior-2026

Requiere OPENAI_API_KEY en el .env (ver .env.example).
"""

from __future__ import annotations

import argparse
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pdfplumber
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field

load_dotenv()


# ---------------------------------------------------------------------------
# Esquema de salida esperado del LLM, como modelos de Pydantic
# (subconjunto de candidato.cv en caso.json)
# ---------------------------------------------------------------------------

class Experiencia(BaseModel):
    empresa: str
    puesto: str
    fecha_inicio: str = Field(description="Formato AAAA-MM")
    fecha_fin: str = Field(description="Formato AAAA-MM, o 'actualidad' si sigue en el puesto")
    descripcion: str


class Formacion(BaseModel):
    titulo: str
    institucion: str
    anio_fin: int


class Idioma(BaseModel):
    idioma: str
    nivel: str = Field(description="ej. A1-C2, o 'nativo'")


class CVEstructurado(BaseModel):
    """Esquema que el modelo debe rellenar a partir del texto libre del CV."""
    nombre_candidato: str = Field(description="Nombre completo detectado en el CV")
    idioma: str = Field(description="Idioma principal en el que está escrito el CV, ej. 'es'")
    experiencia: list[Experiencia]
    formacion: list[Formacion]
    habilidades_tecnicas: list[str]
    idiomas: list[Idioma]
    certificaciones: list[str]


# ---------------------------------------------------------------------------
# Paso 1: extracción de texto del PDF
# ---------------------------------------------------------------------------

def extraer_texto_pdf(ruta_pdf: Path) -> str:
    """Extrae el texto plano del PDF, página a página."""
    paginas = []
    with pdfplumber.open(ruta_pdf) as pdf:
        for pagina in pdf.pages:
            paginas.append(pagina.extract_text() or "")
    return "\n".join(paginas)


# ---------------------------------------------------------------------------
# Paso 2: estructuración del texto con el LLM (Structured Outputs + Pydantic)
# ---------------------------------------------------------------------------

def estructurar_cv_con_llm(texto_cv: str) -> CVEstructurado:
    """Llama a la API de OpenAI para estructurar el texto libre del CV.

    client.chat.completions.parse() valida la respuesta contra el modelo de
    Pydantic (CVEstructurado) y ya devuelve una instancia tipada — si el
    modelo no puede cumplir el esquema, lanza una excepción en vez de
    devolver JSON a medio validar.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Falta OPENAI_API_KEY en el .env — necesaria para estructurar el CV con el LLM."
        )

    client = OpenAI(api_key=api_key)

    completado = client.chat.completions.parse(
        model="gpt-4.1-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "Extraes la información de CVs y la estructuras según el "
                    "esquema proporcionado. No inventes datos que no aparezcan "
                    "en el texto; si un campo no se puede determinar, usa una "
                    "lista vacía o una cadena vacía."
                ),
            },
            {"role": "user", "content": f"CV:\n{texto_cv}"},
        ],
        response_format=CVEstructurado,
    )

    cv_estructurado = completado.choices[0].message.parsed
    if cv_estructurado is None:
        # El SDK deja 'parsed' a None si el modelo rehusó responder
        # (ver completado.choices[0].message.refusal) en vez de lanzar excepción.
        rechazo = completado.choices[0].message.refusal
        raise RuntimeError(f"El modelo no devolvió una estructura válida: {rechazo}")

    return cv_estructurado


# ---------------------------------------------------------------------------
# Paso 3: ensamblar el 'caso.json' completo
# ---------------------------------------------------------------------------

def construir_caso(cv_estructurado: CVEstructurado, texto_cv: str, ruta_pdf: Path, puesto_id: str) -> dict:
    """Combina el CV estructurado (validado por Pydantic) con la plantilla de nodos del DAG."""
    return {
        "id": f"caso-{uuid.uuid4().hex[:8]}",
        "fecha_creacion": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "puesto_id": puesto_id,

        "candidato": {
            "id": f"cand-{uuid.uuid4().hex[:8]}",
            "nombre": cv_estructurado.nombre_candidato,
            "cv": {
                "formato_original": "pdf",
                "idioma": cv_estructurado.idioma,
                "texto_extraido": texto_cv.strip(),
                # model_dump() convierte cada modelo de Pydantic (Experiencia,
                # Formacion, Idioma) a dict plano, listo para json.dump.
                "experiencia": [e.model_dump() for e in cv_estructurado.experiencia],
                "formacion": [f.model_dump() for f in cv_estructurado.formacion],
                "habilidades_tecnicas": cv_estructurado.habilidades_tecnicas,
                "idiomas": [i.model_dump() for i in cv_estructurado.idiomas],
                "certificaciones": cv_estructurado.certificaciones,
            },
        },

        # Misma plantilla de nodos que data/caso.json — ajusta si tu DAG
        # concreto usa otros nodos, reglas o prompts.
        "nodos": [
            {
                "id": "n1",
                "tipo": "rule",
                "payload": {
                    "regla": "filtro_requisitos_minimos",
                    "descripcion": "Descarta si no cumple los requisitos obligatorios del puesto",
                },
            },
            {
                "id": "n2",
                "tipo": "llm",
                "payload": {
                    "prompt_template": "evaluar_experiencia_relevante",
                    "modelo": "gpt-4.1-mini6",
                    "descripcion": "Analiza el texto del CV frente a los requisitos deseables",
                },
            },
            {
                "id": "n3",
                "tipo": "transformacion",
                "payload": {
                    "accion": "calcular_score_ponderado",
                    "entradas": ["n1", "n2"],
                },
            },
        ],

        "metadata": {
            "origen": f"pdf:{ruta_pdf.name}",
            "reclutador_asignado": "...",
        },
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Convierte un CV en PDF al JSON del caso de entrada del DAG.")
    parser.add_argument("pdf", type=Path, help="Ruta al CV en PDF")
    parser.add_argument("--puesto-id", required=True, help="puesto_id del perfil de puesto contra el que se evaluará")
    parser.add_argument("--out", type=Path, default=None, help="Ruta de salida del JSON (por defecto: <nombre_pdf>.json)")
    parser.add_argument("--save-db", action="store_true", help="Guardar el CV y el caso en la base de datos")
    args = parser.parse_args()

    texto_cv = extraer_texto_pdf(args.pdf)
    if not texto_cv.strip():
        raise RuntimeError(
            f"No se pudo extraer texto de {args.pdf}. Si es un PDF escaneado (imagen), "
            "hace falta pasar OCR antes (ej. pytesseract) — este script no lo incluye."
        )

    cv_estructurado = estructurar_cv_con_llm(texto_cv)
    caso = construir_caso(cv_estructurado, texto_cv, args.pdf, args.puesto_id)

    ruta_salida = args.out or args.pdf.with_suffix(".json")
    with open(ruta_salida, "w", encoding="utf-8") as f:
        json.dump(caso, f, ensure_ascii=False, indent=2)

    print(f"CV convertido y guardado en: {ruta_salida}")
    
    # Guardar en base de datos si se solicita
    if args.save_db:
        try:
            from db_helper import guardar_caso_completo
            cv_id, oferta_id, caso_id = guardar_caso_completo(caso)
            print(f"✓ Guardado en BBDD:")
            print(f"  - CV Document ID: {cv_id}")
            print(f"  - Job Posting ID: {oferta_id}")
            print(f"  - Case ID: {caso_id}")
        except Exception as e:
            print(f"⚠ Error al guardar en BBDD: {e}")
            print("  El JSON se guardó correctamente, pero no se pudo guardar en la base de datos.")


if __name__ == "__main__":
    main()
