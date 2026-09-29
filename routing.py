"""Declaraciones de criterio y guías de ruta.

Este módulo es el CORAZÓN del mecanismo y es deliberadamente datos, no lógica:
las declaraciones que el clasificador recibe y las guías que se inyectan en el
turno. Separarlas del código permite revisarlas, versionarlas y sobreescribirlas
sin tocar el motor.

Las declaraciones siguen un principio de diseño que la investigación estableció:
cada ruta se declara por el RESULTADO ESPERADO, no por la tarea. Las que describen
una tarea (skill, research) dependen del verbo del texto; la que nombra un
resultado (history) es más estable.

ALCANCE: cuatro rutas. ``memory`` y ``user`` se retiraron del esquema. La memoria
de hechos es TRANSVERSAL: el prefetch la inyecta en cada turno, sea cual sea el
tema, así que un carril propio duplicaba lo que ya llega sin clasificador (medido:
37% de los turnos consulta la memoria, 5% la recibía como ruta). El perfil del
usuario viaja siempre en el system prompt por la misma razón.

Ver docs/paper-es.md §4.2 y Apéndices A y B del estudio de caso.
"""

from __future__ import annotations

from typing import Dict, Optional

# El orden es el orden de presentación de las opciones al clasificador.
ROUTES = ("skill", "research", "history", "others")

# Nombre de la ruta de escape. No inyecta guía: declara que no hay ruta definida.
ESCAPE_ROUTE = "others"


def declarations() -> Dict[str, str]:
    """Criterios de clasificación, uno por ruta.

    Ya no recibe ``user_name``: el parámetro existía solo para la declaración de
    ``user``, que se retiró del esquema. El clasificador no necesita saber quién
    es el usuario para decidir el punto de partida del turno.
    """
    return {
        "skill": (
            "El texto implica explicita o implicitamente la ejecucion de una tarea "
            "que puede ejecutarse como un proceso de computadora."
        ),
        "research": (
            "Cualquier proceso o redaccion que implique investigar algo."
        ),
        "history": (
            "Cualquier accion que implique la recuperacion de historial o recuerdos "
            "de sesiones o conversaciones pasadas."
        ),
        ESCAPE_ROUTE: "Lo que no encaja en las choices anteriores.",
    }


def guides() -> Dict[str, str]:
    """Guías inyectadas en el turno, una por ruta.

    Las guías siguen tres propiedades de diseño verificadas en el estudio:

    1. **Nombran la herramienta exacta**, no la intención. ``research`` no dice
       "busca información": nombra la herramienta de búsqueda y aclara que el
       wiki es una carpeta local, no internet (la confusión se midió).
    2. **Encadenan con condición de salida** ("si esto no alcanza, entonces..."),
       para que el agente no quede bloqueado si la fuente indicada no tiene el dato.
    3. **Acotan la libertad, no la eliminan**: el último paso devuelve el criterio
       al modelo en lugar de imponerle un guion.

    Las rutas y herramientas nombradas corresponden al arnés sobre el que se
    midió el mecanismo. Para otro arnés, sobreescribir vía ``overrides_path``.
    """
    return {
        "skill": (
            "[ruta: skill] Paso 1 (obligatorio): revisa el catalogo de skills y si hay "
            "uno que cubra la tarea, cargalo y segui su procedimiento. "
            "Paso 2: si no hay ninguno, no busques en internet por defecto ni inventes "
            "un procedimiento largo: ejecuta con tu criterio y avisa que no habia skill. "
            "Paso 3: si la accion es irreversible o toca infraestructura, pedi "
            "confirmacion antes. Si el procedimiento fue nuevo, ofrece guardarlo como skill."
        ),
        "research": (
            "[ruta: research] Paso 1: consulta la base de conocimiento local usando la "
            "herramienta de busqueda sobre su carpeta y lectura de archivos sobre su "
            "indice (es una carpeta de markdown en esta maquina, NO es internet). "
            "Paso 2: si la base no tiene datos suficientes, entonces usa busqueda web. "
            "No respondas de memoria."
        ),
        "history": (
            "[ruta: history] Paso 1: busca en el historial de conversaciones con la "
            "herramienta de busqueda de sesiones antes de responder. La respuesta esta "
            "en lo que ya se hablo, no en tu entrenamiento. "
            "Paso 2: si no aparece, dilo y ofrece alternativas."
        ),
        # Unica ruta que no inyecta orientacion: es el escape explicito.
        ESCAPE_ROUTE: (
            "[ruta: others] Sin ruta definida para este turno. No cargues skills ni "
            "busques en fuentes: resuelve directamente con tu criterio y responde."
        ),
    }


def load_overrides(path: str) -> Optional[Dict[str, object]]:
    """Carga declaraciones y/o guías desde un YAML o JSON.

    Forma esperada del archivo::

        declarations:
          skill: "..."
          research: "..."
        guides:
          skill: "..."
          research: "..."

    Cada clave es opcional. Devuelve ``None`` ante cualquier problema (el llamador
    usa los valores internos). Nunca lanza: un archivo de configuración roto no
    puede tumbar el turno.
    """
    if not path:
        return None
    try:
        import json
        import os

        real = os.path.expanduser(path)
        if not os.path.isfile(real):
            return None
        with open(real, "r", encoding="utf-8") as fh:
            text = fh.read()
        try:
            data = json.loads(text)
        except Exception:
            try:
                import yaml
            except Exception:
                return None
            data = yaml.safe_load(text)
        if not isinstance(data, dict):
            return None
        out: Dict[str, object] = {}
        for key in ("declarations", "guides"):
            block = data.get(key)
            if isinstance(block, dict):
                out[key] = {str(k): str(v) for k, v in block.items() if v is not None}
        return out or None
    except Exception:
        return None
