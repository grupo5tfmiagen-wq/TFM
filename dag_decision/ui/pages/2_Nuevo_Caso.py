"""Pagina: lanzar un caso nuevo (CV + oferta ya en BD) por el motor de decision DAG."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # dag_decision/, para poder importar src.*

import streamlit as st

from src.db.base import SessionLocal
from src.ui_support import graph_runner, queries
from src.ui_support.render import build_graph_dot, compute_node_statuses, render_case_result, render_pipeline_diagram

st.set_page_config(page_title="Nuevo Caso", page_icon="🆕")
st.title("Nuevo Caso")

with SessionLocal() as session:
    cvs = queries.list_cv_documents(session)
    jobs = queries.list_job_postings(session)

if not cvs or not jobs:
    st.warning(
        "Hacen falta CVs y ofertas en la base de datos. Ejecuta "
        "`scripts/load_demo_data.py` primero."
    )
    st.stop()

cv_choice = st.selectbox("Candidato", cvs, format_func=lambda cv: f"{cv.candidate_name} ({cv.candidate_id})")
job_choice = st.selectbox("Oferta", jobs, format_func=lambda job: f"{job.titulo} ({job.external_id})")

_NODE_LABELS = {
    "rule_evaluator": "1. Requisitos obligatorios",
    "llm_decision": "2. Evaluación LLM",
    "validation": "3. Validación",
    "human_escalation": "4. Revisión humana",
    "final_decision": "5. Decisión final",
}


def _run_streaming(step_iterator, diagram_slot, status_slot) -> tuple[dict, dict | None]:
    """Consume un generador de `graph_runner` (`start_case_streaming` /
    `resume_case_streaming`), redibujando el diagrama del pipeline en
    `diagram_slot` en cada paso segun va terminando cada nodo de verdad —
    no es una animacion simulada, cada frame corresponde a un nodo que
    acaba de ejecutarse en el grafo real.

    Devuelve `(result, interrupt_payload)`; al terminar, limpia los
    placeholders para que no quede el "rastro" en vivo duplicado con el
    diagrama persistente que se pinta mas abajo con `render_pipeline_diagram`.
    """
    result: dict = {}
    interrupt_payload = None

    for node_key, node_output, accumulated in step_iterator:
        result = accumulated
        if node_key == "__interrupt__":
            interrupt_payload = node_output
            status_slot.warning("Pausado esperando revisión humana.")
            diagram_slot.graphviz_chart(
                build_graph_dot(compute_node_statuses(result, is_paused=True)), width="stretch"
            )
            break

        status_slot.info(f"Ejecutando: {_NODE_LABELS.get(node_key, node_key)}...")
        diagram_slot.graphviz_chart(
            build_graph_dot(compute_node_statuses(result, is_paused=False)), width="stretch"
        )
    else:
        status_slot.success("Pipeline completado.")

    diagram_slot.empty()
    status_slot.empty()
    return result, interrupt_payload


if st.button("Lanzar caso", type="primary"):
    status_slot = st.empty()
    diagram_slot = st.empty()
    try:
        result, interrupt_payload = _run_streaming(
            graph_runner.start_case_streaming(str(cv_choice.id), str(job_choice.id)),
            diagram_slot,
            status_slot,
        )
    except ValueError as exc:
        st.error(str(exc))
    else:
        st.session_state["nuevo_caso_case_id"] = result.get("case_id")
        st.session_state["nuevo_caso_result"] = result
        st.session_state["nuevo_caso_interrupt"] = interrupt_payload

case_id = st.session_state.get("nuevo_caso_case_id")
if case_id:
    st.divider()
    st.subheader(f"Caso {case_id}")

    result = st.session_state["nuevo_caso_result"]
    interrupt_payload = st.session_state.get("nuevo_caso_interrupt")

    st.markdown("##### Recorrido por el pipeline")
    render_pipeline_diagram(result, is_paused=bool(interrupt_payload))

    render_case_result(result)

    with st.expander("Ver JSON crudo"):
        st.json({k: v for k, v in result.items() if k != "__interrupt__"})

    if interrupt_payload:
        st.warning("El caso esta pausado esperando revision humana.")

        with st.form("resolver_escalacion"):
            outcome_choice = st.radio("Decision", ["fit", "not_fit"], horizontal=True)
            reviewer = st.text_input("Identificador de revisor")
            submitted = st.form_submit_button("Resolver y continuar")

        if submitted:
            if not reviewer:
                st.error("Indica un identificador de revisor.")
            else:
                status_slot = st.empty()
                diagram_slot = st.empty()
                resumed_result, resumed_interrupt = _run_streaming(
                    graph_runner.resume_case_streaming(case_id, outcome_choice, reviewer, previous_result=result),
                    diagram_slot,
                    status_slot,
                )
                st.session_state["nuevo_caso_result"] = resumed_result
                st.session_state["nuevo_caso_interrupt"] = resumed_interrupt
                st.rerun()
