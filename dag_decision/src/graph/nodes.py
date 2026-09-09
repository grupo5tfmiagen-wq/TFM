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

Instrumentacion de LangSmith (trazabilidad):
`@traceable` ya captura automaticamente, por nodo, la entrada (argumentos),
la salida (valor devuelto) y el tiempo de ejecucion en cuanto
`LANGSMITH_TRACING=true` este en el `.env`. A eso se le anade, via
`_tag_current_run` (ver mas abajo), lo que LangSmith no da gratis:

- Tags/metadata por caso (`case_id`, `case_type`) en cada nodo, para poder
  filtrar y agrupar trazas por caso en la UI de LangSmith.
- Tags de resultado (`rule_passed`, `requires_review`, `outcome`,
  `escalated`) en el nodo que los produce, para poder ver tasas (agrupando
  por tag en LangSmith) sin montar un dashboard aparte.
- Tokens consumidos y coste estimado de cada llamada LLM (`llm_decision`),
  ya que `with_structured_output` sin `include_raw=True` descarta esa
  metadata.
- Tiempo total del caso end-to-end y tiempo de espera de revision humana,
  calculados en `final_decision_node` a partir de `Case.created_at` y de
  `HumanEscalation.created_at`/`resolved_at` (esto no lo captura LangSmith
  solo con `@traceable`, porque el `interrupt()` puede dejar el caso pausado
  dias enteros entre dos invocaciones distintas del grafo).

`_tag_current_run` nunca debe poder tumbar el pipeline real: cualquier fallo
al anotar el run de LangSmith se ignora en silencio.
"""
from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timezone

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.types import interrupt
from langsmith import get_current_run_tree, traceable
from pydantic import BaseModel, Field

from ..db.base import SessionLocal
from ..db.models.case import Case
from ..db.models.final_decision import FinalDecision
from ..db.models.human_escalation import HumanEscalation
from ..db.models.llm_decision import LlmDecision
from ..db.models.node_execution import CaseNodeExecution
from ..db.models.rule_evaluation import RuleEvaluation
from ..db.models.validation import Validation
from ..escalation.service import (
    create_escalation,
    get_pending_escalation,
    resolve_escalation,
)
from .state import CaseState
from .tracing import traced_node

load_dotenv()

CONFIDENCE_THRESHOLD = float(os.environ.get("CONFIDENCE_THRESHOLD", "0.8"))


class CandidateAssessment(BaseModel):
    """Salida estructurada esperada del LLM Decision Node."""

    fit_label: str = Field(description="Uno de: 'fit', 'not_fit', 'unclear'.")
    confidence: float = Field(ge=0.0, le=1.0)
    justification: str


def _llm() -> ChatOpenAI:
    return ChatOpenAI(model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"), temperature=0)


def _tag_current_run(*, tags: list[str] | None = None, metadata: dict | None = None) -> None:
    """Anade tags/metadata al run activo de LangSmith, si hay uno.

    Se apoya en `get_current_run_tree()`, que solo devuelve algo dentro de
    una funcion decorada con `@traceable` y con el tracing habilitado; si no
    hay run activo (tracing desactivado, o se llama fuera de un nodo
    trazado) no hace nada. Cualquier fallo se ignora en silencio: anotar la
    traza es una mejora de observabilidad, nunca debe poder tumbar el
    pipeline real.
    """
    try:
        run_tree = get_current_run_tree()
        if run_tree is None:
            return
        if tags:
            existing = list(run_tree.tags or [])
            run_tree.tags = existing + [t for t in tags if t not in existing]
        if metadata:
            run_tree.extra = run_tree.extra or {}
            run_tree.extra.setdefault("metadata", {}).update(metadata)
    except Exception:
        pass


def _case_metadata(state: CaseState) -> dict:
    """Metadata comun a todos los nodos, para poder filtrar por caso en LangSmith."""
    return {"case_id": state.get("case_id"), "case_type": state.get("case_type")}


# Precio aproximado por millon de tokens (USD). Configurable por variables de
# entorno porque cambia con el tiempo y con el modelo: los valores por
# defecto son los de gpt-4o-mini en el momento de escribir esto, hay que
# revisarlos si cambias de modelo o si OpenAI actualiza precios.
_INPUT_PRICE_PER_1M_USD = float(os.environ.get("OPENAI_INPUT_PRICE_PER_1M_USD", "0.15"))
_OUTPUT_PRICE_PER_1M_USD = float(os.environ.get("OPENAI_OUTPUT_PRICE_PER_1M_USD", "0.60"))


def _estimate_cost_usd(input_tokens: int | None, output_tokens: int | None) -> float | None:
    """Coste estimado (USD) de una llamada LLM a partir de sus tokens."""
    if input_tokens is None or output_tokens is None:
        return None
    cost = (input_tokens / 1_000_000) * _INPUT_PRICE_PER_1M_USD
    cost += (output_tokens / 1_000_000) * _OUTPUT_PRICE_PER_1M_USD
    return round(cost, 6)


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

        _tag_current_run(
            tags=[f"rule_passed:{passed}"],
            metadata={
                **_case_metadata(state),
                "missing_skills": missing_skills,
                "years_experience": years_experience,
                "min_years_required": min_years_required,
            },
        )

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

    Tambien captura tokens consumidos y coste estimado de la llamada (ver
    `_estimate_cost_usd`), que quedan tanto en `node_execution.output_data`
    como en la metadata del run de LangSmith.
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
        # `include_raw=True` conserva el AIMessage original (con
        # `usage_metadata`) ademas del objeto parseado; sin esto,
        # `with_structured_output` descarta el conteo de tokens.
        structured_llm = _llm().with_structured_output(CandidateAssessment, include_raw=True)
        raw_result = structured_llm.invoke(prompt)
        assessment: CandidateAssessment = raw_result["parsed"]

        usage = getattr(raw_result.get("raw"), "usage_metadata", None) or {}
        input_tokens = usage.get("input_tokens")
        output_tokens = usage.get("output_tokens")
        total_tokens = usage.get("total_tokens")
        estimated_cost_usd = _estimate_cost_usd(input_tokens, output_tokens)

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
        result["input_tokens"] = input_tokens
        result["output_tokens"] = output_tokens
        result["total_tokens"] = total_tokens
        result["estimated_cost_usd"] = estimated_cost_usd
        node_execution.output_data = result

        _tag_current_run(
            tags=[f"fit_label:{assessment.fit_label}"],
            metadata={
                **_case_metadata(state),
                "confidence": assessment.confidence,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "estimated_cost_usd": estimated_cost_usd,
            },
        )

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

        _tag_current_run(
            tags=[f"requires_review:{requires_review}"],
            metadata={**_case_metadata(state), "is_valid": is_valid, "confidence": confidence},
        )

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

    La logica de la cola de revision vive en `src/escalation/service.py`.
    La primera sesion registra la escalacion (solo una vez: al reanudar, la
    escalacion pendiente ya existe y se reutiliza, por lo que el nodo es
    idempotente) y deja una fila `CaseNodeExecution` en estado "waiting"
    enlazada desde `HumanEscalation.node_execution_id`. La segunda sesion,
    tras la reanudacion, resuelve la escalacion y cierra la auditoria.
    """
    case_id = state["case_id"] # type: ignore
    llm_decision = state.get("llm_decision") or {}
    # Antes aqui se volcaba el dict entero de `llm_decision` como texto
    # (`f"...{state.get('llm_decision')}"`), lo que dejaba un "reason"
    # ilegible en la cola de escalaciones. Ahora se guarda solo el texto que
    # de verdad justifica la revision: la `justification` que ya escribio el
    # LLM en `llm_decision_node`.
    reason = llm_decision.get("justification") or "El LLM no proporciono una justificacion."

    with SessionLocal() as session:
        escalation = get_pending_escalation(session, case_id)
        if escalation is None:
            node_execution = CaseNodeExecution(
                case_id=uuid.UUID(case_id),
                node_key="human_escalation",
                input_data={
                    "llm_decision": state.get("llm_decision"),
                    "validation": state.get("validation"),
                },
                status="waiting",
                started_at=datetime.now(timezone.utc),
            )
            session.add(node_execution)
            session.flush()
            escalation = create_escalation(
                session,
                case_id=case_id,
                reason=reason,
                node_execution_id=node_execution.id,
            )
            case = session.get(Case, uuid.UUID(case_id))
            if case is not None:
                case.status = "waiting_human"
                case.current_node_key = "human_escalation"
            session.commit()
        escalation_id = str(escalation.id)

    decision = interrupt(
        {
            "case_id": case_id,
            "escalation_id": escalation_id,
            "question": "Revisa el caso y decide el resultado ('fit' o 'not_fit').",
            "llm_decision": state.get("llm_decision"),
        }
    )

    with SessionLocal() as session:
        escalation = get_pending_escalation(session, case_id)
        if escalation is not None:
            resolve_escalation(
                session,
                escalation.id,
                outcome=decision.get("outcome"),
                reviewer=decision.get("reviewer"),
            )
            if escalation.node_execution_id is not None:
                node_execution = session.get(CaseNodeExecution, escalation.node_execution_id)
                if node_execution is not None:
                    node_execution.status = "completed"
                    node_execution.output_data = {"human_feedback": decision}
                    node_execution.finished_at = datetime.now(timezone.utc)
            case = session.get(Case, uuid.UUID(case_id))
            if case is not None:
                case.status = "running"
            session.commit()

    return {"human_feedback": decision}


@traceable(name="final_decision")
def final_decision_node(state: CaseState) -> dict:
    """Modulo 6: consolida todo en el resultado oficial del caso.

    Ademas de consolidar el resultado, calcula dos metricas que
    `@traceable` no puede capturar solo (porque el caso puede quedar
    pausado por `interrupt()` dias enteros entre dos invocaciones distintas
    del grafo, asi que no son "tiempo de ejecucion de un nodo"):

    - `total_case_seconds`: desde `Case.created_at` hasta ahora.
    - `human_review_seconds`: desde que se creo la `HumanEscalation` hasta
      que se resolvio (`None` si el caso no paso por revision humana).
    """
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

        case = session.get(Case, uuid.UUID(case_id))

        human_review_seconds = None
        if human_feedback:
            last_escalation = (
                session.query(HumanEscalation)
                .filter_by(case_id=case_id, status="resolved")
                .order_by(HumanEscalation.resolved_at.desc())
                .first()
            )
            if last_escalation and last_escalation.resolved_at and last_escalation.created_at:
                human_review_seconds = (
                    last_escalation.resolved_at - last_escalation.created_at
                ).total_seconds()

        total_case_seconds = None
        if case is not None and getattr(case, "created_at", None):
            total_case_seconds = (datetime.now(timezone.utc) - case.created_at).total_seconds()

        session.add(
            FinalDecision(
                case_id=case_id,
                outcome=outcome,
                consolidated_from=consolidated,
                decided_by="human" if human_feedback else "system",
            )
        )

        if case is not None:
            case.status = "closed"
            case.current_node_key = "final_decision"

        node_execution.output_data = {
            "outcome": outcome,
            "total_case_seconds": total_case_seconds,
            "human_review_seconds": human_review_seconds,
        }

        _tag_current_run(
            tags=[f"outcome:{outcome}", f"escalated:{bool(human_feedback)}"],
            metadata={
                **_case_metadata(state),
                "total_case_seconds": total_case_seconds,
                "human_review_seconds": human_review_seconds,
            },
        )

    return {"outcome": outcome}