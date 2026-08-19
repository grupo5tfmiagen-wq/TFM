"""Tests unitarios de `human_escalation_node` (Modulo 5) con BD simulada.

Aqui `interrupt()` se sustituye por un doble para probar el nodo de forma
aislada: el comportamiento real de pausa/reanudacion de LangGraph se cubre
en `test_human_escalation_flow.py`.
"""
from unittest.mock import Mock

import pytest
from langgraph.errors import GraphInterrupt

import src.graph.nodes as nodes_module
from src.db.models.human_escalation import HumanEscalation
from src.db.models.node_execution import CaseNodeExecution
from src.escalation.service import create_escalation


def test_primera_ejecucion_crea_escalacion_y_pausa(patch_session, sample_state, stored_case, monkeypatch):
    monkeypatch.setattr(nodes_module, "interrupt", Mock(side_effect=GraphInterrupt("pausado")))

    with pytest.raises(GraphInterrupt):
        nodes_module.human_escalation_node(sample_state)

    escalations = patch_session.stored(HumanEscalation)
    assert len(escalations) == 1
    assert escalations[0].status == "pending"
    assert str(escalations[0].case_id) == sample_state["case_id"]

    # Auditoria: fila CaseNodeExecution en "waiting" enlazada desde la escalacion.
    executions = patch_session.stored(CaseNodeExecution)
    assert len(executions) == 1
    assert executions[0].node_key == "human_escalation"
    assert executions[0].status == "waiting"
    assert escalations[0].node_execution_id == executions[0].id

    # El caso queda marcado como a la espera de revision humana.
    assert stored_case.status == "waiting_human"
    assert stored_case.current_node_key == "human_escalation"


def test_reanudacion_resuelve_escalacion_y_devuelve_feedback(
    patch_session, sample_state, stored_case, monkeypatch
):
    decision = {"outcome": "not_fit", "reviewer": "luis"}
    monkeypatch.setattr(nodes_module, "interrupt", Mock(return_value=decision))

    result = nodes_module.human_escalation_node(sample_state)

    assert result == {"human_feedback": decision}

    esc = patch_session.stored(HumanEscalation)[0]
    assert esc.status == "resolved"
    assert esc.resolution == "not_fit"
    assert esc.assigned_to == "luis"
    assert esc.resolved_at is not None

    execution = patch_session.stored(CaseNodeExecution)[0]
    assert execution.status == "completed"
    assert execution.output_data == {"human_feedback": decision}
    assert execution.finished_at is not None

    # El caso vuelve a "running" para que el grafo continue hasta el cierre.
    assert stored_case.status == "running"


def test_reanudacion_no_duplica_la_escalacion(patch_session, sample_state, stored_case, monkeypatch):
    """Al reanudar, LangGraph re-ejecuta el nodo entero: no debe crear duplicados."""
    existente = create_escalation(
        patch_session, case_id=sample_state["case_id"], reason="creada en la primera pasada"
    )
    patch_session.commits = 0
    decision = {"outcome": "fit", "reviewer": "ana"}
    monkeypatch.setattr(nodes_module, "interrupt", Mock(return_value=decision))

    result = nodes_module.human_escalation_node(sample_state)

    assert result == {"human_feedback": decision}
    escalations = patch_session.stored(HumanEscalation)
    assert len(escalations) == 1
    assert escalations[0].id == existente.id
    assert escalations[0].status == "resolved"
