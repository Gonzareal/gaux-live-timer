"""Guardado y lectura a fondo: cerrar y volver a abrir el timer, disco lleno, archivos
editados a mano con cualquier valor raro en cada ajuste, y nombres con cualquier carácter."""
import copy
import json
import math
import os

import pytest

import live_timer as L
from conftest import OS, TK_ERRORS, drain, make_app, open_daw, step


def _clean():
    OS.reset()
    for f in (L.CONF_FILE, L.DATA_FILE):
        try:
            os.remove(f)
        except OSError:
            pass


def _leaves(d, path=()):
    for k, v in d.items():
        if isinstance(v, dict) and v:
            yield from _leaves(v, path + (k,))
        else:
            yield path + (k,)


def _set(d, path, val):
    for k in path[:-1]:
        d = d[k]
    d[path[-1]] = val


LEAVES = list(_leaves(L.DEFAULT_CONF))
RAROS = [None, "xyz", -1, 10 ** 12, [], {"a": 1}, True, float("inf")]


@pytest.mark.parametrize("path", LEAVES, ids=[".".join(p) for p in LEAVES])
@pytest.mark.parametrize("raro", range(len(RAROS)))
def test_cada_ajuste_con_valor_raro(app, path, raro):
    """Cualquier ajuste con cualquier valor raro: el timer abre, dibuja, cuenta y guarda."""
    _clean()
    conf = copy.deepcopy(L.DEFAULT_CONF)
    val = RAROS[raro]
    _set(conf, path, val)
    os.makedirs(L.APP_DIR, exist_ok=True)
    with open(L.CONF_FILE, "w") as f:
        f.write(json.dumps(conf, allow_nan=True))
    a = make_app()
    try:
        open_daw(a)
        step(a, 70)
        for _ in range(3):
            a.render_frame(force=True)
        a.refresh_text()
        a.save_conf()
        assert a.W > 0 and a.H > 0
        if a.conf.get("daws") == []:          # desmarcó todos los DAWs: a propósito no cuenta
            assert a.session == 0
        else:
            assert a.session > 60
        saved = L.load_json(L.CONF_FILE)
        assert isinstance(saved, dict)
        json.dumps(saved, allow_nan=False)                 # lo guardado es JSON válido
        assert not TK_ERRORS, TK_ERRORS
    finally:
        TK_ERRORS.clear()
        a.root.destroy()


@pytest.mark.parametrize("cut", [1, 5, 17, 40, 80, 120, 200, 333, 500, -3, -1])
def test_datos_cortados_a_la_mitad(cut):
    """Un corte de luz a mitad de guardado: el timer abre y respalda lo que había."""
    _clean()
    good = {"dias": {"2026-11-10": 100.0, "2026-11-11": 200.0},
            "proyectos": {"A": {"segundos": 300.0, "dias": {"2026-11-11": 300.0},
                                "sesiones": 2, "creado": None, "ultima": None, "daw": ""}},
            "sesiones": []}
    raw = json.dumps(good, indent=2)
    os.makedirs(L.APP_DIR, exist_ok=True)
    with open(L.DATA_FILE, "w") as f:
        f.write(raw[:cut])
    a = make_app()
    try:
        open_daw(a)
        step(a, 30)
        assert a.session == pytest.approx(30, abs=0.5)
        L.save_json(L.DATA_FILE, a.data)
        assert L.load_json(L.DATA_FILE)["dias"]
    finally:
        a.root.destroy()


@pytest.mark.parametrize("err", [OSError, PermissionError, IOError])
def test_disco_lleno_no_detiene_el_timer(fresh, monkeypatch, err):
    """Si no se puede guardar (disco lleno, permisos, iCloud), el timer sigue contando."""
    app = fresh
    open_daw(app)
    step(app, 10)

    def boom(*a, **k):
        raise err("No space left on device")
    monkeypatch.setattr(L, "_write_json", boom)
    app.last_save = -1e9
    app.last_tick -= 1
    app.watch_front(reschedule=False)
    app.tick()                                   # guardado automático que falla
    pending = app.root.tk.splitlist(app.root.tk.call("after", "info"))
    assert pending, "el siguiente tick quedó programado"
    drain(app)
    step(app, 60)
    assert app.session == pytest.approx(71, abs=1)
    monkeypatch.undo()
    app.last_save = -1e9
    step(app, 1)
    assert L.load_json(L.DATA_FILE)["dias"]


def test_ajustes_que_no_se_pueden_guardar(fresh, monkeypatch):
    app = fresh

    def boom(*a, **k):
        raise PermissionError("solo lectura")
    monkeypatch.setattr(L, "_write_json", boom)
    app.conf["tema"] = "gaux"
    app.save_conf()
    app.set_project("Algo", auto=False)
    app.rename_project("Algo", "Otro")
    app.delete_project("Otro")
    assert "Otro" not in app.data["proyectos"]


NOMBRES = ["Westing Time With U", "Orginal Mix", "CRAZY SYNTHS", "Ñandú", "Café ☕",
           "日本語", "🔥🔥", "a/b\\c", 'comillas "dobles"', "tab\tdentro", "  espacios  ",
           "x" * 60, "MAYÚSCULAS y minúsculas", "123", "con:dos:puntos", "<html>", "null",
           "Sin asignar 2", "../../etc", "emoji 🎧 mezcla"]


@pytest.mark.parametrize("nombre", NOMBRES)
def test_nombre_sobrevive_al_reinicio(fresh, nombre):
    """El nombre de cada proyecto vuelve igual después de cerrar y abrir (sin 'corregirlo')."""
    app = fresh
    app.set_project(nombre, auto=False)
    open_daw(app)
    step(app, 90)
    OS.running = False
    app.last_proc_check = -1e9
    step(app, 1)
    want = nombre.strip()[:60]
    b = make_app()
    try:
        assert want in b.data["proyectos"]
        assert b.data["proyectos"][want]["segundos"] == pytest.approx(90, abs=1)
        assert b.data["proyectos"][want]["sesiones"] == 1
        assert b.conf["proyecto"] == want and b.project_name() == want
    finally:
        b.root.destroy()


@pytest.mark.parametrize("tema", list(L.TEMAS))
@pytest.mark.parametrize("vista", ["completa", "compacta", "mini"])
def test_reinicio_recuerda_todo(fresh, tema, vista):
    """Cerrar y abrir: mismo estilo, misma vista, mismo tamaño, mismo lugar, mismas horas."""
    app = fresh
    app.conf.update(tema=tema, vista=vista, orientacion="horizontal")
    app.apply_conf()
    key = app.pos_key()
    app.conf["escala"][key] = 1.3
    app.apply_conf()
    app.root.update_idletasks()
    open_daw(app)
    step(app, 125)
    app.save_conf()
    app.quit_requested = False
    app._close_session()
    b = make_app()
    try:
        assert b.conf["tema"] == tema and b.conf["vista"] == vista
        assert b.scale_for(key) == pytest.approx(1.3)
        assert sum(b.data["dias"].values()) == pytest.approx(125, abs=1)
        assert (b.W, b.H) == (app.W, app.H)
    finally:
        b.root.destroy()


def test_quinientas_sesiones_y_mil_proyectos_cargan_rapido(fresh):
    import time
    app = fresh
    app.data["proyectos"] = {f"P{i}": {"segundos": i * 60.0, "dias": {"2026-11-15": i * 60.0},
                                       "sesiones": i % 7, "creado": None, "ultima": None,
                                       "daw": "Ableton Live"} for i in range(1000)}
    app.data["sesiones"] = [{"inicio": "2026-11-15T10:00:00", "fin": "2026-11-15T11:00:00",
                             "segundos": 3600, "proyectos": {"P1": 3600}}] * 500
    L.save_json(L.DATA_FILE, app.data)
    t = time.perf_counter()
    b = make_app()
    try:
        assert len(b.data["proyectos"]) == 1000
        assert time.perf_counter() - t < 8
        t = time.perf_counter()
        b.open_projects()
        b.root.update()
        assert time.perf_counter() - t < 8, "la ventana de proyectos abre rápido con 1000"
    finally:
        b.root.destroy()


def test_no_guarda_numeros_invalidos(fresh):
    """Aunque algo raro meta un NaN o infinito, el archivo queda como JSON válido."""
    app = fresh
    app.data["dias"]["2026-11-15"] = float("nan")
    app.data["proyectos"]["X"] = {"segundos": float("inf"), "dias": {}, "sesiones": 0,
                                  "creado": None, "ultima": None, "daw": ""}
    L.save_json(L.DATA_FILE, app.data)
    with open(L.DATA_FILE) as f:
        json.loads(f.read(), parse_constant=lambda c: (_ for _ in ()).throw(ValueError(c)))
    b = make_app()
    try:
        g = b.goal_values()
        assert all(math.isfinite(v) for v in g.values())
        open_daw(b)
        step(b, 10)
        b.refresh_text()
    finally:
        b.root.destroy()


def test_mostrar_mas_proyectos(fresh):
    app = fresh
    app.data["proyectos"] = {f"P{i:03d}": {"segundos": (200 - i) * 60.0, "dias": {},
                                           "sesiones": 0, "creado": None, "ultima": None,
                                           "daw": ""} for i in range(150)}
    app.open_projects()
    w = app.projects_win
    app.root.update()
    shown = lambda: [k for k in w._row_labels]   # noqa: E731
    assert len(shown()) == w.PAGE and "P000" in shown()
    w._more()
    assert len(shown()) == 2 * w.PAGE
    w._more()
    assert len(shown()) == 150 and "P149" in shown()
    w.delete("P149")
    assert "P149" not in app.data["proyectos"] and len(shown()) == 149
    w.destroy()
