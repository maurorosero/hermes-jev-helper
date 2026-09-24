"""hermes-jev-helper — ayuda de ruta para el arnés, basada en un clasificador tipado.

QUÉ HACE
--------
Antes de cada llamada al modelo, clasifica la intención del turno con un modelo de
decisión que recibe un esquema cerrado de seis rutas (``skill``, ``research``,
``memory``, ``history``, ``user``, ``others``) y anexa al turno una guía en
lenguaje natural que nombra dónde buscar.

QUÉ NO HACE
-----------
No ejecuta la tarea, no redacta la respuesta, no elige herramientas y no modifica
el resultado del modelo. Solo orienta el PUNTO DE PARTIDA del turno.

POR QUÉ UN PLUGIN EN PROCESO
----------------------------
La decisión de ruta se toma en ``pre_llm_call`` y necesita vivir en el proceso para
poder compartirse con otros puntos del turno. Un gancho de shell no puede sostener
ese estado (cada invocación es un subproceso sin memoria), y un skill es texto que
el agente puede seguir u omitir, lo que reintroduce la improvisación que el
mecanismo busca reducir. Ver docs/paper-es.md §4.1.

Alcance de esta versión: registra ``pre_llm_call`` (decide e inyecta) y
``on_session_start`` (limpia el estado por turno). No registra ``pre_tool_call``:
la verificación de que el turno usó la fuente indicada es trabajo futuro (§8 del
estudio de caso), y declarar un hook que no se registra sería inconsistente.

FAIL-OPEN
---------
Ningún fallo del clasificador puede romper un turno. Sin credencial, sin red, con
timeout o con respuesta inesperada, el plugin no inyecta nada y la conversación
sigue igual que si no estuviera instalado. Todo el estado por turno vive en memoria
del proceso y se descarta al terminar.

CONFIGURACIÓN
-------------
Las claves se leen de ``plugins.entries.hermes-jev-helper.settings`` (ver
``config_schema`` en plugin.yaml). Ver README.md para el detalle.

Referencia del mecanismo y de las mediciones: docs/paper-es.md
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, Optional

from .classifier import Classifier, Decision, resolve_api_key
from .routing import ESCAPE_ROUTE, ROUTES, declarations, guides, load_overrides
from .telemetry import Telemetry, compact_probs, text_fingerprint

logger = logging.getLogger(__name__)

# Símbolos que la suite de tests monta desde el paquete (mismo patrón que el
# plugin de referencia del arnés).
__all__ = [
    "RouteHelper", "Classifier", "Decision", "Telemetry",
    "compact_probs", "text_fingerprint", "resolve_api_key", "register",
    "ROUTES", "ESCAPE_ROUTE", "MAX_TEXT_CHARS",
]

# Máximo de caracteres del mensaje del usuario que se envían al clasificador.
# Un turno puede traer texto enorme (una pega larga); clasificar la intención no
# requiere el cuerpo completo y recortar protege el costo y la latencia.
MAX_TEXT_CHARS = 2000

# Guardia de reentrada: el hook corre una vez por turno, pero un doble dispatch
# (reintento del arnés, turno reanudado) no debe clasificar dos veces el mismo texto.
_MAX_TRACKED_TURNS = 64


class RouteHelper:
    """Estado y lógica del plugin, una instancia por carga."""

    def __init__(self, ctx: Any) -> None:
        self._ctx = ctx
        self._turns: Dict[str, str] = {}      # turn_id -> ruta inyectada
        self._last_route: Optional[str] = None
        self._telemetry: Optional[Telemetry] = None

    # ------------------------------------------------------------------ config
    def _get(self, key: str, default: Any = None) -> Any:
        try:
            value = self._ctx.get_config(key, None)
        except Exception as exc:
            logger.debug("jev-helper: no se pudo leer la config %r: %s", key, exc)
            return default
        return default if value is None else value

    @property
    def enabled(self) -> bool:
        return bool(self._get("enabled", True))

    @property
    def inject(self) -> bool:
        return bool(self._get("inject", True))

    @property
    def read_user_md(self) -> bool:
        return bool(self._get("read_user_md", True))

    def _api_key_env(self) -> str:
        """Nombre de la variable de entorno que contiene la credencial."""
        return str(self._get("api_key_env", "OPENROUTER_API_KEY") or "OPENROUTER_API_KEY")

    def _classifier(self) -> Classifier:
        return Classifier(
            endpoint=str(self._get("endpoint", "") or ""),
            model=str(self._get("model", "") or ""),
            timeout_s=float(self._get("timeout_s", 8.0) or 8.0),
            retries=int(self._get("retries", 2) or 2),
            min_confidence=float(self._get("min_confidence", 0.0) or 0.0),
            api_key_env=self._api_key_env(),
        )

    def _telem(self) -> Telemetry:
        """Telemetría local, construida una sola vez por carga del plugin.

        Escribe a un ARCHIVO, nunca al mensaje del modelo: lo que se anexa al turno
        se paga como tokens de entrada en cada llamada, y la telemetría no debe
        costar payload.
        """
        telem = self._telemetry
        if telem is None:
            telem = self._telemetry = Telemetry(
                str(self._get("telemetry_path", "") or "") or None,
                enabled=bool(self._get("telemetry", True)),
            )
        return telem

    def _record_telemetry(self, clf: Classifier, text: str, route: str,
                          decision: Optional[Decision], **extra: Any) -> None:
        """Escribe una línea de telemetría. Fail-open: nunca rompe el turno."""
        try:
            fields: Dict[str, Any] = {
                "route": route,
                "fp": text_fingerprint(text),
            }
            if decision is not None:
                fields["conf"] = round(decision.confidence, 2)
                fields["probs"] = compact_probs(decision.probabilities)
                fields["raw"] = decision.route
            fields["lat_ms"] = round(clf.last_latency_ms, 1)
            fields["attempts"] = clf.last_attempts
            if clf.last_error:
                fields["err"] = clf.last_error
            fields.update(extra)
            self._telem().record(**fields)
        except Exception:
            pass

    def _criteria_and_guides(self) -> tuple[Dict[str, str], Dict[str, str], str]:
        """Devuelve (declaraciones, guías, nombre de usuario).

        Un archivo de overrides, si existe y es válido, reemplaza por clave. Si no,
        se usan los valores internos del módulo ``routing``.
        """
        name = self._user_name() if self.read_user_md else ""
        decl = declarations(name)
        gds = guides()

        override_path = str(self._get("overrides_path", "") or "")
        if override_path:
            data = load_overrides(override_path)
            if data:
                if isinstance(data.get("user_name"), str) and data["user_name"]:
                    # El nombre del override tiene precedencia y recalcula la declaración.
                    name = str(data["user_name"])
                    decl = declarations(name)
                decl.update(data.get("declarations") or {})  # type: ignore[arg-type]
                gds.update(data.get("guides") or {})         # type: ignore[arg-type]
        return decl, gds, name

    def _user_name(self) -> str:
        """Nombre del usuario leído del perfil real, no de una lista codificada.

        Estrategia: sobre las entradas del perfil, contar los nombres propios que
        aparecen en dos o más entradas y elegir el más frecuente. Si algo falla,
        devuelve cadena vacía y la declaración usa el texto genérico.
        """
        try:
            from tools.memory_tool import get_memory_dir  # type: ignore

            path = get_memory_dir() / "USER.md"
        except Exception:
            path = os.path.expanduser("~/.hermes/memories/USER.md")
        try:
            with open(path, "r", encoding="utf-8") as fh:
                text = fh.read()
        except Exception:
            return ""
        if not text.strip():
            return ""

        # Formato del perfil: entradas separadas por un delimitador en línea propia.
        entries = [e.strip() for e in re.split(r"\n\s*§\s*\n", text) if e.strip()]
        if not entries:
            entries = [text]
        counts: Dict[str, int] = {}
        for entry in entries:
            head = re.match(r"^([A-ZÁÉÍÓÚÑ][\wáéíóúñ]+)(?=\s*[:,]|\s)", entry)
            if head:
                token = head.group(1)
                counts[token] = counts.get(token, 0) + 1
        candidates = set(re.findall(r"\b([A-ZÁÉÍÓÚÑ][\wáéíóúñ]{2,})\b", text))
        for token in candidates:
            hits = sum(1 for e in entries if re.search(rf"\b{re.escape(token)}\b", e))
            if hits >= 2:
                counts[token] = max(counts.get(token, 0), hits)
        if not counts:
            return ""
        return max(counts, key=lambda k: counts[k])

    # ------------------------------------------------------------------- hooks
    def on_pre_llm_call(self, **kwargs: Any) -> Optional[Dict[str, str]]:
        """Clasifica el turno y devuelve ``{"context": guía}``, o ``None``.

        El arnés anexa este contexto al MENSAJE DEL USUARIO (no al system prompt),
        por lo que no invalida la caché del prompt.
        """
        if not self.enabled:
            return None

        text = kwargs.get("user_message")
        if not isinstance(text, str) or not text.strip():
            return None

        turn_id = str(kwargs.get("turn_id") or "")
        # Reentrada: si este turno ya se clasificó, se reusa la ruta ya decidida.
        if turn_id and turn_id in self._turns:
            route = self._turns[turn_id]
            _, gds, _ = self._criteria_and_guides()
            guide = gds.get(route)
            # Se registra con src="reentry" para poder separar los reintentos del
            # arnés de las clasificaciones reales al analizar.
            self._record_telemetry(self._classifier(), text, route, None, src="reentry")
            return {"context": guide} if (guide and self.inject) else None

        decl, gds, _ = self._criteria_and_guides()
        clf = self._classifier()
        # El contrato es fail-open, así que la resolución de credencial y la
        # clasificación se envuelven aquí: el arnés también aísla los fallos de
        # hook, pero el plugin no debe depender de eso para cumplirlo.
        try:
            key = resolve_api_key(self._api_key_env())
            decision: Optional[Decision] = clf.classify(
                text[:MAX_TEXT_CHARS], decl, api_key=key
            )
        except Exception as exc:
            logger.debug("jev-helper: clasificación fallida (fail-open): %s", exc)
            self._record_telemetry(clf, text, ESCAPE_ROUTE, None,
                                   src="fresh", exc=type(exc).__name__)
            return None
        if decision is None:
            # Se registra el motivo real del fallo (no_key, budget, http_429, ...):
            # sin esto, un clasificador que falla siempre es indistinguible de uno
            # que nunca se llama.
            self._record_telemetry(clf, text, ESCAPE_ROUTE, None, src="fresh")
            return None

        route = decision.route if decision.route in ROUTES else ESCAPE_ROUTE
        if clf.below_threshold(decision):
            logger.debug(
                "jev-helper: confianza %.2f por debajo del umbral; se trata como %s",
                decision.confidence, ESCAPE_ROUTE,
            )
            route = ESCAPE_ROUTE

        # El registro va aquí, antes de decidir si se inyecta: así el modo
        # observación (inject=false) también queda medido.
        self._record_telemetry(
            clf, text, route, decision, src="fresh",
            off=("threshold" if clf.below_threshold(decision) else None),
            inj=bool(self.inject),
        )

        if turn_id:
            if len(self._turns) >= _MAX_TRACKED_TURNS:
                self._turns.clear()
            self._turns[turn_id] = route
        self._last_route = route
        logger.debug(
            "jev-helper: turno -> %s (conf %.2f, prob %s)",
            route, decision.confidence, decision.probabilities or {},
        )

        if not self.inject:
            return None
        guide = gds.get(route)
        return {"context": guide} if guide else None

    def on_session_start(self, **kwargs: Any) -> None:
        """Limpia el estado por turno al abrir sesión."""
        self._turns.clear()
        self._last_route = None
        # Cada línea ya se escribió con flush; aquí solo se libera el descriptor.
        if self._telemetry is not None:
            self._telemetry.close()
            self._telemetry = None


def register(ctx: Any) -> None:
    """Punto de entrada del plugin."""
    helper = RouteHelper(ctx)
    ctx.register_hook("pre_llm_call", helper.on_pre_llm_call)
    ctx.register_hook("on_session_start", helper.on_session_start)
    logger.debug("hermes-jev-helper registrado (pre_llm_call)")
