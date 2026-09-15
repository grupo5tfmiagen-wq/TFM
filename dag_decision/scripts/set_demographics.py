"""Script de una sola vez para rellenar `sexo`/`anio_nacimiento` en los CVs
de demo ya cargados — solo para la auditoria de sesgos en Metricas (ver el
comentario junto a esas columnas en `src/db/models/cv_document.py`; nunca
se envian al grafo de decision).

Uso (desde `dag_decision/`, con el venv activo):

    .venv\\Scripts\\python scripts\\set_demographics.py

Antes de ejecutar, edita el diccionario `DEMOGRAPHICS` de abajo con los
valores reales para tus CVs de demo. Primero te lista lo que hay en BD (con
sus `candidate_id`) y te pide confirmacion antes de tocar nada; los
candidatos que no aparezcan en el diccionario se dejan tal cual.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.db.base import SessionLocal  # noqa: E402
from src.db.models.cv_document import CVDocument  # noqa: E402

# candidate_id -> (sexo, anio_nacimiento). Ajusta con tus valores reales.
DEMOGRAPHICS: dict[str, tuple[str, int]] = {
    "demo-ana-morales": ("F", 1990),
    "cand-465a76dc": ("M", 1982),
    "demo-diego-navarro": ("M", 1987),
    "demo-elena-vargas": ("F", 1995),
    "demo-lucas-romero": ("M", 1992),
    "demo-marta-suarez": ("F", 1991),
    "cand-8beb94b2": ("F", 1991),
}


def main() -> None:
    with SessionLocal() as session:
        cvs = session.query(CVDocument).order_by(CVDocument.candidate_name).all()

        print(f"{len(cvs)} CVs en la base de datos:\n")
        for cv in cvs:
            marker = " <- se actualizara" if cv.candidate_id in DEMOGRAPHICS else ""
            print(
                f"  {cv.candidate_id:20s} {cv.candidate_name:30s} "
                f"sexo={cv.sexo!r:8} anio_nacimiento={cv.anio_nacimiento}{marker}"
            )

        desconocidos = set(DEMOGRAPHICS) - {cv.candidate_id for cv in cvs}
        if desconocidos:
            print(f"\nAviso: estos candidate_id de DEMOGRAPHICS no existen en BD: {sorted(desconocidos)}")

        confirm = input("\n¿Aplicar los cambios marcados arriba? [s/N] ")
        if confirm.strip().lower() != "s":
            print("Cancelado, no se ha tocado nada.")
            return

        updated = 0
        for cv in cvs:
            if cv.candidate_id in DEMOGRAPHICS:
                sexo, anio_nacimiento = DEMOGRAPHICS[cv.candidate_id]
                cv.sexo = sexo
                cv.anio_nacimiento = anio_nacimiento
                updated += 1
        session.commit()
        print(f"\n{updated} CV(s) actualizados.")


if __name__ == "__main__":
    main()
