"""Pagina: indicadores operativos y de calidad del motor de decision."""
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st

from src.db.base import SessionLocal
from src.ui_support import queries

st.set_page_config(page_title="Metricas", page_icon="📈", layout="wide")

st.markdown(
    """
    <style>
        .metric-card {padding: 0.45rem 0.2rem 0.2rem;}
        div[data-testid="stMetric"] {background: #f6f8fc; border-left: 4px solid #1f77b4; padding: 0.85rem; border-radius: 6px;}
        div[data-testid="stMetricLabel"] {color: #44546a;}
    </style>
    """,
    unsafe_allow_html=True,
)
st.title("Metricas del motor de decision")
st.caption("Seguimiento de volumen, decisiones finales, intervencion humana y calidad de la evaluacion.")

with SessionLocal() as session:
    postings = queries.list_job_postings(session)

filter_left, filter_right = st.columns([2, 3])
with filter_left:
    date_range = st.date_input(
        "Periodo de analisis",
        value=(date.today() - timedelta(days=30), date.today()),
        max_value=date.today(),
    )
with filter_right:
    posting_options = {"Todas las ofertas": None}
    posting_options.update({f"{posting.titulo}": str(posting.id) for posting in postings})
    selected_posting = st.selectbox("Oferta", list(posting_options))

if isinstance(date_range, tuple) and len(date_range) == 2:
    start_date, end_date = date_range
else:
    start_date = end_date = date_range

with SessionLocal() as session:
    metrics = queries.get_dashboard_metrics(
        session,
        start_date=start_date,
        end_date=end_date,
        job_posting_id=posting_options[selected_posting],
    )

if not metrics["total_cases"]:
    st.info("No hay casos para los filtros seleccionados. Ajusta el periodo o ejecuta nuevos casos.")
    st.stop()

top_row = st.columns(3)
top_row[0].metric("Casos evaluados", metrics["total_cases"])
top_row[1].metric("Casos cerrados", metrics["closed_cases"])
top_row[2].metric("Tasa de aprobacion", f"{metrics['fit_rate']:.1f}%")
bottom_row = st.columns(2)
bottom_row[0].metric("Casos escalados", metrics["escalated_cases"])
bottom_row[1].metric("Revisiones pendientes", metrics["pending_escalations"])

if metrics["average_confidence"] is not None:
    st.caption(f"Confianza media del LLM: {metrics['average_confidence']:.1f}%")

left_chart, right_chart = st.columns(2)
with left_chart:
    st.subheader("Resultado de decisiones cerradas")
    if metrics["outcomes"]:
        outcome_frame = pd.DataFrame(metrics["outcomes"]).set_index("resultado")
        st.bar_chart(outcome_frame, color="#1f77b4")
    else:
        st.info("Todavia no hay decisiones finales en este periodo.")
with right_chart:
    st.subheader("Resoluciones de revision humana")
    if metrics["escalation_resolutions"]:
        resolution_frame = pd.DataFrame(metrics["escalation_resolutions"]).set_index("resolucion")
        st.bar_chart(resolution_frame, color="#2a9d8f")
    else:
        st.info("No hay escalaciones humanas resueltas en este periodo.")

st.subheader("Evolucion de casos")
daily_frame = pd.DataFrame(metrics["cases_by_day"]).set_index("fecha")
st.line_chart(daily_frame, color="#e76f51")

st.subheader("Rendimiento por oferta")
job_frame = pd.DataFrame(metrics["jobs"])
st.dataframe(
    job_frame[["oferta", "casos", "cerrados", "fit", "tasa_fit"]],
    column_config={
        "oferta": "Oferta",
        "casos": "Casos",
        "cerrados": "Cerrados",
        "fit": "Aprobados",
        "tasa_fit": st.column_config.NumberColumn("Tasa de aprobacion", format="%.1f%%"),
    },
    hide_index=True,
    width="stretch",
)