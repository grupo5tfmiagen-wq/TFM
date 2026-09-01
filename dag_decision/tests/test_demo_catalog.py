"""Comprobaciones del catalogo que alimenta la demostracion de Streamlit."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.load_demo_data import DEFAULT_CATALOG_PATH, read_catalog  # noqa: E402


def test_demo_catalog_contains_multiple_cvs_and_jobs():
    catalog = read_catalog(DEFAULT_CATALOG_PATH)

    assert len(catalog["cv_documents"]) >= 5
    assert len(catalog["job_postings"]) >= 4
    assert {cv["candidate_id"] for cv in catalog["cv_documents"]} >= {
        "demo-marta-suarez",
        "demo-lucas-romero",
    }
    assert {job["external_id"] for job in catalog["job_postings"]} >= {
        "puesto-backend-senior-2026",
        "puesto-backend-junior-2026",
    }