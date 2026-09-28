# soul/

Los dos estados del prompt de identidad del agente, conservados como evidencia
para la línea de investigación sobre escritura de prompts de arnés.

## Convención de nombres

| Archivo | Qué es |
|---|---|
| `andrea-soul-old.md` | El prompt de identidad **anterior**, tal como estaba en producción. Se conserva **verbatim** y no se edita: es la evidencia del estado que se midió. |
| `andrea-soul-original.md` | El prompt de identidad **que se implementa**: la versión redactada a partir de los hallazgos. Es el "original" en el sentido de fuente canónica vigente. |

`old` = el que se retira. `original` = el que rige. Los nombres son deliberados:
`old` marca un estado agotado, `original` marca la fuente desde la cual se
derivan las siguientes iteraciones.

## De qué es evidencia este par

La medición comparada de los dos archivos es parte del respaldo empírico del
estudio de caso sobre la honestidad como componente del entregable
(`docs/paper-honestidad-es.md`). Lo que el par permite verificar:

| Medición | `andrea-soul-old.md` | `andrea-soul-original.md` |
|---|---|---|
| Tamaño | 14.423 chars (~4.006 tokens) | 12.640 chars (~3.511 tokens) |
| Viñetas de regla | 42 | 18 |
| Secciones | 9 | 10 |
| Secciones del método de 5 pasos | 2 (disparadores contradictorios) | 1 (disparador acotado) |
| Declaración por resultado esperado | 0 ocurrencias | sección inicial |

Ambos archivos se cargan en el slot #1 de identidad del arnés y **se pagan
completos en cada turno**, por lo que la diferencia de tamaño es un costo
recurrente, no una diferencia de archivo.

## Uso

Para volver al estado anterior:

```bash
cp soul/andrea-soul-old.md ~/.hermes/SOUL.md
```

Para el estado vigente:

```bash
cp soul/andrea-soul-original.md ~/.hermes/SOUL.md
```

Cambiar `SOUL.md` toma efecto en la **siguiente** sesión: el prompt de sistema es
byte-estable durante la vida de una conversación (invariante de caché del arnés),
así que la sesión abierta sigue con el prompt con el que arrancó.

## Por qué se versiona aquí y no en el wiki

`SOUL.md` es un artefacto de la capa 3 (código y configuración del arnés), no de
la capa 2 (conocimiento consolidado). Su lugar es el repositorio del plugin que
implementa los refuerzos, junto al paper que lo justifica. Un cambio de prompt
de identidad es un cambio de configuración auditable: necesita historia, diff y
reversión, y eso lo da git.
