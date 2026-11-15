"""Simulaciones largas al azar (días enteros de trabajo) comparadas con un modelo exacto.

Cada semilla arma una jornada distinta: abrir y cerrar el DAW, cambiar de app, quedarse
quieto, pausar, tomar breaks, cambiar de set, elegir proyectos a mano, dormir el equipo y
cruzar la medianoche. Al final el timer debe haber contado exactamente lo mismo que el
modelo: por día, por proyecto y por sesión, y todo debe volver a leerse igual del disco.
"""
import datetime as dt
import json
import random

import pytest

import live_timer as L
import reloj
from conftest import OS, TK_ERRORS, drain

TITLES = [
    ("CRAZY SYNTHS  [CRAZY SYNTHS Project] - Ableton Live 12 Suite", "CRAZY SYNTHS"),
    ("Tahelly Project - Ableton Live 12 Suite", "Tahelly Project"),
    ("Westing Time With U [Westing Time With U Project] - Ableton Live 12 Suite",
     "Westing Time With U"),
    ("Untitled - Ableton Live 12 Suite", None),
    ("Ableton Live 12 Suite", None),
    ("Orginal Mix*  [Orginal Mix Project] - Ableton Live 12 Suite", "Orginal Mix"),
    ("Ñandú Café ★ [x] - Ableton Live 12 Suite", "Ñandú Café ★"),
]
MANUAL = ["", "Remix Pedido", "Sin asignar", "Ideas"]
LIMIT = 300
TOL = 0.1          # el reloj real corre unos microsegundos entre tick y tick


class Model:
    """Lo que el timer debería contar, segundo a segundo."""

    def __init__(self):
        self.live_open = False
        self.last_front_live = False
        self.other_n = 0
        self.session = 0.0
        self.session_proj = {}
        self.dias = {}
        self.proj = {}
        self.sesiones = []
        self.detected = None
        self.manual = None
        self.conf_proj = ""
        self.auto = True

    def name(self):
        if self.auto and self.detected:
            return self.detected
        return self.conf_proj or L.SIN_PROYECTO

    def tick(self, d, today, running, front, idle, title):
        if self.live_open:                       # watch_front antes del tick
            self._front(front)
        if running and not self.live_open:
            self.live_open = True
            self.manual = None
            self.session = 0.0
            self._front(front)
        elif not running and self.live_open:
            self.live_open = False
            if self.session >= 60:
                self.sesiones.append((int(self.session),
                                      {k: int(v) for k, v in self.session_proj.items()
                                       if v >= 1}))
            for n, s in self.session_proj.items():
                if s >= 60 and n in self.proj:
                    self.proj[n]["ses"] += 1
            self.session_proj = {}
            self.session = 0.0
            self.detected = None
        if not self.live_open:
            return
        front_live = self.last_front_live if front == "self" else front == "live"
        counting = not self.manual and front_live and idle < LIMIT
        if front == "live" and self.auto:
            n = L.project_from_title(title)
            if n != self.detected:
                self.detected = n
                if n:
                    self._rec(n)
        if counting:
            self.session += d
            n = self.name()
            r = self._rec(n)
            r["s"] += d
            for day, part in L.GauxTimer._split_days(d):
                self.dias[day] = self.dias.get(day, 0) + part
                r["dias"][day] = r["dias"].get(day, 0) + part
            self.session_proj[n] = self.session_proj.get(n, 0) + d

    def _front(self, front):
        if front == "live":
            self.other_n = 0
            self.last_front_live = True
        elif front == "other":
            self.other_n += 1
            if self.other_n >= 2:
                self.last_front_live = False

    def _rec(self, n):
        return self.proj.setdefault(n, {"s": 0.0, "dias": {}, "ses": 0})


def _fresh(app, start):
    reloj.set_now(start)
    OS.reset()
    app.conf = L.deep_merge(L.DEFAULT_CONF, {})
    app.conf["limite_inactividad"] = LIMIT
    app.data = {"dias": {}, "sesiones": [], "proyectos": {}}
    for k, v in dict(live_open=False, counting=False, manual=None, session=0.0,
                     session_proj={}, streak=0.0, vclock=0.0, last_count_v=None,
                     detected=None, reached={}, front="other", last_front_live=False,
                     _other_n=0, card=None, settings=None, projects_win=None,
                     pending_splash=False).items():
        setattr(app, k, v)
    L.LIVE_PID[0] = None
    TK_ERRORS.clear()
    app.apply_conf()
    drain(app)


def _run_tick(app, model, d):
    """Un tick de 'd' segundos en el timer y en el modelo (con el calendario avanzando)."""
    reloj.advance(d)
    today = L.dt.date.today().isoformat()
    app.last_proc_check = -1e9             # revisar el proceso en cada tick
    app._title_t = -1e9                    # y el título del DAW también
    app.last_tick = __import__("time").monotonic() - d / L.SPEED
    app.watch_front(reschedule=False)
    app.tick()
    counted = d if d <= 5 * L.SPEED else 0.0
    model.tick(counted, today, OS.running, OS.front, OS.idle, OS.title)


def _advance(app, model, secs):
    while secs > 0:
        d = min(4.0, secs)
        _run_tick(app, model, d)
        secs -= d
    drain(app)


def _check(app, model):
    assert app.live_open == model.live_open
    assert app.session == pytest.approx(model.session, abs=TOL)
    assert app.detected == model.detected
    assert app.project_name() == model.name()
    assert set(app.data["dias"]) == set(model.dias)
    for k, v in model.dias.items():
        assert app.data["dias"][k] == pytest.approx(v, abs=TOL), k
    recs = app.data["proyectos"]
    assert set(recs) == set(model.proj), (set(recs), set(model.proj))
    for n, r in model.proj.items():
        assert recs[n]["segundos"] == pytest.approx(r["s"], abs=TOL), n
        assert recs[n]["sesiones"] == r["ses"], n
        for k, v in r["dias"].items():
            assert recs[n]["dias"][k] == pytest.approx(v, abs=TOL)
    got = [(s["segundos"], s["proyectos"]) for s in app.data["sesiones"]]
    assert got == model.sesiones
    # cuadra: lo de cada día es la suma de lo de cada proyecto ese día
    for day, total in app.data["dias"].items():
        by_proj = sum(r["dias"].get(day, 0) for r in recs.values())
        assert by_proj == pytest.approx(total, abs=TOL)
    # nada negativo, nada fuera de su sitio
    assert all(v >= 0 for v in app.data["dias"].values())
    assert app.session >= 0 and app.streak >= 0


def _jornada(app, seed, start):
    rnd = random.Random(seed)
    _fresh(app, start)
    model = Model()
    OS.running = False
    OS.title = TITLES[0][0]
    for _ in range(rnd.randint(20, 45)):
        ev = rnd.random()
        if ev < 0.12:
            OS.running = not OS.running
        elif ev < 0.34:
            OS.front = rnd.choice(["live", "live", "live", "other", "self"])
        elif ev < 0.44:
            OS.idle = rnd.choice([0, 0, 10, LIMIT - 1, LIMIT, LIMIT + 500])
        elif ev < 0.58:
            OS.title = rnd.choice(TITLES)[0]
        elif ev < 0.66 and app.live_open:
            if app.manual:
                app.resume()
                model.manual = None
            elif rnd.random() < 0.5:
                app.toggle_pause()
                model.manual = "pausa"
            else:
                app.start_break()
                model.manual = "break"
            drain(app)
        elif ev < 0.72:
            name = rnd.choice(MANUAL)
            auto = rnd.choice([None, True, False])
            app.set_project(name, auto=auto)
            model.conf_proj = "" if name == L.SIN_PROYECTO else name
            if auto is not None:
                model.auto = auto
            if name and name != L.SIN_PROYECTO:
                model._rec(name)
            drain(app)
        elif ev < 0.76:
            # el equipo se duerme: un salto grande que no cuenta
            _run_tick(app, model, rnd.choice([30, 600, 3 * 3600]))
            drain(app)
        _advance(app, model, rnd.choice([1, 3, 4, 7, 30, 61, 120, 300, 900]))
        _check(app, model)
    OS.running = False                     # fin del día: cerrar el DAW
    _advance(app, model, 4)
    _check(app, model)
    # lo guardado en disco es exactamente lo que hay en memoria
    L.save_json(L.DATA_FILE, app.data)
    disk = L.load_json(L.DATA_FILE)
    assert json.loads(json.dumps(app.data)) == disk
    assert not TK_ERRORS, TK_ERRORS


STARTS = [dt.datetime(2026, 11, 15, 9, 0), dt.datetime(2026, 11, 15, 23, 10),
          dt.datetime(2026, 12, 31, 22, 30), dt.datetime(2027, 2, 28, 21, 0),
          dt.datetime(2028, 2, 28, 23, 50), dt.datetime(2026, 11, 22, 23, 30)]


@pytest.mark.parametrize("seed", range(200))
def test_jornada_al_azar(app, seed):
    try:
        _jornada(app, seed, STARTS[seed % len(STARTS)])
    finally:
        reloj.restore()
        OS.reset()
        app.live_open = False
        drain(app)
