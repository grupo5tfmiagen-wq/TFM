"""Carga idempotente de CVs y ofertas para la demostracion de Streamlit.

Uso desde ``dag_decision/``:
    .venv\\Scripts\\python scripts\\load_demo_data.py

El catalogo por defecto esta en ``data/demo_catalog.json``. Cada ejecucion
crea o actualiza los registros identificados por ``candidate_id`` y
``external_id``, por lo que es seguro lanzarlo antes de cada demo.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.db.base import SessionLocal
from src.db.models import CVDocument, JobPosting

DEFAULT_CATALOG_PATH = Path(__file__).resolve().parent.parent / "data" / "demo_catalog.json"

CV_FIELDS = (
    "candidate_name",
    "original_filename",
    "original_format",
    "idioma",
    "texto_extraido",
    "experiencia",
    "formacion",
    "habilidades_tecnicas",
    "idiomas",
    "certificaciones",
)
JOB_FIELDS = (
    "titulo",
    "descripcion",
    "requisitos_minimos",
    "requisitos_deseables",
    "habilidades_requeridas",
    "idiomas_requeridos",
    "experiencia_minima_anios",
    "formacion_minima",
    "ubicacion",
    "tipo_contrato",
    "salario_min",
    "salario_max",
)


def read_catalog(path: Path) -> dict[str, list[dict[str, Any]]]:
    """Lee y valida la estructura minima de un catalogo de demostracion."""
    with path.open(encoding="utf-8") as catalog_file:
        catalog = json.load(catalog_file)

    if not isinstance(catalog, dict):
        raise ValueError("El catalogo debe ser un objeto JSON.")

    for section, identifier in (("cv_documents", "candidate_id"), ("job_postings", "external_id")):
        rows = catalog.get(section)
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"'{section}' debe contener al menos un registro.")
        if any(not isinstance(row, dict) or not row.get(identifier) for row in rows):
            raise ValueError(f"Cada registro de '{section}' debe tener '{identifier}'.")
        identifiers = [row[identifier] for row in rows]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError(f"Hay identificadores duplicados en '{section}'.")

    return catalog


def _copy_fields(record: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    return {field: record.get(field) for field in fields}


def seed_demo_data(catalog_path: Path) -> dict[str, int]:
    """Crea o actualiza los CVs y ofertas definidos en ``catalog_path``."""
    catalog = read_catalog(catalog_path)
    summary = {"cvs_created": 0, "cvs_updated": 0, "jobs_created": 0, "jobs_updated": 0}

    with SessionLocal() as session:
        for record in catalog["cv_documents"]:
            cv = session.query(CVDocument).filter(CVDocument.candidate_id == record["candidate_id"]).first()
            values = _copy_fields(record, CV_FIELDS)
            values["raw_json"] = record
            if cv is None:
                session.add(CVDocument(candidate_id=record["candidate_id"], **values))
                summary["cvs_created"] += 1
            else:
                for field, value in values.items():
                    setattr(cv, field, value)
                summary["cvs_updated"] += 1

        for record in catalog["job_postings"]:
            job = session.query(JobPosting).filter(JobPosting.external_id == record["external_id"]).first()
            values = _copy_fields(record, JOB_FIELDS)
            if job is None:
                session.add(
                    JobPosting(
                        external_id=record["external_id"],
                        activa=True,
                        fecha_publicacion=datetime.now(timezone.utc),
                        **values,
                    )
                )
                summary["jobs_created"] += 1
            else:
                for field, value in values.items():
                    setattr(job, field, value)
                job.activa = True
                summary["jobs_updated"] += 1

        session.commit()

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Carga los datos de demostracion de Streamlit.")
    parser.add_argument(
        "--catalog",
        type=Path,
        default=DEFAULT_CATALOG_PATH,
        help="Ruta al catalogo JSON (por defecto: data/demo_catalog.json).",
    )
    args = parser.parse_args()

    summary = seed_demo_data(args.catalog)
    print("Datos de demostracion cargados:")
    print(f"  CVs creados: {summary['cvs_created']}; actualizados: {summary['cvs_updated']}")
    print(f"  Ofertas creadas: {summary['jobs_created']}; actualizadas: {summary['jobs_updated']}")


if __name__ == "__main__":
    main()