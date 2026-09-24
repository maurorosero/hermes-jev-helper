#!/usr/bin/env python3
"""A/B v4: rutas ajustadas (clarify, wiki via search_files/read_file, memory con libertad).

Cambios vs v3:
  - usa /tmp/ab-hook/ruta-jev-v4.py (las 6 rutas ajustadas)
  - guarda la RESPUESTA COMPLETA (no truncada) para poder evaluar calidad
  - mide reasoning_tokens por caso (en v3 dio 0 en las 20 corridas)

Diseno: 10 casos fijos, deepseek-v4.1-flash, mismo orden.
  FASE A: sin hook (control)   FASE B: con hook
Seguridad: backup byte-exacto; restauracion por copia.
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
OUT = Path("/tmp/ab-hook/resultados-v4.json")

HOOK_BLOCK = """
# --- A/B temporal: guia de ruta via pre_llm_call (quitar al terminar) ---
hooks:
  pre_llm_call:
    - command: "/tmp/ab-hook/ruta-jev-v4.py"
      timeout: 25
hooks_auto_accept: true
# --- fin A/B temporal ---
"""

CASOS = [
    ("revisa si el contenedor de Frigate esta vivo", "skill"),
    ("revisa el estado de los repos git en ~/developers", "skill"),
    ("busca en el wiki si existe la entidad del holding", "research"),
    ("investiga opciones de NVR con GPU para 8 camaras", "research"),
    ("investiga como facturan las ONG en Panama", "research"),
    ("cuanto mide el lote de la casa de Don Bosco", "memory"),
    ("cual es la licencia de Odoo Enterprise para LATAM", "memory"),
    ("que te dije ayer sobre el hotel", "history"),
    ("como le gusta que le hable al usuario", "user"),
    ("cuentame un chiste corto", "others"),
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
            capture_output=True, text=True, timeout=500, env=env, cwd=str(HOME))
        salida = (p.stdout or "") + (p.stderr or "")
        rc = p.returncode
    except subprocess.TimeoutExpired:
        salida, rc = "", "TIMEOUT"
    dt = time.perf_counter() - t0
    m = re.search(r"session_id:\s*(\S+)", salida)
    resp = ""
    if m:
        resp = salida.split(m.group(0), 1)[-1]
        resp = resp.replace("__HERMES_CWD_", "").strip()
    return {"texto": texto, "con_hook": con_hook,
            "session_id": m.group(1) if m else None,
            "seg": round(dt, 1), "rc": rc,
            "respuesta_completa": resp}


def medir(session_id: str) -> dict:
    out = {"calls": None, "tin": None, "tout": None, "reasoning": None,
           "tools": [], "ruta": None}
    if not session_id:
        return out
    try:
        c = sqlite3.connect(f"file:{STATE}?mode=ro", uri=True)
        r = c.execute(
            """SELECT SUM(api_call_count), SUM(input_tokens), SUM(output_tokens),
                      SUM(reasoning_tokens)
               FROM session_model_usage WHERE session_id=?""", (session_id,)).fetchone()
        if r and r[0]:
            out.update({"calls": r[0], "tin": r[1], "tout": r[2], "reasoning": r[3]})
        out["tools"] = [x[0] for x in c.execute(
            """SELECT tool_name FROM messages
               WHERE session_id=? AND tool_name IS NOT NULL ORDER BY id""", (session_id,))]
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
    print(f"\n{'='*64}\nFASE {etq}\n{'='*64}", flush=True)
    res = []
    for i, (texto, ruta) in enumerate(CASOS, 1):
        print(f"\n[{i}/{len(CASOS)}] {texto}", flush=True)
        r = correr(texto, con_hook)
        r["ruta_esperada"] = ruta
        r.update(medir(r["session_id"]))
        res.append(r)
        print(f"   session={r['session_id']}  {r['seg']}s  ciclos={r['calls']}  "
              f"in={r['tin']}  out={r['tout']}  reason={r['reasoning']}", flush=True)
        print(f"   ruta={r['ruta']}", flush=True)
        print(f"   tools: {r['tools']}", flush=True)
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

    # GUARD: el hook debe ser ejecutable y devolver contexto. Sin esto, un +x
    # faltante hace que el hook falle en silencio (fail-open) y la fase "con hook"
    # corra en realidad SIN guia.
    HK = "/tmp/ab-hook/ruta-jev-v4.py"
    if not os.access(HK, os.X_OK):
        print(f"ERROR: {HK} NO es ejecutable; abortando"); sys.exit(1)
    prueba = subprocess.run(
        [HK], input='{"extra":{"user_message":"revisa el estado de los repos git"}}',
        capture_output=True, text=True, timeout=90)
    if "[ruta:" not in (prueba.stdout or ""):
        print(f"ERROR: el hook no devolvio contexto. stdout={prueba.stdout!r} "
              f"stderr={prueba.stderr[:200]!r}; abortando"); sys.exit(1)
    print(f"GUARD OK: hook ejecutable y devuelve contexto")
    print(f"hook activado ({CFG})")
    try:
        fase(True)
    finally:
        CFG.write_text(original)
        assert CFG.read_text() == original, "config NO quedo byte-exacta"
        print("\nconfig restaurada byte-exacto")

    # ---- reporte con el formto aceptado ----
    data = json.loads(OUT.read_text())
    import statistics as st
    print(f"\n{'='*64}\nRESUMEN\n{'='*64}")

    def stats(rs):
        v = [r for r in rs if r.get("calls")]
        return {
            "calls": st.median([r["calls"] for r in v]),
            "tin":   st.median([r["tin"] for r in v]),
            "tout":  st.median([r["tout"] for r in v]),
            "seg":   st.median([r["seg"] for r in rs]),
            "reason": sum((r.get("reasoning") or 0) for r in v),
            "n": len(v),
        }

    a = stats(data["SIN hook"]); b = stats(data["CON hook"])
    print(f"{'':22s} {'SIN hook':>12s} {'CON hook':>12s} {'delta':>10s}")
    for k, lbl, fmt in (("calls","ciclos (mediana)",".1f"), ("tin","input (mediana)",",.0f"),
                        ("tout","output (mediana)",",.0f"), ("seg","tiempo (mediana)",".0f")):
        d = ((b[k]-a[k])/a[k]*100) if a[k] else 0
        print(f"{lbl:22s} {a[k]:>12{fmt}} {b[k]:>12{fmt}} {d:>9.1f}%")
    print(f"{'reasoning (total)':22s} {a['reason']:>12,} {b['reason']:>12,}")

    print(f"\nRUTA INYECTADA POR JEV:")
    for r in data["CON hook"]:
        ok = "OK " if r.get("ruta") == r["ruta_esperada"] else "-> "
        print(f"  {ok} ruta={str(r.get('ruta')):9s} esperada={r['ruta_esperada']:9s} "
              f"{r['texto'][:44]}")
    print(f"\ndetalle: {OUT}")


if __name__ == "__main__":
    main()
