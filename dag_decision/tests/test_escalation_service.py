"""Tests unitarios del servicio de la Human Escalation Layer (`src/escalation/`)."""
import uuid

import pytest

from src.db.models.human_escalation import HumanEscalation
from src.escalation.service import (
    STATUS_PENDING,
    STATUS_RESOLVED,
    create_escalation,
    get_escalation,
    get_pending_escalation,
    list_pending_escalations,
    resolve_escalation,
)


def test_create_escalation_asigna_id_y_estado_pendiente(fake_session):
    esc = create_escalation(fake_session, case_id=str(uuid.uuid4()), reason="confianza baja")

    assert esc.id is not None
    assert esc.status == STATUS_PENDING
    assert esc.reason == "confianza baja"
    assert esc.resolved_at is None
    assert esc in fake_session.stored(HumanEscalation)


def test_create_escalation_acepta_uuid_y_enlaza_node_execution(fake_session):
    case_id = uuid.uuid4()
    node_execution_id = uuid.uuid4()

    esc = create_escalation(
        fake_session, case_id=case_id, reason="revision", node_execution_id=node_execution_id
    )

    assert esc.case_id == case_id
    assert esc.node_execution_id == node_execution_id


def test_get_pending_escalation_devuelve_la_mas_reciente(fake_session):
    case_id = uuid.uuid4()
    antigua = create_escalation(fake_session, case_id=case_id, reason="antigua")
    resolve_escalation(fake_session, antigua.id, outcome="fit", reviewer="ana")
    reciente = create_escalation(fake_session, case_id=case_id, reason="reciente")

    encontrada = get_pending_escalation(fake_session, str(case_id))

    assert encontrada is not None
    assert encontrada.id == reciente.id


def test_get_pending_escalation_none_si_no_hay_pendientes(fake_session):
    assert get_pending_escalation(fake_session, uuid.uuid4()) is None


def test_list_pending_escalations_solo_pendientes_en_orden_fifo(fake_session):
    primera = create_escalation(fake_session, case_id=uuid.uuid4(), reason="1")
    segunda = create_escalation(fake_session, case_id=uuid.uuid4(), reason="2")
    resuelta = create_escalation(fake_session, case_id=uuid.uuid4(), reason="3")
    resolve_escalation(fake_session, resuelta.id, outcome="fit", reviewer="ana")

    pendientes = list_pending_escalations(fake_session)

    assert [e.id for e in pendientes] == [primera.id, segunda.id]


def test_resolve_escalation_registra_decision_y_fecha(fake_session):
    esc = create_escalation(fake_session, case_id=uuid.uuid4(), reason="revision")

    resuelta = resolve_escalation(fake_session, esc.id, outcome="not_fit", reviewer="luis")

    assert resuelta.status == STATUS_RESOLVED
    assert resuelta.resolution == "not_fit"
    assert resuelta.assigned_to == "luis"
    assert resuelta.resolved_at is not None


def test_resolve_escalation_falla_si_no_existe(fake_session):
    with pytest.raises(ValueError, match="no encontrada"):
        resolve_escalation(fake_session, uuid.uuid4(), outcome="fit")


def test_resolve_escalation_falla_si_ya_esta_resuelta(fake_session):
    esc = create_escalation(fake_session, case_id=uuid.uuid4(), reason="revision")
    resolve_escalation(fake_session, esc.id, outcome="fit", reviewer="ana")

    with pytest.raises(ValueError, match="no esta pendiente"):
        resolve_escalation(fake_session, esc.id, outcome="not_fit", reviewer="luis")

    # La decision original no se sobrescribe.
    assert get_escalation(fake_session, esc.id).resolution == "fit"
