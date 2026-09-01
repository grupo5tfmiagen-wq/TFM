"""Consultas de solo lectura para la UI Streamlit.

Separadas de `src/escalation/service.py` porque no forman parte del
contrato que usan los nodos del grafo: solo alimentan las paginas de
listado/auditoria (selectbox de CVs/ofertas, historial de casos).
"""
from __future__ import annotations

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
