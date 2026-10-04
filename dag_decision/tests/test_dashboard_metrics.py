"""Pruebas de los KPI agregados que alimentan la pagina de metricas."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from src.ui_support.queries import _summarize_dashboard_cases


def _case(
    case_id: str,
    created_at: datetime,
    *,
    job_id: str,
    job_title: str,
    outcome: str | None = None,
    decided_by: str | None = None,
    decided_at: datetime | None = None,
    confidence: float | None = None,
    total_tokens: int | None = None,
    estimated_cost_usd: float | None = None,
    escalations: list | None = None,
    sexo: str | None = None,
    anio_nacimiento: int | None = None,
):
    final_decision = None
    if outcome:
        final_decision = SimpleNamespace(
            outcome=outcome,
            decided_by=decided_by,
            decided_at=decided_at or created_at,
        )
    has_llm_execution = confidence is not None or total_tokens is not None or estimated_cost_usd is not None
    llm_decisions = [] if confidence is None else [SimpleNamespace(confidence=confidence)]
    output_data = {}
    if total_tokens is not None:
        output_data["total_tokens"] = total_tokens
    if estimated_cost_usd is not None:
        output_data["estimated_cost_usd"] = estimated_cost_usd
    cv_document = (
        SimpleNamespace(sexo=sexo, anio_nacimiento=anio_nacimiento)
        if sexo is not None or anio_nacimiento is not None
        else None
    )
    return SimpleNamespace(
        id=case_id,
        cv_document=cv_document,
        job_posting_id=job_id,
        job_posting=SimpleNamespace(titulo=job_title),
        created_at=created_at,
        final_decision=final_decision,
        human_escalations=escalations or [],
        node_executions=[
            SimpleNamespace(
                node_key="llm_decision",
                llm_decisions=llm_decisions,
                output_data=output_data,
            )
        ]
        if has_llm_execution
        else [],
    )


def test_dashboard_metrics_distinguishes_final_outcomes_and_human_review():
    started_at = datetime(2026, 9, 10, 9, tzinfo=timezone.utc)
    resolved_escalation = SimpleNamespace(
        case_id="case-3",
        status="resolved",
        resolution="not_fit",
        created_at=started_at + timedelta(days=1),
        resolved_at=started_at + timedelta(days=1, minutes=30),
    )
    pending_escalation = SimpleNamespace(
        case_id="case-4",
        status="pending",
        resolution=None,
        created_at=started_at + timedelta(days=2),
        resolved_at=None,
    )
    cases = [
        _case(
            "case-1",
            started_at,
            job_id="job-a",
            job_title="Oferta A",
            outcome="fit",
            decided_by="system",
            decided_at=started_at + timedelta(seconds=10),
            confidence=0.9,
            total_tokens=100,
            estimated_cost_usd=0.01,
            sexo="mujer",
            anio_nacimiento=1985,
        ),
        _case(
            "case-2",
            started_at,
            job_id="job-a",
            job_title="Oferta A",
            outcome="rejected",
            decided_at=started_at + timedelta(seconds=20),
            sexo="Hombre",
            anio_nacimiento=1990,
        ),
        _case(
            "case-3",
            started_at + timedelta(days=1),
            job_id="job-b",
            job_title="Oferta B",
            outcome="not_fit",
            decided_by="human",
            decided_at=started_at + timedelta(days=1, seconds=60),
            confidence=0.4,
            total_tokens=200,
            estimated_cost_usd=0.02,
            escalations=[resolved_escalation],
            sexo="M",
            anio_nacimiento=1992,
        ),
        _case(
            "case-4",
            started_at + timedelta(days=2),
            job_id="job-b",
            job_title="Oferta B",
            confidence=0.5,
            total_tokens=300,
            estimated_cost_usd=0.03,
            escalations=[pending_escalation],
            sexo="mujer",
            anio_nacimiento=1980,
        ),
    ]

    metrics = _summarize_dashboard_cases(cases)

    assert metrics["total_cases"] == 4
    assert metrics["final_decisions"] == 3
    assert metrics["open_cases"] == 1
    assert metrics["fit_cases"] == 1
    assert metrics["not_fit_cases"] == 1
    assert metrics["rejected_cases"] == 1
    assert metrics["fit_rate"] == pytest.approx(100 / 3)
    assert metrics["escalated_cases"] == 2
    assert metrics["escalation_rate"] == 50
    assert metrics["pending_escalations"] == 1
    assert metrics["human_decisions"] == 1
    assert metrics["average_confidence"] == pytest.approx(60)
    assert metrics["average_human_review_minutes"] == pytest.approx(30)
    assert metrics["average_decision_seconds"] == pytest.approx(30)
    assert metrics["rule_filter_rate"] == 25
    assert metrics["llm_calls"] == 3
    assert metrics["llm_usage_records"] == 3
    assert metrics["total_llm_tokens"] == 600
    assert metrics["total_llm_cost_usd"] == pytest.approx(0.06)
    assert {row["resultado"]: row["casos"] for row in metrics["outcomes"]} == {
        "Aprobado": 1,
        "No apto": 1,
        "Descartado por reglas": 1,
    }
    assert {row["resolucion"]: row["casos"] for row in metrics["human_resolutions"]} == {
        "No apto segun revisor": 1
    }

    jobs = {row["oferta"]: row for row in metrics["jobs"]}
    assert jobs["Oferta A"]["descartados_por_reglas"] == 1
    assert jobs["Oferta B"]["escalados"] == 2
    assert jobs["Oferta B"]["tasa_aprobacion"] == 0

    # Metricas de sesgo: solo cuentan casos cerrados, y "M"/"Hombre" se
    # normalizan al mismo grupo. case-4 (abierto) no entra en ningun grupo.
    by_sex = {row["grupo"]: row for row in metrics["by_sex"]}
    assert by_sex["Mujer"]["casos"] == 1
    assert by_sex["Mujer"]["tasa_fit"] == 100
    assert by_sex["Mujer"]["confianza_media"] == pytest.approx(90)
    assert by_sex["Hombre"]["casos"] == 2
    assert by_sex["Hombre"]["tasa_fit"] == 0
    assert by_sex["Hombre"]["tasa_escalacion"] == 50
    assert by_sex["Hombre"]["confianza_media"] == pytest.approx(40)

    by_decade = {row["grupo"]: row["casos"] for row in metrics["by_birth_decade"]}
    assert by_decade == {"1980s": 1, "1990s": 2}


def test_dashboard_metrics_ignore_cases_without_demographics():
    started_at = datetime(2026, 9, 10, 9, tzinfo=timezone.utc)
    cases = [_case("case-1", started_at, job_id="job-a", job_title="Oferta A", outcome="fit")]

    metrics = _summarize_dashboard_cases(cases)

    assert metrics["by_sex"] == []
    assert metrics["by_birth_decade"] == []
