"""Importa todos los modelos ORM para que se registren en `Base.metadata` (necesario para el autogenerate de Alembic)."""
from .case import Case
from .cv_document import CVDocument
from .final_decision import FinalDecision
from .human_escalation import HumanEscalation
from .job_posting import JobPosting
from .llm_decision import LlmDecision
from .node_execution import CaseNodeExecution
from .rule_evaluation import RuleEvaluation
from .validation import Validation

__all__ = [
    "Case",
    "CVDocument",
    "CaseNodeExecution",
    "RuleEvaluation",
    "LlmDecision",
    "Validation",
    "HumanEscalation",
    "FinalDecision",
    "JobPosting",
]
