"""Construye y compila el motor de decision DAG como un `StateGraph` de LangGraph.

Este es el Modulo 1 (DAG Engine) de la arquitectura: conecta los nodos Rule
Evaluator, LLM Decision, Confidence & Validation, Human Escalation y
Decision final, y controla el enrutado entre ellos.
"""
from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, StateGraph

from .nodes import (
    final_decision_node,
    human_escalation_node,
    llm_decision_node,
    rule_evaluator_node,
    validation_node,
)
from .state import CaseState


def _route_after_rules(state: CaseState) -> str:
    return "llm_decision" if state["rule_result"]["passed"] else "final_decision"


def _route_after_validation(state: CaseState) -> str:
    return "human_escalation" if state.get("requires_human") else "final_decision"


def build_graph(checkpointer: BaseCheckpointSaver):
    """Compila el DAG con el checkpointer de LangGraph indicado.

    El checkpointer habilita pausa/reanudacion (necesario para
    `human_escalation_node`) y usa `thread_id` (el id del caso) para
    mantener aislado el estado de cada caso.
    """
    graph = StateGraph(CaseState)

    graph.add_node("rule_evaluator", rule_evaluator_node)
    graph.add_node("llm_decision", llm_decision_node)
    graph.add_node("validation", validation_node)
    graph.add_node("human_escalation", human_escalation_node)
    graph.add_node("final_decision", final_decision_node)

    graph.set_entry_point("rule_evaluator")
    graph.add_conditional_edges(
        "rule_evaluator",
        _route_after_rules,
        {"llm_decision": "llm_decision", "final_decision": "final_decision"},
    )
    graph.add_edge("llm_decision", "validation")
    graph.add_conditional_edges(
        "validation",
        _route_after_validation,
        {"human_escalation": "human_escalation", "final_decision": "final_decision"},
    )
    graph.add_edge("human_escalation", "final_decision")
    graph.add_edge("final_decision", END)

    return graph.compile(checkpointer=checkpointer)
