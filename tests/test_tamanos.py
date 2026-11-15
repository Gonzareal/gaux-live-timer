"""Tamaños a fondo: cada punto intermedio de la escala, sesiones larguísimas, textos largos y
todas las combinaciones de metas, sin que nada se salga ni se pise."""
import itertools

import pytest

import live_timer as L
from conftest import OS, drain, open_daw, step, visible_bbox_ok
from test_widget import setup
from test_widget import text_overlaps as _overlaps


def text_overlaps(app):
    """Como en test_widget, sin contar las copias del glitch del título (son a propósito)."""
    ghosts = {g[0] if isinstance(g, (tuple, list)) else g for g in getattr(app, "ghosts", [])}
    texts = {app.cv.itemcget(g, "text") for g in ghosts if app.cv.type(g) == "text"}
    return [o for o in _overlaps(app) if not (o[0] == o[1] and o[0] in texts)]

VISTAS = ["completa", "compacta", "mini"]
ORIENT = ["horizontal", "vertical"]


def _scales(vista):
    lo, hi = L.ESCALA_LIM["mini" if vista == "mini" else "otra"]
    n = int(round((hi - lo) / 0.1))
    return [round(lo + i * (hi - lo) / n, 3) for i in range(n + 1)]


CASOS = [(v, o, k) for v in VISTAS for o in ORIENT for k in _scales(v)]


@pytest.mark.parametrize("vista,orient,k", CASOS,
                         ids=[f"{v}-{o}-{k}" for v, o, k in CASOS])
def test_cada_punto_de_la_escala(fresh, vista, orient, k):
    app = fresh
    setup(app, "gaux", vista, orient, k)
    open_daw(app)
    step(app, 3725)                       # 1:02:05 en el reloj
    app.render_frame(force=True)
    assert visible_bbox_ok(app) == []
    assert text_overlaps(app) == []
    assert app.root.geometry().startswith(f"{app.W}x{app.H}")
    # el reloj nunca baja de 8 pt
    import tkinter.font as tkf
    for d in app.digits:
        f = tkf.Font(root=app.root, font=app.cv.itemcget(d["main"], "font"))
        assert abs(f.actual("size")) >= L.MIN_FONT


@pytest.mark.parametrize("vista", VISTAS)
@pytest.mark.parametrize("orient", ORIENT)
def test_mas_escala_nunca_achica(fresh, vista, orient):
    app = fresh
    prev = None
    for k in _scales(vista):
        setup(app, "noche", vista, orient, k)
        if prev:
            assert app.W >= prev[0] and app.H >= prev[1], (k, prev, (app.W, app.H))
        prev = (app.W, app.H)


SESIONES = [0, 59, 60, 3599, 3600, 9 * 3600 + 59 * 60 + 59, 10 * 3600, 23 * 3600 + 59 * 60,
            99 * 3600 + 59 * 60 + 59, 100 * 3600, 250 * 3600 + 7]


@pytest.mark.parametrize("secs", SESIONES)
@pytest.mark.parametrize("vista", VISTAS)
@pytest.mark.parametrize("orient", ORIENT)
def test_sesiones_largas_caben(fresh, secs, vista, orient):
    """Ni 250 horas seguidas sacan el reloj de su caja."""
    app = fresh
    setup(app, "gaux", vista, orient, 1.0)
    open_daw(app)
    app.session = float(secs)
    app.refresh_text()
    app.render_frame(force=True)
    shown = "".join(app.cv.itemcget(d["main"], "text") for d in app.digits)
    assert shown.replace(" ", "") == L.fmt_clock(min(secs, L.CLOCK_MAX)).replace(" ", "")
    assert visible_bbox_ok(app) == []
    assert text_overlaps(app) == []


LARGOS = ["A", "Westing Time With U (Orginal Mix) — versión extendida para el club 2026",
          "ÑÑÑÑÑÑÑÑÑÑÑÑÑÑÑÑÑÑÑÑÑÑÑÑÑÑÑÑÑÑ", "WWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWW",
          "🔥🔥 Fuego 🔥🔥", "日本語のプロジェクト名", "x" * 60]


@pytest.mark.parametrize("nombre", LARGOS)
@pytest.mark.parametrize("vista", VISTAS)
@pytest.mark.parametrize("orient", ORIENT)
@pytest.mark.parametrize("tema", ["gaux", "noche", "personal"])
def test_nombres_largos_no_se_salen(fresh, nombre, vista, orient, tema):
    app = fresh
    app.conf["metas"]["diaria"]["nombre"] = nombre[:24]
    app.conf["personal"]["nombre"] = nombre[:28]
    setup(app, tema, vista, orient, 1.0)
    app.set_project(nombre, auto=False)
    open_daw(app)
    step(app, 30)
    app.render_frame(force=True)
    assert visible_bbox_ok(app) == []
    assert text_overlaps(app) == []


COMBOS = [c for n in range(4) for c in itertools.combinations(["diaria", "semanal", "mensual"], n)]


@pytest.mark.parametrize("metas", COMBOS, ids=["+".join(c) or "ninguna" for c in COMBOS])
@pytest.mark.parametrize("vista", VISTAS)
@pytest.mark.parametrize("orient", ORIENT)
def test_cualquier_combinacion_de_metas(fresh, metas, vista, orient):
    app = fresh
    for k in ("diaria", "semanal", "mensual"):
        app.conf["metas"][k]["activa"] = k in metas
    setup(app, "gaux", vista, orient, 1.0)
    open_daw(app)
    step(app, 600)
    app.render_frame(force=True)
    assert {b["key"] for b in app.bars} <= set(metas)
    if vista == "completa":
        assert {b["key"] for b in app.bars} == set(metas)
    assert visible_bbox_ok(app) == []
    assert text_overlaps(app) == []


@pytest.mark.parametrize("vista", VISTAS)
@pytest.mark.parametrize("orient", ORIENT)
@pytest.mark.parametrize("estado", ["pausa", "break", "fondo", "inactivo", "sesion"])
def test_cada_estado_en_cada_vista(fresh, vista, orient, estado):
    app = fresh
    setup(app, "gaux", vista, orient, 1.0)
    open_daw(app)
    step(app, 10)
    if estado == "pausa":
        app.toggle_pause()
    elif estado == "break":
        app.start_break()
    elif estado == "fondo":
        OS.front = "other"
    elif estado == "inactivo":
        OS.idle = 10_000
    step(app, 5, 2)
    assert app.state == estado
    for _ in range(30):
        app.phase += 0.05
        app.render_frame(force=True)
    assert visible_bbox_ok(app) == []
    assert text_overlaps(app) == []
    drain(app)


@pytest.mark.parametrize("vista,orient,k", CASOS,
                         ids=[f"{v}-{o}-{k}" for v, o, k in CASOS])
def test_cartel_de_descanso_cabe(fresh, vista, orient, k, monkeypatch):
    """El cartel BREAK/RECHARGE que tapa el reloj nunca se sale del widget."""
    app = fresh
    setup(app, "gaux" if k * 10 % 2 else "noche", vista, orient, k)
    open_daw(app)
    step(app, 3725)
    assert app.lvl == 2
    real = L.time.monotonic
    monkeypatch.setattr(L.time, "monotonic", lambda: 4000.5 + (real() % 1) * 0)
    app.render_frame(force=True)
    monkeypatch.undo()
    assert app.brk_items, "el cartel debe aparecer"
    cv = app.cv
    for it in app.brk_items:
        b = cv.bbox(it)
        assert b[0] >= -2 and b[1] >= -2 and b[2] <= app.W + 2 and b[3] <= app.H + 2, (b, app.W, app.H)
    bg, tx = app.brk_items
    tb, rb = cv.bbox(tx), cv.bbox(bg)
    assert tb[0] >= rb[0] - 1 and tb[2] <= rb[2] + 1, "el texto queda dentro del cartel"


@pytest.mark.parametrize("vista", VISTAS)
@pytest.mark.parametrize("orient", ORIENT)
def test_cartel_de_descanso_deja_el_reloj_igual(fresh, vista, orient, monkeypatch):
    """Después del cartel, el reloj vuelve exactamente como estaba (los ':' ocultos siguen ocultos)."""
    app = fresh
    setup(app, "gaux", vista, orient, 1.0)
    open_daw(app)
    step(app, 3725)
    cv = app.cv
    st = lambda i: cv.itemcget(i, "state") or "normal"   # noqa: E731
    before = [st(d["main"]) for d in app.digits]
    units = [st(u) for u in cv.find_withtag("clockunit")]
    for t in (4000.5, 4002.5, 4000.2, 4003.9):
        monkeypatch.setattr(L.time, "monotonic", lambda t=t: t)
        app._break_flash(True)
    monkeypatch.undo()
    app._break_flash(False)
    assert [st(d["main"]) for d in app.digits] == before
    assert [st(u) for u in cv.find_withtag("clockunit")] == units


@pytest.mark.parametrize("vista", VISTAS)
@pytest.mark.parametrize("tema", ["gaux", "noche", "personal"])
def test_horas_de_animacion_sin_fugas(fresh, vista, tema):
    """Miles de cuadros (glitch, rayos, cartel de descanso, metas cumplidas): el lienzo no
    acumula elementos, así que el timer no se pone lento después de horas abierto."""
    app = fresh
    app.conf["metas"]["diaria"]["segundos"] = 60
    setup(app, tema, vista, "horizontal", 1.0)
    open_daw(app)
    step(app, 30)
    app.render_frame(force=True)
    base = len(app.cv.find_all())
    for i in range(1500):
        if i % 50 == 0:
            step(app, 61)                      # cambia el minuto, se cumple la meta, BREAK…
        app.phase += 0.033
        app.render_frame()
    app.particles and [app.render_frame() for _ in range(200)]
    for _ in range(120):
        app.phase += 0.033
        app.render_frame()
    grown = len(app.cv.find_all()) - base
    assert grown <= 30, f"el lienzo creció {grown} elementos"
