"""Pagina: indicadores operativos y de calidad del motor de decision."""
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import altair as alt
import pandas as pd
import streamlit as st

from src.db.base import SessionLocal
from src.ui_support import queries


def _format_duration(seconds: float | None) -> str:
    """Representa una duracion breve de forma legible en una tarjeta KPI."""
    if seconds is None:
        return "Sin datos"
    if seconds < 60:
        return f"{seconds:.0f} s"
    minutes = round(seconds / 60)
    if minutes < 60:
        return f"{minutes} min"
    hours, remaining_minutes = divmod(minutes, 60)
    return f"{hours} h {remaining_minutes} min"


def _format_cost(amount: float | None) -> str:
    """Representa costes pequenos de LLM sin perder precision util."""
    if amount is None:
        return "Sin datos"
    return f"${amount:.4f}" if amount < 1 else f"${amount:.2f}"


st.set_page_config(page_title="Metricas", page_icon="📈", layout="wide")

st.markdown(
    """
    <style>
        div[data-testid="stMetric"] {background: #f6f8fc; border-left: 4px solid #1f77b4; padding: 0.85rem; border-radius: 6px;}
        div[data-testid="stMetricLabel"] {color: #44546a;}
    </style>
    """,
    unsafe_allow_html=True,
)
st.title("Metricas del motor de decision")
st.caption("Actividad, decisiones finales, intervencion humana y calidad de la evaluacion.")

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

st.subheader("Resultados y calidad")
result_row = st.columns(4)
result_row[0].metric("Casos analizados", metrics["total_cases"])
result_row[1].metric(
    "Decisiones finales",
    metrics["final_decisions"],
    delta=f"{metrics['open_cases']} sin decision",
    delta_color="off",
)
result_row[2].metric(
    "Aprobados",
    metrics["fit_cases"],
    delta=f"{metrics['fit_rate']:.1f}% de decisiones finales",
    delta_color="off",
)
result_row[3].metric(
    "Confianza LLM",
    f"{metrics['average_confidence']:.1f}%" if metrics["average_confidence"] is not None else "Sin datos",
)

st.subheader("Intervencion humana")
review_row = st.columns(3)
review_row[0].metric(
    "Casos escalados",
    metrics["escalated_cases"],
    delta=f"{metrics['escalation_rate']:.1f}% de casos analizados",
    delta_color="off",
)
review_row[1].metric(
    "En cola humana",
    metrics["pending_escalations"],
    delta=f"{metrics['human_decisions']} decisiones resueltas",
    delta_color="off",
)
review_row[2].metric(
    "Tiempo medio de revision",
    _format_duration(
        metrics["average_human_review_minutes"] * 60
        if metrics["average_human_review_minutes"] is not None
        else None
    ),
)

st.subheader("Eficiencia operativa")
efficiency_row = st.columns(3)
efficiency_row[0].metric(
    "Filtrados por reglas",
    metrics["rejected_cases"],
    delta=f"{metrics['rule_filter_rate']:.1f}% sin llamada al LLM",
    delta_color="off",
)
usage_detail = (
    "Sin ejecuciones LLM"
    if not metrics["llm_calls"]
    else f"{metrics['llm_usage_records']}/{metrics['llm_calls']} con coste · "
    f"{metrics['total_llm_tokens']:,} tokens"
    if metrics["total_llm_tokens"] is not None
    else f"{metrics['llm_usage_records']}/{metrics['llm_calls']} con coste registrado"
)
efficiency_row[1].metric(
    "Coste estimado LLM",
    _format_cost(metrics["total_llm_cost_usd"]),
    delta=usage_detail,
    delta_color="off",
)
efficiency_row[2].metric("Tiempo hasta decision", _format_duration(metrics["average_decision_seconds"]))

left_chart, right_chart = st.columns(2)
with left_chart:
    st.subheader("Resultado de decisiones cerradas")
    if metrics["outcomes"]:
        outcome_frame = pd.DataFrame(metrics["outcomes"])
        outcome_chart = (
            alt.Chart(outcome_frame)
            .mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4)
            .encode(
                x=alt.X("casos:Q", title="Casos"),
                y=alt.Y("resultado:N", title=None, sort="-x", axis=alt.Axis(labelLimit=220)),
                color=alt.Color(
                    "resultado:N",
                    scale=alt.Scale(
                        domain=["Aprobado", "No apto", "Descartado por reglas", "Sin conclusion"],
                        range=["#2a9d8f", "#e76f51", "#e9c46a", "#6c757d"],
                    ),
                    legend=None,
                ),
                tooltip=[alt.Tooltip("resultado:N", title="Resultado"), alt.Tooltip("casos:Q", title="Casos")],
            )
            .properties(height=250)
        )
        st.altair_chart(outcome_chart, width="stretch")
    else:
        st.info("Todavia no hay decisiones finales en este periodo.")
with right_chart:
    st.subheader("Decisiones de revision humana")
    if metrics["human_resolutions"]:
        resolution_frame = pd.DataFrame(metrics["human_resolutions"])
        resolution_chart = (
            alt.Chart(resolution_frame)
            .mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4)
            .encode(
                x=alt.X("casos:Q", title="Casos"),
                y=alt.Y("resolucion:N", title=None, sort="-x", axis=alt.Axis(labelLimit=220)),
                color=alt.Color(
                    "resolucion:N",
                    scale=alt.Scale(range=["#2a9d8f", "#e76f51"]),
                    legend=None,
                ),
                tooltip=[alt.Tooltip("resolucion:N", title="Decision"), alt.Tooltip("casos:Q", title="Casos")],
            )
            .properties(height=250)
        )
        st.altair_chart(resolution_chart, width="stretch")
    else:
        st.info("No hay escalaciones humanas resueltas en este periodo.")

st.subheader("Actividad por dia")
activity_frame = pd.DataFrame(metrics["activity_by_day"])
activity_frame["fecha"] = pd.to_datetime(activity_frame["fecha"])
activity_long = activity_frame.melt("fecha", var_name="serie", value_name="casos")
activity_chart = (
    alt.Chart(activity_long)
    .mark_line(point=True, strokeWidth=3)
    .encode(
        x=alt.X("fecha:T", title=None),
        y=alt.Y("casos:Q", title="Casos", scale=alt.Scale(zero=True)),
        color=alt.Color(
            "serie:N",
            title=None,
            scale=alt.Scale(domain=["casos_iniciados", "decisiones_finales"], range=["#457b9d", "#e76f51"]),
        ),
        tooltip=[alt.Tooltip("fecha:T", title="Fecha"), alt.Tooltip("serie:N", title="Serie"), alt.Tooltip("casos:Q", title="Casos")],
    )
    .properties(height=260)
)
st.altair_chart(activity_chart, width="stretch")

st.subheader("Rendimiento por oferta")
job_frame = pd.DataFrame(metrics["jobs"])
st.dataframe(
    job_frame[
        [
            "oferta",
            "casos",
            "decisiones_finales",
            "aprobados",
            "no_aptos",
            "descartados_por_reglas",
            "escalados",
            "tasa_aprobacion",
        ]
    ],
    column_config={
        "oferta": "Oferta",
        "casos": "Casos",
        "decisiones_finales": "Decisiones finales",
        "aprobados": "Aprobados",
        "no_aptos": "No aptos",
        "descartados_por_reglas": "Descartados por reglas",
        "escalados": "Escalados",
        "tasa_aprobacion": st.column_config.NumberColumn("Tasa de aprobacion", format="%.1f%%"),
    },
    hide_index=True,
    width="stretch",
)

st.divider()
st.subheader("Sesgo por institución educativa")
st.caption(
    "Tasa de aprobación entre candidatos que cursaron estudios en cada institución "
    "(candidato.cv.education del caso). Con pocos casos por institución, la tasa "
    "puede no ser representativa — mira siempre la columna 'Casos' antes de sacar "
    "conclusiones."
)
if metrics["institutions"]:
    institutions_frame = pd.DataFrame(metrics["institutions"])
    st.dataframe(
        institutions_frame[["institucion", "casos", "fit", "tasa_fit"]],
        column_config={
            "institucion": "Institución",
            "casos": "Casos",
            "fit": "Aprobados",
            "tasa_fit": st.column_config.NumberColumn("Tasa de aprobación", format="%.1f%%"),
        },
        hide_index=True,
        width="stretch",
    )
else:
    st.info("No hay datos de institución educativa en los casos de este periodo.")

def _render_bias_table(rows: list[dict], group_label: str) -> None:
    if not rows:
        st.info(f"No hay casos con dato de {group_label.lower()} registrado en este periodo.")
        return
    frame = pd.DataFrame(rows)
    st.dataframe(
        frame[["grupo", "casos", "fit", "tasa_fit", "tasa_escalacion", "confianza_media"]],
        column_config={
            "grupo": group_label,
            "casos": "Casos",
            "fit": "Aprobados",
            "tasa_fit": st.column_config.NumberColumn("Tasa de aprobación", format="%.1f%%"),
            "tasa_escalacion": st.column_config.NumberColumn("Tasa de escalación", format="%.1f%%"),
            "confianza_media": st.column_config.NumberColumn("Confianza media LLM", format="%.1f%%"),
        },
        hide_index=True,
        width="stretch",
    )


st.subheader("Sesgo por sexo")
st.caption(
    "El sexo del candidato nunca se envía al modelo (no forma parte del payload que "
    "evalúan las reglas ni el LLM) — esta tabla cruza el dato, guardado solo para "
    "auditoría, con el resultado real del caso. Con pocos casos por grupo, la tasa "
    "puede no ser representativa: mira siempre la columna 'Casos'."
)
_render_bias_table(metrics["by_sex"], "Sexo")

st.subheader("Sesgo por década de nacimiento")
st.caption("Mismo cruce que arriba, agrupado por década de nacimiento del candidato.")
_render_bias_table(metrics["by_birth_decade"], "Década")

with st.expander("Glosario de terminos"):
    st.markdown(
        """
| Termino | Significado |
| --- | --- |
| Caso analizado | Evaluacion de un CV frente a una oferta de empleo. |
| Decision final | Resultado oficial persistido al terminar el flujo. |
| Aprobado (`fit`) | El candidato se considera adecuado para la oferta. |
| No apto (`not_fit`) | El LLM o el revisor concluye que el candidato no encaja. |
| Descartado por reglas (`rejected`) | El candidato no supera requisitos obligatorios; no llega al LLM. |
| Escalacion humana | Caso enviado a una persona por baja confianza o resultado no concluyente. |
| En cola humana | Escalacion que espera todavia la resolucion de un revisor. |
| Confianza LLM | Seguridad declarada por el modelo sobre su valoracion. |
| Tasa de aprobacion | Casos `fit` sobre el total de decisiones finales. |
| Tasa de escalacion | Casos con revision humana sobre el total de casos analizados. |
| Tiempo medio de revision | Minutos entre crear y resolver una escalacion humana. |
| Filtrado por reglas | Casos `rejected` que no llegan al LLM por incumplir requisitos obligatorios. |
| Coste estimado LLM | Suma del coste aproximado de las llamadas con uso de tokens disponible. |
| Tiempo hasta decision | Tiempo medio entre crear un caso y registrar su decision final. |
| Sesgo por institucion educativa | Comparativa de resultados entre instituciones declaradas en la formacion del CV. |
| Sesgo por sexo | Comparativa de resultados por sexo, usado solo para auditoria y nunca enviado al modelo. |
| Sesgo por decada de nacimiento | Comparativa de resultados por cohortes de edad, usado solo para auditoria. |
        """
    )
