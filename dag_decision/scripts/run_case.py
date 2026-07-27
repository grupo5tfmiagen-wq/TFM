"""Ejecucion de ejemplo, de principio a fin, del motor de decision DAG para un caso.

Uso (desde `dag_decision/`, con el venv activo y `.env` relleno, incluyendo
un `OPENAI_API_KEY` real y, opcionalmente, `LANGSMITH_API_KEY`):

    .venv\\Scripts\\python scripts\\run_case.py

Crea una fila `Case`, ejecuta el grafo hasta que llega a una decision final
o se pausa en la Human Escalation Layer, y si se pausa, lo reanuda con una
decision humana simulada para poder ejercitar todo el flujo de principio a
fin. Si `LANGSMITH_TRACING=true` esta activo, la ejecucion tambien aparece
como una traza en https://smith.langchain.com/ bajo el `LANGSMITH_PROJECT`.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from langgraph.types import Command  # noqa: E402

from src.db.base import SessionLocal  # noqa: E402
from src.db.checkpointer import get_checkpointer  # noqa: E402
from src.db.models.case import Case  # noqa: E402
from src.graph.build import build_graph  # noqa: E402

EXAMPLE_PAYLOAD = {
    "years_experience": 3,
    "has_cv": True,
    "has_id_document": True,
    "profile_summary": "Ingeniero de software con experiencia en backend y datos.",
}


def main() -> None:
    with SessionLocal() as session:
        case = Case(case_type="candidate_selection", status="running", payload=EXAMPLE_PAYLOAD)
        session.add(case)
        session.commit()
        case_id = str(case.id)

    print(f"Case created: {case_id}")

    with get_checkpointer() as checkpointer:
        graph = build_graph(checkpointer)
        config = {"configurable": {"thread_id": case_id}}

        initial_state = {
            "case_id": case_id,
            "case_type": "candidate_selection",
            "payload": EXAMPLE_PAYLOAD,
        }
        result = graph.invoke(initial_state, config=config)

        if "__interrupt__" in result:
            interrupt_payload = result["__interrupt__"][0].value
            print("Paused for human review:", interrupt_payload)

            simulated_human_decision = {"outcome": "fit", "reviewer": "demo_reviewer"}
            result = graph.invoke(Command(resume=simulated_human_decision), config=config)

        print("Final result:", result)


if __name__ == "__main__":
    main()
