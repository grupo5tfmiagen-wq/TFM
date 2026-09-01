"""Pagina: lanzar un caso nuevo (CV + oferta ya en BD) por el motor de decision DAG."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # dag_decision/, para poder importar src.*

import streamlit as st

from src.db.base import SessionLocal
from src.ui_support import graph_runner, queries

st.set_page_config(page_title="Nuevo Caso", page_icon="🆕")
st.title("Nuevo Caso")

with SessionLocal() as session:
    cvs = queries.list_cv_documents(session)
    jobs = queries.list_job_postings(session)

if not cvs or not jobs:
    st.warning(
        "Hacen falta CVs y ofertas en la base de datos. Ejecuta "
        "`scripts/load_cv_document.py` y `scripts/load_job_posting.py` primero."
    )
    st.stop()

cv_choice = st.selectbox("Candidato", cvs, format_func=lambda cv: f"{cv.candidate_name} ({cv.candidate_id})")
job_choice = st.selectbox("Oferta", jobs, format_func=lambda job: f"{job.titulo} ({job.external_id})")

if st.button("Lanzar caso", type="primary"):
    with st.spinner("Ejecutando el pipeline..."):
        outcome = graph_runner.start_case(str(cv_choice.id), str(job_choice.id))
    st.session_state["nuevo_caso_case_id"] = outcome["case_id"]
    st.session_state["nuevo_caso_result"] = outcome["result"]
    st.session_state["nuevo_caso_interrupt"] = outcome["interrupt"]

case_id = st.session_state.get("nuevo_caso_case_id")
if case_id:
    st.divider()
    st.subheader(f"Caso {case_id}")

    result = st.session_state["nuevo_caso_result"]
    st.json({k: v for k, v in result.items() if k != "__interrupt__"})

    interrupt_payload = st.session_state.get("nuevo_caso_interrupt")
    if interrupt_payload:
        st.warning("El caso esta pausado esperando revision humana.")
        st.json(interrupt_payload)

        with st.form("resolver_escalacion"):
            outcome_choice = st.radio("Decision", ["fit", "not_fit"], horizontal=True)
            reviewer = st.text_input("Identificador de revisor")
            submitted = st.form_submit_button("Resolver y continuar")

        if submitted:
            if not reviewer:
                st.error("Indica un identificador de revisor.")
            else:
                with st.spinner("Reanudando el caso..."):
                    resumed = graph_runner.resume_case(case_id, outcome_choice, reviewer)
                st.session_state["nuevo_caso_result"] = resumed["result"]
                st.session_state["nuevo_caso_interrupt"] = None
                st.rerun()
    else:
        st.success(f"Decision final: {result.get('outcome')}")
