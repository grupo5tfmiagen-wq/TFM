# Glosario de Términos

## Inteligencia artificial, machine learning y deep learning

**Inteligencia artificial (IA).** La inteligencia artificial puede definirse como la disciplina de la informática dedicada al desarrollo de sistemas capaces de percibir su entorno, razonar y ejecutar acciones con el objetivo de alcanzar determinadas metas. Según Russell y Norvig (2021)\[13\], un agente inteligente es cualquier entidad que recibe información del entorno mediante sensores y actúa sobre él mediante actuadores, maximizando el cumplimiento de sus objetivos.

**Machine Learning (ML).** El aprendizaje automático es una rama de la inteligencia artificial que permite a los sistemas aprender patrones y realizar predicciones a partir de datos sin necesidad de ser programados explícitamente para cada tarea. Los modelos de *machine learning* utilizan algoritmos capaces de mejorar su rendimiento mediante la experiencia adquirida durante el entrenamiento.

**Deep Learning (DL).** El aprendizaje profundo es un subcampo del *machine learning* basado en redes neuronales artificiales con múltiples capas de procesamiento. Estas redes permiten extraer automáticamente representaciones complejas a partir de grandes volúmenes de datos. Los modelos de lenguaje de gran tamaño (LLM) constituyen una aplicación del *deep learning* y se fundamentan en la arquitectura Transformer propuesta por Vaswani et al. (2017) \[6\], que utiliza mecanismos de autoatención para procesar secuencias de información de manera eficiente.

## 

## Arquitectura Transformer

Un *Transformer* es una arquitectura de red neuronal profunda propuesta por Vaswani et al. (2017) \[6\] para tareas de procesamiento del lenguaje natural y modelado de secuencias. A diferencia de las arquitecturas tradicionales basadas en redes neuronales recurrentes (RNN) o convolucionales (CNN), el Transformer prescinde completamente de estos mecanismos y se basa exclusivamente en mecanismos de atención para procesar la información.

La arquitectura Transformer está compuesta por un codificador (*encoder*) y un decodificador (*decoder*), organizados en varias capas que emplean mecanismos de autoatención multicabeza (*multi-head self-attention*) y redes neuronales totalmente conectadas. Gracias a la autoatención, el modelo puede analizar simultáneamente todas las palabras de una secuencia y capturar relaciones tanto locales como globales entre ellas, independientemente de la distancia que las separa.

Además, el Transformer incorpora codificaciones posicionales (*positional encodings*) para conservar la información sobre el orden de los elementos de la secuencia, permitiendo así representar adecuadamente la estructura del lenguaje. Su capacidad para procesar datos en paralelo reduce significativamente el tiempo de entrenamiento y mejora la eficiencia computacional respecto a modelos anteriores.

La introducción de esta arquitectura supuso un cambio de paradigma en el ámbito de la inteligencia artificial y el procesamiento del lenguaje natural, convirtiéndose en la base de los modelos de lenguaje de gran tamaño (LLM) actuales, como GPT, BERT, Gemini o Llama.

## LLM

Los modelos de lenguaje de gran tamaño o *Large Language Models* (LLM) son modelos de inteligencia artificial basados en técnicas de *deep learning* diseñados para comprender y generar lenguaje natural. Estos modelos se construyen sobre la arquitectura Transformer, introducida por Vaswani et al. (2017) \[6\], la cual reemplaza las redes neuronales recurrentes tradicionales mediante mecanismos de autoatención capaces de capturar dependencias complejas dentro de secuencias de texto.

Los LLM se entrenan de forma autosupervisada utilizando enormes volúmenes de datos procedentes de diversas fuentes, como páginas web, libros y repositorios digitales. Durante este proceso de preentrenamiento, el modelo aprende patrones lingüísticos, relaciones semánticas y conocimientos generales mediante tareas predictivas, como la estimación del siguiente token de una secuencia. Gracias a la capacidad de procesamiento paralelo proporcionada por la arquitectura Transformer, estos modelos pueden escalar hasta alcanzar cientos de miles de millones de parámetros.

La principal característica de los LLM reside en su capacidad para modelar el contexto y las relaciones entre palabras mediante mecanismos de atención multicabeza (*multi-head attention*), lo que les permite abordar una amplia variedad de tareas relacionadas con el procesamiento del lenguaje natural, entre las que se incluyen la traducción automática, el resumen de textos, la generación de contenido, la respuesta a preguntas y la generación de código.

Según Zhao et al. (2023) \[7\], los LLM representan una evolución de los modelos de lenguaje tradicionales, caracterizada por el incremento de la escala del entrenamiento, el número de parámetros y la diversidad de los datos utilizados. Estas capacidades les permiten generalizar conocimientos adquiridos durante el entrenamiento y adaptarse a múltiples dominios y aplicaciones con un ajuste adicional mínimo o incluso sin necesidad de entrenamiento específico.

En la actualidad, los LLM constituyen la base tecnológica de numerosos sistemas de inteligencia artificial generativa, como ChatGPT, Gemini, Claude o Llama, y han transformado significativamente la investigación y las aplicaciones industriales relacionadas con el procesamiento del lenguaje natural. 

## Generación aumentada por recuperación (RAG)

La generación aumentada por recuperación, conocida como *Retrieval-Augmented Generation* (RAG), es una arquitectura de inteligencia artificial que combina modelos de lenguaje de gran tamaño (LLM) con sistemas de recuperación de información externos para mejorar la precisión y actualidad de las respuestas generadas. Introducida formalmente por Lewis et al. (2020) \[8\], esta técnica integra un módulo de búsqueda capaz de recuperar documentos relevantes desde una base de conocimiento y un modelo generativo basado en transformadores encargado de producir la respuesta final a partir de la información recuperada.

El funcionamiento de un sistema RAG se fundamenta en dos etapas principales. En primer lugar, un mecanismo de recuperación (*retriever*) identifica y selecciona los documentos más relevantes para una consulta determinada a partir de una colección de datos previamente indexada. Posteriormente, dicha información se incorpora al contexto de entrada del modelo generativo, que utiliza el conocimiento recuperado para generar una respuesta más precisa, coherente y fundamentada.

La aparición de RAG responde a algunas de las principales limitaciones de los modelos de lenguaje tradicionales, como la dependencia exclusiva del conocimiento adquirido durante el entrenamiento y la tendencia a generar información incorrecta o desactualizada. Al incorporar fuentes externas de información durante la inferencia, los sistemas RAG permiten acceder a conocimiento actualizado sin necesidad de volver a entrenar el modelo, reduciendo además el fenómeno de las alucinaciones.

Según Lewis et al. (2020), la combinación de recuperación y generación permite abordar de manera más eficiente tareas intensivas en conocimiento, como la respuesta a preguntas, la búsqueda documental o el resumen automático. Posteriormente, trabajos de revisión como los de Gao et al. (2023) \[9\] y Zhao et al. (2023) \[7\] ampliaron esta definición, describiendo RAG como un paradigma fundamental para extender las capacidades de los LLM mediante la integración de técnicas de recuperación de información, representaciones vectoriales y bases de conocimiento externas.

En la práctica, los sistemas RAG suelen estar compuestos por varias etapas: la indexación de documentos, la generación de representaciones vectoriales mediante *embeddings*, la recuperación de información relevante y la generación de respuestas condicionadas por el contexto recuperado. Gracias a esta arquitectura híbrida, RAG se ha convertido en una de las estrategias más utilizadas para desarrollar asistentes inteligentes, motores de búsqueda avanzados y sistemas empresariales basados en modelos de lenguaje. 

## Agentes

Un agente de inteligencia artificial es una entidad capaz de percibir su entorno, procesar la información obtenida y ejecutar acciones con el objetivo de alcanzar determinadas metas. Según Russell y Norvig (2021) \[13\], un agente inteligente puede definirse como cualquier sistema que recibe información del entorno a través de sensores y actúa sobre él mediante actuadores, seleccionando aquellas acciones que maximizan el cumplimiento de sus objetivos.

La aparición de los modelos de lenguaje de gran tamaño (LLM) ha ampliado considerablemente las capacidades de los agentes tradicionales, dando lugar a una nueva generación de agentes autónomos capaces de razonar, planificar y utilizar herramientas externas. En este contexto, Yao et al. (2022) \[11\] introducen el paradigma *ReAct* (*Reasoning and Acting*), que combina el razonamiento lingüístico con la ejecución de acciones, permitiendo que los modelos alternen entre procesos de reflexión interna y la interacción con fuentes de información externas para resolver tareas complejas.

Los agentes basados en LLM integran habitualmente varios componentes fundamentales: un modelo de lenguaje encargado del razonamiento y la toma de decisiones, un sistema de memoria para almacenar información relevante, mecanismos de planificación para descomponer tareas complejas y un conjunto de herramientas externas, como motores de búsqueda, bases de datos o APIs. Esta arquitectura permite que el agente no solo genere respuestas, sino que también interactúe activamente con su entorno y adapte su comportamiento en función de la información disponible.

Según Weng (2023) \[12\], un agente autónomo basado en LLM puede entenderse como un sistema compuesto por un modelo de lenguaje central que actúa como motor cognitivo y que, apoyado por memoria, planificación y herramientas externas, es capaz de ejecutar tareas de manera semiautónoma o autónoma. Gracias a estas capacidades, los agentes modernos pueden abordar problemas complejos, automatizar procesos y colaborar con los usuarios en múltiples dominios de aplicación.

En la actualidad, los agentes basados en modelos de lenguaje representan una de las principales líneas de investigación en inteligencia artificial, ya que combinan las capacidades lingüísticas de los LLM con mecanismos de razonamiento, recuperación de información y ejecución de acciones, acercándose progresivamente a sistemas capaces de operar de forma autónoma en entornos reales. 

# Bibliografía

\[6\] Vaswani, A., Shazeer, N., Parmar, N., Uszkoreit, J., Jones, L., Gomez, A. N., Kaiser, Ł., & Polosukhin, I. (2017). Attention Is All You Need. Advances in Neural Information Processing Systems, 30, 5998–6008. [https://arxiv.org/abs/1706.03762](https://arxiv.org/abs/1706.03762)  
\[7\] Zhao, W. X., Zhou, K., Li, J., Tang, T., Wang, X., Hou, Y., Min, Y., Zhang, B., Zhang, J., Dong, Z., et al. (2023). A Survey of Large Language Models. arXiv. [https://doi.org/10.48550/arXiv.2303.18223](https://doi.org/10.48550/arXiv.2303.18223)  
\[8\] Lewis, P., Perez, E., Piktus, A., Petroni, F., Karpukhin, V., Goyal, N., Küttler, H., Lewis, M., Yih, W. T., Rocktäschel, T., Riedel, S., & Kiela, D. (2020). Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks. Advances in Neural Information Processing Systems, 33, 9459–9474. [https://doi.org/10.48550/arXiv.2005.11401](https://doi.org/10.48550/arXiv.2005.11401)  
\[9\] Gao, Y., Xiong, Y., Gao, X., Jia, K., Pan, J., Bi, Y., Wang, Y., Cai, J., & Wang, H. (2023). Retrieval-Augmented Generation for Large Language Models: A Survey. [https://doi.org/10.48550/arXiv.2312.10997](https://doi.org/10.48550/arXiv.2312.10997)  
\[10\] Russell, S., & Norvig, P. (2021). Artificial Intelligence: A Modern Approach (4th ed.). Pearson.  
\[11\] Yao, S., Zhao, J., Yu, D., Du, N., Shafran, I., Narasimhan, K., & Cao, Y. (2023). ReAct: Synergizing Reasoning and Acting in Language Models. En The Eleventh International Conference on Learning Representations (ICLR 2023). [https://openreview.net/forum?id=WE\_vluYUL-X](https://openreview.net/forum?id=WE_vluYUL-X)  
\[12\] Weng, L. (2023, 23 de junio). LLM Powered Autonomous Agents. Lil'Log. [https://lilianweng.github.io/posts/2023-06-23-agent/](https://lilianweng.github.io/posts/2023-06-23-agent/)  
\[13\] Russell, S., & Norvig, P. (2021). Artificial Intelligence: A Modern Approach (4th ed.). Pearson.

