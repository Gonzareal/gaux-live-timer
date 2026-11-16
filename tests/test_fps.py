"""Cuadros por segundo del timer: por defecto como siempre (Auto), y quien quiera los baja."""
import json
import os

import pytest

import live_timer as L
from conftest import drain, make_app, open_daw, step
from test_ventanas import click, open_settings, safe, text_of  # noqa: F401


@pytest.mark.parametrize("fluidez,elegido,esperado", [
    ("equilibrado", "auto", 60), ("ahorro", "auto", 60), ("maximo", "auto", 120),
    ("equilibrado", "60", 60), ("equilibrado", "30", 30), ("equilibrado", "15", 15),
    ("maximo", "30", 30), ("maximo", "15", 15), ("ahorro", "15", 15),
])
def test_fps_segun_lo_elegido(fresh, fluidez, elegido, esperado):
    app = fresh
    app.conf["analizador"]["rendimiento"] = fluidez
    app.conf["fps_timer"] = elegido
    assert app.anim_fps() == esperado


def test_por_defecto_queda_como_estaba(fresh):
    assert L.DEFAULT_CONF["fps_timer"] == "auto"
    assert fresh.conf["fps_timer"] == "auto"
    assert fresh.anim_fps() == 60


@pytest.mark.parametrize("raro", [None, 30, "120", "rapido", [], {"a": 1}, -1])
def test_valor_raro_vuelve_a_auto(raro):
    c = json.loads(json.dumps(L.DEFAULT_CONF))
    c["fps_timer"] = raro
    assert L.sanitize_conf(c)["fps_timer"] == "auto"


@pytest.mark.parametrize("elegido", ["auto", "60", "30", "15"])
def test_cuadros_dibujados_de_verdad(fresh, monkeypatch, elegido):
    """Se siguen las esperas que el propio timer programa entre cuadro y cuadro: en 2 s de
    reloj simulado se dibujan los cuadros elegidos (± 2)."""
    app = fresh
    app.conf["fps_timer"] = elegido
    open_daw(app)
    step(app, 5)
    app.splash_until = 0
    drain(app)
    t = [1000.0]
    monkeypatch.setattr(L.time, "perf_counter", lambda: t[0])
    drawn, pending = [], []
    real = app.render_frame
    monkeypatch.setattr(app, "render_frame", lambda *a, **k: (drawn.append(t[0]), real(*a, **k)))
    monkeypatch.setattr(app.root, "after", lambda ms, fn, *a: pending.append((t[0] + ms / 1000, fn)))
    app._anim_next = t[0]
    app._anim_last = t[0]
    app.anim()
    end = t[0] + 2.0
    while t[0] < end and pending:
        when, fn = pending.pop(0)
        t[0] = max(t[0], when)
        if fn == app.anim:
            fn()
    want = app.anim_fps() * 2
    assert want - 2 <= len(drawn) <= want + 2, (elegido, len(drawn), want)


def test_se_elige_en_ajustes_y_se_guarda(safe):
    app = safe
    s = open_settings(app, "apariencia")
    labels = {}

    def walk(w):
        for c in w.winfo_children():
            if text_of(c) in ("Auto", "60 fps", "30 fps", "15 fps"):
                labels.setdefault(text_of(c), []).append(c)
            walk(c)
    walk(s)
    # "60 fps" también existe en la fila de Fluidez: el de los cuadros del timer es el último
    for txt, val in [("30 fps", "30"), ("15 fps", "15"), ("Auto", "auto")]:
        click(labels[txt][-1])
        assert s.c["fps_timer"] == val
    click(labels["30 fps"][-1])
    s.save()
    with open(L.CONF_FILE) as f:
        assert json.load(f)["fps_timer"] == "30"
    b = make_app()
    try:
        assert b.anim_fps() == 30
    finally:
        b.root.destroy()


@pytest.mark.parametrize("elegido", ["30", "15"])
def test_con_menos_cuadros_todo_se_ve_y_cuenta_igual(fresh, elegido):
    from conftest import visible_bbox_ok
    app = fresh
    app.conf["fps_timer"] = elegido
    open_daw(app)
    step(app, 125)
    assert app.session == pytest.approx(125, abs=1)
    for _ in range(40):
        app.phase += 0.05
        app.render_frame()
    assert visible_bbox_ok(app) == []
