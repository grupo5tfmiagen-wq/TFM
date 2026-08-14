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

La logica de negocio de `rule_evaluator_node` y `llm_decision_node` esta
tomada de `rule_node` / `llm_node` en el prototipo `DAGEngine.py`. El
`payload` del caso usa las mismas claves en ingles que traen los ficheros
JSON reales (`case.json` + `job_profile.json`, ver `scripts/run_case.py`).
La forma esperada es:

    payload = {
        "candidate": {"cv": {"technical_skills": [...], "experience": [...]}},
        "job_profile": {
            "mandatory_requirements": {
                "technical_skills": [...],
                "min_years_experience": <int>,
            },
            "desired_requirements": {"technical_skills": [...]},
        },
    }

No se ha portado el bucle generico de cola de nodos (`carga_del_caso`,
`dag_engine_selecciona_nodo`, `quedan_nodos`) ni el nodo de transformacion de
score ponderado del prototipo: `build.py` implementa el Modulo 1 (DAG
Engine) como un pipeline fijo de 5 nodos con dos bifurcaciones, no como una
cola generica de nodos por caso, asi que esa parte de DAGEngine.py no aplica
a esta version productiva.
"""
from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timezone

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


def _parse_year_month(value: str | None) -> date | None:
    """Convierte un valor "YYYY-MM" (formato de `experience` en el CV) a `date`."""
    if not value:
        return None
    year, month = value.split("-")
    return date(int(year), int(month), 1)


def _years_of_experience(experience_entries: list[dict]) -> float:
    """Suma la duracion de cada entrada de `candidate.cv.experience` (en anios).

    Cada entrada trae `start_date`/`end_date` en formato "YYYY-MM";
    `end_date` puede venir como "present" para un puesto en curso, en cuyo
    caso se usa la fecha de hoy. No se corrigen solapamientos entre
    entradas: se asume que el CV ya viene con periodos no solapados, igual
    que en el `case.json` de referencia.
    """
    total_months = 0
    for entry in experience_entries:
        start = _parse_year_month(entry.get("start_date"))
        end_raw = entry.get("end_date")
        end = date.today() if end_raw in (None, "present") else _parse_year_month(end_raw)
        if start is None or end is None:
            continue
        total_months += max(0, (end.year - start.year) * 12 + (end.month - start.month))
    return round(total_months / 12, 1)


@traceable(name="rule_evaluator")
def rule_evaluator_node(state: CaseState) -> dict:
    """Modulo 2: Rule Evaluator.

    Dos reglas obligatorias, tomadas de `rule_node` en DAGEngine.py mas la de
    anos de experiencia pedida como ampliacion:

    1. Habilidades tecnicas obligatorias (`job_profile.mandatory_requirements.technical_skills`)
       frente a las del CV (`candidate.cv.technical_skills`).
    2. Anos de experiencia minimos (`job_profile.mandatory_requirements.min_years_experience`),
       calculados a partir del historial `candidate.cv.experience` (ver `_years_of_experience`).

    Si falla cualquiera de las dos, el caso queda descartado (`passed=False`)
    y `build.py::_route_after_rules` lo envia directamente a
    `final_decision`, sin pasar por el LLM.
    """
    payload = state["payload"] # type: ignore
    with traced_node(state["case_id"], "rule_evaluator", payload) as (session, node_execution): # type: ignore
        cv = payload.get("candidate", {}).get("cv", {})
        requirements = payload.get("job_profile", {}).get("mandatory_requirements", {})

        candidate_skills = set(cv.get("technical_skills", []))
        required_skills = set(requirements.get("technical_skills", []))
        missing_skills = sorted(required_skills - candidate_skills)

        years_experience = _years_of_experience(cv.get("experience", []))
        min_years_required = requirements.get("min_years_experience", 0)
        meets_experience = years_experience >= min_years_required

        passed = not missing_skills and meets_experience

        session.add(
            RuleEvaluation(
                node_execution_id=node_execution.id,
                rule_name="candidate_min_requirements",
                result_bool=passed,
                details={
                    "missing_skills": missing_skills,
                    "years_experience": years_experience,
                    "min_years_required": min_years_required,
                    "meets_experience": meets_experience,
                },
            )
        )
        node_execution.output_data = {
            "passed": passed,
            "missing_skills": missing_skills,
            "years_experience": years_experience,
            "min_years_required": min_years_required,
        }

    return {
        "rule_result": {
            "passed": passed,
            "missing_skills": missing_skills,
            "years_experience": years_experience,
            "min_years_required": min_years_required,
        }
    }


@traceable(name="llm_decision")
def llm_decision_node(state: CaseState) -> dict:
    """Modulo 3: evaluacion semantica del candidato mediante un LLM.

    Incorpora al prompt las habilidades deseables del perfil de puesto — la
    misma senal que usaba el cociente ad-hoc de `llm_node` en DAGEngine.py —
    para que el LLM real valore la afinidad del candidato con ellas como
    parte de su juicio estructurado, en vez de calcularla con una formula.
    """
    payload = state["payload"] # type: ignore
    desired_skills = sorted(
        payload.get("job_profile", {}).get("desired_requirements", {}).get("technical_skills", [])
    )
    prompt = (
        "Evalua si el siguiente candidato encaja en el puesto ofertado, "
        "prestando especial atencion a su afinidad con las habilidades "
        "deseables del perfil (no obligatorias, mejoran el ajuste). "
        "Responde de forma estructurada, con una justificacion breve.\n\n"
        f"Datos del candidato: {payload.get('candidate')}\n\n"
        f"Habilidades deseables del puesto: {desired_skills}"
    )
    with traced_node(state["case_id"], "llm_decision", {"prompt": prompt}) as (session, node_execution): # type: ignore
        structured_llm = _llm().with_structured_output(CandidateAssessment)
        assessment: CandidateAssessment = structured_llm.invoke(prompt) # type: ignore

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
    """Modulo 4: comprueba la coherencia de la salida del LLM antes de confiar en ella.

    El detalle completo (is_valid, motivo, requires_review) queda persistido
    en la fila `Validation` de este nodo via `traced_node`; al grafo solo le
    hace falta `requires_human` para decidir la ruta en
    `build.py::_route_after_validation`, asi que es lo unico que se devuelve
    al estado (ver la nota en `state.py` sobre por que se elimino el campo
    `validation`).
    """
    llm_decision = state["llm_decision"] # type: ignore
    with traced_node(state["case_id"], "validation", {"llm_decision": llm_decision}) as (session, node_execution): # type: ignore
        assert llm_decision is not None
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

    return {"requires_human": requires_review}


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
    case_id = state["case_id"] # type: ignore

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
    case_id = state["case_id"] # type: ignore
    consolidated = {
        "rule_result": state.get("rule_result"),
        "llm_decision": state.get("llm_decision"),
        "requires_human": state.get("requires_human"),
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
