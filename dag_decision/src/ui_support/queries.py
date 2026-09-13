"""Consultas de solo lectura para la UI Streamlit.

Separadas de `src/escalation/service.py` porque no forman parte del
contrato que usan los nodos del grafo: solo alimentan las paginas de
listado/auditoria (selectbox de CVs/ofertas, historial de casos).
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timezone

from sqlalchemy.orm import Session, selectinload

from ..db.models.case import Case
from ..db.models.cv_document import CVDocument
from ..db.models.job_posting import JobPosting
from ..db.models.node_execution import CaseNodeExecution


def list_cv_documents(session: Session) -> list[CVDocument]:
    """CVs disponibles para lanzar un caso nuevo, ordenados por nombre."""
    return session.query(CVDocument).order_by(CVDocument.candidate_name).all()


def list_job_postings(session: Session) -> list[JobPosting]:
    """Ofertas disponibles para lanzar un caso nuevo, ordenadas por titulo."""
    return session.query(JobPosting).order_by(JobPosting.titulo).all()


def list_cases(session: Session, status: str | None = None) -> list[Case]:
    """Casos para el historial, mas recientes primero, con sus relaciones de listado ya cargadas."""
    query = session.query(Case).options(
        selectinload(Case.cv_document),
        selectinload(Case.job_posting),
        selectinload(Case.final_decision),
    )
    if status:
        query = query.filter(Case.status == status)
    return query.order_by(Case.created_at.desc()).all()


def get_case_detail(session: Session, case_id: str) -> Case | None:
    """Un caso con todo lo necesario para la vista de detalle/auditoria, o `None` si no existe."""
    return (
        session.query(Case)
        .options(
            selectinload(Case.final_decision),
            selectinload(Case.human_escalations),
            selectinload(Case.node_executions).selectinload(CaseNodeExecution.rule_evaluations),
            selectinload(Case.node_executions).selectinload(CaseNodeExecution.llm_decisions),
            selectinload(Case.node_executions).selectinload(CaseNodeExecution.validations),
        )
        .filter(Case.id == case_id)
        .one_or_none()
    )


def get_dashboard_metrics(
    session: Session,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    job_posting_id: str | None = None,
) -> dict:
    """Agrega los indicadores de negocio que presenta el dashboard de Streamlit."""
    query = session.query(Case).options(
        selectinload(Case.job_posting),
        selectinload(Case.final_decision),
        selectinload(Case.human_escalations),
        selectinload(Case.node_executions).selectinload(CaseNodeExecution.llm_decisions),
    )
    if start_date:
        query = query.filter(Case.created_at >= datetime.combine(start_date, time.min, tzinfo=timezone.utc))
    if end_date:
        query = query.filter(Case.created_at <= datetime.combine(end_date, time.max, tzinfo=timezone.utc))
    if job_posting_id:
        query = query.filter(Case.job_posting_id == job_posting_id)

    cases = query.order_by(Case.created_at.asc()).all()
    outcomes = Counter(
        case.final_decision.outcome for case in cases if case.final_decision is not None
    )
    escalations = [escalation for case in cases for escalation in case.human_escalations]
    escalation_resolutions = Counter(
        escalation.resolution for escalation in escalations if escalation.resolution
    )
    confidences = [
        float(decision.confidence)
        for case in cases
        for execution in case.node_executions
        for decision in execution.llm_decisions
        if decision.confidence is not None
    ]

    cases_by_day = Counter(
        case.created_at.date().isoformat() for case in cases if case.created_at is not None
    )
    jobs: dict[str, dict] = {}
    for case in cases:
        title = case.job_posting.titulo if case.job_posting else "Oferta no disponible"
        summary = jobs.setdefault(title, {"oferta": title, "casos": 0, "fit": 0, "cerrados": 0})
        summary["casos"] += 1
        if case.final_decision:
            summary["cerrados"] += 1
            if case.final_decision.outcome == "fit":
                summary["fit"] += 1

    closed_cases = sum(outcomes.values())
    fit_cases = outcomes["fit"]
    return {
        "total_cases": len(cases),
        "closed_cases": closed_cases,
        "pending_escalations": sum(escalation.status == "pending" for escalation in escalations),
        "escalated_cases": len({escalation.case_id for escalation in escalations}),
        "fit_rate": (fit_cases / closed_cases * 100) if closed_cases else 0.0,
        "average_confidence": (sum(confidences) / len(confidences) * 100) if confidences else None,
        "outcomes": [
            {"resultado": outcome, "casos": count}
            for outcome, count in sorted(outcomes.items())
        ],
        "escalation_resolutions": [
            {"resolucion": resolution, "casos": count}
            for resolution, count in sorted(escalation_resolutions.items())
        ],
        "cases_by_day": [
            {"fecha": day, "casos": count} for day, count in sorted(cases_by_day.items())
        ],
        "jobs": [
            {
                **summary,
                "tasa_fit": round(summary["fit"] / summary["cerrados"] * 100, 1)
                if summary["cerrados"]
                else None,
            }
            for summary in sorted(jobs.values(), key=lambda item: item["casos"], reverse=True)
        ],
    }
