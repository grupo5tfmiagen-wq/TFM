"""Script de ejemplo para sembrar un CV en la base de datos (tabla `cv_documents`).

Carga `script_pdf_json/cv_ejemplo.json` (ya en el esquema español de
`CVDocument`, generado por `cv_to_json_openai.py`) e inserta una fila si el
`candidate_id` todavia no existe. Sirve para tener datos con los que probar
la pagina "Nuevo Caso" de la UI sin pasar por la conversion real de PDF.

Uso:
    python scripts/load_cv_document.py
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.db.base import SessionLocal
from src.db.models import CVDocument

CV_EJEMPLO_PATH = Path(__file__).parent.parent.parent / "script_pdf_json" / "cv_ejemplo.json"


def cargar_cv_ejemplo() -> None:
    """Inserta el CV de ejemplo si no existe ya un `CVDocument` con su `candidate_id`."""
    with open(CV_EJEMPLO_PATH, encoding="utf-8-sig") as f:
        caso_json = json.load(f)
    candidato = caso_json["candidato"]
    cv_data = candidato["cv"]

    db = SessionLocal()
    try:
        existing = db.query(CVDocument).filter(CVDocument.candidate_id == candidato["id"]).first()
        if existing:
            print(f"El CV '{candidato['id']}' ya existe (ID: {existing.id})")
            return

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
            raw_json=cv_data,
        )
        db.add(cv_doc)
        db.commit()
        db.refresh(cv_doc)

        print("✓ CV creado exitosamente:")
        print(f"  ID: {cv_doc.id}")
        print(f"  Candidate ID: {cv_doc.candidate_id}")
        print(f"  Nombre: {cv_doc.candidate_name}")
    finally:
        db.close()


if __name__ == "__main__":
    cargar_cv_ejemplo()
