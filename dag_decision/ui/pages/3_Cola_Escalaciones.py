"""Pagina: cola de revision humana (Human Escalation Layer)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # dag_decision/, para poder importar src.*

import streamlit as st

from src.db.base import SessionLocal
from src.escalation.service import list_pending_escalations
from src.ui_support import graph_runner
from src.ui_support.render import truncate

st.set_page_config(page_title="Cola de Escalaciones", page_icon="📋")
st.title("Cola de Escalaciones")

with SessionLocal() as session:
    pending = list_pending_escalations(session)
    pending_view = [
        {
            "escalation_id": str(e.id),
            "case_id": str(e.case_id),
            "reason": e.reason,
            "created_at": e.created_at,
        }
        for e in pending
    ]

if not pending_view:
    st.info("No hay escalaciones pendientes.")
    st.stop()

st.dataframe(pending_view, width="stretch")

# Antes la etiqueta era "case_id — reason", y `reason` podia ser el dict
# entero de `llm_decision` volcado como texto (ver el fix en
# `human_escalation_node`). Ahora `reason` ya es solo la justificacion del
# LLM, pero aun asi se recorta aqui para que la lista de opciones se pueda
# leer de un vistazo: un case_id corto (8 caracteres) + el motivo truncado.
labels = [f"{row['case_id'][:8]} — {truncate(row['reason'])}" for row in pending_view]
selected_index = st.selectbox("Escalacion a resolver", range(len(pending_view)), format_func=lambda i: labels[i])
selected = pending_view[selected_index]

st.info(f"**Motivo:** {selected['reason'] or '(sin motivo registrado)'}")

with st.form("resolver_desde_cola"):
    outcome_choice = st.radio("Decision", ["fit", "not_fit"], horizontal=True)
    reviewer = st.text_input("Identificador de revisor")
    submitted = st.form_submit_button("Resolver")

if submitted:
    if not reviewer:
        st.error("Indica un identificador de revisor.")
    else:
        with st.spinner("Reanudando el caso..."):
            try:
                resumed = graph_runner.resume_case(selected["case_id"], outcome_choice, reviewer)
            except Exception as exc:
                st.error(f"No se pudo reanudar el caso: {exc}")
            else:
                st.success(f"Caso {selected['case_id']} resuelto. Resultado final: {resumed['result'].get('outcome')}")
                st.rerun()
