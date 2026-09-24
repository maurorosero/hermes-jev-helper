# hermes-jev-helper

Externaliza la decisión de ruta de un arnés de agente a un clasificador tipado de
intención que corre **antes** de la llamada al modelo, e inyecta en el turno una guía
de ruta en lenguaje natural.

El mecanismo no ejecuta la tarea ni produce la respuesta: elige una de seis rutas
(`skill`, `research`, `memory`, `history`, `user`, `others`) y declara una confianza.
El objetivo no es mejorar la calidad de la respuesta, sino **reducir la improvisación
de ruta**: que el mismo patrón de petición reciba la misma clase de ruta.

## Estado

Prototipado y evaluado, **no instalado**. La implementación evaluada es un gancho
`pre_llm_call` de 7,258 bytes (`evidence/ruta-jev-v4.py`).

## Estructura

```
docs/paper-es.md        Estudio de caso completo (español, abstract en inglés)
evidence/               Datos crudos de todas las corridas + instrumentación
```

## Resultado principal

Con el modelo congelado, la proporción de casos que consultan una fuente primaria
*antes* de ejecutar pasa de una banda de 3–6 sobre 10 (media 4.7) a 9–10 sobre 10
(media 9.7). El efecto es un cambio de régimen: deja de haber corridas malas.

Costo del mecanismo: 93–111 tokens por turno (6.1–7.2 % del aumento de tokens de
entrada). El 87.2 % del aumento es salida de herramientas.

## Documento

`docs/paper-es.md` — estudio de caso siguiendo el marco de reporte de Runeson y Höst
(2009), con amenazas a la validez en las cuatro categorías y checklist de
reproducibilidad de Pineau et al. (2020).

## Licencia

Pendiente de definir.
