"""Pagina: lanzar el pipeline para todos los CVs disponibles contra una oferta."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # dag_decision/, para poder importar src.*

import streamlit as st

from src.db.base import SessionLocal
from src.ui_support import graph_runner, queries
from src.ui_support.render import build_graph_dot, compute_node_statuses, render_case_result

st.set_page_config(page_title="Lanzar Lote", page_icon="📦", layout="wide")
st.title("Lanzar Lote")
st.caption("Ejecuta el pipeline para varios candidatos, en serie, contra la misma oferta.")

_NODE_LABELS = {
    "rule_evaluator": "1. Requisitos obligatorios",
    "llm_decision": "2. Evaluación LLM",
    "validation": "3. Validación",
    "human_escalation": "4. Revisión humana",
    "final_decision": "5. Decisión final",
}

with SessionLocal() as session:
    cvs = queries.list_cv_documents(session)
    jobs = queries.list_job_postings(session)

if not cvs or not jobs:
    st.warning(
        "Hacen falta CVs y ofertas en la base de datos. Ejecuta "
        "`scripts/load_demo_data.py` primero."
    )
    st.stop()

job_choice = st.selectbox("Oferta", jobs, format_func=lambda job: f"{job.titulo} ({job.external_id})")

with SessionLocal() as session:
    existing_cv_ids = queries.list_case_cv_ids_for_job(session, str(job_choice.id))

st.write(
    f"**{len(cvs)}** candidatos en total · **{len(existing_cv_ids)}** ya tienen un caso previo para esta oferta."
)

cv_lookup = {str(cv.id): cv for cv in cvs}
option_ids = list(cv_lookup.keys())


def _cv_label(cv_id: str) -> str:
    cv = cv_lookup[cv_id]
    label = f"{cv.candidate_name} ({cv.candidate_id})"
    return f"{label} — ⚠️ ya tiene caso previo" if cv_id in existing_cv_ids else label


selected_cv_ids = st.multiselect(
    "Candidatos a incluir en el lote",
    options=option_ids,
    default=[cv_id for cv_id in option_ids if cv_id not in existing_cv_ids],
    format_func=_cv_label,
)

duplicated_selected = [cv_id for cv_id in selected_cv_ids if cv_id in existing_cv_ids]
if duplicated_selected:
    nombres = ", ".join(cv_lookup[cv_id].candidate_name for cv_id in duplicated_selected)
    st.warning(
        f"{len(duplicated_selected)} candidato(s) seleccionados ya tienen un caso previo para esta oferta "
        f"y se lanzará un caso **duplicado** si continúas: {nombres}."
    )

launch = st.button("Lanzar lote", type="primary", disabled=not selected_cv_ids)

if launch:
    summary_rows = []
    current_cv_id = None
    status_box = None
    diagram_slot = None
    text_slot = None
    result: dict = {}
    interrupt_payload = None

    def _close_current() -> None:
        cv = cv_lookup[current_cv_id]
        with status_box:
            render_case_result(result)
        if interrupt_payload:
            status_box.update(label=f"⏸️ {cv.candidate_name} — pendiente en Cola de Escalaciones", state="error")
            summary_rows.append(
                {"candidato": cv.candidate_name, "case_id": result.get("case_id"), "resultado": "pendiente de revisión"}
            )
        else:
            outcome = result.get("outcome")
            status_box.update(label=f"✅ {cv.candidate_name} — {outcome}", state="complete")
            summary_rows.append({"candidato": cv.candidate_name, "case_id": result.get("case_id"), "resultado": outcome})

    for cv_id, node_key, node_output, accumulated in graph_runner.start_batch_streaming(selected_cv_ids, str(job_choice.id)):
        if cv_id != current_cv_id:
            if current_cv_id is not None:
                _close_current()
            current_cv_id = cv_id
            cv = cv_lookup[cv_id]
            status_box = st.status(f"{cv.candidate_name} ({cv.candidate_id})", expanded=True)
            diagram_slot = status_box.empty()
            text_slot = status_box.empty()
            result = {}
            interrupt_payload = None

        result = accumulated
        if node_key == "__interrupt__":
            interrupt_payload = node_output
            text_slot.warning("Pausado esperando revisión humana.")
            diagram_slot.graphviz_chart(
                build_graph_dot(compute_node_statuses(result, is_paused=True)), width="stretch"
            )
        else:
            text_slot.caption(f"Ejecutando: {_NODE_LABELS.get(node_key, node_key)}...")
            diagram_slot.graphviz_chart(
                build_graph_dot(compute_node_statuses(result, is_paused=False)), width="stretch"
            )

    if current_cv_id is not None:
        _close_current()

    st.divider()
    st.subheader("Resumen del lote")
    st.dataframe(summary_rows, width="stretch")

    if any(row["resultado"] == "pendiente de revisión" for row in summary_rows):
        st.info("Los casos pendientes de revisión se resuelven desde **Cola de Escalaciones**.")
