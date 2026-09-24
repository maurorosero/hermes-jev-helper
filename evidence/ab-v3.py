#!/usr/bin/env python3
"""A/B v3: la guia de ruta (con el Paso 2 de 'skill' corregido), deepseek-v4.1-flash.

Cambio de METRICA respecto al A/B v1 (correccion de Mauro 2026-09-23):
  - v1 media "¿la tool de mi etiqueta esta en las primeras 3 posiciones?"
    → premiaba la coincidencia con MI criterio, no la llegada al dato.
  - v3 mide LLEGADA AL DATO: ¿el agente toco la fuente primaria en algun momento
    de la tarea? Y ademas: ¿aviso cuando no habia skill? (Paso 2)

Diseno: 10 casos fijos, mismo modelo y orden.
  FASE A: sin hook (config original, byte-exacto)
  FASE B: con hook (bloque hooks: agregado al final)
Seguridad: backup byte-exacto de config.yaml; restauracion por copia.
"""
import json
import os
import re
import shutil
import subprocess
import sqlite3
import sys
import time
from pathlib import Path

HOME = Path.home()
CFG = HOME / ".hermes" / "config.yaml"
STATE = HOME / ".hermes" / "state.db"
BK = Path("/tmp/ab-hook/config.yaml.bak")
MODELO = "deepseek-v4.1-flash"
OUT = Path("/tmp/ab-hook/resultados-v3.json")

HOOK_BLOCK = """
# --- A/B temporal: guia de ruta via pre_llm_call (quitar al terminar) ---
hooks:
  pre_llm_call:
    - command: "/tmp/ab-hook/ruta-jev-v2.py"
      timeout: 25
hooks_auto_accept: true
# --- fin A/B temporal ---
"""

CASOS = [
    # (texto, ruta esperada, tools que cuentan como LLEGADA AL DATO)
    ("revisa si el contenedor de Frigate esta vivo", "skill",
     ("terminal", "ha_call_service", "ha_get_state", "ha_list_entities")),
    ("revisa el estado de los repos git en ~/developers", "skill",
     ("terminal",)),
    ("busca en el wiki si existe la entidad del holding", "research",
     ("read_file", "search_files", "web_search", "web_extract")),
    ("investiga opciones de NVR con GPU para 8 camaras", "research",
     ("web_search", "web_extract")),
    ("investiga como facturan las ONG en Panama", "research",
     ("web_search", "web_extract")),
    ("cuanto mide el lote de la casa de Don Bosco", "memory",
     ("fact_store",)),
    ("cual es la licencia de Odoo Enterprise para LATAM", "memory",
     ("fact_store",)),
    ("que te dije ayer sobre el hotel", "history",
     ("session_search",)),
    ("como le gusta que le hable al usuario", "user",
     ("read_file", "search_files")),
    ("cuentame un chiste corto", "others",
     ()),  # sin fuente: la metrica es que NO busque
]


def correr(texto: str, con_hook: bool) -> dict:
    env = os.environ.copy()
    if con_hook:
        env["HERMES_ACCEPT_HOOKS"] = "1"
    t0 = time.perf_counter()
    try:
        p = subprocess.run(
            ["hermes", "chat", "-Q", "--oneshot", "-m", MODELO,
             "--max-turns", "12", "-q", texto],
            capture_output=True, text=True, timeout=500, env=env,
            cwd=str(HOME))
        salida = (p.stdout or "") + (p.stderr or "")
        rc = p.returncode
    except subprocess.TimeoutExpired:
        salida, rc = "", "TIMEOUT"
    dt = time.perf_counter() - t0
    m = re.search(r"session_id:\s*(\S+)", salida)
    # la respuesta final: lo que va despues de la linea session_id
    resp = ""
    if m:
        resp = salida.split(m.group(0), 1)[-1]
    return {"texto": texto, "con_hook": con_hook,
            "session_id": m.group(1) if m else None,
            "seg": round(dt, 1), "rc": rc, "respuesta": resp.strip()[:700]}


def medir(session_id: str) -> dict:
    out = {"calls": None, "tin": None, "tout": None, "tools": [], "ruta": None}
    if not session_id:
        return out
    try:
        c = sqlite3.connect(f"file:{STATE}?mode=ro", uri=True)
        r = c.execute(
            """SELECT SUM(api_call_count), SUM(input_tokens), SUM(output_tokens)
               FROM session_model_usage WHERE session_id=?""", (session_id,)).fetchone()
        if r and r[0]:
            out.update({"calls": r[0], "tin": r[1], "tout": r[2]})
        out["tools"] = [x[0] for x in c.execute(
            """SELECT tool_name FROM messages
               WHERE session_id=? AND tool_name IS NOT NULL ORDER BY id""", (session_id,))]
        # ruta inyectada, leida del sidecar
        row = c.execute("""SELECT api_content, content FROM messages
                           WHERE session_id=? AND role='user' ORDER BY id LIMIT 1""",
                        (session_id,)).fetchone()
        if row:
            t = (row[0] or row[1] or "")
            mm = re.search(r"\[ruta: (\w+)\]", t)
            out["ruta"] = mm.group(1) if mm else None
        c.close()
    except Exception as e:
        out["error"] = str(e)
    return out


def fase(con_hook: bool) -> list:
    etq = "CON hook" if con_hook else "SIN hook"
    print(f"\n{'='*62}\nFASE {etq}\n{'='*62}", flush=True)
    res = []
    for i, (texto, ruta, _) in enumerate(CASOS, 1):
        print(f"\n[{i}/{len(CASOS)}] {texto}", flush=True)
        r = correr(texto, con_hook)
        r["ruta_esperada"] = ruta
        r.update(medir(r["session_id"]))
        res.append(r)
        print(f"   session={r['session_id']} {r['seg']}s calls={r['calls']} "
              f"in={r['tin']} out={r['tout']}", flush=True)
        print(f"   ruta={r['ruta']}  tools={r['tools'][:6]}", flush=True)
        prev = json.loads(OUT.read_text()) if OUT.exists() else {}
        prev[etq] = res
        OUT.write_text(json.dumps(prev, indent=2, ensure_ascii=False))
    return res


def main() -> None:
    if not CFG.exists():
        print("no existe config.yaml"); sys.exit(1)
    if not BK.exists():
        shutil.copy2(CFG, BK)
        print(f"backup: {BK} ({CFG.stat().st_size} b)")

    fase(False)

    original = BK.read_text()
    CFG.write_text(original + HOOK_BLOCK)
    if "pre_llm_call" not in CFG.read_text():
        print("ERROR: hook no escrito; abortando"); sys.exit(1)
    print(f"\nhook activado ({CFG})")
    try:
        fase(True)
    finally:
        CFG.write_text(original)
        assert CFG.read_text() == original, "config NO quedo byte-exacta"
        print(f"\nconfig restaurada byte-exacto")

    # ---- reporte con la metrica corregida ----
    data = json.loads(OUT.read_text())
    print(f"\n{'='*62}\nRESUMEN (metrica: LLEGADA AL DATO)\n{'='*62}")
    tabla = {}
    for etq in ("SIN hook", "CON hook"):
        rs = data.get(etq, [])
        validos = [r for r in rs if r.get("calls")]
        llegaron = 0; evaluables = 0; buscaron_de_mas = 0
        for r in rs:
            exp = next((t for tx, rte, t in CASOS if tx == r["texto"]), ())
            tools = r.get("tools") or []
            if not exp:
                # caso 'others': la metrica es que NO haya buscado
                if not any(t in tools for t in ("web_search", "web_extract",
                                                "session_search", "skill_view")):
                    llegaron += 1
                else:
                    buscaron_de_mas += 1
                evaluables += 1
                continue
            evaluables += 1
            if any(t in tools for t in exp):
                llegaron += 1
        tin = [r["tin"] for r in validos if r["tin"]]
        tout = [r["tout"] for r in validos if r["tout"]]
        calls = [r["calls"] for r in validos]
        seg = [r["seg"] for r in rs]
        tabla[etq] = {"llegaron": llegaron, "eval": evaluables,
                      "tin": sum(tin), "tout": sum(tout),
                      "calls": sum(calls), "seg": sum(seg), "n": len(validos)}
        print(f"\n{etq}: n_validos={len(validos)}/{len(rs)}")
        print(f"  llego al dato: {llegaron}/{evaluables}")
        print(f"  calls={sum(calls)}  in={sum(tin):,}  out={sum(tout):,}  "
              f"tiempo={sum(seg):.0f}s")

    if "SIN hook" in tabla and "CON hook" in tabla:
        a, b = tabla["SIN hook"], tabla["CON hook"]
        print(f"\n{'='*62}\nDELTA (CON vs SIN)\n{'='*62}")
        print(f"  llegada al dato: {a['llegaron']}/{a['eval']} -> {b['llegaron']}/{b['eval']}")
        for k, lbl in (("calls", "calls"), ("tin", "input"), ("tout", "output"), ("seg", "tiempo")):
            x, y = a[k], b[k]
            d = ((y - x) / x * 100) if x else 0
            print(f"  {lbl:7s} {x:>10,} -> {y:>10,}   {d:+.1f}%")
    print(f"\ndetalle: {OUT}")


if __name__ == "__main__":
    main()
