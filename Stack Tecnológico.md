# Stack Tecnológico

**Selección del stack tecnológico**

La elección del stack tecnológico para este proyecto responde a un criterio de priorización del esfuerzo hacia el valor diferencial del sistema. El diseño de un motor de decisión híbrido plantea dos tipos de complejidad claramente distintos: por un lado, la **infraestructura de orquestación** (definición de nodos, gestión de transiciones condicionadas, persistencia de estado y capacidad de pausar/reanudar el flujo ante una intervención humana); por otro, el **diseño del sistema de decisión en sí** (integración de reglas deterministas, nodos LLM, capa de validación de confianza y lógica de escalado humano), que constituye la aportación original de este trabajo.

Construir un motor de orquestación completamente desde cero —incluyendo gestión de grafo, checkpointing y reanudación de casos en espera de revisión humana— es una tarea de infraestructura no trivial, cuya complejidad tiende a subestimarse precisamente porque no resulta visible hasta que se necesita reanudar un caso interrumpido. Dado que el tiempo disponible en un TFM es limitado y que esta infraestructura no aporta valor académico diferencial frente a soluciones ya existentes y maduras, se ha optado por apoyar el Módulo 1 (DAG Engine) en un framework de orquestación consolidado, **LangGraph**, que resuelve de forma nativa la definición de grafos de estado, las transiciones condicionadas y el checkpointing necesario para el escalado humano.

Esta decisión permite reorientar el esfuerzo de diseño hacia los módulos donde reside la contribución original del proyecto: la lógica de evaluación por reglas, la integración y validación de los nodos LLM, la capa de confianza y el mecanismo de escalado humano. El resto de esta sección detalla las tecnologías seleccionadas para cada uno de los módulos de la arquitectura.

**Módulo 1: DAG Engine**

Se escoge **LangGraph** frente a la alternativa de construir un motor de orquestación propio (grafo artesanal sobre NetworkX o similar). Un motor propio exigiría implementar desde cero la gestión de transiciones condicionadas, la persistencia de estado del caso y, sobre todo, el checkpointing necesario para pausar y reanudar un caso ante escalado humano — una pieza cuya complejidad se subestima fácilmente porque no es visible hasta que hay que reanudar un caso interrumpido. Dado que esta infraestructura no aporta valor académico diferencial y el tiempo de un TFM es limitado, se prioriza un framework maduro que la resuelve de forma nativa, liberando tiempo para los módulos donde sí reside la aportación original del proyecto.

**Módulo 2: Rule Evaluator**

Se escoge una implementación propia (reglas en YAML/JSON con evaluador en Pydantic) frente a un motor de reglas de terceros (p. ej. tipo Drools). Un motor externo añadiría una dependencia pesada y, con frecuencia, opacidad sobre cómo se evalúan las reglas internamente — justo lo contrario del requisito de auditabilidad que plantea la propuesta. La implementación propia permite que cada regla sea declarativa, inspeccionable y modificable sin tocar código, y constituye además un componente donde el diseño es una aportación real del trabajo, no una funcionalidad delegada.

**Módulo 3: LLM Decision Nodes**

Se escoge apoyar la llamada al LLM en instructor (salida estructurada validada por Pydantic) frente a invocar la API del modelo con texto libre y parsear la respuesta después. La arquitectura contempla el uso de la API de Claude (Anthropic) o de OpenAI como proveedor del modelo, dejando el proveedor concreto como una decisión desacoplada del resto del sistema gracias a *instructor*, que soporta ambas APIs con la misma interfaz de salida estructurada — en línea con el requisito de modularidad y extensibilidad de la propuesta. Usar texto libre trasladaría todo el riesgo de formato inconsistente a la capa de validación posterior, además de no ofrecer reintento automático ante una salida mal formada. Forzar la estructura en el punto de generación reduce directamente el riesgo señalado en la propia propuesta: tratar la salida del LLM "como si fuera verdad" sin garantías mínimas de formato. 

**Módulo 4: Confidence & Validation Layer**

Se escoge lógica propia sobre Pydantic frente a una librería de validación de mayor nivel (tipo Guardrails AI). Una librería externa de este tipo añadiría capacidades genéricas (detección de toxicidad, PII, etc.) que no son el foco de la propuesta, y en cambio la comprobación específica que se necesita — coherencia con reglas previas, contraste de campos entre nodos — es lógica de dominio que no resuelve una librería genérica. Implementarla a medida mantiene el control total sobre el criterio de "válido / confianza baja / requiere revisión", que es el núcleo de este módulo.

**Módulo 5: Human Escalation Layer**

Se escoge **Streamlit** frente a un desarrollo de frontend a medida (React/FastAPI con interfaz propia). Un frontend a medida consumiría tiempo de desarrollo desproporcionado respecto al objetivo del TFM, que no es demostrar capacidad de diseño de interfaz sino la lógica de escalado y su integración con el resto del motor. Streamlit permite un panel funcional de revisión (aprobar/rechazar/reenrutar) con una inversión mínima, sin comprometer la validez de la demostración.

Se escoge **Postgres** para el registro de casos escalados frente a una base documental, por la misma razón que en el Módulo 6: el estado de un caso escalado sigue un modelo bien definido de transiciones (pendiente, en revisión, resuelto) que requiere garantías transaccionales para no perder ni duplicar un caso cuando varios humanos acceden al panel. Además, al reutilizar la misma base de datos que la capa de persistencia y trazabilidad, se evita duplicar infraestructura y se mantiene una única fuente de verdad para el histórico completo del caso. 

**Módulo 6: Decisión final, persistencia y trazabilidad**

Se escoge **Postgres** frente a una base de datos documental (tipo MongoDB) para el registro de casos y decisiones. El dominio del problema (casos con estado bien definido, reglas de transición, necesidad de integridad transaccional para no perder ni duplicar un caso escalado) encaja mejor con un modelo relacional que con uno documental, que aportaría flexibilidad de esquema innecesaria a costa de garantías transaccionales. Para la trazabilidad de ejecución del grafo se escoge **LangSmith** frente a instrumentación manual con logging propio, ya que al usar LangGraph, LangSmith se integra sin coste adicional de desarrollo y ofrece directamente trazas por nodo, entrada/salida y tiempos — los mismos datos que exigiría construir a mano.

**Capa transversal**

Se escoge **FastAPI** frente a Flask para exponer el motor como servicio, por su validación de tipos nativa (que refuerza la consistencia con el resto del stack basado en Pydantic) y su soporte async, relevante si varios nodos LLM se ejecutan de forma concurrente. Se escoge **Pytest** frente a no incluir una suite de test formal, ya que la propuesta pone el acento en un sistema "auditable y testeable" frente a los enfoques puramente basados en LLM — sin tests sistemáticos por módulo, esa afirmación quedaría sin respaldo empírico en la memoria.

