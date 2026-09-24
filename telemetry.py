"""Telemetría local del clasificador de ruta.

POR QUÉ EXISTE
--------------
La decisión del clasificador (ruta, confianza, latencia, motivo de fallo) existe en
memoria durante el turno y se descartaba al terminar. Sin ella no se puede evaluar si
el clasificador mejora o se degrada: solo quedaba la etiqueta de ruta anexada al
mensaje del usuario.

POR QUÉ UN ARCHIVO Y NO EL MENSAJE AL MODELO
--------------------------------------------
Todo lo que se anexa al turno viaja al proveedor en cada llamada al modelo y se paga
como tokens de entrada. La telemetría NO debe pagarse: se escribe a un archivo local
(JSONL, una línea por clasificación) que ninguna llamada al modelo lee. Esta es la
razón por la que la telemetría no toca la guía inyectada ni su longitud.

COSTO
-----
Un turno que ya gasta ~0,5 s de red clasificando paga aquí una escritura de una línea
(decenas de microsegundos). El registro es O(1), sin locks y sin acumular en memoria:
se serializa y se escribe en el momento. `record()` nunca propaga una excepción; un
fallo de disco incrementa `dropped` y el turno sigue igual.
"""

from __future__ import annotations

import json
import os
import time
import zlib
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_MAX_BYTES = 4 * 1024 * 1024

# El tamaño del archivo se comprueba cada N escrituras, no en cada una: un `stat()`
# por clasificación sería más caro que la propia escritura.
_ROTATE_CHECK_EVERY = 64


def default_path() -> Path:
    """Ruta del archivo de telemetría, derivada del home del perfil.

    No se codifica ``~/.hermes``: el home es configurable por perfil y codificarlo
    escribe la telemetría del perfil equivocado en instalaciones multiplexadas.
    """
    try:
        from hermes_constants import get_hermes_home  # type: ignore

        base = Path(get_hermes_home())
    except Exception:
        base = Path(os.path.expanduser("~/.hermes"))
    return base / "logs" / "jev-helper.jsonl"


def text_fingerprint(text: str) -> str:
    """Huella corta del texto clasificado (CRC32 en hexadecimal, 8 caracteres).

    Permite agrupar el MISMO texto entre corridas para medir la estabilidad de la
    decisión, sin guardar el texto del usuario en disco. Se prefiere ``zlib.crc32``
    sobre ``hashlib`` porque está en C y es más barato en el camino del turno.
    """
    return format(zlib.crc32(text.encode("utf-8", "replace")) & 0xFFFFFFFF, "08x")


class Telemetry:
    """Escritor de telemetría en JSONL. Fail-open por contrato."""

    def __init__(
        self,
        path: Optional[Any] = None,
        *,
        enabled: bool = True,
        max_bytes: int = DEFAULT_MAX_BYTES,
    ) -> None:
        self.enabled = bool(enabled)
        self._path = Path(path) if path else default_path()
        self._max_bytes = int(max_bytes) if max_bytes else DEFAULT_MAX_BYTES
        self._fh = None
        self._writes = 0
        self.dropped = 0

    @property
    def path(self) -> Path:
        return self._path

    @property
    def writes(self) -> int:
        """Líneas escritas con éxito en esta carga del plugin."""
        return self._writes

    def _handle(self):
        fh = self._fh
        if fh is None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            fh = self._fh = open(self._path, "a", encoding="utf-8")
        return fh

    def record(self, **fields: Any) -> None:
        """Anexa una línea con ``fields``. Nunca levanta excepción."""
        if not self.enabled:
            return
        try:
            fields["ts"] = round(time.time(), 3)
            # Sin `indent` ni `default=`: los campos se sanean en el llamador, y un
            # `default` haría un try/except interno por objeto serializado.
            line = json.dumps(fields, separators=(",", ":"), ensure_ascii=False)
            fh = self._handle()
            fh.write(line + "\n")
            # flush explícito: la telemetría debe sobrevivir a una muerte abrupta del
            # gateway, que es justo cuando más interesa.
            fh.flush()
            self._writes += 1
            if not (self._writes % _ROTATE_CHECK_EVERY):
                self._maybe_rotate()
        except Exception:
            self.dropped += 1
            try:
                if self._fh is not None:
                    self._fh.close()
            except Exception:
                pass
            self._fh = None

    def _maybe_rotate(self) -> None:
        """Rota el archivo cuando supera ``max_bytes``, conservando una generación."""
        try:
            if self._path.stat().st_size <= self._max_bytes:
                return
        except Exception:
            return
        try:
            if self._fh is not None:
                self._fh.close()
                self._fh = None
            os.replace(self._path, self._path.with_name(self._path.name + ".1"))
        except Exception:
            pass

    def close(self) -> None:
        try:
            if self._fh is not None:
                self._fh.close()
        except Exception:
            pass
        self._fh = None


def compact_probs(probs: Optional[Dict[str, float]]) -> Dict[str, float]:
    """Redondea la distribución a 2 decimales.

    Achica la línea sin perder nada utilizable: la decisión ya se toma con la opción
    de mayor probabilidad y dos decimales alcanzan para leer el margen entre rutas.
    """
    if not probs:
        return {}
    out: Dict[str, float] = {}
    for key, value in probs.items():
        try:
            rounded = round(float(value), 2)
        except Exception:
            continue
        if rounded:  # las rutas con 0.0 no aportan y son la mayoría
            out[str(key)] = rounded
    return out
