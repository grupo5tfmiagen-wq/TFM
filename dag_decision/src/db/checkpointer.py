"""Configuración del checkpointer de Postgres para LangGraph.

Persiste el propio estado de ejecución del motor DAG (instantáneas por caso)
para poder pausar y reanudar el grafo más adelante, por ejemplo mientras se
espera la Human Escalation Layer. Usa la misma base de datos Postgres que el
esquema de negocio, pero sus tablas (checkpoints, checkpoint_writes,
checkpoint_blobs, checkpoint_migrations) las crea y gestiona el propio
LangGraph mediante `setup()` y no deben modificarse manualmente.
"""
import os

from dotenv import load_dotenv
from langgraph.checkpoint.postgres import PostgresSaver

load_dotenv()

CHECKPOINTER_DATABASE_URL = os.environ["CHECKPOINTER_DATABASE_URL"]


def get_checkpointer() -> PostgresSaver:
    """Devuelve un PostgresSaver conectado a la base de datos Postgres compartida."""
    return PostgresSaver.from_conn_string(CHECKPOINTER_DATABASE_URL)


def setup_checkpointer() -> None:
    """Crea las tablas de checkpoint de LangGraph si todavía no existen.

    Se puede llamar varias veces sin problema (idempotente).
    """
    with get_checkpointer() as checkpointer:
        checkpointer.setup()


if __name__ == "__main__":
    setup_checkpointer()
    print("LangGraph checkpoint tables are ready.")
