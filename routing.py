"""Declaraciones de criterio y guías de ruta.

Este módulo es el CORAZÓN del mecanismo y es deliberadamente datos, no lógica:
las declaraciones que el clasificador recibe y las guías que se inyectan en el
turno. Separarlas del código permite revisarlas, versionarlas y sobreescribirlas
sin tocar el motor.

Las declaraciones siguen un principio de diseño que la investigación estableció:
cada ruta se declara por el RESULTADO ESPERADO, no por la tarea. Las que describen
una tarea (skill, research) dependen del verbo del texto; las que nombran un
resultado (memory, history, user) son más estables.

Ver docs/paper-es.md §4.2 y Apéndices A y B del estudio de caso.
"""

from __future__ import annotations

from typing import Dict, Optional

# El orden es el orden de presentación de las opciones al clasificador.
ROUTES = ("skill", "research", "memory", "history", "user", "others")

# Nombre de la ruta de escape. No inyecta guía: declara que no hay ruta definida.
ESCAPE_ROUTE = "others"


def declarations(user_name: str = "") -> Dict[str, str]:
    """Criterios de clasificación, uno por ruta.

    ``user_name`` entra en la declaración de ``user`` para que la ruta se resuelva
    contra el perfil real y no contra una lista de nombres codificada. Si viene
    vacío, la declaración usa un texto genérico.
    """
    quien = user_name or "el usuario"
    return {
        "skill": (
            "El texto implica explicita o implicitamente la ejecucion de una tarea "
            "que puede ejecutarse como un proceso de computadora."
        ),
        "research": (
            "Cualquier proceso o redaccion que implique investigar algo."
        ),
        "memory": (
            "Obtener o recuperar cualquier dato que implique recuperar facts, datos "
            "persistentes cortos, reglas, criterios. Siempre y cuando el valor "
            "resultante sean redacciones o datos cortos, no mas de un parrafo."
        ),
        "history": (
            "Cualquier accion que implique la recuperacion de historial o recuerdos "
            "de sesiones o conversaciones pasadas."
        ),
        "user": (
            f"El texto se refiere a la persona del usuario ({quien}) o pide "
            "informacion sobre el: su identidad, sus preferencias, sus habitos, su "
            "nivel tecnico, lo que le molesta, su estilo de trato. Incluye cuando el "
            "usuario habla de si mismo en primera persona (mi, mis, yo) sobre esos "
            "temas. Queda EXCLUIDO si es una solicitud o encargo dirigido a quien "
            "responde (un pedido de hacer, entregar o traer algo), aunque use 'mi' o "
            "mencione al usuario como destinatario: ahi el usuario es quien pide, no "
            "el tema del que se guarda informacion."
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
        "memory": (
            "[ruta: memory] Paso 1: busca en la memoria persistente de hechos con su "
            "herramienta de busqueda - es una tool directa, no requiere cargar ningun "
            "skill. Paso 2: si no esta ahi, dilo y ofrece las vias para buscarlo (base "
            "de conocimiento, documentos, o web) y pedi confirmacion antes de salir. "
            "Paso 3: con lo que hayas obtenido, resuelve con libertad, como en others."
        ),
        "history": (
            "[ruta: history] Paso 1: busca en el historial de conversaciones con la "
            "herramienta de busqueda de sesiones antes de responder. La respuesta esta "
            "en lo que ya se hablo, no en tu entrenamiento. "
            "Paso 2: si no aparece, dilo y ofrece alternativas."
        ),
        "user": (
            "[ruta: user] Paso 1: revisa las fuentes primarias del usuario: lee su "
            "archivo de perfil y consulta la base de conocimiento local (carpeta "
            "markdown en esta maquina, NO internet). "
            "Paso 2: si no esta en esas fuentes, usa la herramienta de confirmacion "
            "para PEDIR APROBACION antes de usar busqueda web."
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

        user_name: Mauro
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
        if isinstance(data.get("user_name"), str):
            out["user_name"] = data["user_name"]
        return out or None
    except Exception:
        return None
