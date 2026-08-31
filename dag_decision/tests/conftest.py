"""Fixtures y dobles de prueba compartidos por el juego de tests.

Los tests unitarios y de flujo no tocan Postgres ni OpenAI: usan
`FakeSession`, una sesion en memoria que imita el subconjunto de la API de
SQLAlchemy que usan los nodos y el servicio de escalacion (`add`, `flush`,
`commit`, `get`, `query(...).filter_by(...).order_by(...).first()/all()`).
Los tests de integracion contra el Postgres real viven en
`test_escalation_db_integration.py` y se saltan solos si no hay BD.
"""
import os
import sys
import uuid

import pytest
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Carga el .env real si existe; si no, deja valores de relleno para que
# importar `src.db.base` (que lee DATABASE_URL en tiempo de importacion)
# no rompa los tests que no usan BD. `override=True` es importante: si el
# shell ya trae DATABASE_URL/CHECKPOINTER_DATABASE_URL de otro proyecto,
# el .env local debe ganar para no acabar conectando a una BD inexistente
# (que se manifestaria como un test "colgado" esperando el timeout de conexion).
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"), override=True)
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost:5999/test_db")
os.environ.setdefault("CHECKPOINTER_DATABASE_URL", "postgresql://test:test@localhost:5999/test_db")

from src.db.models.case import Case  # noqa: E402
from src.db.models.human_escalation import HumanEscalation  # noqa: E402


def _normalize(value):
    """Normaliza UUIDs a str para comparar sin depender del tipo almacenado."""
    return str(value) if isinstance(value, uuid.UUID) else value


class FakeQuery:
    """Imita el Query de SQLAlchemy sobre una lista en memoria."""

    def __init__(self, model, items):
        self._model = model
        self._items = list(items)

    def filter_by(self, **kwargs):
        def matches(obj):
            return all(_normalize(getattr(obj, key)) == _normalize(value) for key, value in kwargs.items())

        return FakeQuery(self._model, [obj for obj in self._items if matches(obj)])

    def order_by(self, *criteria):
        items = list(self._items)
        if criteria:
            # Aproxima created_at con la secuencia de insercion en el fake.
            reverse = "desc" in str(criteria[0]).lower()
            items.sort(key=lambda obj: getattr(obj, "_fake_seq", 0), reverse=reverse)
        return FakeQuery(self._model, items)

    def first(self):
        return self._items[0] if self._items else None

    def all(self):
        return list(self._items)


class FakeSession:
    """Sesion en memoria compatible con el uso que hacen nodos y servicio."""

    def __init__(self):
        self._store: dict[type, list] = {}
        self._seq = 0
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    def add(self, obj):
        self._seq += 1
        obj._fake_seq = self._seq
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        self._store.setdefault(type(obj), []).append(obj)

    def flush(self):
        for items in self._store.values():
            for obj in items:
                if getattr(obj, "id", None) is None:
                    obj.id = uuid.uuid4()

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def close(self):
        # No-op deliberado: la misma instancia se reutiliza entre bloques
        # `with SessionLocal()` dentro de un mismo test.
        pass

    def get(self, model, pk):
        for obj in self._store.get(model, []):
            if _normalize(obj.id) == _normalize(pk):
                return obj
        return None

    def query(self, model):
        return FakeQuery(model, self._store.get(model, []))

    def stored(self, model) -> list:
        """Atajo de test: todas las instancias guardadas de un modelo."""
        return list(self._store.get(model, []))


@pytest.fixture()
def fake_session() -> FakeSession:
    return FakeSession()


@pytest.fixture()
def patch_session(monkeypatch, fake_session) -> FakeSession:
    """Redirige el SessionLocal de los nodos y del tracing al FakeSession."""
    import src.graph.nodes as nodes_module
    import src.graph.tracing as tracing_module

    monkeypatch.setattr(nodes_module, "SessionLocal", lambda: fake_session)
    monkeypatch.setattr(tracing_module, "SessionLocal", lambda: fake_session)
    return fake_session


@pytest.fixture()
def sample_state() -> dict:
    """Estado de caso tipico al llegar a la Human Escalation Layer."""
    return {
        "case_id": str(uuid.uuid4()),
        "case_type": "candidate_selection",
        "payload": {"years_experience": 5, "has_cv": True, "has_id_document": True},
        "rule_result": {"passed": True},
        "llm_decision": {"fit_label": "unclear", "confidence": 0.4, "justification": "Perfil ambiguo."},
        "validation": {"is_valid": True, "requires_review": True},
        "requires_human": True,
    }


@pytest.fixture()
def stored_case(fake_session, sample_state) -> Case:
    """Un Case ya persistido (en el fake) correspondiente a `sample_state`."""
    case = Case(
        id=uuid.UUID(sample_state["case_id"]),
        case_type=sample_state["case_type"],
        status="running",
        payload=sample_state["payload"],
    )
    fake_session.add(case)
    return case
