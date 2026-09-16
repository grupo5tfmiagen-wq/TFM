# Guía de preparación y demo con Streamlit

Esta guía deja el entorno listo para una demostración del motor de decisión:
PostgreSQL en Docker, datos de prueba, ejecución desde Streamlit y consulta de
la trazabilidad. Todos los comandos se ejecutan en PowerShell desde la carpeta
`dag_decision` salvo que se indique otra cosa.

## 1. Requisitos

- Windows con PowerShell.
- Python 3.11 o superior disponible con `python --version`.
- Docker Desktop instalado y arrancado.
- Una clave real de OpenAI para ejecutar el nodo LLM. Sin ella se pueden cargar
  datos y navegar por la interfaz, pero no lanzar un caso que pase las reglas.
- Opcional: una cuenta y clave de LangSmith si se quieren ver las trazas web.

## 2. Instalación inicial

Abre PowerShell en la raíz del repositorio y entra en el módulo:

```powershell
Set-Location "C:\Users\Julian\Documents\TFM\dag_decision"
```

Ejecuta el instalador. Crea `.venv`, instala dependencias, crea `.env` desde
`.env.example` cuando no existe, levanta PostgreSQL, aplica migraciones, crea
los checkpoints de LangGraph y comprueba la conexión:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\setup.ps1
```

`setup.ps1` es idempotente: se puede lanzar de nuevo antes de la demo si se
quiere confirmar que la infraestructura sigue preparada. Si Docker Desktop no
está listo, espera a que termine de arrancar y vuelve a ejecutar el comando.

### Instalación para un nuevo miembro del equipo

Después de clonar el repositorio, la secuencia completa para disponer de una
base de datos nueva y los datos de demostración es:

```powershell
git clone https://github.com/grupo5tfmiagen-wq/TFM.git
Set-Location TFM\dag_decision
Set-ExecutionPolicy -Scope Process Bypass
.\setup.ps1
```

Cuando `setup.ps1` termine, edita `.env` e introduce una clave válida en
`OPENAI_API_KEY`. Finalmente carga los datos de la demo y arranca la interfaz:

```powershell
.venv\Scripts\python scripts\load_demo_data.py
.venv\Scripts\python -m streamlit run ui\Home.py
```

La primera ejecución de `setup.ps1` crea `.env` desde `.env.example`. El
archivo `.env` es local y no se sube a Git, por lo que cada persona debe
configurar sus propias claves.

## 3. Configurar las claves

Abre `dag_decision/.env`, que no se versiona, y sustituye al menos esta línea:

```text
OPENAI_API_KEY=tu_clave_real_de_openai
```

La configuración recomendada para la demo es:

```text
OPENAI_MODEL=gpt-4o-mini
LANGSMITH_TRACING=false
CONFIDENCE_THRESHOLD=0.9
```

Para enviar trazas a LangSmith, en lugar de desactivarlo establece
`LANGSMITH_TRACING=true`, rellena `LANGSMITH_API_KEY` con una clave válida y
conserva o cambia `LANGSMITH_PROJECT`. No se debe compartir ni subir `.env` al
repositorio.

## 4. Preparar la base de datos

En una instalación ya hecha, arranca o verifica PostgreSQL:

```powershell
docker compose up -d
.venv\Scripts\python scripts\check_db_connection.py
```

Carga el catálogo de datos de demostración:

```powershell
.venv\Scripts\python scripts\load_demo_data.py
```

El ejecutable lee [data/demo_catalog.json](../data/demo_catalog.json) y crea o
actualiza los registros por su identificador. Por tanto, es seguro ejecutarlo
antes de cada ensayo: no duplica CVs ni ofertas. La salida indica cuántos se
han creado y cuántos se han actualizado.

Como comprobación adicional:

```powershell
.venv\Scripts\python scripts\verify_cv_job_tables.py
```

El catálogo aporta cinco CVs y cuatro ofertas. Pueden aparecer más registros
si se habían cargado ejemplos anteriores; eso no afecta a la interfaz.

### Reiniciar todas las tablas de Docker

Este procedimiento **borra todos los datos locales del proyecto**: CVs,
ofertas, casos, auditorías y checkpoints de LangGraph. Úsalo para repetir la
demo desde una base de datos vacía. No ejecuta cambios en otros contenedores
Docker ni elimina el archivo `.env`.

Detén la aplicación Streamlit si está abierta y ejecuta:

```powershell
docker compose down -v
.\setup.ps1
.venv\Scripts\python scripts\load_demo_data.py
.venv\Scripts\python scripts\verify_cv_job_tables.py
```

`docker compose down -v` elimina el contenedor y el volumen de PostgreSQL
declarados por este proyecto. `setup.ps1` crea un contenedor nuevo, aplica las
migraciones y recrea las tablas de checkpoint; el cargador vuelve a insertar
los cinco CVs y las cuatro ofertas del catálogo.

## 5. Iniciar Streamlit

Con PostgreSQL en marcha, inicia la aplicación:

```powershell
.venv\Scripts\python -m streamlit run ui\Home.py
```

Abre `http://localhost:8501` en el navegador. Mantén esa consola abierta
mientras se hace la demostración y detén el servidor con `Ctrl+C` cuando
termines.

La navegación lateral contiene:

- **Nuevo Caso**: selecciona un CV y una oferta, ejecuta el DAG y muestra el
  resultado o la pausa de revisión humana.
- **Cola de Escalaciones**: muestra los casos pausados y permite resolverlos.
- **Historial de Casos**: muestra cada ejecución y su auditoría por nodo.
- **Metricas**: presenta KPIs y gráficos de decisiones, escalaciones,
   confianza media del LLM, tiempo de revisión, filtrado por reglas, coste LLM
   , rendimiento por oferta y controles de sesgo por institución, sexo y década
   de nacimiento. Incluye un glosario desplegable para interpretar los resultados.

### Glosario de métricas

| Término | Significado |
| --- | --- |
| Caso analizado | Evaluación de un CV frente a una oferta. |
| Decisión final | Resultado oficial registrado al cerrar el flujo. |
| Aprobado (`fit`) | El candidato es adecuado para la oferta. |
| No apto (`not_fit`) | El LLM o revisor determina que no encaja. |
| Descartado por reglas (`rejected`) | No supera requisitos obligatorios y no pasa al LLM. |
| Escalación humana | El caso requiere revisión por baja confianza o falta de conclusión. |
| En cola humana | Escalación aún pendiente de la decisión de un revisor. |
| Confianza LLM | Seguridad declarada por el modelo en su valoración. |
| Tasa de aprobación | Casos `fit` sobre las decisiones finales. |
| Tasa de escalación | Casos escalados sobre los casos analizados. |
| Tiempo medio de revisión | Minutos entre crear y resolver una escalación. |
| Filtrado por reglas | Casos `rejected` que no pasan al LLM por incumplir requisitos obligatorios. |
| Coste estimado LLM | Suma del coste aproximado de llamadas con uso de tokens disponible. |
| Tiempo hasta decisión | Tiempo medio desde crear un caso hasta registrar su decisión final. |
| Sesgo por institución educativa | Comparativa de resultados entre instituciones declaradas en el CV. |
| Sesgo por sexo | Comparativa por sexo, usado solo para auditoría y nunca enviado al modelo. |
| Sesgo por década de nacimiento | Comparativa por cohortes de edad, usada solo para auditoría. |

## 6. Recorridos sugeridos

En **Nuevo Caso**, selecciona las siguientes combinaciones. Los casos que
superan las reglas usan OpenAI y el resultado semántico exacto depende de la
respuesta del modelo; los rechazos indicados son deterministas.

| CV | Oferta | Resultado que demuestra |
| --- | --- | --- |
| Marta Suárez Delgado | Backend Senior - Python y Sistemas Distribuidos | Cumple las reglas; evaluación LLM de un perfil backend sénior. |
| Lucas Romero Martín | Backend Senior - Python y Sistemas Distribuidos | Rechazo directo por experiencia insuficiente. No consume una llamada LLM. |
| Elena Vargas León | Data Engineer - Plataformas Analíticas | Cumple las reglas; afinidad con datos, Airflow, Spark y dbt. |
| Diego Navarro Ruiz | Ingeniero/a MLOps - Plataforma de IA | Cumple las reglas; afinidad con Kubernetes, AWS, Terraform y MLflow. |
| Ana Morales Pérez | Backend Junior - APIs Python | Cumple las reglas; perfil full-stack valorado para backend junior. |

Al lanzar cada combinación se crea un `Case` nuevo. Después abre **Historial de
Casos** para enseñar las ejecuciones de `rule_evaluator`, `llm_decision`,
`validation`, y, cuando corresponda, `human_escalation` y `final_decision`.

## 7. Forzar una escalación humana

La confianza LLM varía entre ejecuciones, por lo que para garantizar este paso
de la demo se puede elevar el umbral temporalmente.

1. Detén Streamlit con `Ctrl+C`.
2. En `.env`, cambia `CONFIDENCE_THRESHOLD=0.8` por:

   ```text
   CONFIDENCE_THRESHOLD=0.99
   ```

3. Vuelve a lanzar Streamlit con el comando de la sección 5.
4. En **Nuevo Caso**, elige Marta, Elena, Diego o Ana junto a su oferta
   sugerida. Tras el LLM aparecerá la solicitud de revisión humana.
5. Selecciona `fit` o `not_fit`, escribe un identificador de revisor y pulsa
   **Resolver y continuar**.
6. Ve a **Historial de Casos** para comprobar que la escalación quedó resuelta
   y la decisión final fue tomada por la persona revisora.
7. Al terminar, restaura `CONFIDENCE_THRESHOLD=0.8` y reinicia Streamlit.

También se puede resolver un caso pausado desde la página **Cola de
Escalaciones**. La pausa se conserva en PostgreSQL, por lo que no se pierde al
cerrar el navegador o reiniciar Streamlit.

## 8. Comandos de ensayo rápido

Este bloque deja el entorno y los datos listos, y lanza Streamlit:

```powershell
Set-Location "C:\Users\Julian\Documents\TFM\dag_decision"
docker compose up -d
.venv\Scripts\python scripts\load_demo_data.py
.venv\Scripts\python scripts\verify_cv_job_tables.py
.venv\Scripts\python -m streamlit run ui\Home.py
```

Para ejecutar el motor sin navegador, con los JSON de ejemplo compatibles:

```powershell
.venv\Scripts\python scripts\run_case.py --case-file data\case_review.json --job-profile-file data\job_profile.json
```

El modo terminal pregunta la decisión humana solo cuando hay una escalación.
Para un ensayo no interactivo se añade `--auto fit` o `--auto not_fit`.

## 9. Problemas frecuentes

| Síntoma | Comprobación o solución |
| --- | --- |
| `docker` no responde | Arranca Docker Desktop y espera a que el daemon esté operativo; después ejecuta `docker compose up -d`. |
| Error de conexión a PostgreSQL | Comprueba `docker compose ps`, el puerto `POSTGRES_PORT=5433` y las URLs de `.env`. |
| No aparecen CVs ni ofertas | Ejecuta `.venv\Scripts\python scripts\load_demo_data.py` y recarga la página. |
| Error de OpenAI al lanzar un caso | Revisa que `OPENAI_API_KEY` sea real y tenga saldo/permisos; vuelve a iniciar Streamlit tras modificar `.env`. |
| No se ve una escalación | Usa `CONFIDENCE_THRESHOLD=0.99`, reinicia Streamlit y lanza una combinación que cumpla las reglas. |
| Streamlit usa el puerto 8501 | Añade `--server.port 8502` al comando y abre `http://localhost:8502`. |

Al finalizar se puede detener la aplicación con `Ctrl+C`. Para parar PostgreSQL
sin borrar los datos, ejecuta `docker compose stop` desde `dag_decision/`.