"""Ayudantes para persistir la trazabilidad de cada nodo en el esquema de negocio.

Estos ayudantes complementan los propios checkpoints de LangGraph (estado
tecnico para el replay) con el rastro de auditoria legible descrito en el
documento de arquitectura: una fila `CaseNodeExecution` por cada ejecucion de
nodo, enlazada con las filas de resultado especificas (`rule_evaluations`,
`llm_decisions`, `validations`, `human_escalations`, `final_decisions`)
creadas por cada nodo.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..db.base import SessionLocal
from ..db.models.node_execution import CaseNodeExecution


@contextmanager
def traced_node(case_id: str, node_key: str, input_data: dict | None):
    """Abre una sesion de BD y una fila `CaseNodeExecution` para una ejecucion de nodo.

    Devuelve `(session, node_execution)`. Quien llama debe fijar
    `node_execution.output_data` antes de que termine el bloque. Si todo va
    bien, la ejecucion se marca como "completed" y se hace commit; si hay una
    excepcion, se marca como "failed", se hace commit y se relanza la
    excepcion.
    """
    session: Session = SessionLocal()
    node_execution = CaseNodeExecution(
        case_id=case_id,
        node_key=node_key,
        input_data=input_data,
        status="running",
        started_at=datetime.now(timezone.utc),
    )
    session.add(node_execution)
    session.flush()
    try:
        yield session, node_execution
    except Exception:
        node_execution.status = "failed"
        node_execution.finished_at = datetime.now(timezone.utc)
        session.commit()
        raise
    else:
        node_execution.status = "completed"
        node_execution.finished_at = datetime.now(timezone.utc)
        session.commit()
    finally:
        session.close()
