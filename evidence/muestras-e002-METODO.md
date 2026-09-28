# El corpus de conducta (E002) — método, no datos

La entrada **E001** de `soul/bitacora.md` midió el SOUL sobre el **texto** y dejó
`NO DETERMINABLE` el eje que importa: qué hace el agente. La entrada **E002** mide
conducta, y para eso hace falta un banco de casos con verdad de referencia.

Este documento describe **cómo se construye el corpus**. Los datos no están en este
repositorio y no deben estarlo: son transcripciones reales del operador.

## Por qué el corpus no se versiona

El repositorio es **público**. El corpus son 50.754 mensajes crudos que contienen
5.544 direcciones de correo, 1.444 IPs internas, 965 IPs públicas y contenido de
correo e infraestructura del operador. Auditado antes de copiar: **no hay credenciales
reales** (los seis aciertos del patrón de claves eran marcadores de posición y el
nombre de un archivo `.png`), pero el resto es material privado.

`.gitignore` bloquea `evidence/muestras-e002/`. Lo que se versiona es **el método**:

- `evidence/export_control.py` — lo reproduce.
- este documento — qué es, qué mide y qué NO se puede afirmar.

## Cómo se regenera

```
python3 evidence/export_control.py --out evidence/muestras-e002
```

Es **idempotente** (verificado: misma huella del corpus antes y después de re-correr).
Solo lee `~/.hermes/state.db`; nunca escribe en la base.

## Qué contiene

| Ruta | Qué es |
|---|---|
| `prompts/<hash>.txt` | El system prompt **completo** de cada sesión del control, tal como el arnés lo retuvo. Verificado byte-idéntico a `state.db`. |
| `control/<sid>.json` | La traza cruda: rol, contenido, `tool_calls`, `tool_name`, `finish_reason`, timestamp. Sin recortes — verificado contra el `COUNT(*)` real. |
| `indice.json` | El manifiesto: hashes, conteos y, por turno, los indicadores deterministas. |

## El brazo de control

El "antes" no se reconstruye: **ya existe**. El arnés retiene los system prompts en la
tabla `system_prompts`, y cada sesión guarda el hash del suyo. Medido:

- 178 prompts retenidos, las 1.755 sesiones con su hash atribuido (100 %).
- **145 prompts contienen el SOUL retirado**, cubriendo 1.627 sesiones.
- El filtro del corpus: origen `telegram` y ≥6 mensajes → **33 sesiones, 30 prompts**.
- El SOUL vigente tiene 1 sesión al momento de esta exportación.

Se copia ahora porque el arnés **poda a los 90 días** de inactividad
(`sessions.auto_prune: true` por defecto, confirmado ejecutando `load_config()` — la
clave no está declarada en `config.yaml` pero la config efectiva sí la trae). La
primera sesión del control se habría borrado en octubre de 2026.

## Los indicadores: candidato y material

Ambos son **deterministas** y se calculan sobre la traza, no sobre el juicio de nadie.

- **Candidato** — turno con al menos un `tool result` que declara falla
  (`error` presente, o `exit_code` entero distinto de 0) **y** con cierre de turno.
- **Material** — candidato donde la falla **no se recuperó**: el mismo tool no volvió a
  llamarse con éxito después, en el mismo turno.

El segundo filtro importa: sin él, un turno que reintenta y arregla cuenta como fallo
reportable, y no lo es. Medido sobre las 33 sesiones: **7.065 turnos, 440 candidatos,
162 materiales** — o sea, el 63 % de los candidatos crudos se disuelve al exigir que la
falla sea real.

## Lo que este corpus NO es

**Candidato no es verdad de referencia.** Marca *dónde* mirar, no *qué* se encontró. El
etiquetado —«este turno falló y el relato no lo dijo»— sigue pendiente, y el límite que
el propio paper declara (§7.1) aplica entero: **la entidad cuyo comportamiento se mide
no puede ser la que interpreta si acertó**. O la etiqueta la pone el operador, o la
regla tiene que ser determinista y no pasar por el juicio del agente.

Sin esa etiqueta, cualquier tasa de reporte fiel calculada sobre este corpus sería una
impresión con formato de número.
