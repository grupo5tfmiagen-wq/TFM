
# Glosario de Términos Académicos: Motor de Decisión Híbrido


## 1. Estructura de Grafos y Orquestación

### Grafo Acíclico Dirigido (DAG - Directed Acyclic Graph)

* **Definición**: Estructura matemática y computacional integrada por un conjunto de vértices (nodos) y aristas dirigidas que no contiene ciclos closed-loop [3].
* **Aplicación en el sistema**: En la arquitectura del motor, el DAG representa el flujo lógico explícito que gobierna la secuencia de evaluación de decisiones de negocio, asegurando que la progresión del proceso sea determinista, auditable y libre de bucles infinitos [3, 4].

### Nodo (Node)

* **Definición**: Unidad operativa o funcional mínima dentro de un grafo acíclico dirigido [4].
* **Aplicación en el sistema**: Cada nodo representa un paso específico del flujo de trabajo, tales como la ejecución de una validación lógica (regla determinista), el enriquecimiento de información, la llamada a un modelo de lenguaje (LLM) o un punto de escalado manual [3].

### Arista (Edge)

* **Definición**: Conexión dirigida unidireccional que une secuencialmente dos nodos en un grafo, estableciendo una relación de precedencia de tipo origen-destino [4].
* **Aplicación en el sistema**: Las aristas modelan las transiciones lógicas entre las diferentes etapas de la decisión, cuya activación puede estar condicionada por el resultado de las evaluaciones de los nodos predecesores [3].

### DAG Engine (Motor del DAG)

* **Definición**: Componente central de software (orquestador) encargado de interpretar el Grafo Acíclico Dirigido y controlar el ciclo de vida de la ejecución de un caso [3, 4].
* **Aplicación en el sistema**: Monitorea qué nodos deben activarse, evalúa las condiciones de transición entre aristas, gestiona los fallos de procesamiento y mantiene la integridad del flujo secuencial [3].

### Estado del Caso (Case State)

* **Definición**: Estructura o registro dinámico de datos (payload) que almacena la información de contexto de una transacción o expediente a lo largo de su procesamiento [3].
* **Aplicación en el sistema**: Es el "hilo conductor" o memoria del flujo de trabajo que se actualiza continuamente con las entradas originales, los scores intermedios de las reglas y las salidas de los nodos LLM, sirviendo de entrada para los nodos subsiguientes [3].

---

## 2. Lógica Determinista y Reglas de Negocio

### Rule Evaluator (Evaluador de Reglas)

* **Definición**: Motor de inferencia diseñado para evaluar de forma automatizada reglas de negocio lógicas predefinidas sobre un conjunto de datos estructurados [3].
* **Aplicación en el sistema**: Módulo que ejecuta de forma rápida y determinista comprobaciones obligatorias, verificación de umbrales cuantitativos, políticas de exclusión y enrutamientos fijos que no requieren interpretación subjetiva [3].

### Regla Determinista (Deterministic Rule)

* **Definición**: Expresión lógica de tipo condicional (`IF-THEN`) que, ante un mismo conjunto de variables de entrada, produce invariablemente el mismo resultado lógico sin margen de incertidumbre o variabilidad estocástica [3].
* **Aplicación en el sistema**: Garantiza el cumplimiento normativo (*compliance*) y la gobernanza sobre criterios de negocio fijos, actuando como primera línea de filtrado y control de calidad en el procesamiento del caso [3].

---

## 3. Procesamiento Semántico e Inteligencia Artificial

### Nodos de Decisión LLM (LLM Decision Nodes)

* **Definición**: Nodos del flujo de ejecución que integran un Modelo de Lenguaje de Gran Tamaño (LLM) para resolver tareas complejas mediante procesamiento de lenguaje natural y razonamiento semántico [3].
* **Aplicación en el sistema**: Se encargan de procesar datos no estructurados (documentos de texto libre, CVs, justificaciones), realizar clasificaciones semánticas, extraer entidades clave o resumir incoherencias lógicas [3, 5].

### Inteligencia Semántica (Semantic Intelligence)

* **Definición**: Capacidad de un sistema computacional para comprender, interpretar y categorizar el contexto, el significado subyacente y la intención dentro de datos textuales en lenguaje natural [3, 5].
* **Aplicación en el sistema**: Complementa la rigidez del Rule Evaluator, permitiendo procesar y estructurar información ambigua que no se ajusta de forma directa a reglas binarias o numéricas estrictas [3].

### Salida Estructurada (Structured Output)

* **Definición**: Técnica de decodificación y restricción sintáctica que obliga a un LLM a generar respuestas que se ajusten estrictamente a un esquema de datos predefinido (por ejemplo, un JSON Schema) [2].
* **Aplicación en el sistema**: Evita fallos de integración con el código de backend eliminando la naturaleza puramente libre del texto generado, facilitando que el resultado del LLM pueda ser consumido de forma directa por el DAG Engine o el Rule Evaluator [2, 3].

---

## 4. Control de Calidad y Gobernanza

### Capa de Validación y Confianza (Confidence & Validation Layer)

* **Definición**: Módulo intermedio de control de calidad encargado de verificar la corrección estructural y la fiabilidad semántica de los resultados emitidos por un nodo de IA [2, 3].
* **Aplicación en el sistema**: Evalúa si la salida del LLM cumple con el formato estructurado esperado, si todos los campos obligatorios están presentes y si el nivel de confianza reportado supera los umbrales mínimos requeridos antes de permitir que el caso continúe en el flujo automatizado [2, 3].

### Inconsistencia Semántica (Semantic Inconsistency)

* **Definición**: Discrepancia o contradicción lógica identificada entre las inferencias semánticas producidas por un modelo de lenguaje y las verdades empíricas de los datos del caso o las reglas de negocio deterministas [3].
* **Aplicación en el sistema**: Desviaciones críticas que detecta la capa de validación (por ejemplo, que el LLM califique a un candidato como "experto" pero el Rule Evaluator determine que tiene 0 años de experiencia), provocando el desvío inmediato del expediente a intervención humana [3].

### Trazabilidad (Traceability)

* **Definición**: Capacidad de registrar, auditar y reconstruir paso a paso el camino lógico seguido por una transacción, incluyendo las entradas, las decisiones intermedias y los actores (humanos o algorítmicos) implicados [3].
* **Aplicación en el sistema**: El motor guarda un log inalterable de cada caso evaluado, detallando qué reglas se aplicaron, qué respuestas dio el LLM, los esquemas de validación y, si existió, la decisión final tomada por un revisor humano [3].

### Gobernanza de la IA (AI Governance)

* **Definición**: Marco ético, técnico y operativo estructurado para garantizar que los sistemas basados en inteligencia artificial operen de manera segura, transparente, explicable y bajo estricto control operativo [1, 3].
* **Aplicación en el sistema**: Consiste en restringir la autonomía del LLM, limitando su rol a la clasificación o interpretación de datos sin permitirle tomar decisiones críticas o desviar flujos del DAG de manera autónoma o no supervisada [3].

---

## 5. Integración y Escalado Humano

### Human-in-the-Loop (HITL)

* **Definición**: Enfoque de diseño de sistemas donde el juicio, la supervisión y la intervención humana están integrados de manera estratégica en el ciclo de ejecución de un proceso automatizado o algoritmo de IA [1].
* **Aplicación en el sistema**: Paradigma bajo el cual se concibe todo el proyecto: la automatización asiste en las tareas repetitivas de bajo riesgo, mientras que el juicio humano se reserva para resolver la incertidumbre o aprobar los casos críticos [1, 3].

### Capa de Escalado Humano (Human Escalation Layer)

* **Definición**: Interfaz y componente lógico encargado de pausar el flujo automatizado de un caso y transferir su control a un operador humano debido a fallos de validación, baja confianza o riesgos de negocio [1, 3].
* **Aplicación en el sistema**: Se activa de forma automática ante la detección de anomalías o clasificaciones dudosas por parte del LLM, permitiendo a un analista revisar la trazabilidad del caso y emitir una resolución manual informada [3].

### Decisión Final (Final Decision)

* **Definición**: Estado de salida oficial y concluyente del flujo del DAG en el que se consolida la resolución del expediente bajo evaluación [3].
* **Aplicación en el sistema**: Cierra el ciclo del caso emitiendo resoluciones formales (como aprobación, rechazo o solicitud de subsanación) tras la confluencia de la lógica de reglas, el análisis de los LLM y las decisiones del revisor humano [3].

---

## 6. Evaluación y Métricas de Rendimiento (KPIs)

### Tasa de Escalado Humano (Human Escalation Rate)

* **Definición**: Métrica cuantitativa que mide la proporción de casos procesados por el sistema que requieren intervención humana frente al total de casos entrantes [1, 3].
* **Aplicación en el sistema**: Permite evaluar el nivel de eficiencia operativa y el grado de automatización segura alcanzado por el motor híbrido [3].

### Precisión de la Decisión (Decision Accuracy)

* **Definición**: Indicador de rendimiento que evalúa la coincidencia entre las resoluciones automáticas adoptadas por el motor y una verdad de referencia o patrón de oro (*ground truth*) definido por expertos [3].
* **Aplicación en el sistema**: Esencial en la validación empírica del TFM para demostrar la fiabilidad y robustez de la arquitectura híbrida frente a un enfoque puramente algorítmico o manual [3].

---

## Bibliografía

[1] Mosqueira-Rey, E., Alonso-Ríos, D., Porto-Pazos, A. B., & Vázquez-Naya, J. M. (2023). Humans in the loop: Exploring the challenges of human participation in automated decision-making systems. Frontiers in Political Science, 5, 1611563. https://doi.org/10.3389/fpos.2025.1611563

[2] Fan, J., et al. (2023). Empirical Study for Structured Output Control in LLMs for Software Engineering. arXiv preprint arXiv:2606.09395v1. https://arxiv.org/abs/2606.09395

[3] MDPI. (2025). Hybrid AI and LLM-Enabled Agent-Based Real-Time Decision Support Architecture for Industrial Batch Processes. MDPI Processes, 7(2), 51. https://doi.org/10.3389/fpos.2025.1611563

[4] Brandes, U., & Erlebach, T. (Eds.). (2005). Network Analysis: Methodological Foundations (Vol. 3418). Springer Science & Business Media. 

[5] Brown, T., et al. (2020). Language Models are Few-Shot Learners. Advances in Neural Information Processing Systems, 33, 1877-1901.