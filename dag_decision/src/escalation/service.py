"""Servicio de la Human Escalation Layer (Modulo 5).

Encapsula la "cola de revision humana" sobre la tabla `human_escalations`:
crear escalaciones, consultar las pendientes (la cola que veria un revisor)
y resolverlas. Es la unica puerta de entrada a esa tabla, de modo que el
nodo del grafo (`human_escalation_node`), la interfaz de revision
(`scripts/review_escalations.py`) y los tests compartan exactamente la
misma logica.

Las funciones reciben la sesion de SQLAlchemy desde fuera y hacen `flush`
pero NUNCA `commit`: quien llama decide cuando confirmar la transaccion
(el nodo confirma al pausar/reanudar; los tests de integracion pueden
hacer rollback y no dejar residuo en la BD).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..db.models.human_escalation import HumanEscalation

STATUS_PENDING = "pending"
STATUS_RESOLVED = "resolved"


def _as_uuid(value: str | uuid.UUID) -> uuid.UUID:
    """Normaliza un identificador que puede llegar como str o como UUID."""
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def create_escalation(
    session: Session,
    *,
    case_id: str | uuid.UUID,
    reason: str,
    node_execution_id: str | uuid.UUID | None = None,
) -> HumanEscalation:
    """Crea una escalacion pendiente para un caso y la devuelve (con id asignado)."""
    escalation = HumanEscalation(
        case_id=_as_uuid(case_id),
        node_execution_id=_as_uuid(node_execution_id) if node_execution_id else None,
        reason=reason,
        status=STATUS_PENDING,
    )
    session.add(escalation)
    session.flush()
    return escalation


def get_escalation(session: Session, escalation_id: str | uuid.UUID) -> HumanEscalation | None:
    """Devuelve una escalacion por id, o None si no existe."""
    return session.get(HumanEscalation, _as_uuid(escalation_id))


def get_pending_escalation(session: Session, case_id: str | uuid.UUID) -> HumanEscalation | None:
    """Devuelve la escalacion pendiente mas reciente de un caso, o None.

    Es la comprobacion de idempotencia del nodo: al reanudar un caso pausado,
    LangGraph re-ejecuta el nodo entero y esta consulta evita crear un
    duplicado de la escalacion.
    """
    return (
        session.query(HumanEscalation)
        .filter_by(case_id=_as_uuid(case_id), status=STATUS_PENDING)
        .order_by(HumanEscalation.created_at.desc())
        .first()
    )


def list_pending_escalations(session: Session) -> list[HumanEscalation]:
    """Devuelve la cola de revision: todas las escalaciones pendientes, FIFO."""
    return (
        session.query(HumanEscalation)
        .filter_by(status=STATUS_PENDING)
        .order_by(HumanEscalation.created_at.asc())
        .all()
    )


def resolve_escalation(
    session: Session,
    escalation_id: str | uuid.UUID,
    *,
    outcome: str,
    reviewer: str | None = None,
) -> HumanEscalation:
    """Marca una escalacion pendiente como resuelta con la decision del revisor.

    Lanza ValueError si la escalacion no existe o ya no esta pendiente, para
    evitar sobrescribir decisiones humanas ya registradas.
    """
    escalation = get_escalation(session, escalation_id)
    if escalation is None:
        raise ValueError(f"Escalacion no encontrada: {escalation_id}")
    if escalation.status != STATUS_PENDING:
        raise ValueError(
            f"La escalacion {escalation_id} no esta pendiente (estado actual: {escalation.status})"
        )
    escalation.status = STATUS_RESOLVED
    escalation.resolution = outcome
    escalation.assigned_to = reviewer
    escalation.resolved_at = datetime.now(timezone.utc)
    session.flush()
    return escalation
