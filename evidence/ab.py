#!/usr/bin/env python3
"""A/B: la guia de ruta inyectada por pre_llm_call, con deepseek-v4.1-flash.

Diseno:
  - 10 casos fijos, mismo modelo, mismo orden.
  - FASE A: sin hook  (config original, byte-exacto)
  - FASE B: con hook  (bloque hooks: agregado al final)
  - Cada corrida es una sesion nueva: hermes chat -Q --oneshot -m deepseek-v4.1-flash
  - Se mide por session_id, leido de state.db: api_call_count, input/output tokens,
    y la SECUENCIA de tools (para ver si busco antes de responder).

Seguridad: backup byte-exacto de config.yaml; restauracion por copia del backup
(nunca round-trip de YAML, para no reformatear el archivo de Mauro).
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
OUT = Path("/tmp/ab-hook/resultados.json")

HOOK_BLOCK = """
# --- A/B temporal: guia de ruta via pre_llm_call (quitar al terminar) ---
hooks:
  pre_llm_call:
    - command: "/tmp/ab-hook/ruta-jev.py"
      timeout: 25
hooks_auto_accept: true
# --- fin A/B temporal ---
"""

CASOS = [
    # (texto, ruta esperada)
    ("revisa si el contenedor de Frigate esta vivo", "skill"),
    ("revisa el estado de los repos git en ~/developers", "skill"),
    ("busca en el wiki si existe la entidad del holding", "skill"),
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
            capture_output=True, text=True, timeout=420, env=env,
            cwd=str(HOME),
        )
        salida = (p.stdout or "") + (p.stderr or "")
        rc = p.returncode
    except subprocess.TimeoutExpired:
        salida, rc = "", "TIMEOUT"
    dt = time.perf_counter() - t0
    m = re.search(r"session_id:\s*(\S+)", salida)
    return {
        "texto": texto, "con_hook": con_hook,
        "session_id": m.group(1) if m else None,
        "seg": round(dt, 1), "rc": rc,
        "respuesta": salida.strip()[-600:],
    }


def medir(session_id: str) -> dict:
    """Lee tokens y secuencia de tools de la sesion en state.db."""
    out = {"calls": None, "tin": None, "tout": None, "cache_rd": None,
           "tools": [], "tool_seq_head": []}
    if not session_id:
        return out
    try:
        c = sqlite3.connect(f"file:{STATE}?mode=ro", uri=True)
        r = c.execute(
            """SELECT SUM(api_call_count), SUM(input_tokens), SUM(output_tokens),
                      SUM(cache_read_tokens)
               FROM session_model_usage WHERE session_id=?""", (session_id,)).fetchone()
        if r and r[0]:
            out.update({"calls": r[0], "tin": r[1], "tout": r[2], "cache_rd": r[3]})
        tools = [x[0] for x in c.execute(
            """SELECT tool_name FROM messages
               WHERE session_id=? AND tool_name IS NOT NULL ORDER BY id""", (session_id,))]
        out["tools"] = tools
        out["tool_seq_head"] = tools[:6]
        c.close()
    except Exception as e:
        out["error"] = str(e)
    return out


def fase(con_hook: bool) -> list:
    etq = "CON hook" if con_hook else "SIN hook"
    print(f"\n{'='*62}\nFASE {etq}\n{'='*62}", flush=True)
    res = []
    for i, (texto, ruta) in enumerate(CASOS, 1):
        print(f"\n[{i}/{len(CASOS)}] {texto}", flush=True)
        r = correr(texto, con_hook)
        r["ruta_esperada"] = ruta
        r.update(medir(r["session_id"]))
        res.append(r)
        print(f"   session={r['session_id']}  {r['seg']}s  calls={r['calls']}  "
              f"in={r['tin']}  out={r['tout']}", flush=True)
        print(f"   tools: {r['tool_seq_head']}", flush=True)
        # guardar progreso incremental
        prev = json.loads(OUT.read_text()) if OUT.exists() else {}
        prev[etq] = res
        OUT.write_text(json.dumps(prev, indent=2, ensure_ascii=False))
    return res


def main() -> None:
    if not CFG.exists():
        print("no existe config.yaml"); sys.exit(1)

    # backup byte-exacto
    if not BK.exists():
        shutil.copy2(CFG, BK)
        print(f"backup: {BK}  ({CFG.stat().st_size} b)")

    fase(False)

    # activar hook (append textual: no reformatea el YAML de Mauro)
    original = BK.read_text()
    CFG.write_text(original + HOOK_BLOCK)
    print(f"\nhook activado en {CFG}")
    if "pre_llm_call" not in CFG.read_text():
        print("ERROR: el hook no quedo escrito; abortando fase B"); sys.exit(1)
    try:
        fase(True)
    finally:
        CFG.write_text(original)
        assert CFG.read_text() == original, "la config NO quedo byte-exacta"
        print(f"\nconfig restaurada byte-exacto desde {BK}")

    # reporte
    data = json.loads(OUT.read_text())
    print(f"\n{'='*62}\nRESUMEN\n{'='*62}")
    for etq in ("SIN hook", "CON hook"):
        rs = [r for r in data.get(etq, []) if r.get("calls")]
        if not rs:
            print(f"{etq}: sin datos"); continue
        tot_in = sum(r["tin"] or 0 for r in rs)
        tot_out = sum(r["tout"] or 0 for r in rs)
        tot_calls = sum(r["calls"] or 0 for r in rs)
        tot_seg = sum(r["seg"] for r in rs)
        print(f"{etq}: n={len(rs)}  calls={tot_calls}  in={tot_in:,}  out={tot_out:,}  "
              f"tiempo={tot_seg:.0f}s")
        buscaron = sum(1 for r in rs if any(
            t in (r["tool_seq_head"] or []) for t in
            ("skill_view", "fact_store", "session_search", "web_search", "read_file")))
        print(f"   buscaron en fuente primaria antes de responder: {buscaron}/{len(rs)}")
    print(f"\ndetalle: {OUT}")


if __name__ == "__main__":
    main()
