"""Ejecucion de ejemplo, de principio a fin, del motor de decision DAG para un caso.

Uso (desde `dag_decision/`, con el venv activo y `.env` relleno, incluyendo
un `OPENAI_API_KEY` real y, opcionalmente, `LANGSMITH_API_KEY`):

    .venv\\Scripts\\python scripts\\run_case.py
    .venv\\Scripts\\python scripts\\run_case.py --case-file data\\case.json --job-profile-file data\\job_profile.json

Carga el caso desde un fichero JSON con la forma de `scripts/data/case.json`
(candidato + cola de nodos del DAG) y el perfil de puesto correspondiente
(`scripts/data/job_profile.json`, casado por `job_id`), crea una fila `Case`,
y ejecuta el grafo hasta que llega a una decision final o se pausa en la
Human Escalation Layer. Si se pausa, el script pregunta la decision por
consola (`fit`/`not_fit` + identificador de revisor) y reanuda el grafo con
ella; con `--auto fit|not_fit` se resuelve automaticamente en vez de
preguntar, util para ejecuciones no interactivas.

OJO: cada ejecucion sin `--resume-case-id` crea un `Case` (thread_id) nuevo,
asi que volver a lanzar el script NO continua un caso pausado en una
ejecucion anterior, crea uno distinto. Para reanudar un caso que se quedo
pausado en `human_escalation` en otra ejecucion, usa:

    .venv\\Scripts\\python scripts\\run_case.py --resume-case-id <case_id>

(o, alternativamente, `scripts/review_escalations.py --review`, que lista
toda la cola de casos pausados y deja elegir cual resolver).

Si `LANGSMITH_TRACING=true` esta activo, la ejecucion tambien aparece como
una traza en https://smith.langchain.com/ bajo el `LANGSMITH_PROJECT`.
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
VALID_OUTCOMES = ("fit", "not_fit")


def _ask(prompt: str, valid: tuple[str, ...] | None = None) -> str:
    """Pide un valor por consola, repitiendo hasta recibir uno valido/no vacio."""
    while True:
        value = input(prompt).strip()
        if value and (valid is None or value in valid):
            return value
        print(f"  Entrada no valida. Valores aceptados: {', '.join(valid)}" if valid else "  Entrada vacia.")


def _ask_human_decision() -> dict:
    outcome = _ask(f"Tu decision [{'/'.join(VALID_OUTCOMES)}]: ", VALID_OUTCOMES)
    reviewer = _ask("Tu identificador de revisor: ")
    return {"outcome": outcome, "reviewer": reviewer}


def _load_json(path: Path) -> dict:
    """Carga un fichero JSON con un mensaje de error mas util si falla.

    Usa `utf-8-sig` en vez de `utf-8` a proposito: en Windows es habitual
    guardar ficheros como "UTF-8 with BOM" (p.ej. desde el Bloc de notas o
    al copiar/pegar desde algunos editores), y ese BOM al inicio del fichero
    rompe el parseo de JSON con errores que no apuntan a la causa real
    (tipicamente "Expecting property name..." unas lineas mas abajo de
    donde esta el problema real). `utf-8-sig` lo descarta automaticamente si
    esta presente, y no afecta en nada si no lo esta.

    Si el JSON sigue sin ser valido, relanza el error con el trozo de texto
    exacto alrededor del caracter que fallo, para no tener que ir a ciegas.
    """
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except json.JSONDecodeError as exc:
        raw = path.read_text(encoding="utf-8-sig")
        start = max(exc.pos - 40, 0)
        end = min(exc.pos + 40, len(raw))
        snippet = raw[start:end]
        raise ValueError(
            f"{path} no es JSON valido: {exc.msg} "
            f"(linea {exc.lineno}, columna {exc.colno}, caracter {exc.pos}).\n"
            f"Contenido alrededor del error:\n...{snippet}..."
        ) from exc


def load_case_payload(case_file: Path, job_profile_file: Path) -> dict:
    """Carga `case.json` + `job_profile.json` y arma el `payload` del caso.

    `case.json` trae tambien `nodes` (la cola de nodos del DAG del
    prototipo), que no se usa aqui: `build.py` implementa el Modulo 1 (DAG
    Engine) como un pipeline fijo, no como una cola generica (ver la nota al
    inicio de `nodes.py`). Solo hacen falta `candidate` y el `job_profile`
    cargado aparte, que es lo que consumen `rule_evaluator_node` y
    `llm_decision_node`.
    """
    case = _load_json(case_file)
    job_profile = _load_json(job_profile_file)

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
    parser.add_argument(
        "--resume-case-id",
        type=str,
        default=None,
        help="en vez de crear un caso nuevo, reanuda uno ya pausado en human_escalation (ignora --case-file/--job-profile-file)",
    )
    parser.add_argument(
        "--auto",
        choices=VALID_OUTCOMES,
        default=None,
        help="si el caso escala a revision humana, resuelve automaticamente con esta decision (reviewer='auto') en vez de preguntar por consola",
    )
    args = parser.parse_args()

    if args.resume_case_id:
        case_id = args.resume_case_id
        with get_checkpointer() as checkpointer: # type: ignore
            graph = build_graph(checkpointer)
            config = {"configurable": {"thread_id": case_id}}
            human_decision = {"outcome": args.auto, "reviewer": "auto"} if args.auto else _ask_human_decision()
            try:
                result = graph.invoke(Command(resume=human_decision), config=config) # type: ignore
            except Exception as exc:
                print(f"No se pudo reanudar el caso {case_id}: {exc}")
                print("Comprueba que el caso sigue pausado en human_escalation (thread_id = id del caso).")
                return
            print("Final result:", result)
        return

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
            print(f"(para reanudarlo mas tarde: scripts\\run_case.py --resume-case-id {case_id})")

            human_decision = {"outcome": args.auto, "reviewer": "auto"} if args.auto else _ask_human_decision()
            result = graph.invoke(Command(resume=human_decision), config=config) # type: ignore

        print("Final result:", result)


if __name__ == "__main__":
    main()
