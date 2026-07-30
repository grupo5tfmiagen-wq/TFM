"""
Motor de decisión híbrido (DAG + Reglas + LLM) implementado en LangGraph.

Este grafo reproduce el árbol de decisión del diagrama:

    Inicio
      -> Carga del caso
      -> DAG Engine selecciona nodo  <---------------------------+
      -> ¿Qué tipo de nodo es?  (rhombus)                          |
           -> Rule Node -----------+                                |
           -> LLM Node ------------+--> Validation layer (rhombus) |
           -> Transformación ------+          |                    |
                                               |-> Resultado Válido -----> ¿Quedan nodos? --(SI)--
                                               |-> Resultado No válido --> Guardar auditoría y métricas
                                               |-> Requiere revisión ---> Human Escalation -> ¿Quedan nodos?
                                                                                  |
                                                                                (NO)
                                                                                  v
                                                                          Decisión final -> Guardar auditoría y métricas -> FIN

Caso de uso de referencia (TFM): scoring/selección de candidatos.
"""

from __future__ import annotations

import os
from typing import Literal, TypedDict, Annotated
from operator import add

from dotenv import load_dotenv
from langgraph.graph import StateGraph, START, END
from langchain_core.tracers.langchain import wait_for_all_tracers

# Carga las variables definidas en .env (ver .env.example) en os.environ.
load_dotenv()


# ---------------------------------------------------------------------------
# 1. Definición del estado compartido del grafo
# ---------------------------------------------------------------------------

class NodeSpec(TypedDict):
    """Especificación de un nodo pendiente de ejecutar dentro del DAG del caso."""
    id: str
    tipo: Literal["rule", "llm", "transformacion"]
    payload: dict


class DecisionState(TypedDict):
    caso: dict                        # Datos de entrada del caso (candidato + CV + nodos)
    perfil_puesto: dict                # Perfil del puesto contra el que se evalúa el caso
    nodos_pendientes: list[NodeSpec]  # Cola de nodos que el DAG Engine debe ejecutar
    nodo_actual: NodeSpec | None       # Nodo seleccionado en la iteración actual
    resultado_actual: dict | None      # Resultado producido por rule/llm/transformación
    estado_validacion: Literal["valido", "no_valido", "requiere_revision"] | None
    revision_humana: dict | None       # Resultado de la escalada humana, si aplica
    decision_final: dict | None
    auditoria: Annotated[list[dict], add]  # Traza completa (append-only) para trazabilidad


# ---------------------------------------------------------------------------
# 2. Nodos del grafo
# ---------------------------------------------------------------------------

def carga_del_caso(state: DecisionState) -> dict:
    """Nodo 'Carga del caso': normaliza la entrada y prepara la cola de nodos del DAG."""
    caso = state["caso"]
    # En un caso real, aquí se construiría la cola de nodos a partir de la
    # definición del DAG asociada a este tipo de caso (ej. YAML/JSON de reglas).
    nodos_pendientes = caso.get("nodos", [])
    return {
        "nodos_pendientes": nodos_pendientes,
        "auditoria": [{"evento": "carga_del_caso", "caso_id": caso.get("id")}],
    }


def dag_engine_selecciona_nodo(state: DecisionState) -> dict:
    """Nodo 'DAG Engine selecciona nodo': saca el siguiente nodo de la cola."""
    pendientes = list(state["nodos_pendientes"])
    nodo_actual = pendientes.pop(0)
    return {
        "nodos_pendientes": pendientes,
        "nodo_actual": nodo_actual,
        "auditoria": [{"evento": "nodo_seleccionado", "nodo_id": nodo_actual["id"], "tipo": nodo_actual["tipo"]}],
    }


def que_tipo_nodo_es(state: DecisionState) -> Literal["rule_node", "llm_node", "transformacion"]:
    """Arista condicional 'Qué tipo nodo es' (rhombus): enruta según el tipo de nodo."""
    tipo = state["nodo_actual"]["tipo"]
    return {"rule": "rule_node", "llm": "llm_node", "transformacion": "transformacion"}[tipo]


def rule_node(state: DecisionState) -> dict:
    """Se encarga de ejecutar reglas dependiendo de los estados (ej. reglas YAML/Pydantic).

    Aquí: filtro de requisitos obligatorios (n1) — compara las habilidades
    técnicas del CV contra 'requisitos_obligatorios.habilidades_tecnicas'
    del perfil de puesto. En producción esto lo resolvería el Rule
    Evaluator real (reglas YAML/JSON + Pydantic), no una comparación ad-hoc.
    """
    nodo = state["nodo_actual"]
    cv = state["caso"]["candidato"]["cv"]
    requisitos = state["perfil_puesto"]["requisitos_obligatorios"]

    habilidades_cv = set(cv.get("habilidades_tecnicas", []))
    habilidades_requeridas = set(requisitos.get("habilidades_tecnicas", []))
    faltantes = habilidades_requeridas - habilidades_cv

    resultado = {
        "tipo": "rule",
        "nodo_id": nodo["id"],
        "cumple_obligatorios": not faltantes,
        "habilidades_faltantes": sorted(faltantes),
    }
    return {
        "resultado_actual": resultado,
        "auditoria": [{"evento": "rule_node_ejecutado", "nodo_id": nodo["id"], "cumple": resultado["cumple_obligatorios"]}],
    }


def llm_node(state: DecisionState) -> dict:
    """Procesamiento por LLM (ej. análisis del CV con Claude/OpenAI + instructor).

    Aquí: evaluación de la experiencia relevante (n2) frente a los
    'requisitos_deseables' del perfil, usando el texto libre del CV.
    """
    nodo = state["nodo_actual"]
    # TODO: sustituir por la llamada real al LLM Decision Node, usando
    # ANTHROPIC_API_KEY / OPENAI_API_KEY (cargadas desde .env) para el cliente,
    # pasándole cv["texto_extraido"] y perfil_puesto["requisitos_deseables"].
    _ = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY")

    cv = state["caso"]["candidato"]["cv"]
    deseables = state["perfil_puesto"]["requisitos_deseables"]

    habilidades_cv = set(cv.get("habilidades_tecnicas", []))
    habilidades_deseables = set(deseables.get("habilidades_tecnicas", []))
    coincidentes = habilidades_cv & habilidades_deseables

    if habilidades_deseables:
        proporcion = len(coincidentes) / len(habilidades_deseables)
    else:
        proporcion = 0.5  # sin deseables definidos: afinidad neutra
    # Simplificación de placeholder: en el LLM Decision Node real esto sería
    # un juicio cualitativo del modelo sobre el texto del CV, no un cociente.
    afinidad_deseables = round(0.3 + 0.7 * proporcion, 2)

    resultado = {
        "tipo": "llm",
        "nodo_id": nodo["id"],
        "afinidad_deseables": afinidad_deseables,
        "habilidades_deseables_coincidentes": sorted(coincidentes),
    }
    return {
        "resultado_actual": resultado,
        "auditoria": [{"evento": "llm_node_ejecutado", "nodo_id": nodo["id"], "afinidad": afinidad_deseables}],
    }


def transformacion(state: DecisionState) -> dict:
    """Modifica el estado en función de las entradas recibidas (nodo de transformación).

    Aquí: calcula el score ponderado (n3) combinando el resultado del rule_node
    (n1) y del llm_node (n2) según los pesos de 'criterios_puntuacion' del perfil.
    """
    nodo = state["nodo_actual"]
    criterios = state["perfil_puesto"]["criterios_puntuacion"]

    # 'resultado_actual' en este punto es la salida del llm_node (n2), que es
    # el nodo inmediatamente anterior. Si n1 (rule_node) no hubiera cumplido
    # los obligatorios, validation_layer ya habría cortado a 'no_valido' y
    # nunca se habría llegado hasta aquí — por eso el componente de
    # habilidades obligatorias se puede dar por cumplido (1.0).
    #
    # Simplificación de ejemplo: en un DAG con más nodos, n3 leería los
    # resultados concretos de n1/n2 (declarados en payload["entradas"]) desde
    # una tabla de resultados intermedios por nodo, no solo el último
    # "resultado_actual".
    afinidad_deseables = state["resultado_actual"].get("afinidad_deseables", 0.5)
    score = (
        criterios["peso_habilidades_tecnicas"] * 1.0       # cumple_obligatorios del rule_node
        + criterios["peso_experiencia"] * afinidad_deseables  # afinidad_deseables del llm_node
        + criterios["peso_formacion"] * 1.0
        + criterios["peso_competencias_blandas"] * 0.7      # TODO: evaluar competencias blandas reales
    )

    resultado = {"tipo": "transformacion", "nodo_id": nodo["id"], "score_ponderado": round(score, 2)}
    return {
        "resultado_actual": resultado,
        "auditoria": [{"evento": "transformacion_ejecutada", "nodo_id": nodo["id"], "score": resultado["score_ponderado"]}],
    }


def validation_layer(state: DecisionState) -> dict:
    """Confidence & Validation Layer: evalúa el resultado del nodo recién ejecutado.

    Compara 'score_ponderado' (cuando el nodo es una transformación) contra
    los umbrales del perfil de puesto para decidir la rama de salida.
    """
    resultado = state["resultado_actual"]
    criterios = state["perfil_puesto"]["criterios_puntuacion"]

    if resultado["tipo"] == "rule":
        # Si no cumple los requisitos obligatorios, el caso se cierra aquí
        # mismo como 'no_valido' (la rama 'Resultado No válido' del diagrama
        # va directa a 'Guardar auditoría y métricas', sin pasar por
        # ¿Quedan nodos? ni por Decisión final) — no tiene sentido seguir
        # evaluando n2/n3 si el candidato ya está descartado.
        if resultado["cumple_obligatorios"]:
            estado_validacion: Literal["valido", "no_valido", "requiere_revision"] = "valido"
        else:
            estado_validacion = "no_valido"
    elif "score_ponderado" in resultado:
        score = resultado["score_ponderado"]
        if score >= criterios["umbral_aprobacion_automatica"]:
            estado_validacion = "valido"
        elif score >= criterios["umbral_revision_humana"]:
            estado_validacion = "requiere_revision"
        else:
            estado_validacion = "no_valido"
    else:
        # Otros resultados intermedios (ej. llm_node) se consideran válidos
        # por defecto para poder seguir avanzando por el DAG; solo el rule_node
        # (obligatorios) y la transformación final (score) deciden la ruta.
        estado_validacion = "valido"

    return {
        "estado_validacion": estado_validacion,
        "auditoria": [{"evento": "validacion", "resultado": estado_validacion}],
    }


def enruta_validacion(state: DecisionState) -> Literal["resultado_valido", "resultado_no_valido", "requiere_revision"]:
    """Arista condicional 'Validation layer' (rhombus): 3 salidas posibles."""
    return {
        "valido": "resultado_valido",
        "no_valido": "resultado_no_valido",
        "requiere_revision": "requiere_revision",
    }[state["estado_validacion"]]


def resultado_valido(state: DecisionState) -> dict:
    """Nodo terminal de la rama 'Resultado Válido' -> continúa hacia ¿Quedan nodos?."""
    return {"auditoria": [{"evento": "resultado_valido"}]}


def resultado_no_valido(state: DecisionState) -> dict:
    """Nodo terminal de la rama 'Resultado No válido' -> va directo a guardar auditoría."""
    return {"auditoria": [{"evento": "resultado_no_valido"}]}


def requiere_revision(state: DecisionState) -> dict:
    """Nodo intermedio 'Requiere revisión' -> deriva a Human Escalation."""
    return {"auditoria": [{"evento": "requiere_revision"}]}


def human_escalation(state: DecisionState) -> dict:
    """Human Escalation Layer: escala el caso a un humano (ej. cola en Postgres + Streamlit)."""
    # TODO: sustituir por la integración real con la cola de revisión humana,
    # usando POSTGRES_HOST/PORT/DB/USER/PASSWORD (cargadas desde .env) para
    # insertar el caso en la tabla de revisiones pendientes que consume Streamlit.
    revision = {"nodo_id": state["nodo_actual"]["id"], "resolucion": "aprobado_manualmente"}
    return {
        "revision_humana": revision,
        "auditoria": [{"evento": "human_escalation", "resolucion": revision["resolucion"]}],
    }


def quedan_nodos(state: DecisionState) -> Literal["si", "no"]:
    """Arista condicional '¿Quedan nodos?' (decision): SI vuelve a seleccionar nodo, NO cierra el ciclo."""
    return "si" if state["nodos_pendientes"] else "no"


def decision_final(state: DecisionState) -> dict:
    """Nodo 'Decisión final': consolida los resultados acumulados en la decisión de salida.

    Usa el resultado y la validación del último nodo procesado (en este
    ejemplo, la transformación que calcula 'score_ponderado'). En un DAG con
    más nodos tras la transformación, aquí se recorrería 'auditoria' para
    localizar el evento 'transformacion_ejecutada' en vez de fiarse del
    último 'resultado_actual'.
    """
    resultado = state["resultado_actual"]
    decision = {
        "caso_id": state["caso"].get("id"),
        "puesto_id": state["perfil_puesto"].get("puesto_id"),
        "score_ponderado": resultado.get("score_ponderado"),
        "estado_validacion": state["estado_validacion"],
        "requirio_revision_humana": state["revision_humana"] is not None,
    }
    return {
        "decision_final": decision,
        "auditoria": [{"evento": "decision_final", "decision": decision}],
    }


def guardar_auditoria_y_metricas(state: DecisionState) -> dict:
    """Nodo terminal (terminator): persiste la traza de auditoría y las métricas (ej. Postgres + LangSmith)."""
    # TODO: sustituir por la persistencia real en Postgres. El trazado en
    # LangSmith ya se activa solo con LANGCHAIN_TRACING_V2/LANGCHAIN_API_KEY
    # (cargadas desde .env) sin necesidad de código adicional aquí.
    return {"auditoria": [{"evento": "auditoria_guardada"}]}


# ---------------------------------------------------------------------------
# 3. Construcción del grafo
# ---------------------------------------------------------------------------

def build_graph() -> StateGraph:
    g = StateGraph(DecisionState)

    g.add_node("carga_del_caso", carga_del_caso)
    g.add_node("dag_engine_selecciona_nodo", dag_engine_selecciona_nodo)
    g.add_node("rule_node", rule_node)
    g.add_node("llm_node", llm_node)
    g.add_node("transformacion", transformacion)
    g.add_node("validation_layer", validation_layer)
    g.add_node("resultado_valido", resultado_valido)
    g.add_node("resultado_no_valido", resultado_no_valido)
    g.add_node("requiere_revision", requiere_revision)
    g.add_node("human_escalation", human_escalation)
    g.add_node("decision_final", decision_final)
    g.add_node("guardar_auditoria_y_metricas", guardar_auditoria_y_metricas)

    g.add_edge(START, "carga_del_caso")
    g.add_edge("carga_del_caso", "dag_engine_selecciona_nodo")

    # "Que tipo nodo es" (rhombus)
    g.add_conditional_edges(
        "dag_engine_selecciona_nodo",
        que_tipo_nodo_es,
        {
            "rule_node": "rule_node",
            "llm_node": "llm_node",
            "transformacion": "transformacion",
        },
    )

    g.add_edge("rule_node", "validation_layer")
    g.add_edge("llm_node", "validation_layer")
    g.add_edge("transformacion", "validation_layer")

    # "Validation layer" (rhombus, 3 salidas)
    g.add_conditional_edges(
        "validation_layer",
        enruta_validacion,
        {
            "resultado_valido": "resultado_valido",
            "resultado_no_valido": "resultado_no_valido",
            "requiere_revision": "requiere_revision",
        },
    )

    g.add_edge("resultado_no_valido", "guardar_auditoria_y_metricas")
    g.add_edge("requiere_revision", "human_escalation")

    # "Quedan nodos?" (decision) — dos puntos de entrada: resultado_valido y human_escalation
    g.add_conditional_edges(
        "resultado_valido",
        quedan_nodos,
        {"si": "dag_engine_selecciona_nodo", "no": "decision_final"},
    )
    g.add_conditional_edges(
        "human_escalation",
        quedan_nodos,
        {"si": "dag_engine_selecciona_nodo", "no": "decision_final"},
    )

    g.add_edge("decision_final", "guardar_auditoria_y_metricas")
    g.add_edge("guardar_auditoria_y_metricas", END)

    return g


graph = build_graph().compile()


# ---------------------------------------------------------------------------
# 4. Ejemplo de ejecución
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json
    from pathlib import Path

    data_dir = Path(__file__).parent / "data"

    with open(data_dir / "caso.json", encoding="utf-8") as f:
        caso = json.load(f)

    with open(data_dir / "perfil_puesto.json", encoding="utf-8") as f:
        perfil_puesto = json.load(f)

    if caso["puesto_id"] != perfil_puesto["puesto_id"]:
        raise ValueError(
            f"El caso referencia puesto_id={caso['puesto_id']!r} pero el "
            f"perfil cargado es {perfil_puesto['puesto_id']!r}"
        )

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

    try:
        resultado = graph.invoke(estado_inicial)

        print("Decisión final:", resultado["decision_final"])
        print("\nTraza de auditoría:")
        for evento in resultado["auditoria"]:
            print(" -", evento)
    finally:
        # Forzar el vaciado de las trazas de LangSmith antes de que el
        # proceso termine. LANGCHAIN_TRACING_V2/LANGCHAIN_API_KEY (cargadas
        # desde .env) ya activan el tracing automático, que usa un cliente
        # singleton interno; wait_for_all_tracers() reutiliza ESE cliente y
        # espera a que vacíe sus runs pendientes. NO instanciar aquí un
        # Client() nuevo: crearlo justo antes de morir el intérprete abre
        # hilos de fondo propios que compiten con el shutdown (falla en
        # Windows con "can't create new thread at interpreter shutdown").
        # En un servicio de larga duración, llama a esto en el shutdown
        # handler (ej. el lifespan de FastAPI), no en cada request.
        wait_for_all_tracers()
