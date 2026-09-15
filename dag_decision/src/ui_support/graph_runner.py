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


def _stream_graph(case_id: str, graph_input: Any, seed: dict[str, Any] | None = None):
    """Ejecuta el grafo con `graph.stream(..., stream_mode='updates')` en vez
    de `graph.invoke(...)`, cediendo el progreso nodo a nodo.

    `stream_mode="updates"` hace que LangGraph vaya soltando un dict
    `{node_key: salida_del_nodo}` cada vez que un nodo termina, en vez de
    esperar al resultado final de una tacada (como hace `invoke`). Eso es lo
    que permite pintar el diagrama del pipeline en tiempo real.

    Cede tuplas `(node_key, node_output, accumulated_state)`. Si el caso se
    pausa, la ultima tupla cedida tiene `node_key == "__interrupt__"` con el
    payload de `interrupt()` en `node_output`.

    `seed` deja arrancar `accumulated_state` con lo que ya se sabia de antes
    (usado por `resume_case_streaming`: al reanudar, LangGraph solo vuelve a
    emitir los nodos que faltan por ejecutar — `human_escalation` y
    `final_decision` — no los que ya se ejecutaron antes de la pausa, asi que
    sin `seed` el diagrama "olvidaria" ese progreso previo).
    """
    with get_checkpointer() as checkpointer:  # type: ignore
        graph = build_graph(checkpointer)
        config = {"configurable": {"thread_id": case_id}}

        accumulated: dict[str, Any] = {"case_id": case_id, "case_type": "candidate_selection"}
        if seed:
            accumulated.update({k: v for k, v in seed.items() if k != "__interrupt__"})

        for chunk in graph.stream(graph_input, config=config, stream_mode="updates"):  # type: ignore
            for node_key, node_output in chunk.items():
                if node_key == "__interrupt__":
                    interrupt_payload = node_output[0].value if node_output else None
                    yield "__interrupt__", interrupt_payload, dict(accumulated)
                    return
                if isinstance(node_output, dict):
                    accumulated.update(node_output)
                yield node_key, node_output, dict(accumulated)


def start_case_streaming(cv_id: str, job_id: str):
    """Version en streaming de `start_case` (ver `_stream_graph`): crea el
    `Case` en BD exactamente igual, pero en vez de devolver el resultado de
    una tacada, va cediendo el progreso nodo a nodo para que la UI pueda ir
    pintando el diagrama del pipeline en tiempo real."""
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

    initial_state = {"case_id": case_id, "case_type": "candidate_selection", "payload": payload}
    yield from _stream_graph(case_id, initial_state)


def resume_case_streaming(case_id: str, outcome: str, reviewer: str, previous_result: dict[str, Any] | None = None):
    """Version en streaming de `resume_case` (ver `_stream_graph`). Pasa el
    `result` acumulado hasta la pausa como `previous_result`/`seed`, para que
    el diagrama siga mostrando como "hecho" lo que ya se ejecuto antes de
    pausarse en vez de reiniciar el progreso desde cero."""
    yield from _stream_graph(
        case_id, Command(resume={"outcome": outcome, "reviewer": reviewer}), seed=previous_result
    )


def start_batch_streaming(cv_ids: list[str], job_id: str):
    """Lanza el pipeline en serie para varios CVs contra la misma oferta.

    Reutiliza `start_case_streaming` para cada CV, uno detras de otro (nunca
    en paralelo). Cede tuplas `(cv_id, node_key, node_output,
    accumulated_state)`, igual que `start_case_streaming` pero con el
    `cv_id` delante, para que quien consuma el generador sepa a que
    candidato del lote pertenece cada paso.

    No comprueba si un CV ya tiene un caso previo para esta oferta: quien
    llama a esto (la pagina de Streamlit) decide que `cv_ids` incluir,
    despues de preguntarselo al usuario si hay duplicados.
    """
    for cv_id in cv_ids:
        for node_key, node_output, accumulated in start_case_streaming(cv_id, job_id):
            yield cv_id, node_key, node_output, accumulated
