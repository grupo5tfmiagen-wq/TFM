"""Tests para `scripts/run_case.py`: `_load_json` (BOM + mensaje de error
util) y `load_case_payload` (casar `case.json`/`job_profile.json` por
`job_id`).

`run_case.py` es un script suelto (no forma parte del paquete `src`), asi
que se carga por ruta con `importlib`. Al importarlo arrastra los mismos
imports pesados que `src.graph.nodes` (`src.db.*`), que `conftest.py` ya
deja stubeados.
"""
import importlib.util
import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUN_CASE_PATH = PROJECT_ROOT / "scripts" / "run_case.py"


def _load_run_case_module():
    spec = importlib.util.spec_from_file_location("run_case_under_test", RUN_CASE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def run_case():
    return _load_run_case_module()


CASE_CONTENT = {
    "id": "case-test",
    "job_id": "job-backend-senior-2026",
    "candidate": {"cv": {"technical_skills": ["Python"]}},
}
JOB_PROFILE_CONTENT = {
    "job_id": "job-backend-senior-2026",
    "mandatory_requirements": {"technical_skills": ["Python"], "min_years_experience": 3},
}


class TestLoadJson:
    def test_loads_plain_utf8_file(self, run_case, tmp_path):
        path = tmp_path / "case.json"
        path.write_text(json.dumps(CASE_CONTENT), encoding="utf-8")
        assert run_case._load_json(path) == CASE_CONTENT

    def test_loads_utf8_file_with_bom(self, run_case, tmp_path):
        # Simula el caso real que motivo este fix: un fichero guardado como
        # "UTF-8 con BOM" desde Windows (Bloc de notas, algunos editores).
        path = tmp_path / "case_bom.json"
        path.write_bytes(b"\xef\xbb\xbf" + json.dumps(CASE_CONTENT).encode("utf-8"))
        assert run_case._load_json(path) == CASE_CONTENT

    def test_invalid_json_raises_value_error_with_snippet(self, run_case, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text('{\n  "a": 1,\n}\n', encoding="utf-8")
        with pytest.raises(ValueError) as excinfo:
            run_case._load_json(path)
        assert "no es JSON valido" in str(excinfo.value)
        assert '"a": 1' in str(excinfo.value)


class TestLoadCasePayload:
    def test_combines_candidate_and_job_profile(self, run_case, tmp_path):
        case_path = tmp_path / "case.json"
        job_path = tmp_path / "job_profile.json"
        case_path.write_text(json.dumps(CASE_CONTENT), encoding="utf-8")
        job_path.write_text(json.dumps(JOB_PROFILE_CONTENT), encoding="utf-8")

        loaded = run_case.load_case_payload(case_path, job_path)

        assert loaded["source_case_id"] == "case-test"
        assert loaded["payload"]["candidate"] == CASE_CONTENT["candidate"]
        assert loaded["payload"]["job_profile"] == JOB_PROFILE_CONTENT

    def test_raises_when_job_id_mismatch(self, run_case, tmp_path):
        case_path = tmp_path / "case.json"
        job_path = tmp_path / "job_profile.json"
        case_path.write_text(json.dumps(CASE_CONTENT), encoding="utf-8")
        mismatched = {**JOB_PROFILE_CONTENT, "job_id": "job-other-2026"}
        job_path.write_text(json.dumps(mismatched), encoding="utf-8")

        with pytest.raises(ValueError, match="job_id"):
            run_case.load_case_payload(case_path, job_path)
