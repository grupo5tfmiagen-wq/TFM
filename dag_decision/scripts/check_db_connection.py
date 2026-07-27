"""Prueba de humo: verifica la conectividad con Postgres y lista las tablas existentes."""
import os
import sys

from sqlalchemy import inspect, text

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.db import models  # noqa: E402,F401  (asegura que los modelos estén registrados)
from src.db.base import engine  # noqa: E402


def main() -> None:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    print("Connection OK.")

    inspector = inspect(engine)
    tables = sorted(inspector.get_table_names())
    print(f"Tables found ({len(tables)}):")
    for table in tables:
        print(f"  - {table}")


if __name__ == "__main__":
    main()
