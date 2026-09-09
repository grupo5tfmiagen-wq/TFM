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
