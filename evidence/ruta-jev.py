#!/usr/bin/env python3
"""Hook pre_llm_call: clasifica el turno con Jev e inyecta la guia de ruta.

Entrada  (stdin): payload JSON del hook. El mensaje viene en extra.user_message.
Salida  (stdout): {"context": "<guia de ruta>"} o {} si no hay nada que inyectar.

Fail-open: ante cualquier error imprime {} (el agente sigue sin guia).
El secreto se obtiene de Infisical; nunca se imprime.
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

EP = "https://openrouter.ai/api/alpha/decisions"
USER_MD = os.path.expanduser("~/.hermes/memories/USER.md")

# La guia es un PUNTERO al camino, no el contenido del skill.
GUIA = {
    "skill": ("[ruta: skill] Antes de cualquier otra accion: busca en el catalogo de skills "
              "uno que cubra esta tarea y cargalo con skill_view. No improvises el "
              "procedimiento ni lo escribas de memoria."),
    "research": ("[ruta: research] Busca primero en el wiki local (~/wiki) empezando por "
                 "index.md. Si no esta ahi, usa web_search y web_extract. No respondas de "
                 "memoria ni de tu entrenamiento."),
    "memory": ("[ruta: memory] Busca primero en fact_store, luego en el wiki (~/wiki), luego "
               "en las herramientas disponibles. No respondas de memoria."),
    "history": ("[ruta: history] Busca en session_search el hilo anterior antes de responder. "
                "La respuesta esta en el historial de conversaciones, no en tu entrenamiento."),
    "user": ("[ruta: user] La informacion del usuario esta en USER.md (ya en tu contexto) o en "
             "el wiki. Si no esta en esas fuentes primarias, pide permiso a Mauro antes de ir "
             "a internet."),
    "others": ("[ruta: others] Sin ruta definida para este turno: resuelve segun tu criterio."),
}


def _nombre_usuario() -> str:
    """Nombre del usuario leido de USER.md. No es lista hardcodeada: es el perfil real."""
    try:
        txt = open(USER_MD).read()
    except Exception:
        return "el usuario"
    entradas = [e.strip() for e in txt.split("\n§\n") if e.strip()]
    cand: dict[str, int] = {}
    for e in entradas:
        m = re.match(r"^([A-ZÁÉÍÓÚÑ][\wáéíóúñ]+)(?=\s*[:,]|\s)", e)
        if m:
            cand[m.group(1)] = cand.get(m.group(1), 0) + 1
    for t in set(re.findall(r"\b([A-ZÁÉÍÓÚÑ][\wáéíóúñ]{2,})\b", txt)):
        n = sum(1 for e in entradas if re.search(rf"\b{re.escape(t)}\b", e))
        if n >= 2:
            cand[t] = max(cand.get(t, 0), n)
    return max(cand, key=cand.get) if cand else "el usuario"


def _decl(nombre: str) -> dict:
    return {
        "skill": ("El texto implica explicitamente o implicitamente la ejecucion de una tarea "
                  "que puede ejecutarse como un proceso de computadora."),
        "research": "Cualquier proceso o redaccion que implique investigar algo.",
        "memory": ("Obtener o recuperar cualquier dato que implique recuperar facts, datos "
                   "persistentes cortos, reglas, criterios. Siempre y cuando el valor resultante "
                   "sean redacciones o datos cortos, no mas de un parrafo."),
        "history": ("Cualquier accion que implique la recuperacion de historial o recuerdos de "
                    "sesiones o conversaciones pasadas."),
        "user": (f"El texto se refiere a la persona del usuario ({nombre}) o pide informacion "
                 "sobre el: su identidad, sus preferencias, sus habitos, su nivel tecnico, lo "
                 "que le molesta, su estilo de trato. Incluye cuando el usuario habla de si "
                 "mismo en primera persona (mi, mis, yo) sobre esos temas. Queda EXCLUIDO si es "
                 "una solicitud o encargo dirigido a quien responde (un pedido de hacer, "
                 "entregar o traer algo), aunque use 'mi' o mencione al usuario como "
                 "destinatario: ahi el usuario es quien pide, no el tema del que se guarda "
                 "informacion."),
        "others": "Lo que no encaja en las choices anteriores.",
    }


def _key() -> str | None:
    try:
        sys.path.insert(0, os.path.expanduser("~/.hermes/scripts"))
        from infisical_auth import get_secret
        return get_secret("OPENROUTER_API_KEY") or os.environ.get("OPENROUTER_API_KEY")
    except Exception:
        return os.environ.get("OPENROUTER_API_KEY")


def clasificar(texto: str, key: str) -> str | None:
    pregunta = {"type": "choice",
                "instructions": "Que es este texto?",
                "criteria": _decl(_nombre_usuario())}
    body = {"model": "~typesafe/jev-latest",
            "state": {"consulta": texto},
            "questions": {"q": pregunta}}
    req = urllib.request.Request(
        EP, data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=25) as r:
        d = json.load(r)
    return d["answers"]["q"].get("choice")


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        print("{}")
        return

    extra = payload.get("extra") or {}
    texto = extra.get("user_message") or ""
    if not isinstance(texto, str) or not texto.strip():
        print("{}")
        return

    key = _key()
    if not key:
        print("{}")
        return

    eleccion = None
    for i in range(2):
        try:
            eleccion = clasificar(texto, key)
            break
        except Exception:
            if i == 0:
                time.sleep(1)

    guia = GUIA.get(eleccion)
    if not guia:
        print("{}")
        return

    print(json.dumps({"context": guia}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("{}")
