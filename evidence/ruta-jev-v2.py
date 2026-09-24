#!/usr/bin/env python3
"""Hook pre_llm_call v2: la guia NOMBRA el skill a cargar, no lo deja a interpretacion.

Correcciones sobre v1 (diagnostico de Mauro 2026-09-23):
  - v1 decia "busca en el wiki local (~/wiki)" -> el agente no sabe que es eso,
    lo interpreta como internet. v2 dice QUE SKILL cargar.
  - v1 no encadenaba: v2 usa "si ... no alcanza, entonces ...".
  - v2 nombra la fuente primaria con su ruta absoluta.

Entrada  (stdin): payload JSON del hook; el mensaje viene en extra.user_message.
Salida  (stdout): {"context": "<guia>"} o {} si no hay nada que inyectar.
Fail-open: ante cualquier error imprime {}.
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

# La guia NOMBRA el skill y la ruta exacta. Nunca deja la fuente a interpretacion.
GUIA = {
    "skill": ("[ruta: skill] Paso 1 (obligatorio): revisa el catalogo con skills_list y si hay un "
              "skill que cubra la tarea, cargalo con skill_view y segui su procedimiento. "
              "Paso 2: si no hay ninguno, no busques en internet por defecto ni inventes un "
              "procedimiento largo: ejecuta con tu criterio y avisame que no habia skill. "
              "Paso 3: si la accion es irreversible o toca infraestructura, preguntame antes. "
              "Si el procedimiento fue nuevo, ofreceme guardarlo como skill."),
    "research": ("[ruta: research] Paso 1: carga el skill 'wiki-llm-rosero' con skill_view y "
                 "consulta el wiki local en ~/wiki empezando por index.md (es una carpeta de "
                 "archivos markdown en esta maquina, NO es internet). Paso 2: si el wiki no "
                 "tiene datos suficientes, entonces usa web_search y web_extract. No respondas "
                 "de memoria ni de tu entrenamiento."),
    "memory": ("[ruta: memory] Paso 1: busca en fact_store con fact_store(action='search'). "
               "Paso 2: si no esta ahi, busca en el wiki local ~/wiki (carpeta markdown en esta "
               "maquina, NO internet). Paso 3: si tampoco esta, entonces usa las herramientas "
               "disponibles. No respondas de memoria ni de tu entrenamiento."),
    "history": ("[ruta: history] Paso 1: busca en el historial de conversaciones con "
                "session_search antes de responder. La respuesta esta en lo que ya se hablo, no "
                "en tu entrenamiento. Paso 2: si no aparece, dilo y ofrece alternativas."),
    "user": ("[ruta: user] La informacion sobre el usuario esta en USER.md (ya en tu contexto) y "
             "en el wiki local ~/wiki. Paso 1: revisa esas dos fuentes. Paso 2: si no esta en "
             "ninguna, pide permiso antes de ir a internet."),
    "others": ("[ruta: others] Sin ruta definida para este turno. No cargues skills ni busques "
               "en fuentes: resuelve directamente con tu criterio y responde."),
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


def _key():
    try:
        sys.path.insert(0, os.path.expanduser("~/.hermes/scripts"))
        from infisical_auth import get_secret
        return get_secret("OPENROUTER_API_KEY") or os.environ.get("OPENROUTER_API_KEY")
    except Exception:
        return os.environ.get("OPENROUTER_API_KEY")


def clasificar(texto: str, key: str):
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
