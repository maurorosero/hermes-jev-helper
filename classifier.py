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
    3. ``infisical_auth.get_secret`` — el helper de la instalación, para el caso
       verificado arriba: la credencial vive en Infisical y no llega al entorno
       del subproceso. Solo se intenta si el helper existe; su ausencia no es error.
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
        scripts = os.path.expanduser("~/.hermes/scripts")
        if os.path.isdir(scripts) and scripts not in sys.path:
            sys.path.insert(0, scripts)
        from infisical_auth import get_secret as infisical_get_secret  # type: ignore

        value = infisical_get_secret(env_name)
        if value:
            return str(value)
    except Exception:
        pass

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

        started = time.monotonic()
        last_error: Optional[Exception] = None
        for attempt in range(self.retries):
            budget_left = self.budget_s - (time.monotonic() - started)
            if budget_left <= 0:
                logger.debug("jev-helper: presupuesto agotado antes del intento %d", attempt + 1)
                break
            # Nunca esperar más que el presupuesto restante: así el peor caso queda
            # bajo el límite de hook del arnés.
            attempt_timeout = max(1.0, min(self.timeout_s, budget_left))
            try:
                req = urllib.request.Request(self.endpoint, data=payload, headers=headers)
                with urllib.request.urlopen(req, timeout=attempt_timeout) as resp:
                    data = json.load(resp)
                return self._parse(data)
            except urllib.error.HTTPError as exc:
                last_error = exc
                logger.debug("jev-helper: HTTP %s en intento %d", exc.code, attempt + 1)
            except Exception as exc:  # red, timeout, JSON inválido
                last_error = exc
                logger.debug("jev-helper: error %s en intento %d", type(exc).__name__, attempt + 1)

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
