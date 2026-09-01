# Motor DAG (LangGraph) y trazabilidad con LangSmith

Este documento describe cómo arrancar y extender la capa de grafo
(`src/graph/`), construida sobre lo ya montado en `src/db/` (Postgres +
Alembic + checkpointer de LangGraph).

## Piezas

- `src/graph/state.py` — `CaseState`: estado compartido del grafo (contrapartida
  ligera del "Estado del Caso"). Se persiste automáticamente vía el
  checkpointer de Postgres en cada paso (permite pausar/reanudar por caso).
- `src/graph/tracing.py` — `traced_node(...)`: helper de contexto que abre una
  fila en `case_node_executions` al entrar a un nodo y la cierra
  (`completed`/`failed`) al salir. Es la trazabilidad de negocio, complementaria
  a los checkpoints técnicos de LangGraph.
- `src/graph/nodes.py` — un nodo por módulo de la arquitectura:
  `rule_evaluator_node` (Módulo 2), `llm_decision_node` (Módulo 3),
  `validation_node` (Módulo 4), `human_escalation_node` (Módulo 5),
  `final_decision_node` (Módulo 6). Caso de ejemplo: selección de candidatos.
- `src/graph/build.py` — `build_graph(checkpointer)`: define el DAG (Módulo 1,
  DAG Engine) y el enrutado condicional entre nodos.
- `scripts/run_case.py` — ejecución de ejemplo: crea un `Case`, invoca el
  grafo, y si se pausa en Human Escalation, pide una decisión humana para
  reanudarlo (`Command(resume=...)`).

## Cómo se relacionan LangGraph y la BD de negocio

Dos capas de persistencia complementarias, ya documentadas en
`docs/database.md`:

1. **Checkpoints de LangGraph** (`checkpoints`, `checkpoint_writes`, ...):
   estado técnico interno para poder reanudar un caso pausado
   (`thread_id` = id del caso). Gestionados por LangGraph, no tocar a mano.
2. **Esquema de negocio** (`cases`, `case_node_executions`,
   `rule_evaluations`, `llm_decisions`, `validations`, `human_escalations`,
   `final_decisions`): trazabilidad legible para auditoría/KPIs, escrita por
   cada nodo mediante `traced_node(...)`.

## Puesta en marcha

1. Instala las dependencias nuevas (ya añadidas a `requirements.txt`):

   ```
   pip install -r requirements.txt
   ```

2. Rellena en `.env`:
   - `OPENAI_API_KEY` (real) y opcionalmente `OPENAI_MODEL`.
   - `LANGSMITH_API_KEY` (crear una en https://smith.langchain.com/) y
     `LANGSMITH_PROJECT` si quieres trazas en LangSmith. Con
     `LANGSMITH_TRACING=true` puesto, todas las llamadas LLM (vía
     `langchain-openai`) y los nodos decorados con `@traceable` se envían
     automáticamente a LangSmith; no hace falta código adicional.

3. Ejecuta un caso CLI con ficheros compatibles:

   ```
  python scripts/run_case.py --case-file data/case_review.json --job-profile-file data/job_profile.json
   ```

   Debería crear un `Case`, ejecutar `rule_evaluator` → `llm_decision` →
   `validation`, y si la confianza del LLM es baja, pausarse en
  `human_escalation` y pedir una decisión por consola, hasta llegar a
  `final_decision`. Usa `--auto fit` o `--auto not_fit` para una ejecución
  no interactiva.

4. Revisa la traza en LangSmith (si está configurado) y las filas creadas en
   Postgres (`cases`, `case_node_executions`, `rule_evaluations`,
   `llm_decisions`, `validations`, `human_escalations`, `final_decisions`).

## Extender el DAG

- Nuevos nodos: añade una función en `nodes.py` (usa `traced_node` si quieres
  fila de auditoría) y regístrala + enruta en `build.py`.
- Nuevas reglas: añade lógica dentro de `rule_evaluator_node` o crea nodos de
  reglas adicionales; cada regla evaluada debería generar una fila
  `RuleEvaluation`.
- Otro proveedor LLM: cambia `_llm()` en `nodes.py` por el chat model de
  `langchain-anthropic`/`langchain-azure-openai`/etc.; el resto del nodo
  (validación, persistencia, LangSmith) no cambia.

## Notas

- `human_escalation_node` no está decorado con `@traceable`: `interrupt()`
  pausa el nodo lanzando `GraphInterrupt`, y LangGraph re-ejecuta la función
  completa al reanudar. Envolverlo con `@traceable` haría que cada pausa
  apareciera como un run fallido en LangSmith.
- El acceso a BD en `human_escalation_node` se divide en dos sesiones cortas
  (antes y después de `interrupt()`) para no mantener una conexión abierta
  mientras el caso está pausado, potencialmente horas o días.
- `CONFIDENCE_THRESHOLD` se lee de `.env` (por defecto `0.8`). Para forzar
  temporalmente el paso por revisión humana en una demo, usa `0.99` y reinicia
  el proceso que ejecuta el grafo.
