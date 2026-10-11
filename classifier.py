"""Cliente del clasificador tipado de intención.

Habla con un modelo de decisión que recibe un esquema cerrado de opciones
(``type: choice``) y devuelve la opción elegida, su confianza y la distribución
sobre todas las opciones.

Contrato de fallo: **fail-open**. Ante cualquier error —credencial ausente, red,
timeout, respuesta inesperada— devuelve ``None`` y el turno sigue sin guía. Un
clasificador que no responde no puede romper la conversación.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_ENDPOINT = "https://openrouter.ai/api/alpha/decisions"
DEFAULT_MODEL = "~typesafe/jev-latest"

# El arnés abandona un callback que excede ``plugins.hook_callback_timeout``
# (default 30 s) y el turno sigue sin guía, en silencio. Este presupuesto deja
# margen bajo ese límite: el clasificador deja de reintentar antes de arriesgarse
# a ser abandonado, y así el fallo es explícito (devuelve None) en vez de invisible.
DEFAULT_BUDGET_S = 20.0


@dataclass
class Decision:
    """Resultado de una clasificación."""

    route: str
    confidence: float = 0.0
    probabilities: Dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# DONDE VIVE EL HELPER DE INFISICAL
#
# El helper NO es de este plugin: su dueno es el skill ``hermes-infisical-secrets``.
# Su ruta no se escribe fija aca — se COMPONE, porque ese skill puede estar en un
# directorio externo (``skills.external_dirs`` de ``$HERMES_HOME/config.yaml``, que
# es de donde los carga Hermes) o, si no, en el directorio de skills del home
# activo (``$HERMES_HOME/skills``).
#
# Antes apuntaba a ``~/.hermes/scripts/``, que es la carpeta de scripts sueltos:
# el helper no vive ahi, viven sus consumidores. La copia que habia en esa ruta
# no la mantenia nadie.
#
# Solo stdlib, sin PyYAML: esta maquina no lo trae y de ese helper existen
# bytecode para 3.11/3.12/3.14, o sea que lo importan interpretes distintos.
# ---------------------------------------------------------------------------
SKILL_DUENO = "harness/hermes-infisical-secrets"
HELPER_ARCHIVO = "scripts/infisical_auth.py"


def _hermes_home() -> Path:
    """``HERMES_HOME`` si esta definido; si no, el home del perfil por defecto."""
    return Path(os.environ.get("HERMES_HOME") or (Path.home() / ".hermes"))


def _expandir(entrada: str) -> Path:
    """``~``, ``${VAR}`` y rutas relativas a ``HERMES_HOME`` (la regla del core)."""
    ruta = Path(os.path.expanduser(os.path.expandvars(entrada)))
    return ruta if ruta.is_absolute() else _hermes_home() / ruta


def _external_dirs(cfg_path: Path) -> list:
    """``skills.external_dirs`` de config.yaml, leido por indentacion."""
    try:
        lineas = cfg_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    salida: list = []
    en_skills = False
    en_lista = False
    for cruda in lineas:
        texto = cruda.strip()
        if not texto or texto.startswith("#"):
            continue
        sangria = len(cruda) - len(cruda.lstrip())
        if sangria == 0:
            en_skills, en_lista = texto == "skills:", False
            continue
        if not en_skills:
            continue
        if sangria == 2:
            en_lista = texto == "external_dirs:"
            continue
        if en_lista and texto.startswith("- "):
            salida.append(texto[2:].strip().strip("\"'"))
    return salida


def bases_de_skills() -> list:
    """Directorios donde buscar un skill: los externos primero, el home activo al final."""
    bases = [_expandir(e) for e in _external_dirs(_hermes_home() / "config.yaml")]
    bases.append(_hermes_home() / "skills")
    vistas: set = set()
    salida: list = []
    for base in bases:
        if base.is_dir() and str(base) not in vistas:
            vistas.add(str(base))
            salida.append(base)
    return salida


def resolver_helper_infisical() -> Path:
    """Compone la ruta del helper de Infisical dentro del arbol de skills.

    Falla si no lo encuentra: el llamador decide (este modulo es fail-open), pero
    el mensaje dice DONDE se busco en vez de dejar el fallo mudo.
    """
    relativo = f"{SKILL_DUENO}/{HELPER_ARCHIVO}"
    candidatos = [base / relativo for base in bases_de_skills()]
    for ruta in candidatos:
        if ruta.is_file():
            return ruta
    buscado = "\n".join(f"    - {c}" for c in candidatos) or "    (ninguna base de skills existe)"
    raise RuntimeError(
        f"no encontre el helper de Infisical ({relativo}).\n"
        f"  busque en:\n{buscado}\n"
        f"  lo mantiene el skill hermes-infisical-secrets; si vive en otro lado,\n"
        f"  declara su directorio en skills.external_dirs de "
        f"{_hermes_home() / 'config.yaml'}"
    )


def resolve_api_key(env_name: str) -> Optional[str]:
    """Resuelve la credencial por las vías del arnés, en orden de preferencia.

    El orden importa y responde a un hallazgo verificado en producción: la
    credencial puede NO estar en el entorno del proceso del gateway cuando el
    arnés la inyecta por un *secret source* (Infisical) en lugar de por ``.env``.
    Verificado: leer ``/proc/<pid_gateway>/environ`` no muestra la variable aunque
    el arnés la tenga disponible en su scope.

    Estrategia en cascada, fail-open (devuelve ``None`` si nada funciona):

    1. ``agent.secret_scope.get_secret`` — el resolutor nativo, respeta el scope
       de perfil y el multiplexado. Es la vía correcta y la más barata cuando la
       variable está en el scope.
    2. ``os.environ`` — despliegues que inyectan por entorno (systemd, dotenv).
    3. ``infisical_auth.get_secret`` — el helper de Infisical, para el caso
       verificado arriba: la credencial vive en Infisical y no llega al entorno
       del subproceso. Su ruta se COMPONE (ver el bloque de mas abajo), no se
       escribe fija. Su ausencia no es error, pero queda en el log con el detalle
       de donde se busco.
    """
    if not env_name:
        return None

    try:
        from agent.secret_scope import get_secret  # type: ignore

        value = get_secret(env_name)
        if value:
            return str(value)
    except Exception:
        pass

    try:
        value = os.environ.get(env_name)
        if value:
            return str(value)
    except Exception:
        pass

    try:
        carpeta = str(resolver_helper_infisical().parent)
        if carpeta not in sys.path:
            sys.path.insert(0, carpeta)
        from infisical_auth import get_secret as infisical_get_secret  # type: ignore

        value = infisical_get_secret(env_name)
        if value:
            return str(value)
    except Exception as exc:
        logger.debug("helper de Infisical no disponible: %s", exc)

    return None


class Classifier:
    """Cliente mínimo del endpoint de decisiones."""

    def __init__(
        self,
        *,
        endpoint: str = DEFAULT_ENDPOINT,
        model: str = DEFAULT_MODEL,
        timeout_s: float = 8.0,
        retries: int = 2,
        min_confidence: float = 0.0,
        api_key_env: str = "OPENROUTER_API_KEY",
    ) -> None:
        self.endpoint = endpoint or DEFAULT_ENDPOINT
        self.model = model or DEFAULT_MODEL
        self.api_key_env = api_key_env or "OPENROUTER_API_KEY"
        self.timeout_s = float(timeout_s) if timeout_s else 8.0
        self.retries = max(1, int(retries)) if retries else 1
        self.min_confidence = float(min_confidence or 0.0)
        self.budget_s = DEFAULT_BUDGET_S
        # Último resultado observado. Se llenan en el camino que YA se recorre (el
        # reloj ya estaba tomado para el presupuesto), así que exponerlos para la
        # telemetría no agrega trabajo: es asignar un atributo.
        self.last_error: Optional[str] = None
        self.last_attempts: int = 0
        self.last_latency_ms: float = 0.0

    def classify(
        self,
        text: str,
        criteria: Dict[str, str],
        *,
        api_key: Optional[str] = None,
    ) -> Optional[Decision]:
        """Clasifica ``text`` contra ``criteria``; ``None`` si no se pudo."""
        if not text or not text.strip():
            return None
        key = api_key or resolve_api_key(self.api_key_env)
        if not key:
            self.last_error = "no_key"
            logger.debug("jev-helper: sin credencial disponible; se omite la clasificación")
            return None

        body = {
            "model": self.model,
            "state": {"consulta": text},
            "questions": {
                "q": {
                    "type": "choice",
                    "instructions": "Que es este texto?",
                    "criteria": criteria,
                }
            },
        }
        payload = json.dumps(body).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }

        self.last_error = None
        started = time.monotonic()
        last_error: Optional[Exception] = None
        for attempt in range(self.retries):
            budget_left = self.budget_s - (time.monotonic() - started)
            if budget_left <= 0:
                self.last_error = "budget"
                logger.debug("jev-helper: presupuesto agotado antes del intento %d", attempt + 1)
                break
            # Nunca esperar más que el presupuesto restante: así el peor caso queda
            # bajo el límite de hook del arnés.
            attempt_timeout = max(1.0, min(self.timeout_s, budget_left))
            self.last_attempts = attempt + 1
            try:
                req = urllib.request.Request(self.endpoint, data=payload, headers=headers)
                with urllib.request.urlopen(req, timeout=attempt_timeout) as resp:
                    data = json.load(resp)
                decision = self._parse(data)
                self.last_latency_ms = (time.monotonic() - started) * 1000.0
                if decision is None:
                    self.last_error = "parse"
                return decision
            except urllib.error.HTTPError as exc:
                last_error = exc
                self.last_error = f"http_{exc.code}"
                logger.debug("jev-helper: HTTP %s en intento %d", exc.code, attempt + 1)
            except Exception as exc:  # red, timeout, JSON inválido
                last_error = exc
                self.last_error = type(exc).__name__
                logger.debug("jev-helper: error %s en intento %d", type(exc).__name__, attempt + 1)

        self.last_latency_ms = (time.monotonic() - started) * 1000.0
        if last_error is not None:
            logger.debug("jev-helper: clasificación abandonada: %s", last_error)
        return None

    def _parse(self, data: object) -> Optional[Decision]:
        """Extrae la decisión de la respuesta. Tolerante a formas inesperadas."""
        try:
            if not isinstance(data, dict):
                return None
            answers = data.get("answers")
            if not isinstance(answers, dict):
                return None
            q = answers.get("q")
            if not isinstance(q, dict):
                return None
            route = q.get("choice")
            if not isinstance(route, str) or not route.strip():
                return None
            route = route.strip()
            try:
                confidence = float(q.get("confidence") or 0.0)
            except Exception:
                confidence = 0.0
            raw = q.get("probabilities")
            probs: Dict[str, float] = {}
            if isinstance(raw, dict):
                for key, value in raw.items():
                    try:
                        probs[str(key)] = float(value)
                    except Exception:
                        continue
            return Decision(route=route, confidence=confidence, probabilities=probs)
        except Exception:
            return None

    def below_threshold(self, decision: Decision) -> bool:
        """True si la decisión no alcanza la confianza mínima configurada."""
        if self.min_confidence <= 0.0:
            return False
        return decision.confidence < self.min_confidence
