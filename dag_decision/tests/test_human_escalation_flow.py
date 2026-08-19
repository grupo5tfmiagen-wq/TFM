"""Tests de flujo end-to-end de la Human Escalation Layer a traves del grafo.

Compilan el DAG real con un checkpointer en memoria (`InMemorySaver`) y un
LLM simulado, de modo que el mecanismo autentico de `interrupt()` /
`Command(resume=...)` de LangGraph queda cubierto sin tocar Postgres ni
OpenAI. La BD de negocio se sustituye por el `FakeSession` de `conftest.py`.
"""
import uuid

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

import src.graph.nodes as nodes_module
from src.db.models.case import Case
from src.db.models.final_decision import FinalDecision
from src.db.models.human_escalation import HumanEscalation
from src.graph.build import build_graph
from src.graph.nodes import CandidateAssessment


class _FakeStructuredLLM:
    def __init__(self, assessment):
        self._assessment = assessment

    def invoke(self, _prompt):
        return self._assessment


class _FakeLLM:
    """Sustituto de ChatOpenAI: devuelve siempre la valoracion indicada."""

    def __init__(self, assessment):
        self._assessment = assessment
        self.calls = 0

    def with_structured_output(self, _schema):
        self.calls += 1
        return _FakeStructuredLLM(self._assessment)


def _initial_state(payload: dict) -> tuple[str, dict, dict]:
    case_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": case_id}}
    state = {"case_id": case_id, "case_type": "candidate_selection", "payload": payload}
    return case_id, config, state


GOOD_PAYLOAD = {"years_experience": 5, "has_cv": True, "has_id_document": True}


def test_confianza_baja_pausa_en_escalacion_y_reanuda_hasta_decision_humana(
    patch_session, monkeypatch
):
    assessment = CandidateAssessment(fit_label="unclear", confidence=0.4, justification="Perfil ambiguo.")
    monkeypatch.setattr(nodes_module, "_llm", lambda: _FakeLLM(assessment))
    graph = build_graph(InMemorySaver())
    case_id, config, state = _initial_state(GOOD_PAYLOAD)
    patch_session.add(Case(id=uuid.UUID(case_id), case_type="candidate_selection", status="running", payload=GOOD_PAYLOAD))

    # Primera pasada: el grafo se pausa en human_escalation.
    result = graph.invoke(state, config=config)

    assert "__interrupt__" in result
    interrupt_payload = result["__interrupt__"][0].value
    assert interrupt_payload["case_id"] == case_id
    assert interrupt_payload["escalation_id"]

    escalations = patch_session.stored(HumanEscalation)
    assert len(escalations) == 1
    assert escalations[0].status == "pending"
    assert escalations[0].node_execution_id is not None
    assert patch_session.get(Case, uuid.UUID(case_id)).status == "waiting_human"

    # Reanudacion con la decision del revisor humano.
    decision = {"outcome": "fit", "reviewer": "ana"}
    result = graph.invoke(Command(resume=decision), config=config)

    assert "__interrupt__" not in result
    assert result["human_feedback"] == decision
    assert result["outcome"] == "fit"

    # La escalacion queda resuelta, sin duplicados, y el caso se cierra.
    assert len(patch_session.stored(HumanEscalation)) == 1
    esc = escalations[0]
    assert esc.status == "resolved"
    assert esc.resolution == "fit"
    assert esc.assigned_to == "ana"
    assert esc.resolved_at is not None

    finals = patch_session.stored(FinalDecision)
    assert len(finals) == 1
    assert finals[0].outcome == "fit"
    assert finals[0].decided_by == "human"
    assert patch_session.get(Case, uuid.UUID(case_id)).status == "closed"


def test_confianza_alta_no_escala_y_decide_el_sistema(patch_session, monkeypatch):
    assessment = CandidateAssessment(fit_label="fit", confidence=0.95, justification="Encaje claro.")
    monkeypatch.setattr(nodes_module, "_llm", lambda: _FakeLLM(assessment))
    graph = build_graph(InMemorySaver())
    case_id, config, state = _initial_state(GOOD_PAYLOAD)

    result = graph.invoke(state, config=config)

    assert "__interrupt__" not in result
    assert result["outcome"] == "fit"
    assert result.get("human_feedback") is None
    assert patch_session.stored(HumanEscalation) == []

    finals = patch_session.stored(FinalDecision)
    assert len(finals) == 1
    assert finals[0].decided_by == "system"


def test_reglas_no_superadas_rechazan_sin_llm_ni_escalacion(patch_session, monkeypatch):
    fake_llm = _FakeLLM(CandidateAssessment(fit_label="fit", confidence=0.9, justification="ok"))
    monkeypatch.setattr(nodes_module, "_llm", lambda: fake_llm)
    graph = build_graph(InMemorySaver())
    payload = {"years_experience": 0, "has_cv": True, "has_id_document": True}
    case_id, config, state = _initial_state(payload)

    result = graph.invoke(state, config=config)

    assert "__interrupt__" not in result
    assert result["outcome"] == "rejected"
    assert fake_llm.calls == 0
    assert patch_session.stored(HumanEscalation) == []

    finals = patch_session.stored(FinalDecision)
    assert len(finals) == 1
    assert finals[0].decided_by == "system"
