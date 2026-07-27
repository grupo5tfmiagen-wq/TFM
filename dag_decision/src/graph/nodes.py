"""Funciones de nodo de LangGraph para el motor de decision DAG.

Cada funcion corresponde a un modulo del documento de arquitectura:

- `rule_evaluator_node`      -> Modulo 2: Rule Evaluator
- `llm_decision_node`        -> Modulo 3: LLM Decision Nodes
- `validation_node`          -> Modulo 4: Confidence & Validation Layer
- `human_escalation_node`    -> Modulo 5: Human Escalation Layer
- `final_decision_node`      -> Modulo 6: Decision final

El caso de uso de ejemplo es la seleccion de candidatos, el escenario
principal descrito en los objetivos. Cada nodo persiste su propia fila
`CaseNodeExecution` + fila de resultado (capa de trazabilidad) ademas de
devolver una actualizacion parcial del estado de LangGraph. Los nodos que no
llaman directamente a un LLM se decoran con `@traceable` para que tambien
aparezcan en LangSmith junto a las llamadas LLM (que se trazan
automaticamente via variables de entorno).
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.types import interrupt
from langsmith import traceable
from pydantic import BaseModel, Field

from ..db.base import SessionLocal
from ..db.models.case import Case
from ..db.models.final_decision import FinalDecision
from ..db.models.human_escalation import HumanEscalation
from ..db.models.llm_decision import LlmDecision
from ..db.models.rule_evaluation import RuleEvaluation
from ..db.models.validation import Validation
from .state import CaseState
from .tracing import traced_node

load_dotenv()

CONFIDENCE_THRESHOLD = 0.7


class CandidateAssessment(BaseModel):
    """Salida estructurada esperada del LLM Decision Node."""

    fit_label: str = Field(description="Uno de: 'fit', 'not_fit', 'unclear'.")
    confidence: float = Field(ge=0.0, le=1.0)
    justification: str


def _llm() -> ChatOpenAI:
    return ChatOpenAI(model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"), temperature=0)


@traceable(name="rule_evaluator")
def rule_evaluator_node(state: CaseState) -> dict:
    """Modulo 2: comprobaciones obligatorias deterministas antes de involucrar al LLM."""
    payload = state["payload"]
    with traced_node(state["case_id"], "rule_evaluator", payload) as (session, node_execution):
        min_experience_ok = payload.get("years_experience", 0) >= 2
        has_required_docs = bool(payload.get("has_cv") and payload.get("has_id_document"))
        passed = min_experience_ok and has_required_docs

        session.add(
            RuleEvaluation(
                node_execution_id=node_execution.id,
                rule_name="candidate_min_requirements",
                result_bool=passed,
                details={
                    "min_experience_ok": min_experience_ok,
                    "has_required_docs": has_required_docs,
                },
            )
        )
        node_execution.output_data = {"passed": passed}

    return {"rule_result": {"passed": passed}}


@traceable(name="llm_decision")
def llm_decision_node(state: CaseState) -> dict:
    """Modulo 3: evaluacion semantica del candidato mediante un LLM."""
    payload = state["payload"]
    prompt = (
        "Evalua si el siguiente candidato encaja en el puesto ofertado. "
        "Responde de forma estructurada, con una justificacion breve.\n\n"
        f"Datos del candidato: {payload}"
    )
    with traced_node(state["case_id"], "llm_decision", {"prompt": prompt}) as (session, node_execution):
        structured_llm = _llm().with_structured_output(CandidateAssessment)
        assessment: CandidateAssessment = structured_llm.invoke(prompt)

        llm_decision = LlmDecision(
            node_execution_id=node_execution.id,
            model_name=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            prompt=prompt,
            structured_output=assessment.model_dump(),
            confidence=assessment.confidence,
        )
        session.add(llm_decision)
        session.flush()

        result = assessment.model_dump()
        result["llm_decision_id"] = str(llm_decision.id)
        node_execution.output_data = result

    return {"llm_decision": result}


@traceable(name="validation")
def validation_node(state: CaseState) -> dict:
    """Modulo 4: comprueba la coherencia de la salida del LLM antes de confiar en ella."""
    llm_decision = state["llm_decision"]
    with traced_node(state["case_id"], "validation", {"llm_decision": llm_decision}) as (session, node_execution):
        confidence = llm_decision.get("confidence", 0.0)
        fit_label = llm_decision.get("fit_label")
        is_valid = fit_label in {"fit", "not_fit", "unclear"}
        requires_review = (not is_valid) or fit_label == "unclear" or confidence < CONFIDENCE_THRESHOLD

        llm_decision_id = llm_decision.get("llm_decision_id")
        session.add(
            Validation(
                node_execution_id=node_execution.id,
                llm_decision_id=uuid.UUID(llm_decision_id) if llm_decision_id else None,
                is_valid=is_valid,
                reason=None if is_valid else "unexpected fit_label",
                requires_review=requires_review,
            )
        )
        node_execution.output_data = {"is_valid": is_valid, "requires_review": requires_review}

    return {
        "validation": {"is_valid": is_valid, "requires_review": requires_review},
        "requires_human": requires_review,
    }


def human_escalation_node(state: CaseState) -> dict:
    """Modulo 5: pausa el grafo y espera a un revisor humano.

    No se decora con `@traceable`: `interrupt()` pausa la ejecucion lanzando
    `GraphInterrupt`, y LangGraph vuelve a ejecutar esta funcion entera desde
    el principio al reanudar. Decorarla haria que cada pausa pareciera una
    ejecucion fallida en LangSmith, asi que este nodo se apoya en el propio
    trazado a nivel de grafo de LangGraph. El acceso a BD se divide en dos
    sesiones de corta duracion, antes y despues de `interrupt()`, para no
    mantener una conexion abierta mientras el caso esta pausado.
    """
    case_id = state["case_id"]

    with SessionLocal() as session:
        escalation = (
            session.query(HumanEscalation)
            .filter_by(case_id=case_id, status="pending")
            .order_by(HumanEscalation.created_at.desc())
            .first()
        )
        if escalation is None:
            escalation = HumanEscalation(
                case_id=case_id,
                reason=f"Low confidence or invalid LLM decision: {state.get('llm_decision')}",
                status="pending",
            )
            session.add(escalation)
            session.commit()

    decision = interrupt(
        {
            "case_id": case_id,
            "question": "Revisa el caso y decide el resultado ('fit' o 'not_fit').",
            "llm_decision": state.get("llm_decision"),
        }
    )

    with SessionLocal() as session:
        escalation = (
            session.query(HumanEscalation)
            .filter_by(case_id=case_id, status="pending")
            .order_by(HumanEscalation.created_at.desc())
            .first()
        )
        if escalation is not None:
            escalation.status = "resolved"
            escalation.resolution = decision.get("outcome")
            escalation.assigned_to = decision.get("reviewer")
            escalation.resolved_at = datetime.now(timezone.utc)
            session.commit()

    return {"human_feedback": decision}


@traceable(name="final_decision")
def final_decision_node(state: CaseState) -> dict:
    """Modulo 6: consolida todo en el resultado oficial del caso."""
    case_id = state["case_id"]
    consolidated = {
        "rule_result": state.get("rule_result"),
        "llm_decision": state.get("llm_decision"),
        "validation": state.get("validation"),
        "human_feedback": state.get("human_feedback"),
    }
    with traced_node(case_id, "final_decision", consolidated) as (session, node_execution):
        human_feedback = state.get("human_feedback")
        rule_result = state.get("rule_result") or {}
        if human_feedback:
            outcome = human_feedback.get("outcome", "escalated")
        elif not rule_result.get("passed", False):
            outcome = "rejected"
        else:
            outcome = (state.get("llm_decision") or {}).get("fit_label", "unclear")

        session.add(
            FinalDecision(
                case_id=case_id,
                outcome=outcome,
                consolidated_from=consolidated,
                decided_by="human" if human_feedback else "system",
            )
        )

        case = session.get(Case, uuid.UUID(case_id))
        if case is not None:
            case.status = "closed"
            case.current_node_key = "final_decision"

        node_execution.output_data = {"outcome": outcome}

    return {"outcome": outcome}
