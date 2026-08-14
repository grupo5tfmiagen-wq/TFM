"""Ejecucion de ejemplo, de principio a fin, del motor de decision DAG para un caso.

Uso (desde `dag_decision/`, con el venv activo y `.env` relleno, incluyendo
un `OPENAI_API_KEY` real y, opcionalmente, `LANGSMITH_API_KEY`):

    .venv\\Scripts\\python scripts\\run_case.py
    .venv\\Scripts\\python scripts\\run_case.py --case-file data\\case.json --job-profile-file data\\job_profile.json

Carga el caso desde un fichero JSON con la forma de `scripts/data/case.json`
(candidato + cola de nodos del DAG) y el perfil de puesto correspondiente
(`scripts/data/job_profile.json`, casado por `job_id`), crea una fila `Case`,
ejecuta el grafo hasta que llega a una decision final o se pausa en la Human
Escalation Layer, y si se pausa, lo reanuda con una decision humana simulada
para poder ejercitar todo el flujo de principio a fin. Si
`LANGSMITH_TRACING=true` esta activo, la ejecucion tambien aparece como una
traza en https://smith.langchain.com/ bajo el `LANGSMITH_PROJECT`.
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from langgraph.types import Command  # noqa: E402

from src.db.base import SessionLocal  # noqa: E402
from src.db.checkpointer import get_checkpointer  # noqa: E402
from src.db.models.case import Case  # noqa: E402
from src.graph.build import build_graph  # noqa: E402

DEFAULT_DATA_DIR = Path(__file__).parent.parent / "data"


def load_case_payload(case_file: Path, job_profile_file: Path) -> dict:
    """Carga `case.json` + `job_profile.json` y arma el `payload` del caso.

    `case.json` trae tambien `nodes` (la cola de nodos del DAG del
    prototipo), que no se usa aqui: `build.py` implementa el Modulo 1 (DAG
    Engine) como un pipeline fijo, no como una cola generica (ver la nota al
    inicio de `nodes.py`). Solo hacen falta `candidate` y el `job_profile`
    cargado aparte, que es lo que consumen `rule_evaluator_node` y
    `llm_decision_node`.
    """
    with open(case_file, encoding="utf-8") as f:
        case = json.load(f)
    with open(job_profile_file, encoding="utf-8") as f:
        job_profile = json.load(f)

    if case["job_id"] != job_profile["job_id"]:
        raise ValueError(
            f"El caso referencia job_id={case['job_id']!r} pero el perfil "
            f"cargado es {job_profile['job_id']!r}"
        )

    return {
        "source_case_id": case.get("id"),
        "payload": {"candidate": case["candidate"], "job_profile": job_profile},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-file", type=Path, default=DEFAULT_DATA_DIR / "case.json")
    parser.add_argument("--job-profile-file", type=Path, default=DEFAULT_DATA_DIR / "job_profile.json")
    args = parser.parse_args()

    loaded = load_case_payload(args.case_file, args.job_profile_file)
    payload = loaded["payload"]

    with SessionLocal() as session:
        case = Case(case_type="candidate_selection", status="running", payload=payload)
        session.add(case)
        session.commit()
        case_id = str(case.id)

    print(f"Case created: {case_id} (source: {loaded['source_case_id']})")

    with get_checkpointer() as checkpointer: # type: ignore
        graph = build_graph(checkpointer)
        config = {"configurable": {"thread_id": case_id}}

        initial_state = {
            "case_id": case_id,
            "case_type": "candidate_selection",
            "payload": payload,
        }
        result = graph.invoke(initial_state, config=config) # type: ignore

        if "__interrupt__" in result:
            interrupt_payload = result["__interrupt__"][0].value
            print("Paused for human review:", interrupt_payload)

            simulated_human_decision = {"outcome": "fit", "reviewer": "demo_reviewer"}
            result = graph.invoke(Command(resume=simulated_human_decision), config=config) # type: ignore

        print("Final result:", result)


if __name__ == "__main__":
    main()
