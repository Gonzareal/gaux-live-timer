"""Metas y proyectos a lo largo del calendario: medianoche, lunes, fin de mes, fin de año,
29 de febrero. El timer debe repartir cada segundo en el día en que se trabajó."""
import datetime as dt

import pytest

import live_timer as L
import reloj
from conftest import OS, drain, open_daw


@pytest.fixture
def cal(fresh):
    yield fresh
    reloj.restore()


def work(app, secs):
    """Trabajar 'secs' segundos con el calendario avanzando tick a tick."""
    while secs > 0:
        d = min(4.0, secs)
        reloj.advance(d)
        app.last_tick = __import__("time").monotonic() - d / L.SPEED
        app.watch_front(reschedule=False)
        app.tick()
        secs -= d
    drain(app)


def iso(y, m, d):
    return dt.date(y, m, d).isoformat()


# (inicio, segundos de trabajo, reparto esperado por día)
CRUCES = [
    (dt.datetime(2026, 11, 15, 23, 50), 1200, {iso(2026, 11, 15): 600, iso(2026, 11, 16): 600}),
    (dt.datetime(2026, 12, 31, 23, 58), 240, {iso(2026, 12, 31): 120, iso(2027, 1, 1): 120}),
    (dt.datetime(2027, 2, 28, 23, 59), 120, {iso(2027, 2, 28): 60, iso(2027, 3, 1): 60}),
    (dt.datetime(2028, 2, 28, 23, 59), 120, {iso(2028, 2, 28): 60, iso(2028, 2, 29): 60}),
    (dt.datetime(2028, 2, 29, 23, 59), 120, {iso(2028, 2, 29): 60, iso(2028, 3, 1): 60}),
    (dt.datetime(2026, 11, 30, 23, 0), 7200, {iso(2026, 11, 30): 3600, iso(2026, 12, 1): 3600}),
    (dt.datetime(2026, 6, 30, 23, 59, 58), 4, {iso(2026, 6, 30): 2, iso(2026, 7, 1): 2}),
    (dt.datetime(2026, 11, 15, 22, 0), 3 * 3600,
     {iso(2026, 11, 15): 7200, iso(2026, 11, 16): 3600}),
    (dt.datetime(2026, 11, 15, 12, 0), 8 * 3600, {iso(2026, 11, 15): 8 * 3600}),
    (dt.datetime(2026, 11, 14, 0, 0), 600, {iso(2026, 11, 14): 600}),
]


@pytest.mark.parametrize("start,secs,expected", CRUCES,
                         ids=[c[0].strftime("%Y%m%d-%H%M%S") for c in CRUCES])
def test_reparte_cada_segundo_en_su_dia(cal, start, secs, expected):
    app = cal
    reloj.set_now(start)
    OS.title = "Cruce [x] - Ableton Live 12 Suite"
    open_daw(app)
    work(app, secs)
    # (el reloj de pared simulado y el monotónico real difieren en microsegundos: una astilla
    # de < 0.5 s al otro lado de la medianoche es ruido de la prueba, no del timer)
    assert {k for k, v in app.data["dias"].items() if v >= 0.5} == set(expected)
    for k, v in expected.items():
        assert app.data["dias"][k] == pytest.approx(v, abs=0.2), k
        assert app.data["proyectos"]["Cruce"]["dias"][k] == pytest.approx(v, abs=0.2)
    assert app.session == pytest.approx(secs, abs=0.2)     # la sesión no se corta a medianoche


# Metas: (hoy, {día: horas trabajadas}, esperado diaria/semanal/mensual en horas)
METAS = [
    # domingo 15 nov 2026: la semana empezó el lunes 9
    (dt.date(2026, 11, 15), {"2026-11-09": 2, "2026-11-08": 5, "2026-11-15": 1, "2026-11-01": 3},
     (1, 3, 11)),
    # lunes 16: semana nueva, mes sigue
    (dt.date(2026, 11, 16), {"2026-11-15": 4, "2026-11-16": 1}, (1, 1, 5)),
    # 1 de diciembre (martes): mes nuevo, semana desde el lunes 30 de nov
    (dt.date(2026, 12, 1), {"2026-11-30": 2, "2026-12-01": 3, "2026-11-29": 9}, (3, 5, 3)),
    # 1 de enero 2027 (viernes): semana cruza el año
    (dt.date(2027, 1, 1), {"2026-12-28": 1, "2026-12-31": 2, "2027-01-01": 4, "2026-12-27": 7},
     (4, 7, 4)),
    # año bisiesto
    (dt.date(2028, 2, 29), {"2028-02-28": 2, "2028-02-29": 1, "2028-02-01": 5, "2028-01-31": 8},
     (1, 3, 8)),
    # sin datos
    (dt.date(2026, 11, 15), {}, (0, 0, 0)),
    # solo datos viejos
    (dt.date(2026, 11, 15), {"2025-11-15": 10, "2026-10-31": 3}, (0, 0, 0)),
]


@pytest.mark.parametrize("hoy,dias,esperado", METAS, ids=[str(m[0]) + f"-{i}"
                                                          for i, m in enumerate(METAS)])
def test_metas_por_periodo(cal, hoy, dias, esperado):
    app = cal
    reloj.set_now(dt.datetime(hoy.year, hoy.month, hoy.day, 12))
    app.data["dias"] = {k: v * 3600 for k, v in dias.items()}
    g = app.goal_values()
    assert (g["diaria"] / 3600, g["semanal"] / 3600, g["mensual"] / 3600) == \
        pytest.approx(esperado)
    # y el proyecto da lo mismo si todo fue a un solo proyecto
    app.data["proyectos"] = {"P": {"segundos": sum(dias.values()) * 3600,
                                   "dias": {k: v * 3600 for k, v in dias.items()},
                                   "sesiones": 1, "creado": None, "ultima": None, "daw": ""}}
    v = app.project_values("P")
    assert (v["hoy"] / 3600, v["semana"] / 3600, v["mes"] / 3600) == pytest.approx(esperado)
    app.refresh_text()


@pytest.mark.parametrize("dia", range(1, 32))
def test_cada_dia_de_diciembre(cal, dia):
    """Trabajar 1 h cada día de diciembre: la meta mensual sube 1 h por día."""
    app = cal
    app.data["dias"] = {}
    for d in range(1, dia + 1):
        app.data["dias"][iso(2026, 12, d)] = 3600
    reloj.set_now(dt.datetime(2026, 12, dia, 18))
    g = app.goal_values()
    assert g["mensual"] == dia * 3600
    assert g["diaria"] == 3600
    wd = dt.date(2026, 12, dia).weekday()
    assert g["semanal"] == min(dia, wd + 1) * 3600
    app.refresh_text()


@pytest.mark.parametrize("meta_h,trabajo_min", [(1, 59), (1, 60), (1, 61), (2, 119),
                                                (4, 240), (8, 300)])
def test_meta_diaria_se_cumple_a_su_hora(cal, meta_h, trabajo_min):
    app = cal
    reloj.set_now(dt.datetime(2026, 11, 15, 10))
    app.conf["metas"]["diaria"].update(activa=True, segundos=meta_h * 3600)
    app.apply_conf()
    open_daw(app)
    work(app, trabajo_min * 60)
    app.refresh_text()
    drain(app)
    assert app.reached.get("diaria") == (trabajo_min >= meta_h * 60)


def test_sesion_que_cruza_medianoche_se_registra_una_vez(cal):
    app = cal
    reloj.set_now(dt.datetime(2026, 11, 15, 23, 30))
    open_daw(app)
    work(app, 3600)
    OS.running = False
    app.last_proc_check = -1e9
    work(app, 1)
    s = app.data["sesiones"]
    assert len(s) == 1 and s[0]["segundos"] == pytest.approx(3600, abs=1)
    assert s[0]["inicio"].startswith("2026-11-15T23:30")
    assert s[0]["fin"].startswith("2026-11-16T00:30")


def test_ultima_vez_del_proyecto_sigue_el_reloj(cal):
    app = cal
    reloj.set_now(dt.datetime(2026, 11, 15, 23, 59))
    OS.title = "Late [x] - Ableton Live 12 Suite"
    open_daw(app)
    work(app, 120)
    assert app.data["proyectos"]["Late"]["ultima"] == "2026-11-16T00:01"
