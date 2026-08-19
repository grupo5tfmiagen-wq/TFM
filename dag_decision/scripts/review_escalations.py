"""Interfaz simple por terminal para la Human Escalation Layer (Modulo 5).

Es la "interfaz de revision" sugerida en la planificacion del TFM (Fase 4):
muestra la cola de escalaciones pendientes y permite resolver una de ellas
introduciendo la decision del revisor. Al resolver, reanuda el grafo del
caso correspondiente con `Command(resume=...)`; es el propio
`human_escalation_node` quien marca la escalacion como resuelta en la BD y
continua hasta la decision final.

Uso (desde `dag_decision/`, con el venv activo y `.env` relleno):

    .venv\\Scripts\\python scripts\\review_escalations.py           # solo lista la cola
    .venv\\Scripts\\python scripts\\review_escalations.py --review  # lista y permite resolver
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from langgraph.types import Command  # noqa: E402

from src.db.base import SessionLocal  # noqa: E402
from src.db.checkpointer import get_checkpointer  # noqa: E402
from src.escalation.service import list_pending_escalations  # noqa: E402
from src.graph.build import build_graph  # noqa: E402

VALID_OUTCOMES = ("fit", "not_fit")


def _print_queue(pending) -> None:
    if not pending:
        print("No hay escalaciones pendientes.")
        return
    print(f"\n{len(pending)} escalacion(es) pendiente(s) de revision:")
    for i, esc in enumerate(pending, 1):
        print(f"  [{i}] escalacion={esc.id}")
        print(f"      caso={esc.case_id}  creada={esc.created_at}")
        print(f"      motivo: {esc.reason}")


def _ask(prompt: str, valid: tuple[str, ...] | None = None) -> str:
    while True:
        value = input(prompt).strip()
        if value and (valid is None or value in valid):
            return value
        print(f"  Entrada no valida. Valores aceptados: {', '.join(valid)}" if valid else "  Entrada vacia.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Cola de revision de la Human Escalation Layer.")
    parser.add_argument("--review", action="store_true", help="modo interactivo para resolver un caso")
    args = parser.parse_args()

    with SessionLocal() as session:
        pending = list_pending_escalations(session)
        _print_queue(pending)
        if not args.review or not pending:
            return

        index = int(_ask(f"\nElige el caso a resolver [1-{len(pending)}]: ",
                         tuple(str(n) for n in range(1, len(pending) + 1))))
        escalation = pending[index - 1]
        case_id = str(escalation.case_id)
        outcome = _ask(f"Decision para el caso {case_id} [{'/'.join(VALID_OUTCOMES)}]: ", VALID_OUTCOMES)
        reviewer = _ask("Tu identificador de revisor: ")

    decision = {"outcome": outcome, "reviewer": reviewer}
    with get_checkpointer() as checkpointer:
        graph = build_graph(checkpointer)
        config = {"configurable": {"thread_id": case_id}}
        try:
            result = graph.invoke(Command(resume=decision), config=config)
        except Exception as exc:
            print(f"\nNo se pudo reanudar el caso {case_id}: {exc}")
            print("Comprueba que el caso sigue pausado en human_escalation (thread_id = id del caso).")
            return

    print(f"\nCaso {case_id} reanudado. Resultado final: {result.get('outcome')}")


if __name__ == "__main__":
    main()
