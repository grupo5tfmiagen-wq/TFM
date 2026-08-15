"""Configuracion compartida de pytest.

Dos cosas, ambas para poder testear `src/graph/*.py` como unidades, sin
depender de una base de datos real ni de credenciales de OpenAI/LangSmith:

1. Asegura que el paquete `src` se pueda importar sin depender del
   directorio desde el que se lance `pytest`.
2. Sustituye por dobles minimos los modulos de infraestructura que
   `nodes.py` importa a nivel de modulo (`src.db.*`): si esos modulos reales
   necesitan una conexion a BD o variables de entorno para poder
   *importarse*, los tests unitarios acabarian dependiendo de tener la BD
   levantada solo para poder importar el codigo, que es justo lo que un
   test unitario tiene que evitar.

El comportamiento real de cada test se controla aparte, monkeypencheando
estas clases/funciones dentro de `src.graph.nodes` (ver `tests/test_nodes.py`).
"""
import sys
import types
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class _DummyModel:
    """Doble minimo para una clase de modelo de SQLAlchemy: solo necesita
    ser instanciable con kwargs arbitrarios para que `nodes.py` se pueda
    importar sin fallos. Los tests que necesitan comprobar como se
    persisten estos modelos los sustituyen aparte (ver `patch_models` en
    `tests/test_nodes.py`)."""

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


def _stub_module(name: str, **attrs) -> types.ModuleType:
    if name in sys.modules:
        return sys.modules[name]
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


def _stub_db_package() -> None:
    _stub_module("src.db")
    _stub_module("src.db.base", SessionLocal=_DummyModel)
    _stub_module("src.db.checkpointer", get_checkpointer=_DummyModel)
    _stub_module("src.db.models")
    _stub_module("src.db.models.case", Case=_DummyModel)
    _stub_module("src.db.models.final_decision", FinalDecision=_DummyModel)
    _stub_module("src.db.models.human_escalation", HumanEscalation=_DummyModel)
    _stub_module("src.db.models.llm_decision", LlmDecision=_DummyModel)
    _stub_module("src.db.models.node_execution", CaseNodeExecution=_DummyModel)
    _stub_module("src.db.models.rule_evaluation", RuleEvaluation=_DummyModel)
    _stub_module("src.db.models.validation", Validation=_DummyModel)


_stub_db_package()
