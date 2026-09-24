#!/usr/bin/env python3
"""Choices integradas en UNA pregunta: skill / research / memory / history / user.

El nombre del usuario se lee de USER.md (perfil real, no lista hardcodeada).
Respuestas crudas de Jev, sin interpretacion.
"""
import json, sys, os, time, re, urllib.request, urllib.error
sys.path.insert(0, os.path.expanduser("~/.hermes/scripts"))
from infisical_auth import get_secret

KEY = get_secret("OPENROUTER_API_KEY") or os.environ.get("OPENROUTER_API_KEY", "")
EP = "https://openrouter.ai/api/alpha/decisions"
USER_MD = os.path.expanduser("~/.hermes/memories/USER.md")


def nombre_del_usuario():
    txt = open(USER_MD).read()
    entradas = [e.strip() for e in txt.split("\n§\n") if e.strip()]
    cand = {}
    for e in entradas:
        m = re.match(r"^([A-ZÁÉÍÓÚÑ][\wáéíóúñ]+)(?=\s*[:,]|\s)", e)
        if m:
            cand[m.group(1)] = cand.get(m.group(1), 0) + 1
    for t in set(re.findall(r"\b([A-ZÁÉÍÓÚÑ][\wáéíóúñ]{2,})\b", txt)):
        n = sum(1 for e in entradas if re.search(rf"\b{re.escape(t)}\b", e))
        if n >= 2:
            cand[t] = max(cand.get(t, 0), n)
    return max(cand, key=cand.get) if cand else None


NOMBRE = nombre_del_usuario()

DECL = {
    "skill": ("El texto implica explicitamente o implicitamente la ejecucion de una tarea "
              "que puede ejecutarse como un proceso de computadora."),
    "research": ("Cualquier proceso o redaccion que implique investigar algo."),
    "memory": ("Obtener o recuperar cualquier dato que implique recuperar facts, datos "
               "persistentes cortos, reglas, criterios. Siempre y cuando el valor resultante sean "
               "redacciones o datos cortos, no mas de un parrafo."),
    "history": ("Cualquier accion que implique la recuperacion de historial o recuerdos de "
                "sesiones o conversaciones pasadas."),
    "user": (f"El texto se refiere a la persona del usuario ({NOMBRE}) o pide informacion sobre "
             "el: su identidad, sus preferencias, sus habitos, su nivel tecnico, lo que le "
             "molesta, su estilo de trato. Incluye cuando el usuario habla de si mismo en "
             "primera persona (mi, mis, yo) sobre esos temas. Queda EXCLUIDO si es una solicitud "
             "o encargo dirigido a quien responde (un pedido de hacer, entregar o traer algo), "
             "aunque use 'mi' o mencione al usuario como destinatario: ahi el usuario es quien "
             "pide, no el tema del que se guarda informacion."),
    "others": ("Lo que no encaja en las choices anteriores."),
}

PREGUNTA = {"type": "choice",
            "instructions": "Que es este texto?",
            "criteria": DECL}

CASOS = [
 # skill
 ("pasame el reporte del mes", "skill"),
 ("configura un proveedor nuevo", "skill"),
 ("ejecuta el validador", "skill"),
 ("programa el respaldo de la base de datos", "skill"),
 ("borra los archivos temporales", "skill"),
 # research
 ("investiga actos de habla indirectos", "research"),
 ("haceme un informe de videovigilancia", "research"),
 ("averigua opciones de NVR con GPU", "research"),
 # memory
 ("cuanto cobramos por hora", "memory"),
 ("cual es la capital de Francia", "memory"),
 ("El VPS de Alan corre en Hetzner", "memory"),
 ("como funciona la memoria holografica", "memory"),
 # history
 ("que te dije ayer sobre el hotel", "history"),
 ("que prometimos al cliente del hotel", "history"),
 ("recuerda que hablamos de la videovigilancia", "history"),
 # user
 ("Mauro prefiere respuestas concisas sin preambulo", "user"),
 ("A Mauro le molesta que le den vueltas antes de responder", "user"),
 ("Mauro esta en zona horaria EST", "user"),
 ("Mauro tiene nivel tecnico alto", "user"),
 ("quien es Mauro", "user"),
 ("que prefiere el usuario", "user"),
 ("cuales son mis preferencias", "user"),
 ("mi zona horaria es EST", "user"),
 ("como le gusta que le hable al usuario", "user"),
]


def jev(pregunta, texto, intentos=4):
    for i in range(intentos):
        try:
            body = {"model": "~typesafe/jev-latest", "state": {"consulta": texto},
                    "questions": {"q": pregunta}}
            req = urllib.request.Request(EP, data=json.dumps(body).encode(),
                headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if i == intentos - 1:
                return {"error": f"HTTP {e.code}"}
            time.sleep(3 * (i + 1))
        except Exception as e:
            if i == intentos - 1:
                return {"error": f"{type(e).__name__}: {e}"}
            time.sleep(3 * (i + 1))


ORDEN = ("skill", "research", "memory", "history", "user", "others")
print(f"nombre leido de USER.md: {NOMBRE}\n")
for texto, esp in CASOS:
    d = jev(PREGUNTA, texto)
    if "error" in d:
        print(f"### {texto}\n{{'error': {d['error']!r}}}\n")
        continue
    q = d["answers"]["q"]
    print(f"### {texto}")
    print(f"  choice: {q.get('choice')}   confidence: {q.get('confidence')}")
    for k in ORDEN:
        v = (q.get("probabilities") or {}).get(k)
        if v is not None:
            print(f"    {k}: {v}")
    print()
