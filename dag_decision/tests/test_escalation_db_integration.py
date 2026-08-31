"""Tests de integracion de la Human Escalation Layer contra el Postgres real.

Requieren el Postgres local levantado (`docker compose up -d`), las
migraciones aplicadas y el `.env` configurado; si no hay conexion, se
saltan automaticamente. Todo se ejecuta dentro de una transaccion que se
revierte al terminar cada test (el servicio hace `flush`, nunca `commit`),
asi que no dejan residuo en la base de datos.
"""
import os
import sys

import pytest
from sqlalchemy import text

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

pytestmark = pytest.mark.integration


@pytest.fixture()
def db_session():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from src.db.base import DATABASE_URL

    # Engine propio con timeout de conexion corto: si el Postgres local no
    # esta levantado, el skip salta en ~3s en vez de esperar el timeout por
    # defecto del driver (que puede tardar decenas de segundos).
    sep = "&" if "?" in DATABASE_URL else "?"
    engine = create_engine(f"{DATABASE_URL}{sep}connect_timeout=3", future=True)
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()
    try:
        session.execute(text("SELECT 1"))
    except Exception as exc:
        session.close()
        pytest.skip(f"Postgres no disponible (docker compose up -d): {exc}")
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def test_ciclo_completo_de_escalacion_en_bd_real(db_session):
    from src.db.models.case import Case
    from src.escalation.service import (
        create_escalation,
        get_pending_escalation,
        list_pending_escalations,
        resolve_escalation,
    )

    case = Case(case_type="candidate_selection", status="running", payload={"test": "integracion"})
    db_session.add(case)
    db_session.flush()

    esc = create_escalation(db_session, case_id=case.id, reason="test de integracion")
    assert esc.id is not None
    assert esc.created_at is not None  # server_default de Postgres aplicado

    assert get_pending_escalation(db_session, case.id).id == esc.id
    assert esc in list_pending_escalations(db_session)

    resuelta = resolve_escalation(db_session, esc.id, outcome="fit", reviewer="tester")
    assert resuelta.status == "resolved"
    assert resuelta.resolved_at is not None
    assert get_pending_escalation(db_session, case.id) is None


def test_resolve_escalation_en_bd_rechaza_doble_resolucion(db_session):
    from src.db.models.case import Case
    from src.escalation.service import create_escalation, resolve_escalation

    case = Case(case_type="candidate_selection", status="running", payload={"test": "integracion"})
    db_session.add(case)
    db_session.flush()
    esc = create_escalation(db_session, case_id=case.id, reason="test de integracion")

    resolve_escalation(db_session, esc.id, outcome="fit", reviewer="tester")
    with pytest.raises(ValueError, match="no esta pendiente"):
        resolve_escalation(db_session, esc.id, outcome="not_fit", reviewer="otro")
