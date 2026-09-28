# hermes-jev-helper

Externaliza la decisión de ruta de un arnés de agente a un **clasificador tipado de
intención** que corre *antes* de la llamada al modelo, y anexa al turno una guía de
ruta en lenguaje natural.

El mecanismo no ejecuta la tarea ni produce la respuesta: elige una de seis rutas
(`skill`, `research`, `memory`, `history`, `user`, `others`) y declara una confianza.
El objetivo no es mejorar la calidad de la respuesta, sino **reducir la improvisación
de ruta**: que el mismo patrón de petición reciba la misma clase de ruta.

Es un **plugin de Hermes Agent** (`pre_llm_call`) — no un skill, no un gancho de
shell. La razón está documentada en el estudio de caso (§4.1).

## Instalación

```bash
hermes plugins install maurorosero/hermes-jev-helper
hermes plugins enable hermes-jev-helper
```

O desde un clon local:

```bash
git clone https://github.com/maurorosero/hermes-jev-helper
hermes plugins install ./hermes-jev-helper
hermes plugins enable hermes-jev-helper
```

**Requiere una credencial** para el endpoint del clasificador. El nombre de la
variable es configurable (`api_key_env`, por defecto `OPENROUTER_API_KEY`). La
resolución va en cascada por las vías del arnés —scope de secretos, entorno, y el
helper de Infisical de la instalación— de modo que funciona tanto si el arnés
inyecta la credencial por `.env` como si la sirve un *secret source*.

Sin credencial el plugin **no hace nada**: no inyecta, no falla y no rompe el turno.

## Configuración

Las claves se leen de `plugins.entries.hermes-jev-helper.settings`. También se
editan desde la app de escritorio (pestaña **Capabilities → Plugins**), que las
renderiza a partir del `config_schema` del manifiesto.

| Clave | Por defecto | Qué hace |
|---|---|---|
| `enabled` | `true` | Activa o desactiva la clasificación sin desinstalar |
| `endpoint` | `https://openrouter.ai/api/alpha/decisions` | Endpoint del modelo de decisión |
| `model` | `~typesafe/jev-latest` | Slug del modelo de decisión |
| `api_key_env` | `OPENROUTER_API_KEY` | Nombre de la variable con la credencial |
| `timeout_s` | `25.0` | Timeout por intento |
| `retries` | `2` | Intentos antes de rendirse (fail-open) |
| `min_confidence` | `0.0` | Bajo el umbral se aplica la ruta de escape. `0.0` = desactivado |
| `inject` | `true` | `false` clasifica y registra, pero no inyecta (modo observación) |
| `overrides_path` | — | YAML o JSON que sobreescribe criterios y guías |
| `read_user_md` | `true` | Leer el nombre del usuario del perfil real (`USER.md`) |

Ejemplo:

```yaml
plugins:
  entries:
    hermes-jev-helper:
      settings:
        enabled: true
        min_confidence: 0.0
        inject: true
```

### Sobreescribir criterios y guías

Sin tocar el código, con un archivo:

```yaml
user_name: Mauro
declarations:
  skill: "Criterio propio para esta instalación."
guides:
  skill: "[ruta: skill] Paso 1: ..."
```

Solo las claves presentes se reemplazan; el resto sigue siendo el valor interno.
Un archivo roto se ignora en silencio (nunca tumba el turno).

## Qué hace cada ruta

Las seis guías nombran la **herramienta exacta**, encadenan con una **condición de
salida** ("si esto no alcanza, entonces...") y **acotan la libertad** en lugar de
eliminarla: el último paso devuelve el criterio al modelo.

| Ruta | Orienta hacia |
|---|---|
| `skill` | Cargar un procedimiento almacenado; si no hay, ejecutar y avisar |
| `research` | La base de conocimiento local (carpeta markdown, **no** internet); luego web |
| `memory` | La memoria persistente de hechos; luego ofrecer vías y confirmar |
| `history` | El historial de conversaciones |
| `user` | El archivo de perfil y la base local; pedir aprobación antes de la web |
| `others` | **Nada**: declara que no hay ruta y deja el turno al criterio del modelo |

`others` es la **ruta de escape** y su diseño es deliberado: sin ella, el
clasificador estaría forzado a elegir una de las otras cinco incluso cuando ninguna
aplica, e inyectaría una orientación equivocada con confianza alta. Que su guía diga
"no busques" no contradice el mecanismo: es la forma en que el clasificador declara
que no sabe (estudio de caso, §6.3).

Las rutas nombran las herramientas del arnés sobre el que se midió el mecanismo.
Para otro arnés, usar `overrides_path`.

## Garantías de comportamiento

- **Fail-open.** Sin credencial, sin red, con timeout o con una respuesta
  inesperada, el plugin no inyecta nada. La clasificación y la resolución de
  credencial están envueltas en el propio plugin, sin depender de que el arnés
  aísle el fallo.
- **No rompe la caché del prompt.** El contexto se anexa al *mensaje del usuario*,
  no al system prompt.
- **Sin re-clasificación.** El mismo turno (`turn_id`) no se clasifica dos veces.
- **Texto acotado.** Solo los primeros 2 000 caracteres del turno van al
  clasificador.
- **Estado efímero.** Todo el estado por turno vive en memoria del proceso y se
  limpia al abrir sesión.
- **No escribe nada.** El plugin no toca archivos, configuración ni memoria.

## Desarrollo

```bash
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python pytest

cd tests && ../.venv/bin/python -m pytest -v     # 23 passed
```

La suite corre **sin red** salvo el último test, que clasifica de verdad contra el
endpoint y se omite si no hay credencial.

> **Nota sobre `pytest.ini`:** vive en `tests/` a propósito. Si pytest tomara la
> raíz del repo como `rootdir`, intentaría recolectar el `__init__.py` del plugin (el
> punto de entrada del arnés) como módulo de test y fallaría con *"attempted relative
> import with no known parent package"*. Correr desde `tests/` evita eso.

Verificación contra el contrato del arnés:

```bash
hermes plugins validate ./hermes-jev-helper    # admisión al catálogo
hermes plugins doctor  ./hermes-jev-helper     # contratos reales del runtime
```

## Estado

**Prototipado y evaluado; esta es la primera implementación como plugin.** El
mecanismo se midió como gancho antes de portarlo. Registra `pre_llm_call` y
`on_session_start`; **no** registra `pre_tool_call` (la verificación de que el turno
usó la fuente indicada es trabajo futuro).

Resultado medido con el modelo congelado: la proporción de casos que consultan una
fuente primaria *antes* de ejecutar pasa de una banda de 3–6 sobre 10 (media 4.7) a
9–10 sobre 10 (media 9.7). Costo del mecanismo: 93–111 tokens por turno
(6.1–7.2 % del aumento de tokens de entrada).

## Estructura

```
__init__.py       register(ctx) + el hook pre_llm_call
classifier.py     cliente del modelo de decisión + resolución de credencial
routing.py        declaraciones de criterio y guías (datos, no lógica)
plugin.yaml       manifiesto (kind: standalone, config_schema, provides_hooks)
tests/            suite (32 tests, sin red salvo el de integración)
docs/paper-es.md          estudio de caso completo (español + abstract en inglés)
docs/paper-honestidad-es.md  estudio de caso 2: honestidad como componente del entregable
soul/             los dos estados del prompt de identidad + bitacora de cambios
evidence/         datos crudos de todas las corridas
```

## Referencia

`docs/paper-es.md` — estudio de caso siguiendo el marco de Runeson y Höst (2009),
con amenazas a la validez en las cuatro categorías y checklist de reproducibilidad
de Pineau et al. (2020). Incluye las declaraciones y guías verbatim, las 24
clasificaciones crudas, y las mediciones completas del A/B.

`docs/paper-honestidad-es.md` — segundo estudio de caso, del mismo arnés. Mide el
hueco en el prompt de sistema (21 menciones de *tarea/paso/proceso* contra 0 de
*resultado esperado*) y propone transponer a la **conducta** el principio que este
plugin ya aplica a la **ruta**: declarar por resultado esperado. Su aporte es un
resultado negativo acotado —documenta por qué el prompt no puede resolver el
problema por sí solo— y delimita el borde del mecanismo en el reporte final. La
hoja de ruta de §8.2 es la que este plugin debe implementar.

## Los dos refuerzos que este plugin implementa

El plugin es la **palanca** de dos refuerzos sobre el arnés, y ambos comparten el
mismo principio: **declarar por resultado esperado, desde afuera del agente, antes
de que razone.**

- **Refuerzo 1 — determinismo de ruta.** Que el mismo patrón de petición reciba la
  misma clase de ruta. Implementado y medido (`docs/paper-es.md`).
- **Refuerzo 2 — honestidad del reporte.** Que el entregable declarado incluya el
  relato fiel de lo hecho *y de lo no hecho*, en lugar de pedir honestidad como
  restricción paralela que compite con la tarea y pierde. Diseñado y con hoja de
  ruta (`docs/paper-honestidad-es.md` §6.7 y §8.2); no implementado.

El segundo refuerzo no se implementa antes de diseñar su evaluación. El paso 5 de esa
hoja de ruta —verificar el relato contra la traza de *tool calls*— **no requiere tocar
el motor del arnés**: los hooks que corre después de la acción ya existen en su
declaración oficial de eventos válidos y este plugin todavía no los registra
(`post_tool_call`, `transform_llm_output`, `pre_verify`). La salvedad es que
`pre_verify` sólo dispara si el turno editó archivos, y su alcance está acotado por
`agent.max_verify_nudges` — extenderlo a turnos sin edición es una decisión de diseño
sobre el umbral, no un cambio de motor. Detalle en `docs/paper-honestidad-es.md` §8.2.

## Licencia

MIT — ver `LICENSE`.
