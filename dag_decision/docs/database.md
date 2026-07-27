# Base de datos local (Postgres) para el motor DAG_DECISION

Este proyecto usa Postgres en local (vía Docker Compose) para persistir dos
cosas distintas:

1. **Esquema de negocio** (tablas propias, gestionadas por Alembic): `cases`,
   `dag_definitions`, `case_node_executions`, `rule_evaluations`,
   `llm_decisions`, `validations`, `human_escalations`, `final_decisions`.
   Es la trazabilidad legible y consultable para auditoría y KPIs (accuracy,
   tasa de escalado humano, tiempo de resolución, etc.).
2. **Checkpoints de LangGraph** (tablas `checkpoints`, `checkpoint_writes`,
   `checkpoint_blobs`, `checkpoint_migrations`): estado técnico interno del
   grafo por caso/hilo, gestionado automáticamente por
   `langgraph-checkpoint-postgres`. Habilita pausar y reanudar el grafo (por
   ejemplo, mientras un caso espera revisión humana). **No se deben editar
   estas tablas manualmente ni gestionarlas con Alembic.**

Ambos usan la misma base de datos Postgres (`dag_decision_bdd`).

## Requisitos

- Docker Desktop (o Docker Engine) con Docker Compose. Si no lo tienes,
  descárgalo de https://www.docker.com/products/docker-desktop/.
- Python 3.11+.

## Puesta en marcha rápida (recomendado)

Si es la primera vez que montas el proyecto (o Docker/Python aún no están
instalados/arrancados), ejecuta desde PowerShell:

```
cd dag_decision
.\setup.ps1
```

El script comprueba Docker y Python, crea el entorno virtual, instala
dependencias, genera `.env` si no existe, levanta Postgres, aplica las
migraciones, crea las tablas de checkpoint de LangGraph y verifica la
conexión. Es seguro volver a ejecutarlo (idempotente). Si Docker no está
instalado, el script te avisa y abre la página de descarga.

## Puesta en marcha manual (paso a paso)

1. Copia `.env.example` a `.env` y ajusta usuario/contraseña si lo necesitas:

   ```
   copy .env.example .env
   ```

2. Levanta Postgres:

   ```
   docker compose up -d
   ```

   Comprueba que el contenedor está healthy con `docker ps`.

3. Crea un entorno virtual e instala dependencias:

   ```
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

4. Aplica las migraciones del esquema de negocio:

   ```
   alembic upgrade head
   ```

5. Crea las tablas de checkpoint de LangGraph (idempotente, se puede volver a
   ejecutar sin problema):

   ```
   python src/db/checkpointer.py
   ```

6. Verifica que todo está en orden:

   ```
   python scripts/check_db_connection.py
   ```

   Deberías ver la conexión en `OK` y el listado de las 8 tablas de negocio
   más las tablas de checkpoint de LangGraph.

## Generar nuevas migraciones

Cuando se añadan o modifiquen modelos en `src/db/models/`:

```
alembic revision --autogenerate -m "descripcion del cambio"
alembic upgrade head
```

## Notas de seguridad

- `.env` nunca se commitea (está en `.gitignore`); solo `.env.example` con
  valores de ejemplo.
- `LANGGRAPH_STRICT_MSGPACK=true` restringe la deserialización de checkpoints
  a tipos conocidos y seguros, evitando ejecución de código si la base de
  datos se viera comprometida.
