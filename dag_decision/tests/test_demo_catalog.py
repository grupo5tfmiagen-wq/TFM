"""Comprobaciones del catalogo que alimenta la demostracion de Streamlit."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.load_demo_data import DEFAULT_CATALOG_PATH, read_catalog  # noqa: E402


def test_demo_catalog_contains_cvs_and_job_posting():
    catalog = read_catalog(DEFAULT_CATALOG_PATH)

    assert len(catalog["cv_documents"]) >= 5
    assert len(catalog["job_postings"]) >= 1
    assert "job-backend-python-diversidad-2026" in {job["external_id"] for job in catalog["job_postings"]}


def test_demo_catalog_supports_bias_analysis():
    """El catalogo esta pensado para la demostracion de sesgos: todos los CV
    llevan sexo y ano de nacimiento, y hay variedad en ambos."""
    catalog = read_catalog(DEFAULT_CATALOG_PATH)
    cvs = catalog["cv_documents"]

    assert all(cv.get("sexo") and cv.get("anio_nacimiento") for cv in cvs)
    assert len({cv["sexo"].strip().lower() for cv in cvs}) >= 2
    assert len({cv["anio_nacimiento"] // 10 for cv in cvs}) >= 3
