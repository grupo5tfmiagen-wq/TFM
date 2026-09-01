"""Envoltorio del motor de decision DAG para la UI Streamlit.

Reutiliza el mismo patron que `scripts/run_case.py`/`scripts/review_escalations.py`:
sesion SQLAlchemy y checkpointer de Postgres de vida corta por accion, sin
cachear conexiones entre reruns de Streamlit.
"""
from __future__ import annotations

from typing import Any

from langgraph.types import Command

from ..db.base import SessionLocal
from ..db.checkpointer import get_checkpointer
from ..db.models.case import Case
from ..db.models.cv_document import CVDocument
from ..db.models.job_posting import JobPosting
from ..graph.build import build_graph
from ..graph.payload_builder import build_case_payload


def start_case(cv_id: str, job_id: str) -> dict[str, Any]:
    """Crea un `Case` a partir de un CV y una oferta ya en BD e invoca el grafo.

    Devuelve `{"case_id", "result", "interrupt"}`; `interrupt` trae el
    payload de `interrupt()` si el caso se ha pausado en `human_escalation`,
    o `None` si ha llegado directamente a una decision final.
    """
    with SessionLocal() as session:
        cv = session.get(CVDocument, cv_id)
        job = session.get(JobPosting, job_id)
        if cv is None or job is None:
            raise ValueError("CV u oferta no encontrados en la base de datos.")

        payload = build_case_payload(cv, job)
        case = Case(
            case_type="candidate_selection",
            status="running",
            payload=payload,
            cv_document_id=cv.id,
            job_posting_id=job.id,
        )
        session.add(case)
        session.commit()
        case_id = str(case.id)

    with get_checkpointer() as checkpointer: # type: ignore
        graph = build_graph(checkpointer)
        config = {"configurable": {"thread_id": case_id}}
        initial_state = {"case_id": case_id, "case_type": "candidate_selection", "payload": payload}
        result = graph.invoke(initial_state, config=config) # type: ignore

    interrupt_payload = result["__interrupt__"][0].value if "__interrupt__" in result else None
    return {"case_id": case_id, "result": result, "interrupt": interrupt_payload}


def resume_case(case_id: str, outcome: str, reviewer: str) -> dict[str, Any]:
    """Reanuda un caso pausado en `human_escalation` con la decision del revisor."""
    with get_checkpointer() as checkpointer: # type: ignore
        graph = build_graph(checkpointer)
        config = {"configurable": {"thread_id": case_id}}
        result = graph.invoke(Command(resume={"outcome": outcome, "reviewer": reviewer}), config=config) # type: ignore
    return {"case_id": case_id, "result": result}
