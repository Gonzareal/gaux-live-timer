"""Arnés de pruebas del Gaux Live Timer.

Simula el sistema operativo (qué app está al frente, inactividad, título de la ventana del
DAW, pantallas) para poder probar el timer completo en cualquier máquina, sin Live abierto.
Correr:  xvfb-run -s "-screen 0 1920x1080x24" python -m pytest tests
"""
import os
import sys
import tempfile
import time

import pytest

HOME = tempfile.mkdtemp(prefix="gaux_test_home_")
os.environ["HOME"] = HOME
os.environ["USERPROFILE"] = HOME
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import live_timer as L  # noqa: E402

TK_ERRORS = []


class FakeOS:
    """Lo que el timer le pregunta al sistema."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.running = True
        self.front = "live"
        self.idle = 0.0
        self.title = None
        self.bounds = None
        self.screens = []
        self.proc = "Ableton Live 12 Suite"

    def install(self):
        for n in ("live_running", "frontmost_app", "idle_seconds", "daw_window_title",
                  "daw_window_bounds", "screens"):
            if not hasattr(L, "_REAL_" + n):
                setattr(L, "_REAL_" + n, getattr(L, n))     # las nativas, para test_plataforma
        L.live_running = lambda: self.running and L.is_live_name(self.proc)
        L.frontmost_app = lambda: self.front
        L.idle_seconds = lambda: self.idle
        L.daw_window_title = lambda pid: self.title
        L.daw_window_bounds = lambda pid: self.bounds
        L.screens = lambda: list(self.screens)


OS = FakeOS()
OS.install()


def drain(app):
    """Cancela los after() pendientes: las pruebas controlan el reloj a mano."""
    try:
        for i in app.root.tk.splitlist(app.root.tk.call("after", "info")):
            try:
                app.root.tk.call("after", "cancel", i)   # sin borrar el comando de Python
            except Exception:
                pass
    except Exception:
        pass


def _tick(app, secs):
    app.last_tick = time.monotonic() - secs / L.SPEED
    app.watch_front(reschedule=False)
    app.tick()


def step(app, secs=1.0, n=1, chunk=4.0):
    """Avanza el timer 'n' veces 'secs' segundos (en ticks de hasta 'chunk' s, como el real)."""
    for _ in range(n):
        left = secs
        while left > chunk:
            _tick(app, chunk)
            left -= chunk
        _tick(app, left)
        drain(app)


def suspend(app, secs):
    """El equipo se durmió 'secs' segundos (un solo salto grande)."""
    _tick(app, secs)
    drain(app)


def open_daw(app):
    app.last_proc_check = -1e9
    step(app, 0.0)


def make_app():
    import tkinter
    for intento in range(3):
        try:
            app = L.GauxTimer()
            break
        except tkinter.TclError:          # Windows a veces no encuentra init.tcl al crear
            if intento == 2:              # otro Tk seguido (pasa solo en pruebas)
                raise
            import time
            time.sleep(0.5)
    app.root.report_callback_exception = lambda *a: TK_ERRORS.append(a)
    drain(app)
    return app


@pytest.fixture(scope="session")
def app():
    a = make_app()
    yield a
    try:
        a.root.destroy()
    except Exception:
        pass


@pytest.fixture
def fresh(app):
    """El mismo timer, con datos y ajustes de fábrica y el DAW cerrado."""
    OS.reset()
    for f in (L.CONF_FILE, L.DATA_FILE):
        try:
            os.remove(f)
        except OSError:
            pass
    if app.analyzer:
        app.analyzer.set_visible(False)
        app.analyzer.stop_audio()
    for w in list(app.root.winfo_children()):
        if isinstance(w, __import__("tkinter").Toplevel) and \
                not (app.analyzer and w is app.analyzer.win):
            try:
                w.destroy()
            except Exception:
                pass
    app.settings = None
    app.projects_win = None
    app.conf = L.deep_merge(L.DEFAULT_CONF, {})
    app.data = {"dias": {}, "sesiones": [], "proyectos": {}}
    app.live_open = False
    app.counting = False
    app.manual = None
    app.session = 0.0
    app.session_proj = {}
    app.streak = 0.0
    app.vclock = 0.0
    app.last_count_v = None
    app.detected = None
    app.reached = {}
    app.fs_band = None
    app.ui_busy = False
    app.front = "other"
    app.last_front_live = False
    app._other_n = 0
    app.card = None
    app.splash_until = 0.0
    app.pending_splash = False
    L.LIVE_PID[0] = None
    TK_ERRORS.clear()
    app.apply_conf()
    drain(app)
    yield app
    drain(app)
    assert not TK_ERRORS, TK_ERRORS


def canvas_texts(app):
    cv = app.cv
    return [cv.itemcget(i, "text") for i in cv.find_all()
            if cv.type(i) == "text" and cv.itemcget(i, "state") != "hidden"]


def visible_bbox_ok(app, slack=2):
    """Todo lo visible del widget queda dentro de su ventana."""
    cv = app.cv
    bad = []
    deco = {app.scan} | {it for pair in getattr(app, "bolts", []) for it in pair}
    for i in cv.find_all():
        if cv.itemcget(i, "state") == "hidden" or i in deco:   # rayos y barrido: se recortan
            continue
        if cv.type(i) == "text" and not cv.itemcget(i, "text").strip():
            continue
        b = cv.bbox(i)
        if not b:
            continue
        if b[0] < -slack or b[1] < -slack or b[2] > app.W + slack or b[3] > app.H + slack:
            bad.append((cv.type(i), cv.itemcget(i, "text") if cv.type(i) == "text" else "", b))
    return bad


def win_xy(app):
    """Posición real de la ventana del timer."""
    app.root.update_idletasks()
    g = app.root.geometry()
    _, x, y = g.split("+")[0], g.split("+")[1], g.split("+")[2]
    return int(x), int(y)


def pytest_collection_modifyitems(items):
    """Las pruebas del sistema real (apps falsas en Mac/Windows) van primero, con un solo Tk
    limpio como el timer de verdad, antes de las que abren y cierran cientos de ventanas."""
    items.sort(key=lambda it: 0 if "test_plataforma" in it.nodeid else 1)
