"""Tests del plugin hermes-jev-helper.

Ejecutar sin red y sin credenciales::

    python3 -m pytest tests/ -v

Los tests que requieren el endpoint real se marcan y se saltan si no hay
credencial disponible. El resto verifica el contrato: registro de hooks,
fail-open, forma de la guía, reentrada y configuración.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


# El directorio del plugin tiene guiones (no es un nombre importable), así que el
# paquete se monta en sys.modules bajo un nombre válido para que sus imports
# relativos resuelvan. Mismo patrón que usa el plugin de referencia del arnés
# (hermes-infisical-source) en su test_cli.py.
PACKAGE = "jev_helper_under_test"


def _load_plugin():
    """Carga el paquete por ruta, como lo hace el loader del arnés."""
    spec = importlib.util.spec_from_file_location(
        PACKAGE, ROOT / "__init__.py", submodule_search_locations=[str(ROOT)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[PACKAGE] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def plugin():
    return _load_plugin()


class FakeCtx:
    """Imita la API del PluginContext sin cargar el núcleo."""

    def __init__(self, config=None):
        self.config = dict(config or {})
        self.hooks = {}

    def get_config(self, key, default=None):
        return self.config.get(key, default)

    def register_hook(self, name, callback):
        self.hooks.setdefault(name, []).append(callback)


def _hook(plugin, config=None):
    ctx = FakeCtx(config)
    plugin.register(ctx)
    assert "pre_llm_call" in ctx.hooks, "el plugin debe registrar pre_llm_call"
    return ctx.hooks["pre_llm_call"][0]


# --------------------------------------------------------------------- contrato


def test_registers_expected_hooks(plugin):
    ctx = FakeCtx()
    plugin.register(ctx)
    assert set(ctx.hooks) == {"pre_llm_call", "on_session_start"}


def test_routes_are_complete(plugin):
    from jev_helper_under_test.routing import ESCAPE_ROUTE, ROUTES, declarations, guides

    assert len(ROUTES) == 6
    assert ESCAPE_ROUTE in ROUTES
    decl, gds = declarations("X"), guides()
    assert set(decl) == set(ROUTES), "cada ruta necesita declaración"
    assert set(gds) == set(ROUTES), "cada ruta necesita guía"


def test_escape_route_has_no_orientation(plugin):
    """`others` declara la AUSENCIA de ruta: su guía no debe orientar búsqueda."""
    from jev_helper_under_test.routing import ESCAPE_ROUTE, guides

    text = guides()[ESCAPE_ROUTE]
    assert "Sin ruta definida" in text
    assert "No cargues skills ni busques" in text


def test_user_declaration_names_the_user(plugin):
    from jev_helper_under_test.routing import declarations

    assert "Mauro" in declarations("Mauro")["user"]
    # Sin nombre, la declaración sigue siendo válida (texto genérico).
    assert declarations("")["user"]


# -------------------------------------------------------------------- fail-open


def test_returns_none_without_credential(plugin):
    """Sin credencial: no inyecta y no lanza."""
    pre = _hook(plugin, {"api_key_env": "UNA_VARIABLE_QUE_NO_EXISTE_XYZ"})
    assert pre(session_id="s", turn_id="t1", user_message="hola") is None


def test_configured_env_name_is_honored(plugin):
    """El nombre de la variable de la config debe llegar al clasificador."""
    clf = plugin.Classifier(api_key_env="MI_VARIABLE_PROPIA")
    assert clf.api_key_env == "MI_VARIABLE_PROPIA"
    # Sin default explícito, cae al nombre estándar.
    assert plugin.Classifier().api_key_env == "OPENROUTER_API_KEY"


def test_returns_none_on_empty_message(plugin):
    pre = _hook(plugin)
    assert pre(session_id="s", turn_id="t1", user_message="   ") is None
    assert pre(session_id="s", turn_id="t2", user_message="") is None
    assert pre(session_id="s", turn_id="t3", user_message=None) is None


def test_disabled_does_not_inject(plugin):
    pre = _hook(plugin, {"enabled": False})
    assert pre(session_id="s", turn_id="t1", user_message="pasame el reporte") is None


def test_disabled_does_not_classify(plugin, monkeypatch):
    """Deshabilitado no debe ni intentar la llamada de red."""
    pre = _hook(plugin, {"enabled": False})

    def _boom(*args, **kwargs):
        raise AssertionError("no debe clasificar si está deshabilitado")

    monkeypatch.setattr(plugin.Classifier, "classify", _boom)
    assert pre(session_id="s", turn_id="t1", user_message="hola") is None


def test_classifier_error_is_swallowed(plugin, monkeypatch):
    """Un fallo del clasificador devuelve None, nunca propaga."""

    def _boom(*args, **kwargs):
        raise RuntimeError("fallo simulado")

    monkeypatch.setattr(plugin.Classifier, "classify", _boom)
    pre = _hook(plugin)
    assert pre(session_id="s", turn_id="t1", user_message="hola") is None


def test_response_parse_tolerates_garbage(plugin):
    clf = plugin.Classifier()
    for bad in [None, {}, {"answers": None}, {"answers": {}}, {"answers": {"q": {}}},
                {"answers": {"q": {"choice": ""}}}, "no soy un dict"]:
        assert clf._parse(bad) is None


def test_response_parse_reads_decision(plugin):
    clf = plugin.Classifier()
    dec = clf._parse({"answers": {"q": {"choice": "memory", "confidence": 0.73,
                                        "probabilities": {"memory": 0.78, "others": 0.18}}}})
    assert dec is not None
    assert dec.route == "memory"
    assert dec.confidence == pytest.approx(0.73)
    assert dec.probabilities["others"] == pytest.approx(0.18)


def test_unknown_route_falls_back_to_escape(plugin, monkeypatch):
    """Una ruta fuera del esquema se trata como escape, no se aplica al azar."""
    from jev_helper_under_test.classifier import Decision

    monkeypatch.setattr(plugin.Classifier, "classify",
                        lambda *a, **k: Decision(route="ruta_inventada", confidence=1.0))
    monkeypatch.setattr(plugin, "resolve_api_key", lambda name: "fake-key")
    pre = _hook(plugin)
    result = pre(session_id="s", turn_id="t1", user_message="hola")
    assert result is not None
    # No se aplica la ruta inventada: se aplica la de escape.
    assert "Sin ruta definida" in result["context"]


def test_min_confidence_degrades_to_escape(plugin, monkeypatch):
    """Por debajo del umbral se aplica la ruta de escape (sin orientación)."""
    from jev_helper_under_test.classifier import Decision

    monkeypatch.setattr(plugin.Classifier, "classify",
                        lambda *a, **k: Decision(route="skill", confidence=0.10))
    monkeypatch.setattr(plugin, "resolve_api_key", lambda name: "fake-key")
    pre = _hook(plugin, {"min_confidence": 0.5})
    result = pre(session_id="s", turn_id="t1", user_message="hola")
    assert result is not None
    # La guía inyectada es la de escape, no la de skill.
    assert "Sin ruta definida" in result["context"]


def test_inject_false_classifies_without_injecting(plugin, monkeypatch):
    from jev_helper_under_test.classifier import Decision

    calls = []

    def fake_classify(self, *args, **kwargs):
        calls.append(args)
        return Decision(route="skill", confidence=0.9)

    monkeypatch.setattr(plugin.Classifier, "classify", fake_classify)
    monkeypatch.setattr(plugin, "resolve_api_key", lambda name: "fake-key")
    pre = _hook(plugin, {"inject": False})
    assert pre(session_id="s", turn_id="t1", user_message="pasame el reporte") is None
    assert calls, "debe clasificar aunque no inyecte"


# ------------------------------------------------------------------- reentrada


def test_same_turn_is_not_reclassified(plugin, monkeypatch):
    from jev_helper_under_test.classifier import Decision

    calls = []

    def fake_classify(self, *args, **kwargs):
        calls.append(1)
        return Decision(route="skill", confidence=0.9)

    monkeypatch.setattr(plugin.Classifier, "classify", fake_classify)
    monkeypatch.setattr(plugin, "resolve_api_key", lambda name: "fake-key")
    pre = _hook(plugin)
    first = pre(session_id="s", turn_id="t-mismo", user_message="pasame el reporte")
    second = pre(session_id="s", turn_id="t-mismo", user_message="pasame el reporte")
    assert len(calls) == 1, "el mismo turno no se clasifica dos veces"
    assert first == second


def test_session_start_clears_state(plugin):
    from jev_helper_under_test.classifier import Decision

    ctx = FakeCtx()
    plugin.register(ctx)
    ctx.hooks["pre_llm_call"][0].__self__._turns["x"] = "skill"
    ctx.hooks["on_session_start"][0](session_id="s")
    assert ctx.hooks["pre_llm_call"][0].__self__._turns == {}


# --------------------------------------------------------------- configuracion


def test_defaults_are_sane(plugin):
    clf = plugin.Classifier()
    assert clf.endpoint.startswith("https://")
    assert clf.timeout_s > 0
    assert clf.retries >= 1
    assert clf.min_confidence == 0.0


def test_worst_case_stays_under_the_harness_hook_limit(plugin):
    """El peor caso debe quedar bajo `plugins.hook_callback_timeout` (30s).

    Si un callback lo excede, el arnés lo abandona y la guía se pierde en
    silencio: el fallo deja de ser observable. Este test fija el presupuesto.
    """
    from jev_helper_under_test.classifier import DEFAULT_BUDGET_S

    clf = plugin.Classifier()
    worst_case = clf.timeout_s * clf.retries
    assert worst_case < 30.0, f"peor caso {worst_case}s excede el límite de hook del arnés"
    assert clf.budget_s <= DEFAULT_BUDGET_S


def test_budget_stops_retrying(plugin, monkeypatch):
    """Agotado el presupuesto no se reintenta: se devuelve None de inmediato."""
    import urllib.request

    calls = []

    def _slow(*args, **kwargs):
        calls.append(1)
        raise OSError("endpoint inalcanzable")

    monkeypatch.setattr(urllib.request, "urlopen", _slow)
    clf = plugin.Classifier(timeout_s=5.0, retries=5)
    clf.budget_s = 0.0  # sin presupuesto: no debe intentar ni una vez
    assert clf.classify("hola", {"skill": "x"}, api_key="fake") is None
    assert not calls, "no debe intentar si no hay presupuesto"


def test_text_is_truncated_before_classifying(plugin, monkeypatch):
    captured = {}

    def fake_classify(self, text, criteria, *, api_key=None):
        captured["len"] = len(text)
        return None

    monkeypatch.setattr(plugin.Classifier, "classify", fake_classify)
    monkeypatch.setattr(plugin, "resolve_api_key", lambda name: "fake-key")
    pre = _hook(plugin)
    pre(session_id="s", turn_id="t1", user_message="x" * 5000)
    assert captured.get("len") == plugin.MAX_TEXT_CHARS


def test_overrides_replace_criteria(plugin, tmp_path):
    import json

    path = tmp_path / "ov.json"
    path.write_text(json.dumps({"declarations": {"skill": "CRITERIO PROPIO"}}))
    ctx = FakeCtx({"overrides_path": str(path)})
    plugin.register(ctx)
    helper = ctx.hooks["pre_llm_call"][0].__self__
    decl, _, _ = helper._criteria_and_guides()
    assert decl["skill"] == "CRITERIO PROPIO"
    # Las demás claves siguen siendo las internas.
    assert decl["research"]


def test_broken_overrides_file_is_ignored(plugin, tmp_path):
    path = tmp_path / "roto.json"
    path.write_text("{esto no es json valido")
    ctx = FakeCtx({"overrides_path": str(path)})
    plugin.register(ctx)
    helper = ctx.hooks["pre_llm_call"][0].__self__
    decl, gds, _ = helper._criteria_and_guides()
    assert decl["skill"] and gds["skill"]


def test_user_name_read_from_profile(plugin):
    """El nombre sale del perfil real; si no hay perfil, cadena vacía."""
    ctx = FakeCtx()
    plugin.register(ctx)
    helper = ctx.hooks["pre_llm_call"][0].__self__
    name = helper._user_name()
    assert isinstance(name, str)
    assert "\n" not in name


# ------------------------------------------------------------------ integracion


def test_live_classification_end_to_end(plugin):
    """Clasificación real contra el endpoint, con la credencial de la instalación.

    Se omite (no falla) si no hay credencial disponible: el resto de la suite
    verifica el contrato sin red, así que un entorno sin secretos sigue siendo
    un entorno de test válido.
    """
    from jev_helper_under_test.classifier import resolve_api_key
    from jev_helper_under_test.routing import declarations

    if not resolve_api_key("OPENROUTER_API_KEY"):
        pytest.skip("sin credencial disponible: se omite la prueba de red")

    clf = plugin.Classifier()
    cases = [
        ("pasame el reporte del mes", "skill"),
        ("investiga actos de habla indirectos", "research"),
        ("que te dije ayer sobre el hotel", "history"),
        ("cuanto cobramos por hora", "memory"),
        ("Mauro prefiere respuestas concisas", "user"),
    ]
    hits = 0
    for text, expected in cases:
        dec = clf.classify(text, declarations("Mauro"))
        assert dec is not None, f"el clasificador devolvió None para {text!r}"
        assert dec.route in {"skill", "research", "memory", "history", "user", "others"}
        if dec.route == expected:
            hits += 1
    # Se observó 5/5 en el estudio; se exige mayoría para no acoplar el test al modelo.
    assert hits >= 3, f"solo {hits}/5 rutas coincidieron con la expectativa"
