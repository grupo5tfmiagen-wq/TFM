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

_OUTCOME_LABELS = {
    "fit": "Aprobado",
    "not_fit": "No apto",
    "rejected": "Descartado por reglas",
    "unclear": "Sin conclusion",
}
_OUTCOME_ORDER = ("fit", "not_fit", "rejected", "unclear")
_HUMAN_RESOLUTION_LABELS = {
    "fit": "Aprobado por revisor",
    "not_fit": "No apto segun revisor",
}


def list_cv_documents(session: Session) -> list[CVDocument]:
    """CVs disponibles para lanzar un caso nuevo, ordenados por nombre."""
    return session.query(CVDocument).order_by(CVDocument.candidate_name).all()


def list_job_postings(session: Session) -> list[JobPosting]:
    """Ofertas disponibles para lanzar un caso nuevo, ordenadas por titulo."""
    return session.query(JobPosting).order_by(JobPosting.titulo).all()


def list_case_cv_ids_for_job(session: Session, job_posting_id: str) -> set[str]:
    """IDs de CV que ya tienen al menos un caso lanzado para esta oferta.

    Se usa en "Lanzar Lote" para avisar de duplicados antes de relanzar el
    pipeline sobre un CV que ya se proceso contra la misma oferta.
    """
    rows = (
        session.query(Case.cv_document_id)
        .filter(Case.job_posting_id == job_posting_id, Case.cv_document_id.isnot(None))
        .all()
    )
    return {str(cv_document_id) for (cv_document_id,) in rows}


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


def _bias_group_stats(cases: list[Case], group_key) -> list[dict]:
    """Agrega, por el grupo que devuelva `group_key(case)`, las tres metricas
    de sesgo del dashboard: tasa de aprobacion, tasa de escalacion a
    revision humana y confianza media del LLM. Se usa tanto para sexo como
    para decada de nacimiento (ver `get_dashboard_metrics`). Solo cuenta
    casos ya cerrados (con decision final), igual que el resto de tasas de
    este dashboard; los casos sin dato de grupo (`group_key` devuelve
    `None`, p.ej. CV sin `sexo` relleno) se excluyen en vez de contarse como
    un grupo "desconocido", para no diluir las tasas de los grupos reales.
    """
    groups: dict[str, dict] = {}
    for case in cases:
        if case.final_decision is None:
            continue
        key = group_key(case)
        if key is None:
            continue
        group = groups.setdefault(
            key, {"grupo": key, "casos": 0, "fit": 0, "escalados": 0, "_confidences": []}
        )
        group["casos"] += 1
        if case.final_decision.outcome == "fit":
            group["fit"] += 1
        if case.human_escalations:
            group["escalados"] += 1
        for execution in case.node_executions:
            for decision in execution.llm_decisions:
                if decision.confidence is not None:
                    group["_confidences"].append(float(decision.confidence))

    result = []
    for group in groups.values():
        confidences = group.pop("_confidences")
        casos = group["casos"]
        result.append(
            {
                **group,
                "tasa_fit": round(group["fit"] / casos * 100, 1) if casos else None,
                "tasa_escalacion": round(group["escalados"] / casos * 100, 1) if casos else None,
                "confianza_media": round(sum(confidences) / len(confidences) * 100, 1) if confidences else None,
            }
        )
    return sorted(result, key=lambda item: item["casos"], reverse=True)


def _birth_decade(cv_document: CVDocument | None) -> str | None:
    if cv_document is None or cv_document.anio_nacimiento is None:
        return None
    decade_start = (cv_document.anio_nacimiento // 10) * 10
    return f"{decade_start}s"


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
        selectinload(Case.cv_document),
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
    return _summarize_dashboard_cases(cases)


def _summarize_dashboard_cases(cases: list[Case]) -> dict:
    """Calcula los KPI a partir de los casos ya cargados para facilitar su prueba aislada."""
    outcomes = Counter(
        case.final_decision.outcome for case in cases if case.final_decision is not None
    )
    escalations = [escalation for case in cases for escalation in case.human_escalations]
    human_resolutions = Counter(
        escalation.resolution for escalation in escalations if escalation.resolution
    )
    decision_sources = Counter(
        decision.decided_by or "system"
        for case in cases
        if (decision := case.final_decision) is not None
    )
    confidences = [
        float(decision.confidence)
        for case in cases
        for execution in case.node_executions
        for decision in execution.llm_decisions
        if decision.confidence is not None
    ]
    llm_executions = [
        execution
        for case in cases
        for execution in case.node_executions
        if execution.node_key == "llm_decision"
    ]
    total_tokens = [
        value
        for execution in llm_executions
        if (value := _numeric_output_value(execution.output_data, "total_tokens")) is not None
    ]
    llm_costs = [
        value
        for execution in llm_executions
        if (value := _numeric_output_value(execution.output_data, "estimated_cost_usd")) is not None
    ]
    decision_seconds = [
        (decision.decided_at - case.created_at).total_seconds()
        for case in cases
        if (decision := case.final_decision) is not None
        and decision.decided_at is not None
        and case.created_at is not None
        and decision.decided_at >= case.created_at
    ]

    cases_by_day = Counter(
        case.created_at.date().isoformat() for case in cases if case.created_at is not None
    )
    decisions_by_day = Counter(
        decision.decided_at.date().isoformat()
        for case in cases
        if (decision := case.final_decision) is not None and decision.decided_at is not None
    )
    review_minutes = [
        (escalation.resolved_at - escalation.created_at).total_seconds() / 60
        for escalation in escalations
        if escalation.resolved_at is not None
        and escalation.created_at is not None
        and escalation.resolved_at >= escalation.created_at
    ]

    jobs: dict[str, dict] = {}
    for case in cases:
        title = case.job_posting.titulo if case.job_posting else "Oferta no disponible"
        job_key = str(case.job_posting_id) if case.job_posting_id else title
        summary = jobs.setdefault(
            job_key,
            {
                "oferta": title,
                "casos": 0,
                "decisiones_finales": 0,
                "aprobados": 0,
                "no_aptos": 0,
                "descartados_por_reglas": 0,
                "escalados": 0,
            },
        )
        summary["casos"] += 1
        summary["escalados"] += int(bool(case.human_escalations))
        if case.final_decision:
            summary["decisiones_finales"] += 1
            if case.final_decision.outcome == "fit":
                summary["aprobados"] += 1
            elif case.final_decision.outcome == "not_fit":
                summary["no_aptos"] += 1
            elif case.final_decision.outcome == "rejected":
                summary["descartados_por_reglas"] += 1

    # Sesgo por institucion educativa: no requiere ningun campo nuevo en el
    # esquema, se lee directamente de `Case.payload` (candidate.cv.education),
    # el mismo JSON de entrada que ya usa `rule_evaluator_node`/`llm_decision_node`.
    # Solo se cuentan casos ya cerrados (con decision final), igual que el
    # resto de tasas de aprobacion de este dashboard.
    institutions: dict[str, dict] = {}
    for case in cases:
        if case.final_decision is None:
            continue
        education = ((getattr(case, "payload", {}) or {}).get("candidate") or {}).get("cv", {}).get("education", [])
        seen_institutions = {entry.get("institution") for entry in education if entry.get("institution")}
        for institution in seen_institutions:
            summary = institutions.setdefault(institution, {"institucion": institution, "casos": 0, "fit": 0})
            summary["casos"] += 1
            if case.final_decision.outcome == "fit":
                summary["fit"] += 1

    final_decisions = sum(outcomes.values())
    fit_cases = outcomes["fit"]
    escalated_cases = len({escalation.case_id for escalation in escalations})
    pending_escalations = len({
        escalation.case_id for escalation in escalations if escalation.status == "pending"
    })

    known_outcomes = [
        {"resultado": _OUTCOME_LABELS[outcome], "casos": outcomes[outcome]}
        for outcome in _OUTCOME_ORDER
        if outcomes[outcome]
    ]
    other_outcomes = [
        {"resultado": outcome.replace("_", " ").capitalize(), "casos": count}
        for outcome, count in sorted(outcomes.items())
        if outcome not in _OUTCOME_LABELS
    ]
    return {
        "total_cases": len(cases),
        "closed_cases": final_decisions,
        "final_decisions": final_decisions,
        "open_cases": len(cases) - final_decisions,
        "fit_cases": fit_cases,
        "not_fit_cases": outcomes["not_fit"],
        "rejected_cases": outcomes["rejected"],
        "pending_escalations": pending_escalations,
        "escalated_cases": escalated_cases,
        "human_decisions": decision_sources["human"],
        "fit_rate": (fit_cases / final_decisions * 100) if final_decisions else 0.0,
        "escalation_rate": (escalated_cases / len(cases) * 100) if cases else 0.0,
        "rule_filter_rate": (outcomes["rejected"] / len(cases) * 100) if cases else 0.0,
        "average_confidence": (sum(confidences) / len(confidences) * 100) if confidences else None,
        "average_human_review_minutes": sum(review_minutes) / len(review_minutes) if review_minutes else None,
        "average_decision_seconds": sum(decision_seconds) / len(decision_seconds) if decision_seconds else None,
        "llm_calls": len(llm_executions),
        "llm_usage_records": len(llm_costs),
        "total_llm_tokens": int(sum(total_tokens)) if total_tokens else None,
        "total_llm_cost_usd": sum(llm_costs) if llm_costs else None,
        "outcomes": known_outcomes + other_outcomes,
        "human_resolutions": [
            {
                "resolucion": _HUMAN_RESOLUTION_LABELS.get(
                    resolution, resolution.replace("_", " ").capitalize()
                ),
                "casos": count,
            }
            for resolution, count in sorted(human_resolutions.items())
        ],
        "escalation_resolutions": [
            {"resolucion": resolution, "casos": count}
            for resolution, count in sorted(human_resolutions.items())
        ],
        "institutions": [
            {
                **summary,
                "tasa_fit": round(summary["fit"] / summary["casos"] * 100, 1) if summary["casos"] else None,
            }
            for summary in sorted(institutions.values(), key=lambda item: item["casos"], reverse=True)
        ],
        "by_sex": _bias_group_stats(
            cases, lambda case: getattr(case, "cv_document", None).sexo if getattr(case, "cv_document", None) else None
        ),
        "by_birth_decade": _bias_group_stats(cases, lambda case: _birth_decade(getattr(case, "cv_document", None))),
        "cases_by_day": [
            {"fecha": day, "casos": count} for day, count in sorted(cases_by_day.items())
        ],
        "activity_by_day": [
            {
                "fecha": day,
                "casos_iniciados": cases_by_day[day],
                "decisiones_finales": decisions_by_day[day],
            }
            for day in sorted(set(cases_by_day) | set(decisions_by_day))
        ],
        "jobs": [
            {
                **summary,
                "tasa_aprobacion": round(summary["aprobados"] / summary["decisiones_finales"] * 100, 1)
                if summary["decisiones_finales"]
                else None,
            }
            for summary in sorted(jobs.values(), key=lambda item: item["casos"], reverse=True)
        ],
    }


def _numeric_output_value(output_data: dict | None, key: str) -> float | None:
    """Obtiene un valor numérico no negativo de la salida JSON de un nodo."""
    value = (output_data or {}).get(key)
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None
