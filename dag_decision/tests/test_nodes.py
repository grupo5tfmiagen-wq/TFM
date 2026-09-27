"""Tests unitarios de `src/graph/nodes.py`, uno por nodo/helper.

Todos los tests son de unidad: no tocan ninguna base de datos ni llaman a
OpenAI/LangSmith de verdad. `traced_node`, `SessionLocal`, `_llm` y
`get_current_run_tree` se sustituyen por dobles controlados en cada test, y
las clases de modelo de SQLAlchemy se sustituyen por `_StubModel` (ver
`patch_models`, autouse) para no depender de su esquema real.
"""
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.graph import nodes


# ---------------------------------------------------------------------------
# Fixtures y dobles compartidos
# ---------------------------------------------------------------------------


class _StubModelMeta(type):
    """Metaclase para `_StubModel`: permite que expresiones a nivel de clase
    como `HumanEscalation.created_at.desc()` (usadas dentro de
    `session.query(...).order_by(...)`) no revienten en los tests. El valor
    devuelto es irrelevante: `session.query(...)` esta siempre mockeado, asi
    que ese argumento nunca se evalua de verdad, solo tiene que poder
    *construirse* sin lanzar `AttributeError`."""

    def __getattr__(cls, name):
        return MagicMock()


class _StubModel(metaclass=_StubModelMeta):
    """Doble ligero para las clases de modelo de SQLAlchemy usadas en
    nodes.py: solo guarda los kwargs con los que se instancio y expone un id
    aleatorio, sin tocar ninguna base de datos real."""

    def __init__(self, **kwargs):
        self.id = uuid.uuid4()
        for key, value in kwargs.items():
            setattr(self, key, value)


@pytest.fixture(autouse=True)
def patch_models(monkeypatch):
    for name in ("RuleEvaluation", "LlmDecision", "Validation", "HumanEscalation", "FinalDecision", "Case"):
        monkeypatch.setattr(nodes, name, _StubModel)


@pytest.fixture(autouse=True)
def patch_langsmith(monkeypatch):
    """Sin tracing activo en tests, `get_current_run_tree()` debe devolver
    None (igual que en produccion sin `LANGSMITH_TRACING=true`)."""
    monkeypatch.setattr(nodes, "get_current_run_tree", lambda: None)


@pytest.fixture
def traced_node_calls(monkeypatch):
    """Sustituye `traced_node` por un doble que registra cada llamada y
    expone `(session, node_execution)` como Mock/SimpleNamespace, para poder
    comprobar despues que cada nodo persistio lo esperado."""
    calls = []

    @contextmanager
    def _fake(case_id, node_name, input_payload):
        session = MagicMock()
        node_execution = SimpleNamespace(id=uuid.uuid4(), output_data=None)
        record = SimpleNamespace(
            case_id=case_id,
            node_name=node_name,
            input_payload=input_payload,
            session=session,
            node_execution=node_execution,
        )
        calls.append(record)
        yield session, node_execution

    monkeypatch.setattr(nodes, "traced_node", _fake)
    return calls


def _patch_traced_node_with_session(monkeypatch, session_mock):
    """Variante de `traced_node_calls` para cuando un test necesita
    preconfigurar el `session` (p.ej. `session.get`/`session.query`) antes
    de invocar el nodo."""
    node_execution = SimpleNamespace(id=uuid.uuid4(), output_data=None)

    @contextmanager
    def _fake(case_id, node_name, input_payload):
        yield session_mock, node_execution

    monkeypatch.setattr(nodes, "traced_node", _fake)
    return node_execution


def _base_state(**overrides) -> dict:
    state = {
        "case_id": "11111111-1111-1111-1111-111111111111",
        "case_type": "candidate_selection",
        "payload": {
            "candidate": {
                "cv": {
                    "technical_skills": ["Python", "PostgreSQL", "Docker"],
                    "experience": [{"start_date": "2018-01", "end_date": "present"}],
                }
            },
            "job_profile": {
                "mandatory_requirements": {
                    "technical_skills": ["Python", "PostgreSQL"],
                    "min_years_experience": 3,
                },
                "desired_requirements": {"technical_skills": ["Kubernetes"]},
            },
        },
    }
    state.update(overrides)
    return state


# ---------------------------------------------------------------------------
# Helpers: _parse_year_month / _years_of_experience
# ---------------------------------------------------------------------------


class TestParseYearMonth:
    def test_parses_valid_value(self):
        assert nodes._parse_year_month("2020-05") == date(2020, 5, 1)

    def test_none_and_empty_return_none(self):
        assert nodes._parse_year_month(None) is None
        assert nodes._parse_year_month("") is None


class TestYearsOfExperience:
    def test_single_closed_period(self):
        entries = [{"start_date": "2020-01", "end_date": "2023-01"}]
        assert nodes._years_of_experience(entries) == 3.0

    def test_present_uses_todays_date(self):
        today = date.today()
        start_year = today.year - 2
        entries = [{"start_date": f"{start_year}-01", "end_date": "present"}]
        expected_months = (today.year - start_year) * 12 + (today.month - 1)
        assert nodes._years_of_experience(entries) == round(expected_months / 12, 1)

    def test_sums_multiple_periods(self):
        entries = [
            {"start_date": "2020-01", "end_date": "2021-01"},  # 12 meses
            {"start_date": "2021-06", "end_date": "2022-12"},  # 18 meses
        ]
        assert nodes._years_of_experience(entries) == 2.5

    def test_skips_entries_with_missing_start_date(self):
        entries = [{"start_date": None, "end_date": "2023-01"}]
        assert nodes._years_of_experience(entries) == 0.0

    def test_empty_list_returns_zero(self):
        assert nodes._years_of_experience([]) == 0.0


# ---------------------------------------------------------------------------
# Helpers: _estimate_cost_usd / _case_metadata / _tag_current_run
# ---------------------------------------------------------------------------


class TestEstimateCostUsd:
    def test_none_when_any_token_count_missing(self):
        assert nodes._estimate_cost_usd(None, 100) is None
        assert nodes._estimate_cost_usd(100, None) is None
        assert nodes._estimate_cost_usd(None, None) is None

    def test_computes_expected_cost(self, monkeypatch):
        monkeypatch.setattr(nodes, "_INPUT_PRICE_PER_1M_USD", 1.0)
        monkeypatch.setattr(nodes, "_OUTPUT_PRICE_PER_1M_USD", 2.0)
        cost = nodes._estimate_cost_usd(1_000_000, 500_000)
        assert cost == pytest.approx(2.0)  # 1*1.0 + 0.5*2.0


class TestCaseMetadata:
    def test_extracts_case_id_and_type(self):
        state = {"case_id": "abc", "case_type": "candidate_selection"}
        assert nodes._case_metadata(state) == {"case_id": "abc", "case_type": "candidate_selection"}


class TestTagCurrentRun:
    def test_noop_without_active_run(self, monkeypatch):
        monkeypatch.setattr(nodes, "get_current_run_tree", lambda: None)
        nodes._tag_current_run(tags=["a"], metadata={"x": 1})  # no debe lanzar

    def test_adds_tags_and_metadata_to_active_run(self, monkeypatch):
        run_tree = SimpleNamespace(tags=["existing"], extra={})
        monkeypatch.setattr(nodes, "get_current_run_tree", lambda: run_tree)
        nodes._tag_current_run(tags=["existing", "new"], metadata={"k": "v"})
        assert run_tree.tags == ["existing", "new"]
        assert run_tree.extra["metadata"]["k"] == "v"

    def test_never_raises_if_langsmith_is_broken(self, monkeypatch):
        def _broken():
            raise RuntimeError("boom")

        monkeypatch.setattr(nodes, "get_current_run_tree", _broken)
        nodes._tag_current_run(tags=["x"])  # no debe lanzar


# ---------------------------------------------------------------------------
# Modulo 2: rule_evaluator_node
# ---------------------------------------------------------------------------


class TestRuleEvaluatorNode:
    def test_passes_when_skills_and_experience_are_met(self, traced_node_calls):
        result = nodes.rule_evaluator_node(_base_state())
        assert result["rule_result"]["passed"] is True
        assert result["rule_result"]["missing_skills"] == []

    def test_fails_on_missing_mandatory_skill(self, traced_node_calls):
        state = _base_state()
        state["payload"]["candidate"]["cv"]["technical_skills"] = ["Python"]
        result = nodes.rule_evaluator_node(state)
        assert result["rule_result"]["passed"] is False
        assert "PostgreSQL" in result["rule_result"]["missing_skills"]

    def test_fails_on_insufficient_experience(self, traced_node_calls):
        state = _base_state()
        state["payload"]["candidate"]["cv"]["experience"] = [
            {"start_date": "2024-01", "end_date": "present"}
        ]
        result = nodes.rule_evaluator_node(state)
        assert result["rule_result"]["passed"] is False

    def test_fails_on_insufficient_language_level(self, traced_node_calls):
        state = _base_state()
        state["payload"]["candidate"]["cv"]["languages"] = [{"language": "english", "level": "B1"}]
        state["payload"]["job_profile"]["mandatory_requirements"]["languages"] = [
            {"language": "english", "min_level": "B2"}
        ]
        result = nodes.rule_evaluator_node(state)
        assert result["rule_result"]["passed"] is False
        assert result["rule_result"]["missing_languages"][0]["candidate"] == "B1"

    def test_compares_languages_across_spanish_and_english_names(self, traced_node_calls):
        state = _base_state()
        state["payload"]["candidate"]["cv"]["languages"] = [{"language": "Inglés", "level": "C1"}]
        state["payload"]["job_profile"]["mandatory_requirements"]["languages"] = [
            {"language": "english", "min_level": "B2"}
        ]
        result = nodes.rule_evaluator_node(state)
        assert result["rule_result"]["passed"] is True

    def test_fails_on_missing_required_language(self, traced_node_calls):
        state = _base_state()
        state["payload"]["job_profile"]["mandatory_requirements"]["languages"] = [
            {"language": "english", "min_level": "B2"}
        ]
        result = nodes.rule_evaluator_node(state)
        assert result["rule_result"]["passed"] is False

    def test_fails_on_insufficient_education_level(self, traced_node_calls):
        state = _base_state()
        state["payload"]["candidate"]["cv"]["education"] = [
            {"degree": "Técnico Superior en Desarrollo de Aplicaciones Web (Ciclo Formativo de Grado Superior)"}
        ]
        state["payload"]["job_profile"]["mandatory_requirements"]["min_education"] = "Grado en Ingeniería Informática o equivalente"
        result = nodes.rule_evaluator_node(state)
        assert result["rule_result"]["passed"] is False
        assert result["rule_result"]["meets_education"] is False

    def test_passes_with_higher_education_level(self, traced_node_calls):
        state = _base_state()
        state["payload"]["candidate"]["cv"]["education"] = [{"degree": "Máster en Inteligencia Artificial"}]
        state["payload"]["job_profile"]["mandatory_requirements"]["min_education"] = "Degree in Computer Science or equivalent"
        result = nodes.rule_evaluator_node(state)
        assert result["rule_result"]["passed"] is True

    def test_unverifiable_language_level_does_not_reject_but_is_flagged(self, traced_node_calls):
        state = _base_state()
        state["payload"]["candidate"]["cv"]["languages"] = [{"language": "english", "level": "fluido"}]
        state["payload"]["job_profile"]["mandatory_requirements"]["languages"] = [
            {"language": "english", "min_level": "B2"}
        ]
        result = nodes.rule_evaluator_node(state)
        assert result["rule_result"]["passed"] is True
        assert result["rule_result"]["unverified_requirements"]

    def test_persists_rule_evaluation_row(self, traced_node_calls):
        nodes.rule_evaluator_node(_base_state())
        call = traced_node_calls[-1]
        call.session.add.assert_called_once()
        assert isinstance(call.session.add.call_args[0][0], nodes.RuleEvaluation)


# ---------------------------------------------------------------------------
# Modulo 3: llm_decision_node
# ---------------------------------------------------------------------------


class _FakeStructuredLLM:
    def __init__(self, result):
        self._result = result
        self.invoked_with = None

    def invoke(self, prompt):
        self.invoked_with = prompt
        return self._result


class _FakeLLM:
    def __init__(self, result):
        self._result = result
        self.structured = None

    def with_structured_output(self, schema, include_raw=False):
        assert include_raw is True, "llm_decision_node debe pedir include_raw=True para leer usage_metadata"
        self.structured = _FakeStructuredLLM(self._result)
        return self.structured


class TestLlmDecisionNode:
    def test_returns_structured_assessment_with_token_usage(self, monkeypatch, traced_node_calls):
        assessment = nodes.CandidateAssessment(fit_label="fit", confidence=0.92, justification="Buen ajuste")
        raw_message = SimpleNamespace(usage_metadata={"input_tokens": 120, "output_tokens": 40, "total_tokens": 160})
        fake_llm = _FakeLLM({"parsed": assessment, "raw": raw_message})
        monkeypatch.setattr(nodes, "_llm", lambda: fake_llm)

        result = nodes.llm_decision_node(_base_state())

        decision = result["llm_decision"]
        assert decision["fit_label"] == "fit"
        assert decision["confidence"] == pytest.approx(0.92)
        assert decision["input_tokens"] == 120
        assert decision["output_tokens"] == 40
        assert decision["total_tokens"] == 160
        assert decision["estimated_cost_usd"] == pytest.approx(nodes._estimate_cost_usd(120, 40))
        assert "llm_decision_id" in decision

    def test_prompt_includes_desired_skills_and_candidate_data(self, monkeypatch, traced_node_calls):
        assessment = nodes.CandidateAssessment(fit_label="unclear", confidence=0.5, justification="...")
        fake_llm = _FakeLLM({"parsed": assessment, "raw": SimpleNamespace()})
        monkeypatch.setattr(nodes, "_llm", lambda: fake_llm)

        nodes.llm_decision_node(_base_state())

        prompt = fake_llm.structured.invoked_with
        assert "Kubernetes" in prompt
        assert "PostgreSQL" in prompt

    def test_prompt_excludes_personal_data(self, monkeypatch, traced_node_calls):
        assessment = nodes.CandidateAssessment(fit_label="fit", confidence=0.95, justification="...")
        fake_llm = _FakeLLM({"parsed": assessment, "raw": SimpleNamespace()})
        monkeypatch.setattr(nodes, "_llm", lambda: fake_llm)
        state = _base_state()
        candidate = state["payload"]["candidate"]
        candidate["id"] = "cand-001"
        candidate["name"] = "Marina Etxeberria Zubizarreta"
        candidate["cv"]["education"] = [
            {"degree": "Licenciatura en Informática", "institution": "Universidad Complutense de Madrid", "end_year": 1986}
        ]
        candidate["cv"]["extracted_text"] = (
            "Marina Etxeberria Zubizarreta\nmarina@example.com · +34 600 000 000\n"
            "Licenciada en 1986. Experta en Python."
        )

        nodes.llm_decision_node(state)

        prompt = fake_llm.structured.invoked_with
        for personal in ("Marina", "Etxeberria", "marina@example.com", "600 000 000", "1986", "Complutense", "cand-001"):
            assert personal not in prompt
        assert "Licenciatura en Informática" in prompt
        assert "Experta en Python" in prompt

    def test_missing_usage_metadata_yields_none_cost(self, monkeypatch, traced_node_calls):
        assessment = nodes.CandidateAssessment(fit_label="not_fit", confidence=0.2, justification="...")
        fake_llm = _FakeLLM({"parsed": assessment, "raw": SimpleNamespace()})  # sin usage_metadata
        monkeypatch.setattr(nodes, "_llm", lambda: fake_llm)

        result = nodes.llm_decision_node(_base_state())
        decision = result["llm_decision"]
        assert decision["input_tokens"] is None
        assert decision["estimated_cost_usd"] is None

    def test_persists_llm_decision_row(self, monkeypatch, traced_node_calls):
        assessment = nodes.CandidateAssessment(fit_label="fit", confidence=0.8, justification="...")
        fake_llm = _FakeLLM({"parsed": assessment, "raw": SimpleNamespace()})
        monkeypatch.setattr(nodes, "_llm", lambda: fake_llm)

        nodes.llm_decision_node(_base_state())

        call = traced_node_calls[-1]
        call.session.add.assert_called_once()
        assert isinstance(call.session.add.call_args[0][0], nodes.LlmDecision)


# ---------------------------------------------------------------------------
# Modulo 4: validation_node
# ---------------------------------------------------------------------------


class TestValidationNode:
    def test_valid_and_no_review_when_high_confidence_fit(self, traced_node_calls):
        state = _base_state(llm_decision={"fit_label": "fit", "confidence": 0.95, "llm_decision_id": None})
        result = nodes.validation_node(state)
        assert result["requires_human"] is False

    def test_requires_review_on_not_fit_even_with_high_confidence(self, traced_node_calls):
        # Un rechazo basado en el LLM nunca se decide de forma automatizada (RGPD art. 22).
        state = _base_state(llm_decision={"fit_label": "not_fit", "confidence": 0.99, "llm_decision_id": None})
        result = nodes.validation_node(state)
        assert result["requires_human"] is True
        reasons = traced_node_calls[-1].node_execution.output_data["review_reasons"]
        assert any("no apto" in reason for reason in reasons)

    def test_requires_review_when_rule_requirements_are_unverified(self, traced_node_calls):
        state = _base_state(
            llm_decision={"fit_label": "fit", "confidence": 0.95, "llm_decision_id": None},
            rule_result={"passed": True, "unverified_requirements": ["idioma english: nivel del CV 'fluido'"]},
        )
        result = nodes.validation_node(state)
        assert result["requires_human"] is True

    def test_persists_review_reasons_in_validation_row(self, traced_node_calls):
        state = _base_state(llm_decision={"fit_label": "fit", "confidence": 0.3, "llm_decision_id": None})
        nodes.validation_node(state)
        row = traced_node_calls[-1].session.add.call_args[0][0]
        assert "umbral" in row.reason

    def test_requires_review_on_unclear_label_even_with_high_confidence(self, traced_node_calls):
        state = _base_state(llm_decision={"fit_label": "unclear", "confidence": 0.95, "llm_decision_id": None})
        result = nodes.validation_node(state)
        assert result["requires_human"] is True

    def test_requires_review_on_low_confidence(self, traced_node_calls):
        state = _base_state(llm_decision={"fit_label": "fit", "confidence": 0.3, "llm_decision_id": None})
        result = nodes.validation_node(state)
        assert result["requires_human"] is True

    def test_requires_review_on_unexpected_label(self, traced_node_calls):
        state = _base_state(llm_decision={"fit_label": "maybe", "confidence": 0.95, "llm_decision_id": None})
        result = nodes.validation_node(state)
        assert result["requires_human"] is True

    def test_persists_validation_row(self, traced_node_calls):
        state = _base_state(llm_decision={"fit_label": "fit", "confidence": 0.95, "llm_decision_id": None})
        nodes.validation_node(state)
        call = traced_node_calls[-1]
        call.session.add.assert_called_once()
        assert isinstance(call.session.add.call_args[0][0], nodes.Validation)


# ---------------------------------------------------------------------------
# Modulo 5: human_escalation_node
# ---------------------------------------------------------------------------


def _make_session_local(session_mock):
    ctx = MagicMock()
    ctx.__enter__.return_value = session_mock
    ctx.__exit__.return_value = False
    return MagicMock(return_value=ctx)


class TestHumanEscalationNode:
    """El nodo delega la cola de revision en `src/escalation/service.py`,
    cuyas funciones se sustituyen aqui por dobles para probar solo la
    orquestacion del nodo (crear si no hay pendiente, pausar con
    `interrupt()`, resolver al reanudar). El comportamiento del servicio en
    si se cubre en `test_escalation_service.py` y el del nodo contra una
    sesion mas fiel en `test_human_escalation_node.py`."""

    def _patch_node(self, monkeypatch, *, pending_before, pending_after):
        """Deja el nodo listo para ejecutarse: sesiones MagicMock, servicio
        de escalacion doble e `interrupt()` controlado. Devuelve los dobles
        para las aserciones de cada test."""
        get_pending = MagicMock(side_effect=[pending_before, pending_after])
        create = MagicMock(return_value=pending_before)
        resolve = MagicMock()
        monkeypatch.setattr(nodes, "get_pending_escalation", get_pending)
        monkeypatch.setattr(nodes, "create_escalation", create)
        monkeypatch.setattr(nodes, "resolve_escalation", resolve)
        monkeypatch.setattr(nodes, "SessionLocal", _make_session_local(MagicMock()))
        return SimpleNamespace(get_pending=get_pending, create=create, resolve=resolve)

    def test_creates_pending_escalation_when_none_exists(self, monkeypatch):
        created = SimpleNamespace(id=uuid.uuid4(), status="pending", node_execution_id=None)
        resolved = SimpleNamespace(id=created.id, status="pending", node_execution_id=None)
        doubles = self._patch_node(monkeypatch, pending_before=None, pending_after=resolved)
        doubles.create.return_value = created
        monkeypatch.setattr(nodes, "interrupt", lambda payload: {"outcome": "fit", "reviewer": "tester"})

        state = _base_state(llm_decision={"fit_label": "unclear", "confidence": 0.3})
        result = nodes.human_escalation_node(state)

        assert result["human_feedback"] == {"outcome": "fit", "reviewer": "tester"}
        doubles.create.assert_called_once()
        assert doubles.create.call_args.kwargs["case_id"] == state["case_id"]
        doubles.resolve.assert_called_once()

    def test_resumes_without_creating_duplicate_and_resolves(self, monkeypatch):
        pending = SimpleNamespace(id=uuid.uuid4(), status="pending", node_execution_id=None)
        doubles = self._patch_node(monkeypatch, pending_before=pending, pending_after=pending)
        monkeypatch.setattr(nodes, "interrupt", lambda payload: {"outcome": "not_fit", "reviewer": "ana"})

        state = _base_state(llm_decision={"fit_label": "unclear", "confidence": 0.3})
        nodes.human_escalation_node(state)

        # La escalacion pendiente ya existia: no se crea otra, se resuelve la misma.
        doubles.create.assert_not_called()
        doubles.resolve.assert_called_once()
        assert doubles.resolve.call_args.args[1] == pending.id
        assert doubles.resolve.call_args.kwargs["outcome"] == "not_fit"
        assert doubles.resolve.call_args.kwargs["reviewer"] == "ana"

    def test_interrupt_payload_carries_case_context(self, monkeypatch):
        pending = SimpleNamespace(id=uuid.uuid4(), status="pending", node_execution_id=None)
        self._patch_node(monkeypatch, pending_before=pending, pending_after=pending)

        captured = {}

        def _fake_interrupt(payload):
            captured.update(payload)
            return {"outcome": "fit", "reviewer": "tester"}

        monkeypatch.setattr(nodes, "interrupt", _fake_interrupt)

        state = _base_state(llm_decision={"fit_label": "unclear", "confidence": 0.3})
        nodes.human_escalation_node(state)

        assert captured["case_id"] == state["case_id"]
        assert captured["escalation_id"] == str(pending.id)
        assert "question" in captured


# ---------------------------------------------------------------------------
# Modulo 6: final_decision_node
# ---------------------------------------------------------------------------


class TestFinalDecisionNode:
    def test_outcome_rejected_when_rule_failed(self, monkeypatch):
        session_mock = MagicMock()
        session_mock.get.return_value = None
        session_mock.query.return_value.filter_by.return_value.order_by.return_value.first.return_value = None
        _patch_traced_node_with_session(monkeypatch, session_mock)

        state = _base_state(rule_result={"passed": False, "missing_skills": ["Docker"]})
        result = nodes.final_decision_node(state)
        assert result["outcome"] == "rejected"

    def test_outcome_from_llm_when_rule_passed(self, monkeypatch):
        session_mock = MagicMock()
        session_mock.get.return_value = None
        session_mock.query.return_value.filter_by.return_value.order_by.return_value.first.return_value = None
        _patch_traced_node_with_session(monkeypatch, session_mock)

        state = _base_state(
            rule_result={"passed": True, "missing_skills": []},
            llm_decision={"fit_label": "fit", "confidence": 0.9},
        )
        result = nodes.final_decision_node(state)
        assert result["outcome"] == "fit"

    def test_outcome_from_human_feedback_when_escalated(self, monkeypatch):
        session_mock = MagicMock()
        session_mock.get.return_value = None
        session_mock.query.return_value.filter_by.return_value.order_by.return_value.first.return_value = None
        _patch_traced_node_with_session(monkeypatch, session_mock)

        state = _base_state(
            rule_result={"passed": True, "missing_skills": []},
            llm_decision={"fit_label": "unclear", "confidence": 0.3},
            human_feedback={"outcome": "not_fit", "reviewer": "someone"},
        )
        result = nodes.final_decision_node(state)
        assert result["outcome"] == "not_fit"

    def test_computes_total_and_human_review_seconds(self, monkeypatch):
        case_created = datetime.now(timezone.utc) - timedelta(minutes=10)
        fake_case = SimpleNamespace(created_at=case_created, status=None, current_node_key=None)

        escalation_created = datetime.now(timezone.utc) - timedelta(minutes=8)
        escalation_resolved = datetime.now(timezone.utc) - timedelta(minutes=1)
        fake_escalation = SimpleNamespace(created_at=escalation_created, resolved_at=escalation_resolved)

        session_mock = MagicMock()
        session_mock.get.return_value = fake_case
        session_mock.query.return_value.filter_by.return_value.order_by.return_value.first.return_value = fake_escalation
        node_execution = _patch_traced_node_with_session(monkeypatch, session_mock)

        state = _base_state(
            rule_result={"passed": True, "missing_skills": []},
            llm_decision={"fit_label": "unclear", "confidence": 0.3},
            human_feedback={"outcome": "fit", "reviewer": "someone"},
        )
        nodes.final_decision_node(state)

        assert node_execution.output_data["total_case_seconds"] == pytest.approx(600, abs=5)
        assert node_execution.output_data["human_review_seconds"] == pytest.approx(420, abs=5)
        assert fake_case.status == "closed"
        assert fake_case.current_node_key == "final_decision"

    def test_no_review_seconds_and_no_extra_query_when_not_escalated(self, monkeypatch):
        session_mock = MagicMock()
        session_mock.get.return_value = None
        _patch_traced_node_with_session(monkeypatch, session_mock)

        state = _base_state(
            rule_result={"passed": True, "missing_skills": []},
            llm_decision={"fit_label": "fit", "confidence": 0.9},
        )
        result = nodes.final_decision_node(state)

        assert result["outcome"] == "fit"
        session_mock.query.assert_not_called()
