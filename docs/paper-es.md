---
title: "Determinismo de ruta en arneses de agentes: un clasificador tipado de intención como ayuda externa a la decisión"
short_title: "Determinismo de ruta en arneses de agentes"
author: "Mauro Rosero"
affiliation: "ROSERO ONE"
email: "maurorosero@gmail.com"
date: "2026-09-24"
version: "0.1-draft"
type: "case-study"
status: "borrador para revisión del autor"
venue_target: "Inteligencia Artificial (IBERAMIA) — Open Access, doble ciego"
license: "CC BY-NC 4.0"
language: "es"
abstract_language: "en"
keywords_es: "arnés de agente, clasificación de intención, determinismo, actos de habla indirectos, calibración, LLM como enrutador"
keywords_en: "agent harness, intent classification, determinism, indirect speech acts, calibration, LLM routing"
---

# Determinismo de ruta en arneses de agentes: un clasificador tipado de intención como ayuda externa a la decisión

**Mauro Rosero** — ROSERO ONE · maurorosero@gmail.com
Versión 0.1-draft · 2026-09-24

---

## Resumen

Un agente basado en un modelo de lenguaje decide, en cada turno, de dónde obtener
la información antes de responder: consultar un procedimiento almacenado, buscar
en una base de conocimiento, recuperar un dato persistente, releer el historial de
la conversación, o resolver con su propio criterio. Esa decisión —la *ruta*— se
toma hoy de forma implícita dentro del mismo proceso que produce la respuesta. El
resultado es que el mismo patrón de petición puede recibir rutas distintas en
turnos distintos, sin que exista un artefacto que declare cuál correspondía.

Este trabajo presenta un estudio de caso sobre un arnés de agente en producción
(Hermes, instancia personal de un solo operador) en el que se externaliza esa
decisión a un clasificador tipado de intención que corre *antes* de la llamada al
modelo y que inyecta, en el turno, una guía de ruta en lenguaje natural. El
clasificador no ejecuta la tarea ni produce la respuesta: solo elige una de seis
rutas mutuamente excluyentes y declara una confianza. El objetivo declarado no es
mejorar la calidad de la respuesta, sino **reducir la improvisación de ruta**.

Sobre 24 casos de clasificación, el clasificador coincide con el juicio del
operador en 24 de 24, tras revisar tres divergencias que el propio operador
reclasificó. Sobre un experimento A/B de 10 tareas con el modelo congelado
(`deepseek-v4.1-flash`), la proporción de casos que consultan una fuente primaria
*antes* de ejecutar pasa de 3/10, 6/10 y 5/10 sin el clasificador (media 4.7) a
9/10, 10/10 y 10/10 con él (media 9.7); los tiempos de espera se reducen de uno en
tres a cero en tres, y los casos que exceden el límite de tiempo pasan de uno a
ninguno. La ruta inyectada varía entre corridas (skill 3, research 3, memory 2,
history 1, user 1 sobre 10 casos), lo que confirma que el clasificador no
memoriza un mapeo fijo sino que lee el texto de cada turno.

El costo medible es una guía de 93 a 111 tokens por turno —93 como promedio simple
de las seis guías, 111 ponderado por las rutas efectivamente elegidas— que explica
entre el 6.1 % y el 7.2 % del aumento observado de tokens de entrada; el 87.2 %
restante es salida de herramientas. La varianza entre corridas sin el clasificador es de 1.2× a 49×,
mayor que el efecto atribuible al costo, lo que impide sostener afirmaciones
fuertes sobre costo o latencia. Se reportan también tres límites concretos: el
clasificador no distingue expresiones modales españolas (*haceme un informe*) que
son actos de habla indirectos y caen en la ruta equivocada por convergencia; la
confianza declarada no anticipa el acierto; y la ruta de escape (cuando el
clasificador declara no saber) no inyecta guía alguna, dejando el turno al
criterio del modelo.

El aporte es metodológico y de ingeniería: describe un mecanismo determinista
acotado para hacer explícita una decisión que los arneses actuales dejan implícita,
y reporta con datos crudos dónde ese mecanismo funciona y dónde no.

**Palabras clave:** arnés de agente; clasificación de intención; determinismo;
actos de habla indirectos; calibración; LLM como enrutador.

---

## Abstract

A language-model agent decides, every turn, where to obtain information before
answering: consult a stored procedure, search a knowledge base, retrieve a
persistent fact, re-read conversation history, or resolve from its own judgement.
That decision —the *route*— is currently made implicitly inside the same process
that produces the answer, so the same request pattern may receive different routes
on different turns, with no artifact declaring which one was correct.

This paper presents a case study of an agent harness in production (Hermes, a
single-operator personal instance) in which that decision is externalized to a
typed intent classifier that runs *before* the model call and injects a
natural-language route guide into the turn. The classifier neither executes the
task nor produces the answer: it selects one of six mutually exclusive routes and
declares a confidence. The stated goal is not to improve answer quality but to
**reduce route improvisation**.

Across 24 classification cases the classifier agrees with the operator's judgement
on 24 of 24, after the operator reclassified three divergences. In a 10-task A/B
experiment with the model held fixed (`deepseek-v4.1-flash`), the share of cases
consulting a primary source *before* executing rises from 3/10, 6/10 and 5/10
without the classifier (mean 4.7) to 9/10, 10/10 and 10/10 with it (mean 9.7);
waiting time drops from one in three to zero in three, and cases exceeding the
time limit go from one to none. The injected route varies across runs (skill 3,
research 3, memory 2, history 1, user 1 across 10 cases), confirming the classifier
reads each turn's text rather than memorizing a fixed mapping.

The measurable cost is a route guide of 93 to 111 tokens per turn —93 as the simple
mean of the six guides, 111 weighted by the routes actually chosen— accounting for
6.1 % to 7.2 % of the observed rise in input tokens; the remaining 87.2 % is tool
output.
Between-run variance without the classifier spans 1.2× to 49×, exceeding the
effect attributable to cost, which precludes strong cost or latency claims. Three
concrete limits are also reported: the classifier misroutes Spanish modal
expressions (*haceme un informe*) that are indirect speech acts, misrouting by
convergence; declared confidence does not predict correctness; and the escape
route (when the classifier declares it does not know) injects no guidance at all,
leaving the turn to the model's judgement.

The contribution is methodological and engineering-oriented: it describes a bounded
deterministic mechanism that makes explicit a decision current harnesses leave
implicit, and reports with raw data where that mechanism works and where it does
not.

**Keywords:** agent harness; intent classification; determinism; indirect speech
acts; calibration; LLM routing.

---

## 1. Introducción

### 1.1 El problema

Un agente que usa herramientas resuelve una petición en varios pasos. Antes de
cualquier ejecución, hay una decisión previa que casi nunca se examina: **de dónde
sacar lo que hace falta saber**. El agente puede tener un procedimiento guardado
para esa tarea; puede tener el conocimiento consolidado en una base documental;
puede tener un dato corto en memoria persistente; puede necesitar lo que se dijo
antes en la conversación; o puede que no haga falta buscar nada.

En los arneses actuales esa decisión no está declarada en ningún artefacto. Se
toma dentro del mismo proceso que redacta la respuesta, turno a turno, sin que
nada registre cuál era la ruta correcta ni permita compararla con la elegida.

La consecuencia observable no es que el agente responda mal. Es que **responde
bien por caminos distintos**, y a veces por caminos que no puede reproducir. Un
mismo patrón de petición puede resolverse hoy consultando un procedimiento, mañana
improvisando. La primera forma es auditable; la segunda no.

Esta observación no es original de este trabajo. La literatura de 2026 sobre
*harness engineering* ha establecido que la lógica de control del agente está
"enterrada en el código del controlador", lo que la vuelve difícil de transferir,
comparar y estudiar como objeto científico (Pan et al., 2026). El mismo cuerpo de
trabajo ha medido que cambiar el arnés manteniendo fijos los pesos del modelo
altera sustancialmente el desempeño en tareas (Wu et al., 2026). Si el arnés
importa tanto, y su lógica de control es invisible, entonces la decisión de ruta
es un objeto de estudio legítimo, no un detalle de implementación.

### 1.2 La pregunta

Este trabajo se organiza alrededor de una pregunta acotada:

> ¿Se puede hacer determinista la decisión de ruta de un arnés —que el mismo
> patrón de petición reciba la misma clase de ruta— sin forzar al modelo a un
> flujo rígido y sin tocar el motor del arnés?

Las tres restricciones de esa pregunta son deliberadas y limitan el alcance del
trabajo:

- **Determinista**, no *correcto*. El objetivo no es que la ruta sea la mejor
  posible, sino que sea declarada y reproducible. Se admite explícitamente que un
  error de clasificación entre rutas que convergen al mismo resultado no es un
  fallo grave (§6.3).
- **Sin forzar**. La intervención no puede consistir en un guion fijo de pasos. El
  modelo conserva la libertad de ejecutar como quiera *dentro* de la ruta; lo que
  se fija es el punto de partida.
- **Sin tocar el motor**. El mecanismo se implementa sobre las interfaces públicas
  de extensión del arnés (ganchos de plugin), no modificando el núcleo.

### 1.3 La propuesta en una frase

Un **clasificador tipado de intención** que corre antes de la llamada al modelo,
elige una de seis rutas, y anexa al turno una guía en lenguaje natural que nombra
dónde buscar. No ejecuta, no redacta, no decide: orienta el punto de partida y
declara con qué confianza lo hace.

### 1.4 Aporte y alcance

El aporte de este documento es doble:

1. **Metodológico.** Un marco de evaluación para un mecanismo de arnés que no
   busca mejorar la respuesta sino estabilizar el camino hacia ella. Se separan
   explícitamente tres cosas que tienden a confundirse: eficacia de ruta, costo
   atribuible y varianza de medición.
2. **De ingeniería.** La descripción de un mecanismo acotado, implementado sobre
   interfaces de extensión existentes, con sus límites medidos.

**Lo que este trabajo no es.** No es un benchmark. Es un estudio de caso de un solo
arnés, con un solo operador, y con un número de casos que no permite inferencia
estadística. Se adopta deliberadamente el marco de reporte de estudios de caso en
ingeniería de software (Runeson y Höst, 2009) en lugar del marco de un artículo
experimental, porque la contribución es la descripción de un mecanismo y la
evidencia de su comportamiento en un contexto real, no una comparación entre
tratamientos sobre una población.

### 1.5 Organización

La §2 sitúa el trabajo en seis líneas de investigación convergentes. La §3 describe
el arnés sobre el que se interviene. La §4 detalla el mecanismo y el diseño
experimental. La §5 reporta los datos crudos sin interpretación. La §6 interpreta y
declara el hueco que el trabajo señala. La §7 enumera las amenazas a la validez con
el esquema constructo/interna/externa/conclusión. La §8 propone el trabajo
siguiente y la §9 cierra. Los apéndices contienen las declaraciones verbatim del
clasificador, el inventario de casos y los datos crudos.

---

## 2. Trabajo relacionado

Esta investigación toca seis líneas. Para cada una se indica el trabajo de
referencia, qué aporta, y qué se toma de él aquí. Los identificadores se
verificaron contra la API de arXiv y el HTML del artículo (Apéndice E).

### 2.1 Actos de habla indirectos

El punto de partida es la observación de Grice (1975) sobre la implicatura
conversacional: lo que un hablante *dice* y lo que *hace* al decirlo pueden no
coincidir. Searle (1975) formaliza el caso en que la forma lingüística (una
pregunta) vehicula una fuerza ilocutiva distinta (un pedido). Haverkate (1979)
extiende el análisis a la cortesía en español, donde la atenuación mediante modales
es un recurso sistemático, no una anomalía. Pablos-Ortega (2020) documenta el mismo
fenómeno en el español peninsular contemporáneo.

**Qué se toma de esta línea.** El criterio de clasificación de intención de este
trabajo (§4.2) separa explícitamente la forma verbal de la fuerza ilocutiva, y el
límite reportado en §6.4 —el fracaso con *haceme un informe*— es una instancia
directa del problema que esta literatura describe: una forma imperativa con
enclítico que el clasificador lee como tarea procedimental cuando el operador
espera una ruta investigativa.

### 2.2 Pragmática y modelos de lenguaje

Ma et al. (2025) revisan sistemáticamente el estado de la pragmática en modelos de
lenguaje: conjuntos de datos, evaluación, oportunidades y desafíos. Koo et al.
(2025) evalúan específicamente la comprensión de actos de habla indirectos en
coreano, y encuentran que los modelos rinden por debajo de lo que su desempeño
gramatical sugiere.

**Qué se toma de esta línea.** Estos trabajos establecen que la brecha pragmática
en modelos de lenguaje está medida y documentada, y que no es un problema resuelto.
Eso justifica que un arnés no delegue la decisión de ruta al juicio pragmático del
modelo sin más. La comparación relevante es que Koo et al. miden el techo del
modelo en esta tarea; este trabajo mide lo que ocurre cuando se lo saca del circuito
de decisión mediante un clasificador externo.

### 2.3 Expresiones idiomáticas

Haagsma, Nissim y Bos (2019) abordan la extracción robusta de expresiones
potencialmente idiomáticas, un problema de frontera difusa: la misma secuencia puede
ser composicional o idiomática según el contexto.

**Qué se toma de esta línea.** El límite de §6.4 cae exactamente en el espacio que
este trabajo delimita: *haceme* es un modismo rioplatense, no un modal estándar, y
las reglas basadas en la forma verbal (modal conjugado + infinitivo) no lo capturan.
El trabajo citado trata el problema como clasificación estadística con frontera
difusa; aquí se reporta como un caso que la regla formal no alcanza, lo que motiva
el trabajo futuro de §8.

### 2.4 Enrutado de intención

Guo et al. (2025) proponen MoMA, un marco de orquestación de modelos y agentes para
inferencia adaptativa y eficiente, en el que una capa de decisión elige el
componente adecuado por consulta. El problema de fondo es el mismo que el de este
trabajo: hay una decisión de enrutado que conviene separar del componente que
ejecuta.

**Qué se toma de esta línea.** MoMA enruta *entre componentes de cómputo* para
optimizar eficiencia. Este trabajo enruta *entre fuentes de conocimiento* para
estabilizar el proceso de obtención de la respuesta. Es una diferencia de objetivo,
no de forma, y es el punto donde este trabajo se separa del enrutado de inferencia:
la métrica de éxito no es el costo por consulta sino la reproducibilidad de la ruta.

### 2.5 Calibración y abstención

Liu et al. (2025) revisan cuantificación de incertidumbre y calibración de confianza
en modelos de lenguaje. Becker y Soatto (2024) miden la confianza del modelo a
través de la estabilidad de sus explicaciones. Mao, Mohri y Zhong (2023) tratan el
problema de aprender a delegar entre múltiples expertos, que incluye el caso de
decidir cuándo abstenerse.

**Qué se toma de esta línea.** El clasificador de este trabajo declara una
confianza por ruta y dispone de una ruta de escape cuando ninguna aplica. La
literatura de calibración establece que una confianza declarada no es
automáticamente informativa, y el dato de §5.4 lo confirma en este caso: el
clasificador acertó en casos con confianza 0.32 y en casos con confianza 0.56. La
ruta de escape, por el contrario, funciona como se diseñó (§5.3), aunque su
consecuencia —no inyectar guía alguna— no está evaluada.

### 2.6 No-determinismo de agentes

Yagubyan (2026) mide la reproducibilidad conductual de agentes en canalizaciones
de varias etapas con herramientas y encuentra variación sustancial entre corridas
idénticas. Hydari e Iqbal (2026) analizan el muestreo, el estado y la
estocasticidad de los agentes. Dhage (2026) estudia empíricamente restricciones de
ejecución deterministas en arneses de agentes.

**Qué se toma de esta línea.** Es la línea que da sentido al trabajo. Si la
conducta del agente es sustancialmente no reproducible entre corridas idénticas,
entonces introducir un componente determinista —que siempre produce la misma
decisión ante el mismo texto— es una intervención con fundamento. Dhage (2026) es
el trabajo más cercano al de este documento en motivación, aunque procede por
restricciones de ejecución del intérprete y no por clasificación de intención.

El dato de §5.3 —varianza de 1.2× a 49× entre corridas sin el clasificador, en
token de entrada por caso— es una medición directa de ese no-determinismo en el
arnés de este estudio.

### 2.7 Ingeniería de arneses

Tres trabajos de 2026 definen el campo sobre el que este documento se apoya
directamente.

**Natural-Language Agent Harnesses** (Pan et al., 2026, arXiv:2603.25723, Tsinghua
Shenzhen e HIT Shenzhen) parte de que "el desempeño del agente depende cada vez más
de la ingeniería del arnés, pero el diseño del arnés suele estar enterrado en código
de controlador y en convenciones específicas del tiempo de ejecución, lo que
dificulta transferirlo, compararlo y estudiarlo como objeto científico". Propone
externalizar la lógica de control de alto nivel como un artefacto ejecutable
portable en lenguaje natural, y evalúa viabilidad operacional, ablación de módulos
y migración de código a texto. **Relación con este trabajo:** es el marco
conceptual más cercano. Este documento externaliza *una parte* de esa lógica —la
decisión de ruta— a un artefacto de lenguaje natural, aunque la decisión misma se
toma en un componente tipado externo (§4.2), no en el artefacto.

**HarnessDev** (Wu et al., 2026, arXiv:2609.01437, 19 autores) introduce un
benchmark que desplaza la unidad de evaluación desde las salidas de tarea hacia la
infraestructura ejecutable, con dos etapas (creación y evolución), y evalúa cada
arnés construido en capacidad (éxito de tarea en benchmarks reservados) y
eficiencia (costo en tokens de ejecución). Reporta 2.207 instancias de evaluación
sobre seis modelos creadores y cuatro dominios. Encuentra que los arneses generados
quedan muy por detrás de las referencias hechas por humanos en código e
investigación, y con gran variación de costo de ejecución. **Relación con este
trabajo:** confirma que el arnés es una variable de primera importancia con el
modelo fijo —el supuesto que sostiene el diseño A/B de §4.4— y aporta el antecedente
de medir *costo en tokens de ejecución* como métrica de primera clase, lo que aquí
se retoma en §5.2.

**Harness Handbook** (Wang et al., 2026, arXiv:2607.13285, Tencent HY LLM Frontier,
Indiana, Maryland, Georgia y NUS) parte de que, antes de modificar un arnés, hay que
identificar las ubicaciones de código que implementan el comportamiento objetivo, y
que esa localización de comportamiento es un cuello de botella central: "los
arneses de producción suelen ser grandes, muy acoplados y con comportamiento
distribuido entre archivos, funciones, etapas de ejecución y transiciones de
estado". Propone una representación centrada en comportamiento y una divulgación
progresiva guiada por comportamiento, y encuentra mejoras con *menos tokens de
planificador*. **Relación con este trabajo:** aporta el antecedente directo de medir
tokens de sobrecarga (aquí, el payload de la guía en §5.2) y confirma que reducir
la improvisación de un agente —hacia dónde mirar— es un problema abierto con valor
medido.

### 2.8 Posicionamiento: el hueco

Los tres trabajos de §2.7 externalizan la lógica del arnés a **texto** (NLAH), o
evalúan arneses como artefactos (HarnessDev), o representan el arnés para volverlo
navegable (Harness Handbook). El enrutado de inferencia de §2.4 decide entre
**componentes de cómputo**. La calibración de §2.5 mide la confianza de **un modelo
que responde**.

No se encontró, en la revisión realizada, un trabajo que use un **modelo de decisión
tipado —con un esquema cerrado y fijo de categorías— como clasificador de ruta
dentro de un arnés**, cuya salida sea una guía de ruta inyectada en el turno, y que
se evalúe por reproducibilidad de la ruta en lugar de por calidad de la respuesta.
Ese es el espacio que este documento ocupa. Se declara como hueco de revisión
bibliográfica limitada, no como novedad absoluta (§7.3).

---

## 3. Contexto del arnés

### 3.1 El arnés

El sujeto de este estudio es **Hermes Agent** (Nous Research), un arnés de agente para
modelos de lenguaje que organiza la conversación en turnos, expone herramientas al
modelo (ejecución de código, terminal, archivos, búsqueda web, memoria persistente),
y permite extender su comportamiento mediante **plugins** que se registran en
proceso.

La instancia estudiada es la de un **solo operador**: el autor de este documento la
usa como asistente personal en producción, con acceso a su correo, su casa
automatizada, sus finanzas y su base de conocimiento. Esa condición —un operador, un
arnés, uso real diario— define el alcance del estudio y también sus límites (§7).

### 3.2 El modelo de tres capas

El operador mantiene una separación explícita de tres capas de conocimiento, que es
el sustrato sobre el que opera la decisión de ruta:

| Capa | Qué contiene | Naturaleza |
|---|---|---|
| 1 | Base de investigación cruda, por fecha y línea temática | Materia prima, no consolidada |
| 2 | Wiki LLM — conocimiento verificado y consolidado | Fuente de verdad declarada |
| 3 | Código: repositorios que materializan mejoras del arnés | Artefacto ejecutable |

La regla que gobierna las transiciones es: de la capa 1 a la 2 solo pasa lo que se
verifica; de la 2 a la 3 solo lo que amerita ser código. El conocimiento acumulado
pertenece siempre a la capa 2; el producto final de un hilo de mejora del arnés es
un plugin (capa 3).

**Por qué importa para este trabajo.** La decisión de ruta es, en esencia, la
decisión de *a qué capa ir*. Un turno que pregunta "cómo funciona el protocolo de
memoria holográfica" debería ir a la capa 2 (wiki) o a la 1 (base de investigación);
un turno que pide "programa el respaldo" debería ir a la capa 3 (código). Sin una
declaración de ruta, el agente elige capa de forma implícita en cada turno.

### 3.3 Las fuentes y su acceso

El arnés expone las fuentes a través de tres mecanismos distintos, y esa diferencia
es la que hace que la ruta no sea trivial:

- **Herramientas directas** — `fact_store` (memoria persistente de hechos),
  `session_search` (historial de conversaciones), `read_file` (lectura de
  archivos). No requieren cargar nada previo.
- **Skills** — procedimientos almacenados como texto. Para usarlos hay que
  consultar el catálogo (`skills_list`) y cargar el que corresponda
  (`skill_view`). La carga consume contexto.
- **Archivos del wiki** — una carpeta de markdown en la máquina local, no un sitio
  web. Se accede con `search_files` y `read_file`.

**Observación que motivó el diseño.** Esta última categoría es la que más se
prestaba a confusión en el arnés estudiado: en pruebas previas, el texto de guía que
decía "busca en el wiki local" fue interpretado por el modelo como una búsqueda en
internet, porque "wiki" en el vocabulario del modelo se asocia a web. La corrección
—nombrar la herramienta exacta y aclarar que es una carpeta local— está incorporada
en la versión final del mecanismo (§4.3).

### 3.4 Los puntos de extensión

El arnés ofrece dos puntos de extensión relevantes, y su diferencia determina la
arquitectura elegida (§4.1):

- **`pre_llm_call`** — se ejecuta una vez por turno, antes de la llamada al modelo.
  Recibe el mensaje del usuario y puede devolver contexto que se anexa al turno. No
  rompe la caché del prompt porque se anexa al mensaje, no al sistema.
- **`pre_tool_call`** — se ejecuta antes de cada invocación de herramienta, y puede
  **vetar** la llamada o modificar sus argumentos.

Ambos están disponibles tanto en la forma de *plugin en proceso* como en la de
*gancho de shell* (subproceso). La diferencia técnica entre las dos formas es
decisiva para este trabajo y se discute en §4.1.

---

## 4. Método

### 4.1 Decisión de arquitectura: plugin en proceso

La primera decisión de diseño fue la forma del mecanismo. Se evaluaron dos:

| Criterio | Plugin en proceso | Gancho de shell |
|---|---|---|
| Estado entre invocaciones | Compartido | Ninguno (subproceso nuevo) |
| Puede compartir decisión entre `pre_llm_call` y `pre_tool_call` | Sí | No |
| Costo por turno cuando no aplica | Cero | Arranque de proceso |
| Determinismo del código | Alto | Alto |

Se eligió **plugin en proceso**. La razón determinante es que la decisión de ruta
tomada en `pre_llm_call` debe estar disponible en `pre_tool_call`, para poder
verificar que el turno efectivamente consultó la fuente que la ruta indicaba. Un
gancho de shell no puede sostener ese estado: cada invocación es un subproceso sin
memoria de la anterior.

Se consideró también la alternativa de no usar código y en su lugar auto-cargar un
skill con las instrucciones de ruta. Se descartó por dos motivos: un skill es texto
que el agente *puede* seguir u omitir, lo que reintroduce exactamente la
improvisación que el trabajo busca reducir; y su costo es fijo por sesión
(aproximadamente 870 tokens), mientras que el mecanismo elegido solo paga cuando
clasifica.

### 4.2 El clasificador

El componente central es un clasificador que recibe el texto del turno y devuelve
una de **seis rutas mutuamente excluyentes** con una confianza declarada.

La implementación usa **Jev** (`~typesafe/jev-latest`), un modelo de decisión que
recibe un esquema de pregunta tipada —tipo `choice`, con un conjunto cerrado de
criterios— y devuelve la opción elegida, su confianza y la distribución de
probabilidad sobre todas las opciones.

Las declaraciones de criterio son el artefacto central del mecanismo, y se
reproducen **verbatim** en el Apéndice A. Su forma es deliberada: cada ruta se
declara por el **resultado esperado**, no por la tarea.

- `skill` — "El texto implica explícitamente o implícitamente la ejecución de una
  tarea que puede ejecutarse como un proceso de computadora."
- `research` — "Cualquier proceso o redacción que implique investigar algo."
- `memory` — "Obtener o recuperar cualquier dato que implique recuperar facts,
  datos persistentes cortos, reglas, criterios. Siempre y cuando el valor
  resultante sean redacciones o datos cortos, no más de un párrafo."
- `history` — "Cualquier acción que implique la recuperación de historial o
  recuerdos de sesiones o conversaciones pasadas."
- `user` — "El texto se refiere a la persona del usuario ({nombre}) o pide
  información sobre él..." (con la exclusión explícita de encargos).
- `others` — "Lo que no encaja en las choices anteriores."

**Una decisión de diseño que vale registrar.** La ruta `user` exige el nombre del
usuario dentro de su declaración. En lugar de mantener una lista de nombres
codificada, el nombre se lee del archivo de perfil real del arnés
(`~/.hermes/memories/USER.md`) mediante una heurística de frecuencia sobre las
entradas del perfil. Esto elimina una lista codificada que había existido en
versiones previas del clasificador y que producía coincidencias falsas.

### 4.3 La guía de ruta

La salida del clasificador no se ejecuta: se traduce a una **guía en lenguaje
natural** que se anexa al turno. Las guías tienen una estructura fija de pasos
numerados, y sus tres propiedades de diseño son:

1. **Nombrar la herramienta exacta**, no la intención. La guía de `research` no dice
   "busca información": dice que cargue el skill `wiki-llm-rosero` con `skill_view`,
   y que use `search_files` sobre la carpeta local, aclarando entre paréntesis que
   *no es internet*.
2. **Encadenar con condición de salida explícita.** Cada guía tiene la forma "si
   esto no alcanza, entonces aquello", de modo que el agente no quede bloqueado
   cuando la fuente indicada no tiene el dato.
3. **Acotar la libertad, no eliminarla.** La guía de `memory`, por ejemplo, indica
   el paso 1 y el paso 2, y en el paso 3 dice explícitamente "resuelve con libertad,
   como en `others`".

El texto completo de las seis guías se reproduce en el Apéndice B.

**La ruta de escape.** `others` es la ruta que el clasificador elige cuando ninguna
declaración aplica. Su guía dice: *"Sin ruta definida para este turno. No cargues
skills ni busques en fuentes: resuelve directamente con tu criterio y responde."*

Es decir: `others` **no inyecta una ruta, inyecta la ausencia de ruta**. El diseño es
intencional —es el mecanismo por el que el clasificador declara que no sabe y
devuelve el turno al modelo sin orientación— y se documenta como tal, porque a
primera lectura su texto puede parecer contradictorio (§6.3).

### 4.4 Diseño experimental

Se realizó un experimento A/B con **el modelo congelado** para aislar el efecto del
mecanismo.

**Condiciones.**
- **SIN** — el arnés sin el plugin. Configuración `hooks: None`.
- **CON** — el arnés con el plugin activo.

**Modelo.** `deepseek-v4.1-flash` en las dos condiciones, sin cambios de parámetros.

**Casos.** 10 turnos reales, elegidos para cubrir las seis rutas y tareas
representativas del uso diario: verificación de infraestructura, estado de
repositorios, cálculos de dimensionamiento, trámites administrativos, control del
hogar, configuración de un ERP, un proyecto de videovigilancia, una pregunta de
trato personal y un caso sin ruta definida.

**Repeticiones.** Tres corridas completas por condición, para poder medir varianza
intra-condición.

**Instrumentación.** Cada corrida registra, por caso: identificador de sesión,
duración en segundos, código de retorno, número de ciclos, tokens de entrada,
tokens de salida, y la **secuencia ordenada de herramientas invocadas**. La ruta
inyectada se recupera de la base de estado del arnés, no del texto de la respuesta.

**Métricas.**
- **Eficacia de ruta** — si el caso consulta una fuente primaria *antes* de
  ejecutar. Es la métrica primaria, porque mide directamente lo que el mecanismo
  busca: que la consulta preceda a la acción.
- **Costo** — tokens de entrada por turno, y tokens del payload inyectado.
- **Varianza** — dispersión de tokens de entrada por caso entre corridas de la
  misma condición.

**Restauración.** La configuración del arnés se restauró byte a byte tras cada
corrida, y se verificó con suma de comprobación. El experimento no dejó el plugin
instalado.

### 4.5 Evaluación del clasificador

En paralelo al A/B se evaluó el clasificador de forma directa: **24 textos** con una
ruta esperada asignada por el operador, clasificados en una sola corrida. Los textos
se seleccionaron para cubrir las seis rutas, con énfasis en los casos de frontera:
peticiones en primera persona que son encargos y no información sobre el usuario, y
textos declarativos sobre el entorno.

Los 24 casos y las rutas crudas devueltas por el clasificador están en el Apéndice C.

---

## 5. Resultados

*Esta sección reporta datos sin interpretación. La interpretación está en §6.*

### 5.1 Eficacia de ruta

Proporción de casos que consultan una fuente primaria antes de ejecutar, en tres
corridas por condición:

| Corrida | SIN | CON |
|---|---|---|
| 1 | 3/10 | 9/10 |
| 2 | 6/10 | 10/10 |
| 3 | 5/10 | 10/10 |
| **Media** | **4.7** | **9.7** |

### 5.2 Costo

**Payload inyectado** (una sola guía por turno):

| Ruta | Caracteres | Tokens aprox. |
|---|---|---|
| skill | 537 | 134 |
| research | 439 | 109 |
| user | 435 | 108 |
| memory | 415 | 103 |
| history | 258 | 64 |
| others | 160 | 40 |

Valor representativo: **≈93 tokens por turno** (promedio simple de las seis
guías). Ponderado por las rutas que el clasificador efectivamente eligió en el
experimento —`skill` 3, `research` 3, `memory` 2, `history` 1, `user` 1 sobre 10
casos— el valor es **≈111 tokens por turno**, porque las dos rutas más frecuentes
(`skill` y `research`) son también las dos más extensas.

**Descomposición del aumento de tokens.** Aumento total observado de tokens de
entrada entre condiciones (137,949 tokens):

| Componente | Tokens | Proporción |
|---|---|---|
| Payload de la guía, ponderado (≈111 tok × 76 ciclos) | ≈8,413 | 6.1 % |
| Salida de herramientas (bytes ÷ 4) | +120,286 | 87.2 % |
| **Suma explicada** | — | **93.3 %** |

Se reportan ambos valores del payload —93 simple y 111 ponderado— porque la
diferencia es informativa: la estimación por promedio simple subestima el costo real
en este conjunto de casos, dado que las guías más largas fueron las más elegidas.

**Totales por condición (corrida v4: 10 casos por condición).** No son sumas sobre
las tres corridas, sino de la corrida instrumentada con la versión final del
mecanismo. Se reportan como suma de los casos con datos completos: en la condición
SIN mecanismo, el caso de dimensionamiento de NVR terminó por tiempo excedido y no
registró tokens, de modo que los totales de esa condición corresponden a 9 casos
mientras los de CON corresponden a 10.

| Métrica | SIN (9 casos) | CON (10 casos) | Δ |
|---|---|---|---|
| Ciclos | 53 | 76 | +43.4 % |
| Tokens de entrada (suma) | 191,640 | 329,589 | +72.0 % |
| Tokens de salida (suma) | 33,679 | 38,893 | +15.5 % |
| Tokens totales | 225,319 | 368,482 | +63.5 % |
| Segundos (suma) | 921 | 564 | −38.7 % |

**Sobre los totales anteriores.** Se advierte una limitación de comparabilidad: las
cifras de las dos columnas no cubren el mismo número de casos, porque en la
condición SIN el caso de NVR no completó y por lo tanto no aportó tokens. El
aumento de tokens de entrada de +72.0 % está calculado sobre esa base desigual, y
por eso la comparación principal del documento es la métrica por caso de §5.1 y §5.3,
no estas sumas.

### 5.3 Varianza

Dispersión de tokens de entrada **por caso**, entre las tres corridas de la
condición SIN (donde no hay ninguna intervención que estabilice):

| Caso | Corrida 1 | Corrida 2 | Corrida 3 | Razón |
|---|---|---|---|---|
| Frigate | 21,282 | 65,160 | 1,326 | **49.1×** |
| Don Bosco | 1,603 | 6,614 | 375 | 17.6× |
| Odoo | 48,749 | 6,033 | 10,316 | 8.1× |
| Trato personal | 1,370 | 8,086 | 8,198 | 6.0× |
| Chiste (sin ruta) | 921 | 1,333 | 309 | 4.3× |
| Hotel | 73,444 | 45,661 | 23,774 | 3.1× |
| Holding | 10,856 | 19,808 | 7,669 | 2.6× |
| Git `~/developers` | 31,765 | 18,760 | 13,256 | 2.4× |
| ONG Panamá | 102,651 | 105,660 | 126,417 | 1.2× |

**Nota sobre los casos cubiertos.** La tabla incluye 9 de los 10 casos. El caso
restante (dimensionamiento de NVR con GPU) no se incluye porque **no completó en dos
de las tres corridas** de la condición SIN: en la corrida v3 registró 121,494 tokens
de entrada, y en las corridas v1 y v4 terminó por tiempo excedido sin registrar
tokens. Es, por lo tanto, el caso con mayor dispersión observada del conjunto, y se
declara fuera de la tabla en lugar de estimar sus valores faltantes.

**Consistencia de la primera fuente.** Casos que empiezan consultando la misma
primera fuente en las tres corridas: **3/10 sin** el mecanismo, **5/10 con** él.
Firmas distintas de secuencia de herramientas sobre 30 posibles: **27 sin**, **29
con**. Racha máxima de la misma herramienta consecutiva: 4→7→9 sin, 8→10→4 con.

**Rutas inyectadas** (3 corridas × 10 casos = 30 turnos):

| Ruta | Veces |
|---|---|
| skill | 6 |
| research | 6 |
| memory | 4 |
| history | 2 |
| user | 2 |
| others | 0 |

### 5.4 El clasificador frente al juicio del operador

| Métrica | Resultado |
|---|---|
| Coincidencia con la etiqueta inicial del operador | 21/24 |
| Coincidencia con la etiqueta final del operador | **24/24** |

Por ruta: `skill` 6/6, `research` 3/3, `memory` 3/4, `history` 3/3, `user` 9/9,
`others` 1/1.

Las **tres divergencias** de la etiqueta inicial, con la ruta cruda devuelta por el
clasificador y la distribución de probabilidad:

```
1) "haceme un informe de videovigilancia"
   etiqueta inicial del operador: research
   clasificador: skill, conf 0.85
     skill 0.88  research 0.08  memory 0  history 0  user 0  others 0.04
   Resolución del operador: ambas rutas convergen al resultado; no es error grave.

2) "El VPS de Alan corre en Hetzner"
   etiqueta inicial del operador: memory
   clasificador: others, conf 0.56
     skill 0.01  research 0.01  memory 0.22  history 0  user 0.14  others 0.62
   Resolución del operador: el clasificador acertó — no supo manejarlo con las
   otras opciones y lo derivó a la ruta de escape.

3) "como funciona la memoria holografica"
   etiqueta inicial del operador: memory
   clasificador: research, conf 0.32
     skill 0.01  research 0.44  memory 0.37  history 0  user 0  others 0.18
   Resolución del operador: el clasificador acertó — es una investigación.
```

**La confianza no anticipa el acierto.** Los casos resueltos a favor del
clasificador tenían confianza 0.56 (caso 2) y 0.32 (caso 3) — las dos confianzas
más bajas de las tres divergencias. La divergencia con **mayor confianza (0.85)**
fue la única que el operador resolvió declarando convergencia, no acierto del
clasificador. En las demás rutas la confianza fue alta (0.74 a 1.00) sin que eso
aporte información adicional: los aciertos de `user` (9/9) promediaron 0.93 y los de
`skill` (6/6) promediaron 0.95.

### 5.5 Comportamiento de la ruta de escape

La ruta `others` **no se ejecutó ninguna vez** en los 30 turnos del A/B, aunque el
A/B incluía un caso sin ruta definida. El clasificador resolvió ese caso hacia
`skill`.

En la corrida del clasificador sobre los 24 casos, `others` se eligió una vez, en el
caso 2 de §5.4.

### 5.6 Comparación con un modelo de lenguaje como clasificador

Se comparó el clasificador tipado con un modelo de lenguaje (`openai/gpt-5-mini`)
sobre el mismo conjunto:

| Métrica | Clasificador tipado | Modelo de lenguaje (`openai/gpt-5-mini`) |
|---|---|---|
| Latencia mediana por caso | 556 ms | 7,033 ms — **12.7× más lento** |
| Latencia media por caso | 577 ms | 6,760 ms — 11.7× más lento |
| Costo medio por clasificación | US$0.0000261 | US$0.0008753 — **33.5× más caro** |
| Coincidencia entre ambos | — | 11/15 |

La comparación de latencia se reporta por mediana y por media porque difieren: la
razón de medianas es 12.7× y la de medias 11.7×. La diferencia se debe a que la
distribución del modelo de lenguaje tiene una cola más larga (hasta 10,253 ms) que la
del clasificador tipado (hasta 943 ms).

### 5.7 Estado de la implementación

El mecanismo está **prototipado y evaluado, no instalado** en producción. La
versión evaluada del gancho son 7,258 bytes (archivo `ruta-jev-v4.py`); la configuración del arnés quedó con
`hooks: None` al cierre del experimento. El repositorio del proyecto contiene el
código, y los datos crudos de todas las corridas están en `evidence/`.

---

## 6. Discusión

### 6.1 Qué muestran los datos

**La métrica primaria se mueve, y se mueve por categoría, no de forma continua.**
La proporción de casos que consultan una fuente primaria antes de ejecutar pasa de
una media de 4.7 (rango 3–6 sobre 10) a una media de 9.7 (rango 9–10 sobre 10). Con
el mecanismo, **las tres corridas están en el mismo régimen**; sin él, la dispersión
entre corridas (3, 6, 5) es del mismo orden que la distancia al valor con mecanismo.

Esto es relevante porque el efecto no es un desplazamiento gradual: la intervención
mueve el comportamiento a una banda distinta. La consecuencia práctica es que la
afirmación sostenible no es "mejora en promedio" sino **"deja de haber corridas
malas"**.

**La consistencia de ruta mejora, pero modestamente.** La misma primera fuente en las
tres corridas: 3/10 sin mecanismo, 5/10 con él. Es una mejora de 2 casos sobre 10, y
la firma de la secuencia de herramientas apenas cambia (27 vs 29 distintas de 30).

Aquí hay una lectura que el dato no sostiene y conviene descartar explícitamente: el
mecanismo **no** fija una ruta idéntica en cada caso. Fija el punto de partida
—consultar primero— y deja la secuencia libre. Esto es coherente con el objetivo
declarado (acotar la improvisación, no eliminar la libertad), pero significa que la
reducción de varianza de *secuencia* es pequeña por diseño.

**El costo es despreciable frente al efecto.** El payload es de 93 a 111 tokens por
turno y explica entre el 6.1 % y el 7.2 % del aumento de tokens de entrada. El 87.2 %
del aumento es salida de herramientas, es decir, contenido que el agente
efectivamente consultó. Sumadas, ambas explican el 93.3 %.

La consecuencia metodológica es una separación que conviene mantener: **el costo del
mecanismo y el costo de las consecuencias del mecanismo son dos cosas distintas.**
Atribuir el aumento total de tokens al payload sería incorrecto; el aumento se debe
mayoritariamente a que el agente ahora *sí consulta*, y consultar cuesta tokens.

**La varianza de medición excede el efecto de costo.** Dentro de la condición SIN
mecanismo, el mismo caso consume entre 1.2× y 49.1× más tokens según la corrida. Con
esa dispersión, ninguna afirmación sobre el efecto del mecanismo en costo o latencia
es sostenible en un diseño de tres corridas. Por eso §5.2 reporta medianas y sumas
etiquetadas como tales, y no promedios comparados.

**El clasificador coincide con el operador, pero el dato interesante no es la
coincidencia.** 24/24 tras la revisión del operador. Lo informativo está en las tres
divergencias y en cómo se resolvieron: dos de ellas el operador las reasignó a favor
del clasificador, lo que indica que la etiqueta inicial del operador —no la decisión
del clasificador— era la que necesitaba corrección. En la tercera (la expresión
modal española) el operador resolvió que ambas rutas **convergen**, y por lo tanto
que el error no es grave.

### 6.2 El criterio del error tolerable

Un punto de diseño que surgió durante la evaluación y que conviene hacer explícito,
porque cambia cómo se debe juzgar el clasificador: **un error de clasificación entre
rutas que convergen al mismo resultado no es un fallo grave.**

La formulación del operador es precisa: ese tipo de error "solo le agrega una capa
más de ciclos al LLM", y tratar de resolverlo ajustando el payload sería
sobre-ingeniería.

La consecuencia práctica es que la métrica de coincidencia exacta (24/24) **no es el
indicador de calidad apropiado** para este mecanismo. Una métrica mejor sería cuántos
errores producen una ruta que no puede llegar al resultado. Con los datos de este
estudio ese número es cero en los 24 casos, porque las tres divergencias caían en
rutas que alcanzan el resultado por vías distintas.

Esto conecta con la §2.5: la literatura de abstención y calibración (Mao, Mohri y
Zhong, 2023; Liu et al., 2025) modela el costo del error. Aquí el costo del error no
es uniforme entre pares de rutas: `research`→`skill` es barato (una capa de ciclos
más); `skill`→`others` sería costoso (ninguna orientación). El clasificador no
distingue esa asimetría.

### 6.3 La ruta de escape: por qué su texto parece contradictorio

`others` no inyecta una ruta: inyecta la instrucción de no buscar. Leída aislada, su
guía —"no cargues skills ni busques en fuentes: resuelve directamente con tu
criterio"— parece contradecir el propósito del mecanismo, que es precisamente
orientar la búsqueda.

El diseño es intencional y resuelve un problema real: sin una ruta de escape, el
clasificador estaría forzado a elegir una de las cinco rutas restantes incluso
cuando ninguna aplica, y en ese caso inyectaría una orientación equivocada con
confianza alta. `others` es el mecanismo por el que el clasificador **declara que no
sabe** y devuelve el turno al modelo sin orientación.

El operador lo formuló así: es lo que en el comportamiento humano se llama libre
albedrío, con la diferencia de que el libre albedrío humano opera sobre una lógica
implícita de reglas, mientras que el modelo no la tiene. `others` no llena ese vacío
—lo deja abierto deliberadamente.

**Lo que el dato muestra.** En los 30 turnos del A/B, `others` no se ejecutó ninguna
vez, incluido el caso que el A/B había etiquetado como sin ruta. En la corrida de
clasificación directa, `others` se eligió 1 vez de 24 (caso 2 de §5.4). Es decir:
**la ruta de escape existe y funciona cuando se la necesita, y no se usa como
comodín.** Ese es exactamente el comportamiento deseado, y es un dato favorable que
no estaba garantizado.

Lo que **no** está medido es la consecuencia de `others`: cuánto empeora la conducta
del turno cuando no hay orientación. Es una línea abierta (§8).

### 6.4 Límite reportado: la expresión modal española

El caso más informativo del estudio es el único donde el clasificador falla de forma
sostenida.

```
Texto:  "haceme un informe de videovigilancia"
Ruta:   skill (conf 0.85)  —  skill 0.88  research 0.08  others 0.04
```

El contexto es que la variedad de español del operador (rioplatense) usa *haceme*
como forma de encargo, donde otra variedad usaría *confecciona* o *escribe*. Es un
acto de habla indirecto en el sentido de Searle (1975): la forma es imperativa, la
fuerza es de pedido, y el resultado esperado es una investigación, no una ejecución
de proceso.

**Se aplicó un analizador morfosintáctico** (Stanza 1.14.0, modelo `es` de Stanford NLP) para
verificar la hipótesis de que el problema era detectable por forma verbal:

```
haceme  → hacer   VERB  Mood=Ind|Number=Sing|Person=1|Tense=Pres|VerbForm=Fin
un      → uno     DET
informe → informe NOUN
de      → de      ADP
videovigilancia → videovigilancia NOUN
```

**El resultado refuta la hipótesis.** `haceme` se analiza como verbo conjugado en
indicativo (primera persona singular), no como imperativo, y **no hay infinitivo**
en la oración. La regla formal que el arnés usaba para detectar encargos —modal
conjugado seguido de infinitivo, del tipo "¿puedes pasarme...?"— no aplica, porque
el patrón no está presente.

Esto sitúa el límite exactamente en el espacio que Haagsma, Nissim y Bos (2019)
delimitan: *haceme* es un modismo rioplatense con enclítico, no un modal estándar, y
las reglas basadas en la forma verbal no lo capturan. El analizador sintáctico
tampoco, porque el problema no es de categoría gramatical sino de **uso dialectal**.

**La consecuencia de diseño es concreta.** El ajuste de modismos no puede
implementarse como regla morfosintáctica. Las vías que quedan son: (a) incorporar la
variedad dialectal del operador a las declaraciones del clasificador, de modo que
"haceme + X" se lea como encargo investigativo; o (b) aceptarlo como error tolerable
bajo el criterio de §6.2, dado que `skill` y `research` convergen.

El propio operador dejó abierta la segunda vía al señalar que, con otro verbo, el
resultado podría diferir. Es un caso donde el error no se resuelve por payload.

### 6.5 Qué se sostiene y qué no

**Se sostiene:**

- El mecanismo mueve la proporción de casos que consultan antes de ejecutar, de una
  banda de 3–6/10 a una banda de 9–10/10 con el modelo congelado.
- Su payload es de 93 a 111 tokens por turno, entre el 6.1 % y el 7.2 % del aumento de tokens de entrada.
- El clasificador coincide con el juicio del operador en 24/24 casos tras revisión.
- La ruta de escape no se usa como comodín (0/30 en el A/B) y funciona cuando
  corresponde (1/24 en clasificación directa).
- La confianza declarada no anticipa el acierto.

**No se sostiene, y se declara:**

- Que el mecanismo mejore la **calidad** de la respuesta. No se midió; la
  operacionalización de "mejor" no se definió, y el diseño A/B no la captura.
- Que el mecanismo reduzca el **costo** o la **latencia**. La varianza intra-condición
  (1.2×–49×) excede cualquier efecto atribuible.
- Que el mecanismo reduzca de forma importante la **varianza de secuencia**. La
  mejora medida es de 2 casos sobre 10 en la primera fuente.
- Que los resultados **generalicen** a otros arneses, otros modelos u otros
  operadores. El estudio es de un caso (§7.3).

### 6.6 Dónde se ubica el aporte frente a la literatura

Los tres trabajos de referencia de §2.7 permiten ubicar el aporte con precisión:

- **NLAH** externaliza la lógica de control a un artefacto de lenguaje natural. Este
  trabajo externaliza **una** decisión —la de ruta— pero la toma en un componente
  tipado externo, no en el artefacto de lenguaje natural. La guía inyectada *sí* es
  un artefacto de lenguaje natural; la decisión que la selecciona no lo es.
- **HarnessDev** mide costo en tokens de ejecución como métrica de primera clase.
  Este trabajo hace lo mismo para el payload (93–111 tok) y para las consecuencias
  (87.2 % del aumento), y agrega la separación entre costo propio y costo derivado
  (§6.1).
- **Harness Handbook** mide tokens de planificador y confirma que reducir la
  improvisación de un agente tiene valor medido. Este trabajo mide el efecto de esa
  reducción en la *secuencia de obtención*, no en la localización de código.

Lo que ninguno de los tres hace, según la revisión realizada, es usar un **modelo de
decisión con esquema cerrado y fijo como clasificador de ruta dentro del arnés**,
evaluado por reproducibilidad de ruta. Ese es el hueco que este documento ocupa.

---

## 7. Amenazas a la validez

Se adopta el esquema de cuatro categorías del reporte de estudios de caso en
ingeniería de software (Runeson y Höst, 2009), con el desarrollo posterior de Feldt
et al. (2010) y Sjøberg et al. (2023).

### 7.1 Validez de constructo

*¿Las métricas miden lo que dicen medir?*

**La métrica primaria es una operacionalización, no el objetivo.** "Consultar una
fuente primaria antes de ejecutar" es una aproximación a "no improvisar la ruta". La
aproximación es razonable —si el agente consulta antes de actuar, no improvisó el
punto de partida— pero es una medida de proceso, no de resultado. Un agente podría
consultar la fuente y luego ignorarla; el diseño no lo detecta.

**Mitigación parcial.** Se midió también la consistencia de la primera fuente
(§5.3), que es menos sensible a esa objeción porque no depende de la posición
temporal sino de la identidad de lo consultado. Ambas métricas se mueven en la misma
dirección, aunque con magnitudes distintas (efecto grande en la primera, modesto en
la segunda).

**El payload se mide en tokens estimados.** Los valores de §5.2 derivan de una
estimación de caracteres a tokens (÷4), no de contar tokens con el tokenizador del
modelo. El orden de magnitud es sólido; la cifra exacta no lo es.

**La etiqueta de ruta esperada es del operador.** En la evaluación del clasificador,
el patrón de referencia lo fija el propio operador del arnés estudiado. Esto tiene
una ventaja —es el criterio de uso real— y un riesgo: el criterio podría ser
idiosincrático. En dos de las tres divergencias la etiqueta inicial del operador fue
la que se corrigió, lo que indica que el patrón de referencia no era estable antes de
la revisión. Un patrón fijado *a posteriori* sobre el mismo conjunto que se evalúa
introduce circularidad.

**Mitigación parcial.** Las etiquetas finales se fijaron caso por caso con
justificación declarada, y las tres divergencias se reportan con sus distribuciones
de probabilidad completas (§5.4) para que un lector pueda juzgar la decisión.
Aun así, la circularidad no se elimina: es la principal debilidad metodológica de
este documento.

### 7.2 Validez interna

*¿Hay explicaciones alternativas para los resultados observados?*

**La varianza intra-condición es la amenaza principal.** El mismo caso consume entre
1.2× y 49.1× más tokens de entrada según la corrida (§5.3). Con esa dispersión, la
comparación entre condiciones debería estar respaldada por muchas más repeticiones
que las tres realizadas. **Las métricas de costo y latencia no son concluyentes con
este diseño**, y así se reportan en §6.5.

**El efecto en la métrica primaria es más robusto** precisamente porque las tres
corridas de cada condición caen en bandas separadas sin solapamiento (3–6 vs 9–10).
Pero una separación de bandas con n=3 por banda no permite un intervalo de confianza
inferencial.

**No se aisló el componente responsable.** El mecanismo tiene tres partes: el
clasificador, la guía, y el punto de inyección. El diseño A/B comparó el paquete
completo contra nada. No se realizó una ablación (por ejemplo, inyectar una guía
fija sin clasificador) para determinar cuánto aporta cada parte. **Por lo tanto, este
estudio no puede atribuir el efecto al clasificador en particular.**

Existe evidencia indirecta en la dirección de que la variación de ruta importa: las
rutas inyectadas variaron entre corridas (§5.3), lo que significa que el clasificador
leyó texto distinto y respondió distinto, en lugar de emitir una constante. Pero eso
no es lo mismo que una ablación.

**Confusión de orden.** Las corridas se ejecutaron en secuencia (v1, v3, v4), y las
condiciones dentro de cada versión. No se aleatorizó el orden, ni se intercalaron las
condiciones. Un efecto de calentamiento de caché, de carga de la máquina o de
degradación del proveedor del modelo no puede descartarse con el diseño realizado.

**El segundo recibo de actualización.** Durante el período de medición se ejecutó una
actualización del arnés (de la versión 0.21.3 a la 0.21.4, 2026-09-23). Se detectó un
registro de actualización que el estudio no lanzó, con marca de tiempo previa al
reinicio del servicio. La configuración se restauró byte a byte y se verificó con
suma de comprobación tras cada corrida, pero **no puede afirmarse con certeza que las
corridas anteriores y posteriores a la actualización corrieran sobre el mismo código
del arnés.** Esto es un contaminante conocido y no controlado.

### 7.3 Validez externa

*¿Generalizan los resultados?*

**Es un estudio de un solo caso, y así se declara.** Un arnés, un operador, un
modelo, diez tareas, tres corridas. La literatura de estudios de caso (Runeson y
Höst, 2009) admite este diseño para *generar* teoría y describir mecanismos, no para
generalizar a poblaciones. Las afirmaciones de este documento se limitan a lo
observado.

**El sujeto es atípico y eso corta en dos direcciones.** El operador mantiene una
estructura de tres capas de conocimiento explícita (§3.2) y un vocabulario de rutas
ya definido antes del experimento. Eso hace que el clasificador tenga categorías
naturales sobre las que operar —una condición favorable que un arnés sin esa
estructura no tendría. En sentido contrario, es un usuario técnico con uso diario
intensivo, lo que hace el caso más informativo que uno trivial.

**Riesgo de especificidad al proveedor.** El clasificador se implementó contra una
interfaz específica de un proveedor de modelos de decisión. El mecanismo
conceptual —clasificador tipado antes de la llamada al modelo, guía inyectada— es
independiente de esa elección; la implementación no.

**La limitación bibliográfica se declara.** La afirmación de §2.8 de que no existe
trabajo previo que use un clasificador tipado como enrutador de ruta dentro de un
arnés se basa en la revisión realizada, que no fue sistemática ni exhaustiva. **Debe
leerse como hueco de esta revisión, no como novedad establecida.** Un trabajo
relacionado no encontrado invalidaría esa afirmación sin invalidar los datos.

### 7.4 Validez de conclusión

*¿Las conclusiones se siguen de los datos?*

**Las afirmaciones cuantitativas están acotadas a lo medido.** La §6.5 separa
explícitamente lo que se sostiene de lo que no. En particular, no se afirma mejora de
calidad, ni de costo, ni de latencia.

**La coincidencia 24/24 requiere la lectura correcta.** Es coincidencia con el
patrón de referencia **después** de que el operador revisara tres casos. Reportarla
sin esa calificación sería inflar el resultado; por eso §5.4 reporta ambas cifras
(21/24 inicial, 24/24 final) y las distribuciones completas.

**No se reportan intervalos de confianza ni pruebas de significación** porque el
diseño (n=3 por condición, 10 casos) no los sostiene. Presentar un valor p sobre 30
observaciones con varianza de 49× sería un ejercicio de precisión falsa.

**El resultado más sólido del documento es probablemente el negativo**: que la
confianza declarada por el clasificador no anticipa el acierto (§5.4), y que la
hipótesis de detección morfosintáctica de modismos fue refutada por el analizador
(§6.4). Ambos son hallazgos que limitan el diseño, y ambos surgieron de verificar
una expectativa en lugar de asumirla.

---

## 8. Trabajo futuro

Las cinco líneas siguientes se derivan directamente de límites medidos, no de
posibilidades abiertas.

**1. Ablación del mecanismo.** Separar el efecto del clasificador del efecto de la
guía y del punto de inyección, con al menos una condición adicional que inyecte una
guía fija sin clasificador. Es el experimento que faltó (§7.2) y el que permitiría
atribuir el efecto a un componente.

**2. Más repeticiones por caso.** Para superar la varianza de 1.2×–49× se requiere un
número de corridas por caso que permita estimar dispersión. Es la condición previa
para poder afirmar algo sobre costo y latencia, hoy no sostenible.

**3. Ajuste dialectal del clasificador.** El límite de §6.4 no es resoluble por regla
morfosintáctica —el analizador lo confirmó—. La vía a explorar es incorporar la
variedad dialectal del operador a las declaraciones de criterio, de modo que el
contenido funcione sobre el uso real de la lengua y no sobre una forma verbal ideal.

**4. Medición de la consecuencia de la ruta de escape.** `others` deja el turno sin
orientación. Cuánto empeora la conducta en ese caso no está medido, y es medible con
el mismo diseño A/B, aislando los turnos donde el clasificador elige la escape.

**5. Métrica de error asimétrico.** Hoy la evaluación cuenta coincidencia exacta, que
§6.2 muestra que no es el indicador apropiado. Una métrica que pondere el costo por
par de rutas (barato si convergen, costoso si `skill`→`others`) mediría el mecanismo
por lo que importa.

---

## 9. Conclusión

Este documento describe un mecanismo acotado para hacer explícita y reproducible una
decisión que los arneses de agentes dejan implícita: de dónde obtener la información
antes de responder. El mecanismo externaliza esa decisión a un clasificador tipado
que corre antes de la llamada al modelo, elige una de seis rutas y anexa al turno una
guía en lenguaje natural.

El resultado principal, medido con el modelo congelado, es que la proporción de casos
que consultan una fuente primaria antes de ejecutar pasa de una banda de 3–6 sobre 10
a una banda de 9–10 sobre 10. El efecto se comporta como un cambio de régimen, no
como un desplazamiento gradual: el resultado sostenible no es "mejora en promedio"
sino que **deja de haber corridas malas**.

El costo es de 93 a 111 tokens por turno —entre el 6.1 % y el 7.2 % del aumento
observado de tokens de entrada— mientras que el 87.2 % del aumento corresponde a salida de
herramientas: el agente consulta más porque el mecanismo lo orienta a consultar. La
separación entre el costo del mecanismo y el costo de sus consecuencias es una de las
precisiones metodológicas que el estudio aporta.

El trabajo declara con igual énfasis lo que **no** se sostiene: no se midió mejora de
calidad de respuesta; el efecto sobre costo y latencia no es atribuible con esta
varianza; y no se realizó la ablación que permitiría atribuir el efecto al
clasificador en particular. Los dos hallazgos más firmes son negativos: la confianza
declarada por el clasificador no anticipa el acierto, y la hipótesis de detectar
expresiones modales dialectales por forma verbal fue refutada por el analizador
morfosintáctico.

El aporte se ubica en el espacio que la ingeniería de arneses de 2026 ha abierto:
externalizar la lógica de control para poder estudiarla. Este trabajo externaliza una
decisión, la mide, y reporta dónde funciona y dónde no.

---

## Referencias

Becker, E. y Soatto, S. (2024). *Cycles of Thought: Measuring LLM Confidence through
Stable Explanations*. arXiv:2406.03441.

Dhage, S. (2026). *Harness Engineering for Predictable Agentic Systems: An Empirical
Study of Deterministic Execution Constraints*. arXiv:2608.26197.

Feldt, R., Torkar, R., Angelis, L. y Samuelsson, M. (2010). *Towards Individual
Validation of Software Measures*. En: Validity Threats in Empirical Software
Engineering Research — An Initial Survey.

Grice, H. P. (1975). *Logic and Conversation*. En: Syntax and Semantics, vol. 3
(Speech Acts), pp. 41–58. Academic Press.

Guo, X., Wang, S., Ji, C. et al. (2025). *Towards Generalized Routing: Model and
Agent Orchestration for Adaptive and Efficient Inference*. arXiv:2509.07571.

Haagsma, H., Nissim, M. y Bos, J. (2019). *Casting a Wide Net: Robust Extraction of
Potentially Idiomatic Expressions*. arXiv:1911.08829.

Haverkate, H. (1979). *Impositive Sentences in Spanish: Theory and Description in
Linguistic Pragmatics*. North-Holland Linguistic Series 42, viii+194.

Hydari, M. Z. e Iqbal, R. (2026). *The Token Not Taken: Sampling, State, and the
Stochasticity of AI Agents*. arXiv:2606.08998.

Koo, Y., Lee, J., Park, D. et al. (2025). *Evaluating Large Language Models on
Understanding Korean Indirect Speech Acts*. arXiv:2502.10995.

Liu, X., Chen, T., Da, L. et al. (2025). *Uncertainty Quantification and Confidence
Calibration in Large Language Models: A Survey*. arXiv:2503.15850.

Ma, B., Li, Y., Zhou, W. et al. (2025). *Pragmatics in the Era of Large Language
Models: A Survey on Datasets, Evaluation, Opportunities and Challenges*. ACL 2025.
arXiv:2502.12378.

Mao, A., Mohri, M. y Zhong, Y. (2023). *Principled Approaches for Learning to Defer
with Multiple Experts*. ISAIM 2024. arXiv:2310.14774.

Mohammadi, M., Li, Y., Lo, J. et al. (2025). *Evaluation and Benchmarking of LLM
Agents: A Survey*. arXiv:2507.21504.

Pablos-Ortega, C. (2020). * Pragmatic variation in Spanish requests and apologies*.
Sociocultural Pragmatics 8(1):105–125.

Pan, L., Zou, L., Guo, S., Ni, J. y Zheng, H.-T. (2026). *Natural-Language Agent
Harnesses*. arXiv:2603.25723.

Pineau, J. et al. (2020). *The Machine Learning Reproducibility Checklist*, v2.0.
McGill University / NeurIPS.

Runeson, P. y Höst, M. (2009). *Guidelines for conducting and reporting case study
research in software engineering*. Empirical Software Engineering 14(2):131–164.

Searle, J. R. (1975). *Indirect Speech Acts*. En: Syntax and Semantics, vol. 3
(Speech Acts), pp. 59–82. Academic Press.

Sjøberg, D. I. K. et al. (2023). *Improving the Reporting of Threats to Construct
Validity*. arXiv:2306.05336.

Tiwari, S. y Fofadiya, P. (2026). *Multi-Layered Memory Architectures for LLM Agents:
An Experimental Evaluation of Long-Term Context Retention*. arXiv:2603.29194.

Wang, J., Wang, J., Athiwaratkun, B. et al. (2024). *Mixture-of-Agents Enhances Large
Language Model Capabilities*. arXiv:2406.04692.

Wang, R., Shi, Y., Li, Z. et al. (2026). *Harness Handbook: Making Evolving Agent
Harnesses Readable, Navigable, and Editable*. arXiv:2607.13285.

Wu, Y., Zhang, J., Shi, J. et al. (2026). *HarnessDev: Can LLMs Create and Evolve
Their Own Agent Harness?* arXiv:2609.01437.

Yagubyan, A. (2026). *How Consistent Are LLM Agents? Measuring Behavioral
Reproducibility in Multi-Step Tool-Calling Pipelines*. arXiv:2605.28840.

---

## Apéndice A — Declaraciones de criterio del clasificador (verbatim)

Extraídas del código evaluado. `{nombre}` se resuelve leyendo el perfil real del
usuario, no una lista codificada.

```python
DECL = {
    "skill": ("El texto implica explicitamente o implicitamente la ejecucion de una "
              "tarea que puede ejecutarse como un proceso de computadora."),
    "research": ("Cualquier proceso o redaccion que implique investigar algo."),
    "memory": ("Obtener o recuperar cualquier dato que implique recuperar facts, datos "
               "persistentes cortos, reglas, criterios. Siempre y cuando el valor "
               "resultante sean redacciones o datos cortos, no mas de un parrafo."),
    "history": ("Cualquier accion que implique la recuperacion de historial o recuerdos "
                "de sesiones o conversaciones pasadas."),
    "user": (f"El texto se refiere a la persona del usuario ({NOMBRE}) o pide informacion "
             "sobre el: su identidad, sus preferencias, sus habitos, su nivel tecnico, lo "
             "que le molesta, su estilo de trato. Incluye cuando el usuario habla de si "
             "mismo en primera persona (mi, mis, yo) sobre esos temas. Queda EXCLUIDO si "
             "es una solicitud o encargo dirigido a quien responde (un pedido de hacer, "
             "entregar o traer algo), aunque use 'mi' o mencione al usuario como "
             "destinatario: ahi el usuario es quien pide, no el tema del que se guarda "
             "informacion."),
    "others": ("Lo que no encaja en las choices anteriores."),
}

PREGUNTA = {"type": "choice",
            "instructions": "Que es este texto?",
            "criteria": DECL}
```

---

## Apéndice B — Guías de ruta inyectadas (verbatim)

Cada ruta corresponde a un texto que el gancho `pre_llm_call` anexa al turno.

**[ruta: skill]**
> Paso 1 (obligatorio): revisa el catálogo con `skills_list` y si hay un skill que
> cubra la tarea, cargalo con `skill_view` y seguí su procedimiento. Paso 2: si no
> hay ninguno, no busques en internet por defecto ni inventes un procedimiento largo:
> ejecuta con tu criterio y avisame que no había skill. Paso 3: si la acción es
> irreversible o toca infraestructura, preguntame antes. Si el procedimiento fue
> nuevo, ofreceme guardarlo como skill.

**[ruta: research]**
> Paso 1: carga el skill `wiki-llm-rosero` con `skill_view` y consulta el wiki local:
> usa `search_files` sobre `~/wiki` y `read_file` sobre `index.md` y las páginas que
> encuentres (es una carpeta de markdown en esta máquina, NO es internet). Paso 2: si
> el wiki no tiene datos suficientes, entonces usa `web_search` y `web_extract`. No
> respondas de memoria.

**[ruta: memory]**
> Paso 1: busca en `fact_store` con `fact_store(action='search')` — es una tool
> directa, no requiere cargar ningún skill. Paso 2: si no está ahí, dilo y ofreceme
> las vías para buscarlo (wiki `~/wiki`, documentos, o web) y pregunta antes de
> salir. Paso 3: con lo que hayas obtenido de `fact_store`, resuelve con libertad,
> como en `others`.

**[ruta: history]**
> Paso 1: busca en el historial de conversaciones con `session_search` antes de
> responder. La respuesta está en lo que ya se habló, no en tu entrenamiento. Paso 2:
> si no aparece, dilo y ofrece alternativas.

**[ruta: user]**
> Paso 1: carga el skill `wiki-llm-rosero` con `skill_view` y revisa las fuentes
> primarias del usuario: lee `~/.hermes/memories/USER.md` con `read_file` y consulta
> el wiki local con `search_files` sobre `~/wiki` (carpeta markdown en esta máquina,
> NO internet). Paso 2: si no está en esas fuentes, usa la tool `clarify` para PEDIR
> APROBACIÓN antes de usar `web_search`.

**[ruta: others]**
> Sin ruta definida para este turno. No cargues skills ni busques en fuentes:
> resuelve directamente con tu criterio y responde.

---

## Apéndice C — Los 24 casos de clasificación y su resultado crudo

Salida literal del clasificador, sin interpretación. `conf` es la confianza declarada
para la opción elegida; las columnas siguientes son las probabilidades por ruta.

| # | Texto | Etiqueta | Elegida | conf | skill | research | memory | history | user | others |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | pasame el reporte del mes | skill | skill | 0.87 | 0.89 | 0 | 0.05 | 0.01 | 0 | 0.05 |
| 2 | configura un proveedor nuevo | skill | skill | 1.00 | 1.00 | 0 | 0 | 0 | 0 | 0 |
| 3 | ejecuta el validador | skill | skill | 1.00 | 1.00 | 0 | 0 | 0 | 0 | 0 |
| 4 | programa el respaldo de la base de datos | skill | skill | 1.00 | 1.00 | 0 | 0 | 0 | 0 | 0 |
| 5 | borra los archivos temporales | skill | skill | 1.00 | 1.00 | 0 | 0 | 0 | 0 | 0 |
| 6 | investiga actos de habla indirectos | research | research | 0.98 | 0.02 | 0.98 | 0 | 0 | 0 | 0 |
| 7 | haceme un informe de videovigilancia | research | **skill** | 0.85 | 0.88 | 0.08 | 0 | 0 | 0 | 0.04 |
| 8 | averigua opciones de NVR con GPU | research | research | 0.86 | 0.11 | 0.89 | 0 | 0 | 0 | 0 |
| 9 | cuanto cobramos por hora | memory | memory | 0.74 | 0.01 | 0.01 | 0.78 | 0.01 | 0.01 | 0.18 |
| 10 | cual es la capital de Francia | memory | memory | 0.98 | 0 | 0 | 0.99 | 0 | 0 | 0.01 |
| 11 | El VPS de Alan corre en Hetzner | memory | **others** | 0.56 | 0.01 | 0.01 | 0.22 | 0 | 0.14 | 0.62 |
| 12 | como funciona la memoria holografica | memory | **research** | 0.32 | 0.01 | 0.44 | 0.37 | 0 | 0 | 0.18 |
| 13 | que te dije ayer sobre el hotel | history | history | 0.99 | 0 | 0 | 0 | 1.00 | 0 | 0 |
| 14 | que prometimos al cliente del hotel | history | history | 0.58 | 0.01 | 0.01 | 0.29 | 0.65 | 0 | 0.04 |
| 15 | recuerda que hablamos de la videovigilancia | history | history | 0.99 | 0 | 0 | 0.01 | 0.99 | 0 | 0 |
| 16 | Mauro prefiere respuestas concisas sin preambulo | user | user | 0.98 | 0 | 0 | 0.01 | 0 | 0.98 | 0.01 |
| 17 | A Mauro le molesta que le den vueltas antes de responder | user | user | 0.99 | 0 | 0 | 0 | 0 | 1.00 | 0 |
| 18 | Mauro esta en zona horaria EST | user | user | 0.82 | 0 | 0 | 0.08 | 0 | 0.86 | 0.06 |
| 19 | Mauro tiene nivel tecnico alto | user | user | 0.99 | 0 | 0 | 0 | 0 | 0.99 | 0.01 |
| 20 | quien es Mauro | user | user | 0.77 | 0 | 0.03 | 0.10 | 0 | 0.81 | 0.06 |
| 21 | que prefiere el usuario | user | user | 0.98 | 0 | 0 | 0.01 | 0 | 0.99 | 0 |
| 22 | cuales son mis preferencias | user | user | 0.98 | 0 | 0 | 0.01 | 0 | 0.99 | 0 |
| 23 | mi zona horaria es EST | user | user | 0.97 | 0 | 0 | 0.01 | 0 | 0.98 | 0.01 |
| 24 | como le gusta que le hable al usuario | user | user | 0.92 | 0 | 0 | 0.06 | 0 | 0.94 | 0 |

**Negrita** = divergencia de la etiqueta inicial del operador. Resolución de las tres:
casos 7, 11 y 12 (§5.4).

---

## Apéndice D — Checklist de reproducibilidad

Siguiendo la lista de verificación de Pineau et al. (2020), adaptada a un estudio de
caso de arnés.

| Ítem | Estado |
|---|---|
| Descripción del mecanismo y del algoritmo | Sí — §4.2, §4.3, Apéndices A y B |
| Supuestos declarados | Sí — §1.2, §4.4 |
| Análisis de complejidad (tiempo, espacio) | Parcial — costo medido en tokens y segundos (§5.2); sin análisis asintótico |
| Estadísticas de los datos | Sí — §5.1, §5.3 (n por celda reportado) |
| Descripción del proceso de recolección | Sí — §4.4 |
| Exclusión y preprocesamiento de datos | Sí — los 10 casos se reportan completos; un caso terminó con código de retorno de tiempo excedido y se conserva (§5.2) |
| Versión descargable de los datos | Sí — `evidence/` en el repositorio del proyecto |
| Código de evaluación | Sí — `evidence/ab-v4.py` y los datos crudos |
| Dependencias especificadas | Sí — el código declara sus dependencias |
| Instrucciones para reproducir | Parcial — las corridas requieren el arnés y acceso al proveedor del clasificador |
| Rangos de hiperparámetros | No aplicable — el modelo de ejecución estuvo congelado; no hay entrenamiento |
| Número exacto de corridas | Sí — 3 por condición, 10 casos cada una; 1 corrida de clasificación de 24 casos |
| Medida o estadístico usado, definido | Sí — §4.4 |
| Tendencia central y variación | Sí — §5.1, §5.2, §5.3 (medianas y rangos, no promedios) |
| Tiempo de ejecución por resultado | Sí — §5.2 (segundos por condición) |
| Infraestructura de cómputo | Sí — §3.1, §4.4 (instancia local, un operador) |

---

## Apéndice E — Verificación de identificadores

Todos los identificadores de arXiv citados se verificaron contra la interfaz de
programación de arXiv (`export.arxiv.org/api/query`) y, en los casos en que la
interfaz no devolvió entrada, contra el HTML del artículo.

| ID | Título verificado | Categoría | Fecha | Autores |
|---|---|---|---|---|
| 2603.25723 | Natural-Language Agent Harnesses | — (vía HTML) | — | Pan, Zou, Guo, Ni, Zheng |
| 2609.01437 | HarnessDev: Can LLMs Create and Evolve Their Own Agent Harness? | cs.SE | 2026-09-01 | Wu et al. (19) |
| 2607.13285 | Harness Handbook: Making Evolving Agent Harnesses Readable, Navigable, and Editable | cs.AI | 2026-07-14 | Wang et al. (10) |
| 2502.12378 | Pragmatics in the Era of Large Language Models: A Survey... | cs.CL | 2025-02-17 | Ma et al. (10) — ACL 2025 |
| 2502.10995 | Evaluating Large language models on Understanding Korean indirect Speech acts | cs.CL | 2025-02-16 | Koo et al. (5) |
| 1911.08829 | Casting a Wide Net: Robust Extraction of Potentially Idiomatic Expressions | cs.CL | 2019-11-20 | Haagsma, Nissim, Bos |
| 2509.07571 | Towards Generalized Routing: Model and Agent Orchestration for Adaptive and Efficient Inference | cs.MA | 2025-09-09 | Guo et al. (9) |
| 2503.15850 | Uncertainty Quantification and Confidence Calibration in Large Language Models: A Survey | cs.CL | 2025-03-20 | Liu et al. (6) |
| 2406.03441 | Cycles of Thought: Measuring LLM Confidence through Stable Explanations | cs.CL | 2024-06-05 | Becker, Soatto |
| 2310.14774 | Principled Approaches for Learning to Defer with Multiple Experts | cs.LG | 2023-10-23 | Mao, Mohri, Zhong — ISAIM 2024 |
| 2605.28840 | How Consistent Are LLM Agents? Measuring Behavioral Reproducibility in Multi-Step Tool-Calling Pipelines | cs.CL | 2026-04-23 | Yagubyan |
| 2606.08998 | The Token Not Taken: Sampling, State, and the Stochasticity of AI Agents | cs.AI | 2026-06-08 | Hydari, Iqbal |
| 2608.26197 | Harness Engineering for Predictable Agentic Systems: An Empirical Study of Deterministic Execution Constraints | cs.SE | 2026-08-25 | Dhage |
| 2507.21504 | Evaluation and Benchmarking of LLM Agents: A Survey | cs.LG | 2025-07-29 | Mohammadi et al. (4) |
| 2603.29194 | Multi-Layered Memory Architectures for LLM Agents: An Experimental Evaluation of Long-Term Context Retention | cs.CV | 2026-03-31 | Tiwari, Fofadiya |
| 2406.04692 | Mixture-of-Agents Enhances Large Language Model Capabilities | cs.CL | 2024-06-07 | Wang et al. (5) |

**Nota de método.** El identificador 2603.25723 no devolvió entrada en la interfaz de
programación de arXiv (tanto por `id_list` como por búsqueda), pero su página `abs` y
su HTML responden con el título correcto. Esto es coherente con la observación de que
extracciones automáticas de arXiv pueden devolver contenido cruzado de otro
artículo; por eso cada identificador se verificó individualmente.

**Verificación de venues.** El campo de comentarios de la interfaz confirmó que
2502.12378 es ACL 2025 y que 2310.14774 es ISAIM 2024. Los demás se citan como
preprints de arXiv, sin atribuirles venue.

---

## Apéndice F — Inventario de datos crudos

Archivos en `evidence/`, en el repositorio del proyecto:

| Archivo | Contenido |
|---|---|
| `resultados.json` | A/B corrida 1 (v1) — 2 condiciones × 10 casos |
| `resultados-v3.json` | A/B corrida 2 (v3) — 2 condiciones × 10 casos |
| `resultados-v4.json` | A/B corrida 3 (v4) — 2 condiciones × 10 casos (fuente de §5.2 y §5.3) |
| `respuestas-v4.json` | Texto completo de las respuestas de la corrida 3 |
| `ruta-jev.py` | Gancho v1 |
| `ruta-jev-v2.py` | Gancho v2 |
| `ruta-jev-v4.py` | Gancho v4 — versión evaluada |
| `ab.py`, `ab-v3.py`, `ab-v4.py` | Instrumentación del A/B |
| `jev-crudo-5choices.py` | Clasificador — 6 rutas en una pregunta |
| `corrida-20260923.json` / `.txt` | Salida cruda de los 24 casos (fuente del Apéndice C) |
| `comparativa-jev-llm.json` | Comparación clasificador tipado vs modelo de lenguaje (§5.6) |
| `reglas.py` | Reglas de detección de encargos por forma verbal (§6.4) |
| `arxiv-verificado.json` | Verificación de identificadores (Apéndice E) |

---

*Fin del documento. Versión 0.1-draft para revisión del autor.*
