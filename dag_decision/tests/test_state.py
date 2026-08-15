"""Tests minimos para `src/graph/state.py`.

`CaseState` es un `TypedDict` (`total=False`): no hay logica que probar en
tiempo de ejecucion mas alla de que las claves esperadas existan y se puedan
usar como un dict normal. El ultimo test documenta una decision de diseno
(ver el docstring de `state.py`): que no se vuelva a anadir `validation` sin
darse cuenta de por que se quito.
"""
from src.graph.state import CaseState


def test_allows_partial_state():
    state: CaseState = {"case_id": "case-1"}
    assert state["case_id"] == "case-1"
    assert state.get("outcome") is None


def test_accepts_all_documented_fields():
    state: CaseState = {
        "case_id": "case-1",
        "case_type": "candidate_selection",
        "payload": {"candidate": {}, "job_profile": {}},
        "rule_result": {"passed": True},
        "llm_decision": {"fit_label": "fit"},
        "requires_human": False,
        "human_feedback": None,
        "outcome": "fit",
    }
    assert state["outcome"] == "fit"


def test_validation_field_was_removed():
    assert "validation" not in CaseState.__annotations__
