"""Esquema de estado compartido por el grafo del motor de decision.

Es la contrapartida en LangGraph del "Estado del Caso" descrito en el
documento de arquitectura (Modulo 1: DAG Engine). Es, a proposito, una
estructura ligera y serializable a JSON: LangGraph la persiste mediante el
checkpointer de Postgres (pausa/reanudacion), mientras que cada nodo escribe
ademas un registro mas completo de su propia entrada/salida en el esquema de
negocio (ver `case_node_executions` y tablas relacionadas) para auditoria y
KPIs.
"""
from __future__ import annotations

from typing import Any, TypedDict


class CaseState(TypedDict, total=False):
    case_id: str
    case_type: str
    payload: dict[str, Any]

    # Referencias a CV y oferta laboral (opcionales para compatibilidad)
    cv_document_id: str | None
    job_posting_id: str | None

    rule_result: dict[str, Any] | None
    llm_decision: dict[str, Any] | None
    validation: dict[str, Any] | None
    requires_human: bool
    human_feedback: dict[str, Any] | None

    outcome: str | None
