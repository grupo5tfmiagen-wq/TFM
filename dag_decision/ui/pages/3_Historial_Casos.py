"""Pagina: historial y auditoria de casos."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # dag_decision/, para poder importar src.*

import streamlit as st

from src.db.base import SessionLocal
from src.ui_support import queries

st.set_page_config(page_title="Historial de Casos", page_icon="📊", layout="wide")
st.title("Historial de Casos")


def _human_review_label(case) -> str:
    """Resume si un caso paso por revision humana, distinguiendo el caso de
    que este pendiente ahora mismo del de que ya se resolviera asi en su
    momento (`FinalDecision.decided_by`, que ya guarda `final_decision_node`)."""
    if case.status == "waiting_human":
        return "🕒 Pendiente"
    if case.final_decision and case.final_decision.decided_by == "human":
        return "Sí"
    return "No"


status_filter = st.selectbox("Filtrar por estado", ["(todos)", "running", "waiting_human", "closed"])

with SessionLocal() as session:
    cases = queries.list_cases(session, status=None if status_filter == "(todos)" else status_filter)
    table = [
        {
            "case_id": str(c.id),
            "creado": c.created_at,
            "estado": c.status,
            "revisión humana": _human_review_label(c),
            "outcome": c.final_decision.outcome if c.final_decision else None,
            "candidato": c.cv_document.candidate_name if c.cv_document else None,
            "oferta": c.job_posting.titulo if c.job_posting else None,
        }
        for c in cases
    ]

if not table:
    st.info("No hay casos que coincidan con el filtro.")
    st.stop()


def _iso(value):
    """Convierte datetime/UUID a algo serializable en JSON; deja el resto tal cual."""
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _real_node_entry(ne) -> dict:
    """Entrada de `nodes` para un `CaseNodeExecution` real (todos menos
    `human_escalation`, que no genera fila propia — ver `_pending_or_resolved_entry`)."""
    return {
        "node_key": ne.node_key,
        "status": ne.status,
        "started_at": _iso(ne.started_at),
        "finished_at": _iso(ne.finished_at),
        "input_data": ne.input_data,
        "output_data": ne.output_data,
        "details": {
            "rule_evaluations": [
                {"rule_name": r.rule_name, "result_bool": r.result_bool, "details": r.details}
                for r in ne.rule_evaluations
            ],
            "llm_decisions": [
                {
                    "model_name": l.model_name,
                    "confidence": l.confidence,
                    "structured_output": l.structured_output,
                }
                for l in ne.llm_decisions
            ],
            "validations": [
                {"is_valid": v.is_valid, "requires_review": v.requires_review, "reason": v.reason}
                for v in ne.validations
            ],
        },
    }


def _human_escalation_entry(h) -> dict:
    """Entrada de `nodes` sintetica para `human_escalation_node`: no existe
    ningun `CaseNodeExecution` real para este paso (no esta trazado), asi
    que se construye a partir de la fila `HumanEscalation`, que si existe
    siempre que un caso se pausa — este es el sitio donde queda explicito
    que el caso esta "pending" (esperando revision) o ya "resolved"."""
    status = "pending (esperando revision humana)" if h.status == "pending" else h.status
    return {
        "node_key": "human_escalation",
        "status": status,
        "started_at": _iso(h.created_at),
        "finished_at": _iso(h.resolved_at),
        "input_data": None,
        "output_data": None,
        "details": {"reason": h.reason, "resolution": h.resolution, "assigned_to": h.assigned_to},
    }


def _build_full_case_json(detail) -> dict:
    """Reconstruye el "JSON de inicio a fin" de un caso: una entrada por
    cada nodo ejecutado, en orden cronologico, mas la decision final.

    `human_escalation_node` no genera fila `CaseNodeExecution` (no esta
    trazado a proposito, ver su docstring), asi que sin este merge
    desaparecia sin mas del historial cuando un caso quedaba pausado, sin
    ninguna indicacion de que estaba esperando revision. Aqui se fusiona
    como una entrada mas de `nodes`, en su sitio cronologico, construida a
    partir de `HumanEscalation` en vez de un `CaseNodeExecution`.
    """
    nodes = [_real_node_entry(ne) for ne in detail.node_executions]
    nodes += [_human_escalation_entry(h) for h in detail.human_escalations]
    nodes.sort(key=lambda n: n["started_at"] or "")

    return {
        "case_id": str(detail.id),
        "case_type": detail.case_type,
        "status": detail.status,
        "created_at": _iso(getattr(detail, "created_at", None)),
        "nodes": nodes,
        "final_decision": (
            {
                "outcome": detail.final_decision.outcome,
                "decided_by": detail.final_decision.decided_by,
                "consolidated_from": detail.final_decision.consolidated_from,
            }
            if detail.final_decision
            else None
        ),
    }


@st.dialog("Resultado del caso", width="large")
def _show_case_result_dialog(case_id: str) -> None:
    """Ventana emergente con el JSON completo del caso, de inicio a fin:
    todos los nodos ejecutados (entrada/salida de cada uno), escalaciones
    humanas y decision final, tal como quedo persistido en BD."""
    with SessionLocal() as session:
        detail = queries.get_case_detail(session, case_id)

    if detail is None:
        st.error("No se ha podido cargar el detalle del caso.")
        return

    st.caption(f"Caso {case_id} · estado: {detail.status}")
    st.json(_build_full_case_json(detail))


if "historial_dialog_shown_for" not in st.session_state:
    st.session_state["historial_dialog_shown_for"] = None

event = st.dataframe(
    table,
    width="stretch",
    key="historial_tabla",
    on_select="rerun",
    selection_mode="single-row",
)

selected_rows = event.selection.rows if event and event.selection else []
if selected_rows:
    clicked_case_id = table[selected_rows[0]]["case_id"]
    if st.session_state["historial_dialog_shown_for"] != clicked_case_id:
        st.session_state["historial_dialog_shown_for"] = clicked_case_id
        _show_case_result_dialog(clicked_case_id)
else:
    st.session_state["historial_dialog_shown_for"] = None

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
