# Bitácora del SOUL

Registro de los cambios que se le hacen al prompt de identidad del agente, con el
resultado descriptivo de cada uno y una valoración de cuánto mejora o empeora
frente al estado anterior.

Este archivo es **append-only en su parte de entradas**: una entrada publicada no se
reescribe. Si una medición posterior cambia el veredicto de una entrada, se agrega
una entrada nueva que la revisa y se enlaza; no se corrige la vieja. Lo que cambia
es el presente, no el acta.

---

## Cómo se usa

**Qué es una entrada.** Un cambio al SOUL, con su medición. Cada entrada lleva:

| Campo | Qué registra |
|---|---|
| `id` | `E<n>` correlativo, nunca reutilizado |
| `fecha` | Cuándo se midió |
| `versión` | sha256 corto del archivo que entra y del que sale |
| `tipo` | `medición` (solo mide) · `cambio` (modifica el SOUL) · `revisión` (corrige un veredicto previo) |
| `artefactos` | Los archivos comparados, con su ruta |
| `delta` | Las cifras, medidas — no estimadas |
| `valoración` | MEJORA / IGUAL / EMPEORA / NO DETERMINABLE, por eje, con el tanto |
| `límite` | Qué NO se puede afirmar con esta medición |

**Los tres estados.** `old` es el estado de referencia (el que se retiró);
`original` es el que rige. Cuando hay versiones intermedias, cada entrada nombra
contra cuál mide.

**Las dos clases de afirmación, y no se mezclan.** Una mejora **estructural** se
mide sobre el texto: tamaño, número de reglas, duplicaciones, contradicciones. Una
mejora **conductual** se mide sobre lo que el agente hace, y **requiere un banco de
casos con verdad de referencia**. Este archivo registra las dos, pero las marca
distinto. Presentar una mejora estructural como si probara una conductual es el
error que la bitácora existe para prevenir.

**Regla de honestidad.** Cuando un eje no permite veredicto, se escribe
`NO DETERMINABLE` y se dice por qué. No se redondea a favor.

---

## Índice de entradas

| id | fecha | tipo | Qué mide | Veredicto global |
|---|---|---|---|---|
| [E001](#e001--medición-inicial-old--original) | 2026-09-28 | medición | `old` vs `original`: estructura, carga, contradicciones | MEJORA estructural · conducta NO DETERMINABLE |

---

## E001 — Medición inicial (old → original)

**Fecha:** 2026-09-28
**Tipo:** `medición`
**Artefactos:**
- `old` → `soul/andrea-soul-old.md` — sha256 `30009d04…` — 14.727 bytes
- `original` → `soul/andrea-soul-original.md` — sha256 `3a2add59…` — 12.906 bytes
- Activo en el arnés: `~/.hermes/SOUL.md`, idéntico a `original` (verificado byte a byte)

### Qué cambió, descripto

El `old` tenía la conducta declarada **por el proceso a seguir** y con el método de
cinco pasos definido **dos veces con disparadores distintos**: una vez acotado a
acciones con efecto persistente (la sección "Regla de Oro — El Gatekeeper") y otra
sin acotar ("Cada vez que Mauro te pide algo que requiere análisis, decisión o
construcción"). Una pregunta cae dentro de la segunda definición y fuera de la
primera, de modo que una regla ordenaba el procedimiento completo ante una pregunta
y la otra no aplicaba. Ese doble disparador es el origen del error característico de
tratar una pregunta como una orden.

Además el `old` contenía una **contradicción de rasgos sin condición**: la sección
Identidad declara "proactiva" (actuar sin que lo pidan) y la sección "Lo que evitas"
declara "No haces trabajo no solicitado" (no actuar sin que lo pidan). Ninguna de
las dos estaba acotada por una condición de disparo, así que el modelo elegía y
variaba por turno — el eje exacto donde el operador corrigió repetidamente.

El `original` reescribe la conducta declarándola **por el resultado esperado**,
abre con una sección que define qué cuenta como entregable (incluido el relato fiel
de lo hecho y lo **no** hecho), reduce el método a una sola definición con el
disparador acotado a acciones con efecto, y convierte cada contradicción en una
regla con su condición.

### Delta medido

| Eje | old | original | Δ | Δ% |
|---|---|---|---|---|
| bytes | 14.727 | 12.906 | −1.821 | −12,4 % |
| caracteres | 14.423 | 12.640 | −1.783 | −12,4 % |
| tokens por turno (est.) | 4.006 | 3.511 | −495 | −12,4 % |
| líneas | 163 | 149 | −14 | −8,6 % |
| **viñetas de regla** | **42** | **18** | **−24** | **−57,1 %** |
| encabezados (H1+H2) | 10 | 18 | +8 | +80 % |

**Duplicación por tema** (en cuántas secciones distintas aparece):

| Tema | old | original |
|---|---|---|
| Método y aprobación | 3 secciones | **1** |
| Guardar al corregir | 5 secciones | **1** |
| Investigar / verificar | 7 secciones | 5 |
| No adelantarse | 1 sección | 1 |

**Contradicciones y declaraciones de resultado:**

| Indicador | old | original |
|---|---|---|
| Método de 5 pasos definido N veces | 2 | 1 |
| Disparadores distintos del método | 2 | 1 |
| Contradicciones de rasgo sin condición | 1 | **0** |
| Ocurrencias de "resultado esperado" / "relato fiel" | 0 | **3** |

**Cobertura:** 22 de 22 reglas vivas del `old` están presentes en el `original`.
Ninguna regla se perdió.

### Valoración

| Eje | Veredicto | Tanto | Sustento |
|---|---|---|---|
| Carga por turno | **MEJORA** | −12,4 % (−495 tok) | El costo es recurrente: el prompt se paga completo en cada llamada |
| Nº de reglas apiladas | **MEJORA** | −57,1 % (42→18) | La saturación de restricciones colapsa pasado 5-6 simultáneas (arXiv:2608.12426); se reduce la distancia al umbral |
| Duplicación | **MEJORA** | −8 secciones duplicadas | Cada repetición es una restricción más contra el mismo presupuesto |
| Contradicciones de disparador | **MEJORA** | 2→1, y la restante acotada | Es la causa directa del error de tratar una pregunta como una orden |
| Contradicción de rasgo | **MEJORA** | 1→0 | Resuelta por condición, no por supresión de uno de los dos rasgos |
| Declaración por resultado esperado | **MEJORA** | 0→3 ocurrencias | Traslada la honestidad de la columna de las restricciones a la de las entregas (paper §6.7) |
| Pérdida de reglas | **IGUAL** | 0 pérdidas | Cobertura 22/22 verificada |
| Fragmentación estructural | **NO DETERMINABLE** | +8 encabezados | Más encabezados ayudan a ubicar una regla al editar y a la vez fragmentan el texto; las dos lecturas tienen respaldo y ninguna se midió aquí |
| Numeración explícita del método | **NO DETERMINABLE** | numerado → flujo en línea | El `old` numeraba los pasos (verificable de un vistazo); el `original` los enuncia como flujo dentro de una prosa que explica el contradictorio. Es un intercambio, no una ganancia, y no se midió |
| Conducta real del agente | **NO DETERMINABLE** | — | No hay medición de conducta (ver límite) |

**Veredicto global de E001:** MEJORA **estructural** con conducta **no determinable**.
Las mejoras de tamaño, duplicación y contradicciones son hechos medidos sobre el
texto. La mejora de comportamiento es una expectativa razonada, no un resultado.

### Límite — qué NO se puede afirmar con esta medición

1. **Que el agente se comporte mejor.** No se aplicó tratamiento ni se midió
   conducta. No existe todavía el banco de casos con verdad de referencia que haría
   falta, y es el paso 2 de la hoja de ruta de `docs/paper-honestidad-es.md` §8.2.
2. **Que 18 reglas estén por debajo del umbral.** Siguen por encima del rango de
   5-6 restricciones simultáneas que la literatura reporta como límite de
   seguimiento confiable. La reducción mejora la posición; **no resuelve el
   problema**. Declararlo resuelto sería el error que la bitácora previene.
3. **Que el cambio no esté condicionado.** La literatura advierte que una
   intervención de prompt que parece exitosa puede producir desalineación
   condicional, reactivable por disparadores léxicamente cercanos al propio texto
   (arXiv:2604.25891). Una evaluación futura debe incluir variantes léxicas.
4. **Que la reducción de contradicciones se traduzca en cumplimiento.** La
   separación de secciones no establece prioridad confiable por sí sola
   (arXiv:2502.15851, "Control Illusion"), y los modelos detectan conflictos pero
   rara vez los declaran al usuario (arXiv:2511.14342).
5. **Que el efecto se vea en esta sesión.** El prompt de sistema es byte-estable
   durante la vida de una conversación: el cambio rige desde la sesión siguiente.

### Próxima medición sugerida

Una entrada `E002` de tipo `medición` sobre conducta, y para eso el requisito es el
banco de casos, no otra comparación de texto. Sin verdad de referencia, cualquier
valoración de conducta sería una impresión — y las impresiones son lo que este
archivo no registra.
