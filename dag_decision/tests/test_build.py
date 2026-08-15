"""Tests para `src/graph/build.py`.

Las funciones de enrutado (`_route_after_rules`, `_route_after_validation`)
son puras, asi que se prueban aisladas sin levantar el grafo. `build_graph`
solo lleva un smoke test: si el cableado de nodos/aristas tiene un nombre
que no casa o un ciclo invalido, `compile()` lanza y el test lo detecta.
"""
from unittest.mock import MagicMock

from langgraph.checkpoint.base import BaseCheckpointSaver

from src.graph import build


class TestRouteAfterRules:
    def test_routes_to_llm_decision_when_rule_passed(self):
        state = {"rule_result": {"passed": True}}
        assert build._route_after_rules(state) == "llm_decision"

    def test_routes_to_final_decision_when_rule_failed(self):
        state = {"rule_result": {"passed": False}}
        assert build._route_after_rules(state) == "final_decision"


class TestRouteAfterValidation:
    def test_routes_to_human_escalation_when_required(self):
        state = {"requires_human": True}
        assert build._route_after_validation(state) == "human_escalation"

    def test_routes_to_final_decision_when_not_required(self):
        state = {"requires_human": False}
        assert build._route_after_validation(state) == "final_decision"

    def test_routes_to_final_decision_when_key_missing(self):
        # `requires_human` puede faltar si el caso nunca llego a `validation`
        # (p.ej. lo descarto `rule_evaluator`); `.get()` debe tratarlo como False.
        assert build._route_after_validation({}) == "final_decision"


class TestBuildGraph:
    def test_compiles_without_raising(self):
        checkpointer = MagicMock(spec=BaseCheckpointSaver)
        graph = build.build_graph(checkpointer=checkpointer)
        assert graph is not None
