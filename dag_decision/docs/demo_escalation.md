# Demo end-to-end: Human Escalation Layer (muestra del TFM)

Este documento guía paso a paso la demostración en vivo del motor de decisión
DAG con escalación humana, usando datos realistas: el CV de **Marta Suárez
Delgado** (`script_pdf_json/cv_ejemplo.json`) y la oferta **"Backend Senior —
Python y Sistemas Distribuidos"** (`scripts/load_job_posting.py`).

La demo recorre los 6 módulos de la arquitectura y muestra las dos capas de
persistencia: los checkpoints de LangGraph (pausa/reanudación) y el esquema de
negocio (trazabilidad auditable en Postgres).
---

## 0. Requisitos previos

| Requisito | Comprobación |
| Docker Desktop arrancado | `docker ps` responde sin error |
| Postgres del proyecto levantado | `docker compose up -d` (contenedor `dag_decision_postgres`, puerto **5433**) |
| Migraciones aplicadas | `python -m alembic upgrade head` (ya hecho si usaste `setup.ps1`) |
| Tablas de checkpoint de LangGraph | `python src/db/checkpointer.py` (idempotente) |
| `.env` relleno | `OPENAI_API_KEY` real; opcionalmente `LANGSMITH_API_KEY` + `LANGSMITH_TRACING=true` |

Comprobación rápida (desde `dag_decision/`):

```powershell
docker compose up -d
.venv\Scripts\python scripts\check_db_connection.py
```

Debe listar las 13 tablas (8 de negocio + 4 de checkpoint + `alembic_version`).

---

## 1. Qué va a pasar (mapa del flujo)

```
rule_evaluator ──(pasa reglas)──> llm_decision ──> validation ──(requiere revisión)──> human_escalation
      │                                                                                     │
      └──(no pasa)──> final_decision                                              (interrupt: pausa)
                                                                                          │
                                              revisor humano decide (fit / not_fit) ──────┘
                                                                                          │
                                                              final_decision <────────────┘
```

En la demo, el LLM evalúa a Marta frente a la oferta. Según la confianza que
devuelva, el caso puede:

- **Escalar a humano** (confianza < 0.7 o `fit_label = unclear`): el grafo se
  **pausa** en `human_escalation` y tú actúas como revisor.
- **No escalar** (confianza alta y etiqueta clara): el grafo llega solo a
  `final_decision`. Si quieres forzar la escalación para la muestra, edita
  temporalmente `CONFIDENCE_THRESHOLD` en `src/graph/nodes.py` (p. ej. a `0.99`).

---

## 2. Ejecutar la demo

Desde `dag_decision/`, con el venv activo:

```powershell
.venv\Scripts\python scripts\demo_escalation.py
```

Para ensayar sin interactuar (decisión automática):

```powershell
.venv\Scripts\python scripts\demo_escalation.py --auto fit
```

---

## 3. Paso a paso de lo que verás

### Paso 1 — Datos de entrada: oferta + CV

El script carga (o reutiliza si ya existen) la oferta y el CV en la BD, y crea
el `Case` enlazado a ambos (`cv_document_id`, `job_posting_id`).

```
======================================================================
  1. DATOS DE ENTRADA: oferta + CV
======================================================================
Oferta reutilizada: Backend Senior - Python y Sistemas Distribuidos (id=...)
CV reutilizado: Marta Suárez Delgado (id=...)

Caso creado: 3f8a...-...-...-...-............
  Candidata: Marta Suárez Delgado (6 anios de experiencia)
  Oferta:    Backend Senior - Python y Sistemas Distribuidos
```

**Qué mirar en la BD:** fila nueva en `cases` (status `running`), con
`payload` JSONB que combina el CV y los requisitos de la oferta.

### Paso 2 — Ejecución del grafo: reglas → LLM → validación

El grafo ejecuta tres nodos, cada uno dejando su rastro:

- **`rule_evaluator`** (Módulo 2): comprueba requisitos obligatorios
  (≥2 años de experiencia, CV y documento de identidad). Marta los cumple.
  Escribe en `rule_evaluations` y `case_node_executions`.
- **`llm_decision`** (Módulo 3): `gpt-4o-mini` evalúa el encaje con salida
  estructurada (`fit_label`, `confidence`, `justification`). Escribe en
  `llm_decisions`.
- **`validation`** (Módulo 4): aplica el umbral de confianza (0.7) y marca
  `requires_review` si procede. Escribe en `validations`.

### Paso 3 — Pausa en la Human Escalation Layer

Si la validación marca revisión, el grafo se **pausa** (`interrupt()` de
LangGraph). El estado del caso queda guardado en las tablas de checkpoint
(`thread_id` = id del caso) y la escalación queda registrada:

```
======================================================================
  3. PAUSA EN LA HUMAN ESCALATION LAYER
======================================================================
Pregunta al revisor: Revisa el caso y decide el resultado ('fit' o 'not_fit').
Escalacion id: ...
Decision del LLM: fit=unclear confianza=0.55
Justificacion del LLM: ...

Cola de revision pendiente: 1 caso(s)
```

**Qué mirar en la BD:**
- `human_escalations`: fila `pending` con el motivo y enlace a
  `case_node_executions` (que queda en estado `waiting`).
- `cases.status` = `waiting_human`.

### Paso 4 — Decisión del revisor humano

El script te pide tu decisión y tu identificador:

```
======================================================================
  4. DECISION DEL REVISOR HUMANO
======================================================================
Tu decision [fit/not_fit]: fit
Tu identificador de revisor: julian
```

Al introducirla, el script reanuda el grafo con `Command(resume=...)`:
`human_escalation_node` marca la escalación como `resolved` (con revisor y
timestamp), cierra la auditoría del nodo y devuelve el control al grafo.

> Alternativa: la cola también se puede gestionar con la interfaz
> `scripts/review_escalations.py --review` (útil si el caso se pausó en otra
> ejecución).

### Paso 5 — Decisión final y trazabilidad

`final_decision` (Módulo 6) consolida todo: como hay feedback humano, el
`outcome` es tu decisión y `decided_by = "human"`. El caso se cierra
(`status = closed`). El script imprime el rastro completo:

```
======================================================================
  TRAZABILIDAD DEL CASO EN LA BD
======================================================================

[rule_evaluator] estado=completed
  -> rule_evaluation: regla=candidate_min_requirements resultado=True ...
[llm_decision] estado=completed
  -> llm_decision: modelo=gpt-4o-mini fit=unclear confianza=0.55
[validation] estado=completed
  -> validation: valida=True requiere_revision=True
[human_escalation] estado=completed
  -> human_escalation: estado=resolved resolucion=fit revisor=julian

[final_decision] outcome=fit decidido_por=human
```

---

## 4. Verificación manual en Postgres (opcional)

```sql
-- El caso y su estado final
SELECT id, status, current_node_key FROM cases ORDER BY created_at DESC LIMIT 1;

-- La escalación resuelta
SELECT status, resolution, assigned_to, resolved_at FROM human_escalations
ORDER BY created_at DESC LIMIT 1;

-- La auditoría nodo a nodo
SELECT node_key, status, started_at, finished_at FROM case_node_executions
WHERE case_id = '<id-del-caso>' ORDER BY started_at;
```

---

## 5. Trazas en LangSmith (opcional)

Si `LANGSMITH_TRACING=true` y `LANGSMITH_API_KEY` es válida, la ejecución
completa aparece en https://smith.langchain.com/ bajo el proyecto
`dag-decision`: la llamada al LLM y cada nodo `@traceable` con sus tiempos.
El nodo `human_escalation` no se traza a propósito (ver `docs/graph.md`).

---

## 6. Resumen para la defensa

| Módulo | Qué demuestra la demo |
|---|---|
| 1. DAG Engine | Orquestación con LangGraph, enrutado condicional, checkpoints |
| 2. Rule Evaluator | Filtro determinista auditable (`rule_evaluations`) |
| 3. LLM Decision | Salida estructurada con confianza (`llm_decisions`) |
| 4. Validation | Umbral de confianza que gobierna la escalación (`validations`) |
| 5. Human Escalation | Pausa/reanudación real, cola de revisión, decisión humana registrada |
| 6. Decisión final | Consolidación y cierre del caso (`final_decisions`) |

**Argumento central:** el sistema es *gobernado* — ninguna decisión de baja
confianza se aplica sin revisión humana, y todo el recorrido queda auditado
en la BD, listo para los KPIs de la Fase 5 (tasa de escalado, tiempo de
resolución, trazabilidad).
