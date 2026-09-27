"""Helpers de renderizado para las paginas de Streamlit.

Centraliza como se muestra el resultado de un caso (`CaseState` acumulado
que devuelve `graph.invoke()`), para no repetir la logica de "que significa
cada campo" en cada pagina y para que un caso rechazado se explique con el
mismo nivel de detalle que uno aceptado.
"""
from __future__ import annotations

from typing import Any

import streamlit as st

_OUTCOME_DISPLAY = {
    "fit": ("✅ Candidato apto", "success"),
    "not_fit": ("❌ Candidato no apto", "error"),
    "rejected": ("🚫 Descartado — no cumple los requisitos obligatorios", "error"),
    "unclear": ("⚠️ Resultado no concluyente", "warning"),
    "escalated": ("🕒 Resuelto tras revision humana", "info"),
}


def _rule_rejection_reason(rule_result: dict[str, Any]) -> str:
    """Compone en una frase por que no paso el filtro de requisitos
    obligatorios, a partir de lo que devuelve `rule_evaluator_node`."""
    reasons = []

    missing_skills = rule_result.get("missing_skills") or []
    if missing_skills:
        reasons.append(f"le faltan las habilidades obligatorias: {', '.join(missing_skills)}")

    years = rule_result.get("years_experience")
    min_years = rule_result.get("min_years_required")
    if years is not None and min_years is not None and years < min_years:
        reasons.append(f"tiene {years} años de experiencia (se requieren {min_years})")

    for language in rule_result.get("missing_languages") or []:
        if language.get("candidate"):
            reasons.append(
                f"su nivel de {language.get('language')} es {language.get('candidate')} "
                f"(se requiere {language.get('required')})"
            )
        else:
            reasons.append(f"no acredita {language.get('language')} (se requiere {language.get('required')})")

    if rule_result.get("meets_education") is False:
        candidate_level = rule_result.get("candidate_education_level") or "ninguna titulación"
        reasons.append(
            f"su formación ({candidate_level}) es inferior a la exigida "
            f"({rule_result.get('required_education_level')})"
        )

    if not reasons:
        return "No cumple los requisitos obligatorios del puesto."
    return "No cumple los requisitos obligatorios: " + "; ".join(reasons) + "."


def render_rule_result(rule_result: dict[str, Any] | None) -> None:
    """Bloque 1: filtro de requisitos obligatorios (Rule Evaluator)."""
    if not rule_result:
        return

    with st.container(border=True):
        st.markdown("##### 1. Requisitos obligatorios")
        if rule_result.get("passed"):
            years = rule_result.get("years_experience")
            min_years = rule_result.get("min_years_required")
            st.success(
                f"Cumple los requisitos obligatorios "
                f"({years} años de experiencia frente a un mínimo de {min_years})."
            )
            unverified = rule_result.get("unverified_requirements") or []
            if unverified:
                st.warning(
                    "Requisitos que no se han podido verificar automáticamente "
                    "(el caso pasará a revisión humana): " + "; ".join(unverified)
                )
        else:
            st.error(_rule_rejection_reason(rule_result))


def render_llm_decision(llm_decision: dict[str, Any] | None) -> None:
    """Bloque 2: evaluacion semantica del LLM (habilidades deseables)."""
    if not llm_decision:
        return

    with st.container(border=True):
        st.markdown("##### 2. Evaluación del ajuste (LLM)")
        col1, col2 = st.columns(2)
        col1.metric("Valoración", llm_decision.get("fit_label", "—"))
        confidence = llm_decision.get("confidence")
        col2.metric("Confianza", f"{confidence:.0%}" if confidence is not None else "—")
        st.write(llm_decision.get("justification") or "El LLM no proporciono una justificacion.")


def render_human_feedback(human_feedback: dict[str, Any] | None, requires_human: bool) -> None:
    """Bloque 3: revision humana, si el caso llego a pasar por ahi."""
    if human_feedback:
        with st.container(border=True):
            st.markdown("##### 3. Revisión humana")
            st.info(
                f"Resuelto manualmente como **{human_feedback.get('outcome')}** "
                f"por **{human_feedback.get('reviewer', 'revisor no identificado')}**."
            )
    elif requires_human:
        st.warning("Este caso esta pendiente de revision humana.")


def render_outcome_banner(outcome: str | None) -> None:
    """Cabecera con el resultado final, si ya se alcanzo (`final_decision`)."""
    if not outcome:
        return
    label, kind = _OUTCOME_DISPLAY.get(outcome, (f"Resultado: {outcome}", "info"))
    getattr(st, kind)(label)


def render_case_result(result: dict[str, Any]) -> None:
    """Renderiza el `CaseState` completo de un caso en bloques legibles.

    Pensado para sustituir un `st.json(result)` a secas: cada etapa del
    pipeline (reglas, LLM, revision humana) se explica en su propio bloque,
    tanto si el caso termina aceptado como si termina rechazado — antes solo
    se explicaba el motivo cuando el caso salia adelante.
    """
    render_outcome_banner(result.get("outcome"))
    render_rule_result(result.get("rule_result"))
    render_llm_decision(result.get("llm_decision"))
    render_human_feedback(result.get("human_feedback"), bool(result.get("requires_human")))


def truncate(text: str | None, length: int = 80) -> str:
    """Recorta un texto largo para usarlo en una etiqueta corta (selectbox,
    fila de tabla...), añadiendo "…" si se recorta. Usado para no volcar un
    texto largo entero donde solo hace falta identificar la fila."""
    text = (text or "").strip()
    if not text:
        return "(sin motivo registrado)"
    if len(text) <= length:
        return text
    return text[: length - 1].rstrip() + "…"


# ---------------------------------------------------------------------------
# Diagrama del pipeline (build.py): que camino siguio un caso por el grafo
# ---------------------------------------------------------------------------
#
# Esto es una reconstruccion "a posteriori" a partir del `CaseState` final
# (`result`), no una animacion en vivo nodo a nodo: `graph_runner.start_case`
# llama a `graph.invoke(...)`, que es bloqueante y no va emitiendo progreso
# intermedio. Para una version en vivo (ir iluminando cada nodo segun se
# ejecuta de verdad) haria falta cambiar esa llamada a `graph.stream(...)`
# en `graph_runner.py` y leer aqui los eventos segun van llegando — no se
# ha tocado eso porque no forma parte de lo que se tiene a mano ahora mismo.

_NODE_STYLE = {
    "pending": ("#e0e0e0", "black", "solid"),   # aun no le toca / no aplica
    "done": ("#81c784", "black", "solid"),      # ya se ejecuto
    "waiting": ("#ffb74d", "black", "dashed"),  # pausado aqui ahora mismo
    "skipped": ("#f5f5f5", "#9e9e9e", "dashed"),  # no se llego por la rama que tomo el caso
}


def compute_node_statuses(result: dict[str, Any], is_paused: bool) -> dict[str, str]:
    """Deduce, a partir del `CaseState` final de un caso, por que nodos del
    pipeline paso y cual quedo pendiente o sin visitar."""
    rule_result = result.get("rule_result")
    llm_decision = result.get("llm_decision")
    requires_human = result.get("requires_human")
    human_feedback = result.get("human_feedback")
    outcome = result.get("outcome")

    statuses: dict[str, str] = {"rule_evaluator": "done" if rule_result is not None else "pending"}

    if rule_result is not None and not rule_result.get("passed"):
        # Descartado en las reglas obligatorias: el resto del pipeline no llega a ejecutarse.
        statuses["llm_decision"] = "skipped"
        statuses["validation"] = "skipped"
        statuses["human_escalation"] = "skipped"
        statuses["final_decision"] = "done" if outcome is not None else "pending"
        return statuses

    statuses["llm_decision"] = "done" if llm_decision is not None else "pending"
    # `validation_node` no deja nada propio en el `CaseState` (ver la nota en
    # state.py sobre por que se quito ese campo): si hubo `llm_decision`,
    # `validation` tuvo que ejecutarse justo despues.
    statuses["validation"] = "done" if llm_decision is not None else "pending"

    if llm_decision is None:
        statuses["human_escalation"] = "pending"
    elif requires_human:
        statuses["human_escalation"] = "done" if human_feedback is not None else "waiting"
    else:
        statuses["human_escalation"] = "skipped"

    statuses["final_decision"] = "done" if outcome is not None else ("waiting" if is_paused else "pending")
    return statuses


def build_graph_dot(status_by_node: dict[str, str]) -> str:
    """Genera el DOT del pipeline de `build.py`, coloreando cada nodo segun
    `status_by_node` (ver `compute_node_statuses`). Se renderiza con
    `st.graphviz_chart(...)`, que no necesita graphviz instalado en el
    sistema: Streamlit lo dibuja en el navegador a partir del texto DOT."""

    def node(key: str, label: str) -> str:
        fill, font, style = _NODE_STYLE[status_by_node.get(key, "pending")]
        return f'"{key}" [label="{label}", style="filled,{style}", fillcolor="{fill}", fontcolor="{font}"];'

    return "\n".join(
        [
            "digraph pipeline {",
            "rankdir=LR;",
            'node [shape=box, fontname="Helvetica", margin="0.2,0.15"];',
            node("rule_evaluator", "1. Requisitos\nobligatorios"),
            node("llm_decision", "2. Evaluación\nLLM"),
            node("validation", "3. Validación"),
            node("human_escalation", "4. Revisión\nhumana"),
            node("final_decision", "5. Decisión\nfinal"),
            '"rule_evaluator" -> "llm_decision" [label="cumple"];',
            '"rule_evaluator" -> "final_decision" [label="no cumple"];',
            '"llm_decision" -> "validation";',
            '"validation" -> "human_escalation" [label="requiere revisión"];',
            '"validation" -> "final_decision" [label="no requiere revisión"];',
            '"human_escalation" -> "final_decision";',
            "}",
        ]
    )


def render_pipeline_diagram(result: dict[str, Any], is_paused: bool) -> None:
    """Dibuja el pipeline coloreado con el camino que siguio este caso."""
    st.graphviz_chart(build_graph_dot(compute_node_statuses(result, is_paused)), width="stretch")
