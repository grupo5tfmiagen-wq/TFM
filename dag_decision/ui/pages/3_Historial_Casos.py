"""Pagina: historial y auditoria de casos."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # dag_decision/, para poder importar src.*

import streamlit as st

from src.db.base import SessionLocal
from src.ui_support import queries

st.set_page_config(page_title="Historial de Casos", page_icon="📊", layout="wide")
st.title("Historial de Casos")

status_filter = st.selectbox("Filtrar por estado", ["(todos)", "running", "waiting_human", "closed"])

with SessionLocal() as session:
    cases = queries.list_cases(session, status=None if status_filter == "(todos)" else status_filter)
    table = [
        {
            "case_id": str(c.id),
            "creado": c.created_at,
            "estado": c.status,
            "outcome": c.final_decision.outcome if c.final_decision else None,
            "candidato": c.cv_document.candidate_name if c.cv_document else None,
            "oferta": c.job_posting.titulo if c.job_posting else None,
        }
        for c in cases
    ]

if not table:
    st.info("No hay casos que coincidan con el filtro.")
    st.stop()

st.dataframe(table, width="stretch")

case_ids = [row["case_id"] for row in table]
selected_case_id = st.selectbox("Ver detalle del caso", case_ids)

with SessionLocal() as session:
    detail = queries.get_case_detail(session, selected_case_id)

if detail is None:
    st.error("No se ha podido cargar el detalle del caso.")
    st.stop()

st.divider()
st.subheader(f"Detalle — {selected_case_id}")
st.write(f"Estado: **{detail.status}** · Tipo: {detail.case_type}")

for node_execution in detail.node_executions:
    with st.expander(f"Nodo: {node_execution.node_key} ({node_execution.status})"):
        st.json(node_execution.output_data or {})
        for rule in node_execution.rule_evaluations:
            st.write(f"Regla **{rule.rule_name}** → {'✅ pasa' if rule.result_bool else '❌ no pasa'}")
            st.json(rule.details or {})
        for llm in node_execution.llm_decisions:
            st.write(f"LLM ({llm.model_name}) · confianza: {llm.confidence}")
            st.json(llm.structured_output or {})
        for validation in node_execution.validations:
            st.write(
                f"Validacion: {'válida' if validation.is_valid else 'no válida'} · "
                f"requiere revision humana: {validation.requires_review}"
            )

if detail.human_escalations:
    st.subheader("Escalaciones humanas")
    for esc in detail.human_escalations:
        st.write(f"[{esc.status}] {esc.reason} → resolucion: {esc.resolution} (revisor: {esc.assigned_to})")

if detail.final_decision:
    st.subheader("Decision final")
    st.write(f"Outcome: **{detail.final_decision.outcome}**")
    st.json(detail.final_decision.consolidated_from or {})
