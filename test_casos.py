"""
Ejecuta los tres casos de ejemplo (data/caso*.json) contra el mismo perfil de
puesto (data/perfil_puesto.json) y resume el resultado de cada uno.

Uso: python test_casos.py
"""

from __future__ import annotations

import json
from pathlib import Path

from DAGEngine import graph, DecisionState

DATA_DIR = Path(__file__).parent / "data"

CASOS = [
    "caso.json",           # cumple obligatorios y deseables -> aprobación automática
    "caso_revision.json",  # cumple obligatorios, poca afinidad con deseables -> revisión humana
    "caso_no_valido.json", # no cumple un requisito obligatorio -> descartado, sin score
    "cv_ejemplo.json",      # caso de ejemplo generado desde un CV en PDF con cv_to_json.py
]


def ejecutar_caso(nombre_fichero: str, perfil_puesto: dict) -> None:
    with open(DATA_DIR / nombre_fichero, encoding="utf-8") as f:
        caso = json.load(f)

    estado_inicial: DecisionState = {
        "caso": caso,
        "perfil_puesto": perfil_puesto,
        "nodos_pendientes": [],
        "nodo_actual": None,
        "resultado_actual": None,
        "estado_validacion": None,
        "revision_humana": None,
        "decision_final": None,
        "auditoria": [],
    }

    resultado = graph.invoke(estado_inicial)

    print(f"\n=== {nombre_fichero} (caso_id={caso['id']}) ===")
    if resultado["decision_final"] is not None:
        print("Decisión final:", resultado["decision_final"])
    else:
        # Caso descartado por no cumplir obligatorios: el diagrama envía
        # 'Resultado No válido' directo a 'Guardar auditoría y métricas',
        # sin pasar por 'Decisión final'. El estado de validación queda
        # igualmente registrado en la traza de auditoría.
        print("Decisión final: (no se generó — caso descartado en la validación)")
    print("Estado de validación:", resultado["estado_validacion"])


if __name__ == "__main__":
    with open(DATA_DIR / "perfil_puesto.json", encoding="utf-8") as f:
        perfil_puesto = json.load(f)

    for nombre in CASOS:
        ejecutar_caso(nombre, perfil_puesto)
