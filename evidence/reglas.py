#!/usr/bin/env python3
"""Donde buscar — las reglas del criterio (los 4 casos).

PASO 1 (stanza)  modismo    -> true/false   (modal conjugado + infinitivo)
PASO 2 (jev)     imperativo -> true/false   (manda una orden o no)

Los 4 casos posibles:
  no modismo + imperativo     -> skill (directo)
  no modismo + no imperativo  -> calcular tipo de memoria con jev
  modismo + imperativo        -> jev choice skill/no-skill; p_skill * 0.75 vs
                                 p_no_skill. Si gana no_skill -> tipo de memoria
  modismo + no imperativo     -> calcular tipo de memoria con jev

La parte de la ultima regla que decia "si es imperativo y no hay modismo jev
analiza si es skill o no" NO se implementa: es el mismo caso que la primera
regla y la contradice (una dice skill directo, la otra que Jev decida). Manda la
primera, que es la que quedo definida para ese caso.

Uso:
    python3 reglas.py --consulta "que prometimos al cliente del hotel"
    python3 reglas.py --consulta "..." --contexto "..." --json

Codigos: 0 ok | 2 sin Jev / pasa la pelota al agente
"""

import argparse
import glob
import json
import os
import sys
import urllib.request

ENDPOINT = "https://openrouter.ai/api/alpha/decisions"
MODELO = "~typesafe/jev-latest"
TIMEOUT = 60
HELPER_DIR = os.path.expanduser("~/.hermes/scripts")
STANZA_CACHE = os.path.expanduser("~/.cache/stanza")
FACTOR = 0.50   # el descuento que definio Mauro para el caso con modismo

MODALES = ("poder", "deber", "querer", "can", "could", "would", "will",
           "pouvoir", "vouloir", "potere", "dovere", "konnen", "mussen", "wollen")


# ------------------------------------------------------------------ Jev

def _key():
    if HELPER_DIR not in sys.path:
        sys.path.insert(0, HELPER_DIR)
    try:
        from infisical_auth import get_secret  # type: ignore

        v = get_secret("OPENROUTER_API_KEY")
        if v:
            return v
    except Exception:
        pass
    return os.environ.get("OPENROUTER_API_KEY", "")


def jev(pregunta, texto, contexto=None):
    k = _key()
    if not k:
        raise RuntimeError("sin OPENROUTER_API_KEY")
    state = {"consulta": texto}
    if contexto:
        state["contexto_reciente"] = contexto
    cuerpo = {"model": MODELO, "state": state, "questions": {"q": pregunta}}
    req = urllib.request.Request(
        ENDPOINT, data=json.dumps(cuerpo).encode("utf-8"),
        headers={"Authorization": f"Bearer {k}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        d = json.load(r)
    a = d.get("answers", {}).get("q", {})
    probs = {kk: round(float(vv), 4) for kk, vv in (a.get("probabilities") or {}).items()}
    return a.get("choice"), probs


# ------------------------------------------------------------------ PASO 1

def idiomas_existentes():
    for p in sorted(glob.glob(os.path.join(STANZA_CACHE, "*", "resources", "resources.json")), reverse=True):
        try:
            with open(p) as fh:
                d = json.load(fh)
        except Exception:
            continue
        out = [k for k, v in d.items() if isinstance(v, dict) and "tokenize" in v]
        if out:
            return sorted(out)
    return []


def modelo_instalado(lang):
    for proc in ("tokenize", "pos"):
        if not glob.glob(os.path.join(STANZA_CACHE, "*", "resources", lang, proc, "*")):
            return False
    return True


_NLP = {}   # cache: el Pipeline carga el modelo en memoria; crearlo por llamada
            # la agota (sin cache, 28 cargas en una corrida = SIGKILL 137)


def _pipeline(lang):
    import stanza  # type: ignore

    if lang not in _NLP:
        _NLP[lang] = stanza.Pipeline(lang=lang, processors="tokenize,mwt,pos,lemma",
                                     verbose=False, download_method=None)
    return _NLP[lang]


def paso1_modismo(texto, lang):
    if not lang:
        return {"modismo": None, "razon": "sin idioma"}
    if not modelo_instalado(lang):
        return {"modismo": None, "razon": f"modelo Stanza de '{lang}' no instalado",
                "instalar_con": f'python3 -c "import stanza; stanza.download(\'{lang}\')"'}
    try:
        doc = _pipeline(lang)(texto)
    except Exception as e:
        return {"modismo": None, "razon": f"{type(e).__name__}: {e}"}

    modal = None
    hay_inf = False
    for s in doc.sentences:
        for w in s.words:
            f = {}
            if w.feats:
                for par in w.feats.split("|"):
                    kk, _, vv = par.partition("=")
                    f[kk] = vv
            if f.get("VerbForm") == "Inf":
                hay_inf = True
            if f.get("VerbForm") == "Fin" and (w.lemma or "").lower() in MODALES:
                modal = w.lemma
    return {"modismo": bool(modal and hay_inf), "modal": modal, "infinitivo": hay_inf}


def idioma(texto):
    ex = idiomas_existentes()
    try:
        ch, _ = jev({"type": "choice",
                     "instructions": f"En que idioma esta escrito este texto? Texto: '{texto}'",
                     "criteria": {l: f"el texto esta escrito en {l}" for l in ex}}, texto)
        if ch:
            return {"idioma": ch, "origen": "jev"}
    except Exception:
        pass
    try:
        from langdetect import detect_langs  # type: ignore

        pr = detect_langs(texto)
        if pr:
            return {"idioma": pr[0].lang, "origen": "langdetect"}
    except Exception:
        pass
    return {"idioma": None, "origen": None}


# ------------------------------------------------------------------ PASO 2

PREG_IMPERATIVO = {"type": "choice",
                   "instructions": "El texto, le manda una orden al interlocutor (imperativo), o no?",
                   "criteria": {
                       "imperativo": ("El texto le manda una orden al interlocutor: le dice que haga "
                                      "algo. Incluye el imperativo directo (dame, pasame, decime, crea, "
                                      "escribe, programa, ejecuta, configura, revisa, fijate, traeme, "
                                      "toma, anda) y tambien el pedido cortes con modal (podes/podrias "
                                      "+ infinitivo), que por costumbre es un mandato."),
                       "no_imperativo": ("El texto NO le manda una orden: pregunta algo, pide "
                                         "informacion, pide una explicacion, o recuerda algo ya "
                                         "conversado."),
                   }}


def paso2_imperativo(texto, contexto=None):
    try:
        ch, probs = jev(PREG_IMPERATIVO, texto, contexto)
    except Exception as e:
        return {"imperativo": None, "razon": f"{type(e).__name__}: {e}"}
    p = float(probs.get("imperativo", 0.0))
    return {"imperativo": (ch == "imperativo") if ch else None, "choice": ch,
            "probabilidades": probs, "p_imperativo": p}


# ------------------------------------------------------------------ skill o no

PREG_SKILL = {"type": "choice",
              "instructions": ("Para cumplir este pedido, el agente tiene que CARGAR Y SEGUIR un "
                               "procedimiento guardado, o no?"),
              "criteria": {
                  "skill": ("Para cumplirlo hay que CARGAR Y SEGUIR un procedimiento guardado: una "
                            "receta paso a paso, con sus comandos y su orden. El agente no lo sabe "
                            "de memoria; tiene que abrir el skill y ejecutarlo."),
                  "no_skill": ("No hay ningun procedimiento guardado que cargar: se resuelve "
                               "ejecutando algo puntual (consultar un dato, correr un comando suelto) "
                               "o contestando con lo que el agente ya sabe."),
              }}


def decidir_skill(texto, contexto=None):
    """choice skill/no_skill. Devuelve (p_skill, p_no_skill, detalle)."""
    try:
        ch, probs = jev(PREG_SKILL, texto, contexto)
    except Exception as e:
        return None, None, {"estado": "sin_jev", "razon": f"{type(e).__name__}: {e}"}
    return (probs.get("skill"), probs.get("no_skill"),
            {"estado": "ok", "choice": ch, "probabilidades": probs})


# ------------------------------------------------------------------ capas

CAPAS = {
    "user": ("Perfil breve y curado del principal (~1,375 caracteres, unas 7 entradas): "
             "quien es, sus preferencias, su estilo y lo que le molesta. Es un resumen "
             "DELIBERADAMENTE CORTO; no esperes aca el detalle completo de un tema."),
    "memory": ("Datos operativos cortos que el agente recuerda SIEMPRE, sin importar el tema: "
               "convenciones del entorno, gates activos, reglas de trato, particularidades de "
               "las herramientas. Presupuesto fijo (~2,200 caracteres)."),
    "fact_store": ("Almacen de hechos por demanda. Se escribe aca lo que solo importa cuando "
                   "aparece un tema concreto: un cliente, un dispositivo, un proyecto, un "
                   "precio, una IP. Hechos cortos, recuperados por palabra clave."),
    "session_search": ("Registro de las conversaciones: que se dijo, se prometio, se acordo o "
                       "quedo pendiente en una sesion anterior. Es historial de trabajo, no "
                       "conocimiento consolidado."),
    "wiki": ("Conocimiento consolidado del holding, para varios agentes o humanos: el DETALLE "
             "COMPLETO de un tema con sus relaciones y sus fuentes. Incluye guias de "
             "procedimiento (cuando el procedimiento es compartido, no de un solo agente), "
             "conceptos, comparaciones, decisiones y lecciones. Se usa cuando hace falta "
             "profundidad, no un dato suelto."),
}


def tipo_de_memoria(texto, contexto=None):
    """Pondera las 5 capas y devuelve las que quedan arriba de 0.5."""
    try:
        ch, probs = jev({"type": "choice",
                         "instructions": ("La respuesta esta guardada en alguna de estas memorias. "
                                          "Cual es la MAS probable que ya la contenga?"),
                         "criteria": CAPAS}, texto, contexto)
    except Exception as e:
        return {"estado": "sin_jev", "razon": f"{type(e).__name__}: {e}", "buscar_en": []}
    arriba = sorted(((c, p) for c, p in probs.items() if p > 0.5), key=lambda x: -x[1])
    return {"estado": "ok", "probabilidades": probs,
            "buscar_en": [c for c, _ in arriba],
            "ninguna_arriba": not arriba}


# ------------------------------------------------------------------ flujo

def analizar(texto, contexto=None, factor=FACTOR):
    r = {"consulta": texto, "contexto": bool(contexto), "factor": factor}

    i = idioma(texto)
    r["idioma"] = i
    m = paso1_modismo(texto, i.get("idioma"))
    r["paso1"] = m
    imp = paso2_imperativo(texto, contexto)
    r["paso2"] = imp

    modismo = m.get("modismo")
    imperativo = imp.get("imperativo")
    r["regla"] = None

    if modismo is None or imperativo is None:
        r["destino"] = None
        r["nota"] = "Falta modismo o imperativo: pasa la pelota al agente."
        return r

    if not modismo and imperativo:
        # R3
        r["regla"] = "R3: no modismo + imperativo -> skill"
        r["destino"] = "skills"; r["buscar_en"] = ["skills"]
        return r

    if not modismo and not imperativo:
        # R4
        r["regla"] = "R4: no modismo + no imperativo -> tipo de memoria"
        cap = tipo_de_memoria(texto, contexto)
        r["capas"] = cap
        r["buscar_en"] = cap.get("buscar_en", [])
        r["destino"] = r["buscar_en"][0] if r["buscar_en"] else None
        if not r["buscar_en"]:
            r["nota"] = "Ninguna capa quedo arriba de 0.5."
        return r

    if modismo and imperativo:
        # R5: p_skill * factor vs p_no_skill
        r["regla"] = f"modismo + imperativo -> skill*{factor} vs no_skill"
        p_sk, p_no, det = decidir_skill(texto, contexto)
        r["decision_skill"] = det
        if p_sk is None:
            r["destino"] = None
            r["nota"] = "Jev no disponible para decidir skill."
            return r
        ajustado = p_sk * factor
        r["calculo"] = {"p_skill": p_sk, "p_skill_ajustado": round(ajustado, 4),
                        "p_no_skill": p_no, "factor": factor}
        if ajustado > p_no:
            r["destino"] = "skills"; r["buscar_en"] = ["skills"]
            return r
        cap = tipo_de_memoria(texto, contexto)
        r["capas"] = cap
        r["buscar_en"] = cap.get("buscar_en", [])
        r["destino"] = r["buscar_en"][0] if r["buscar_en"] else None
        if not r["buscar_en"]:
            r["nota"] = "No es skill y ninguna capa quedo arriba de 0.5."
        return r

    # modismo + no imperativo -> calcular tipo de memoria
    r["regla"] = "modismo + no imperativo -> tipo de memoria"
    cap = tipo_de_memoria(texto, contexto)
    r["capas"] = cap
    r["buscar_en"] = cap.get("buscar_en", [])
    r["destino"] = r["buscar_en"][0] if r["buscar_en"] else None
    if not r["buscar_en"]:
        r["nota"] = "Ninguna capa quedo arriba de 0.5."
    return r


def main():
    ap = argparse.ArgumentParser(description="Donde buscar — 6 reglas (stanza + jev).")
    ap.add_argument("--consulta", required=True)
    ap.add_argument("--contexto", default=None)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    r = analizar(a.consulta, a.contexto)

    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return 2 if r["destino"] is None else 0

    print(f'Consulta: {r["consulta"]}')
    print(f'  P1 modismo    : {r["paso1"].get("modismo")}'
          + (f' (modal={r["paso1"].get("modal")})' if r["paso1"].get("modismo") else "")
          + (f' [{r["paso1"].get("razon")}]' if r["paso1"].get("razon") else ""))
    print(f'  P2 imperativo : {r["paso2"].get("imperativo")} '
          f'(p={r["paso2"].get("p_imperativo")})')
    print(f'  REGLA         : {r["regla"]}')
    if r.get("calculo"):
        c = r["calculo"]
        print(f'  CALCULO       : {c["p_skill"]} x {c["factor"]} = {c["p_skill_ajustado"]} '
              f'vs {c["p_no_skill"]}')
    if r.get("capas"):
        print("  CAPAS (arriba de 0.5):")
        for k, v in sorted(r["capas"]["probabilidades"].items(), key=lambda x: -x[1]):
            print(f'          {k:15} {v:.2f}{"  <-" if v > 0.5 else ""}')
    print(f'  DESTINO       : {r["destino"] or "(pasa la pelota al agente)"}')
    print(f'  BUSCAR EN     : {" > ".join(r["buscar_en"]) if r["buscar_en"] else "(nada)"}')
    if r.get("nota"):
        print(f'  NOTA          : {r["nota"]}')
    return 2 if r["destino"] is None else 0


if __name__ == "__main__":
    sys.exit(main())
