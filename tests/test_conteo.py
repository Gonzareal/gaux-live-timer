"""Conteo del tiempo con cada DAW, proyectos, sesiones, metas y guardado de los datos."""
import datetime as dt
import json
import os

import pytest

import live_timer as L
from conftest import OS, drain, make_app, open_daw, step, suspend

DAW_CASOS = [
    # (proceso, título de la ventana, proyecto esperado, DAW)
    ("Ableton Live 12 Suite", "CRAZY SYNTHS  [CRAZY SYNTHS Project] - Ableton Live 12 Suite",
     "CRAZY SYNTHS", "Ableton Live"),
    ("Live", "Tahelly Project - Ableton Live 12 Suite", "Tahelly Project", "Ableton Live"),
    ("FL64.exe", "Mi Beat.flp - FL Studio 2024", "Mi Beat", "FL Studio"),
    ("OsxFL", "FL Studio 2024 - Mi Beat", "Mi Beat", "FL Studio"),
    ("Logic Pro", "Mi Track - Tracks", "Mi Track", "Logic Pro"),
    ("Pro Tools", "Edit: Sesión Final", "Sesión Final", "Pro Tools"),
    ("Cubase14.exe", "Cubase Pro Project - Remix", "Remix", "Cubase"),
    ("Nuendo 13", "Nuendo Project - Score Film", "Score Film", "Nuendo"),
    ("Studio One 6", "Studio One - Demo", "Demo", "Studio One"),
    ("Bitwig Studio", "Groove - Bitwig Studio", "Groove", "Bitwig Studio"),
    ("REAPER", "Mi Track - REAPER v7.22 - Registered to Gaux", "Mi Track", "REAPER"),
    ("Reason 12", "Rack - Reason", "Rack", "Reason"),
    ("GarageBand", "Idea - Tracks", "Idea", "GarageBand"),
    ("Cakewalk.exe", "Cakewalk by BandLab - [Rock.cwp - Track]", "Rock", "Cakewalk"),
    ("Ardour8", "Club Mix - Ardour", "Club Mix", "Ardour"),
    ("Renoise", "Chip.xrns - Renoise 3.4", "Chip", "Renoise"),
    ("Digital Performer", "Film.dpdoc - Digital Performer", "Film", "Digital Performer"),
]
IDS = [c[3] + "-" + c[0] for c in DAW_CASOS]


def today():
    return dt.date.today().isoformat()


@pytest.mark.parametrize("proc,title,proj,daw", DAW_CASOS, ids=IDS)
def test_cuenta_con_cada_daw(fresh, proc, title, proj, daw):
    app = fresh
    OS.proc, OS.title = proc, title
    open_daw(app)
    assert app.live_open
    step(app, 600)
    assert app.session == pytest.approx(600, abs=1)
    assert app.data["dias"][today()] == pytest.approx(600, abs=1)
    assert app.project_name() == proj
    rec = app.data["proyectos"][proj]
    assert rec["segundos"] == pytest.approx(600, abs=4)
    assert rec["daw"] == daw


@pytest.mark.parametrize("proc,title,proj,daw", DAW_CASOS, ids=IDS)
def test_no_cuenta_con_el_daw_atras(fresh, proc, title, proj, daw):
    app = fresh
    OS.proc, OS.title = proc, title
    open_daw(app)
    OS.front = "other"
    step(app, 1, 3)
    before = app.session
    step(app, 300)
    assert app.session == pytest.approx(before)
    assert app.state == "fondo"


@pytest.mark.parametrize("proc,title,proj,daw", DAW_CASOS, ids=IDS)
def test_daw_desactivado_no_cuenta(fresh, proc, title, proj, daw):
    app = fresh
    key = next(k for k, n, _ in L.DAWS if n == daw)
    app.conf["daws"] = [k for k, _, _ in L.DAWS if k != key]
    app.apply_targets()
    OS.proc, OS.title = proc, title
    open_daw(app)
    step(app, 60)
    assert not app.live_open and app.session == 0


@pytest.mark.parametrize("proc,title,proj,daw", DAW_CASOS, ids=IDS)
def test_cerrar_el_daw_guarda_la_sesion(fresh, proc, title, proj, daw):
    app = fresh
    OS.proc, OS.title = proc, title
    open_daw(app)
    step(app, 180)
    OS.running = False
    app.last_proc_check = -1e9
    step(app, 1)
    assert not app.live_open and app.session == 0
    saved = L.load_json(L.DATA_FILE)
    s = saved["sesiones"][-1]
    assert s["segundos"] == pytest.approx(180, abs=2)
    assert s["proyectos"][proj] == pytest.approx(180, abs=5)
    assert saved["proyectos"][proj]["sesiones"] == 1


@pytest.mark.parametrize("limite", [60, 120, 300, 600, 1800])
def test_inactividad_pausa(fresh, limite):
    app = fresh
    app.conf["limite_inactividad"] = limite
    open_daw(app)
    step(app, 10)
    OS.idle = limite + 1
    step(app, 100)
    assert app.state == "inactivo" and app.session == pytest.approx(10, abs=0.5)
    OS.idle = 0
    step(app, 10)
    assert app.counting and app.session == pytest.approx(20, abs=0.5)


@pytest.mark.parametrize("secs", [6, 60, 3600, 8 * 3600])
def test_equipo_dormido_no_suma(fresh, secs):
    app = fresh
    open_daw(app)
    step(app, 10)
    suspend(app, secs)
    assert app.session == pytest.approx(10, abs=0.5)


def test_pausa_manual(fresh):
    app = fresh
    open_daw(app)
    step(app, 10)
    app.toggle_pause()
    step(app, 100)
    assert app.state == "pausa" and app.session == pytest.approx(10, abs=0.5)
    app.toggle_pause()
    step(app, 10)
    assert app.session == pytest.approx(20, abs=0.5)


def test_reabrir_el_daw_empieza_sesion_nueva(fresh):
    app = fresh
    open_daw(app)
    step(app, 120)
    OS.running = False
    app.last_proc_check = -1e9
    step(app, 1)
    OS.running = True
    open_daw(app)
    step(app, 30)
    assert app.session == pytest.approx(30, abs=1)
    assert len(app.data["sesiones"]) == 1


def test_sesion_corta_no_se_registra(fresh):
    app = fresh
    open_daw(app)
    step(app, 30)
    OS.running = False
    app.last_proc_check = -1e9
    step(app, 1)
    assert app.data["sesiones"] == []


def test_maximo_500_sesiones(fresh):
    app = fresh
    app.data["sesiones"] = [{"segundos": 60}] * 600
    open_daw(app)
    step(app, 70)
    OS.running = False
    app.last_proc_check = -1e9
    step(app, 1)
    assert len(app.data["sesiones"]) == 500


def test_cambio_de_dia_a_medianoche(fresh):
    import reloj
    app = fresh
    try:
        reloj.set_now(dt.datetime(2026, 11, 14, 23, 58))
        open_daw(app)
        for _ in range(45):                      # 3 minutos, el reloj avanza con cada tick
            reloj.advance(4)
            step(app, 4)
        assert app.data["dias"]["2026-11-14"] == pytest.approx(120, abs=1)
        assert app.data["dias"]["2026-11-15"] == pytest.approx(60, abs=1)
    finally:
        reloj.restore()


def test_autoguardado_cada_30s(fresh):
    app = fresh
    open_daw(app)
    app.last_save = 0
    step(app, 45)
    saved = L.load_json(L.DATA_FILE)
    assert saved["dias"][today()] > 0


# ---------------------------------------------------------------- proyectos
def test_proyecto_detectado_cambia_al_cambiar_de_set(fresh):
    app = fresh
    OS.title = "Uno [Uno Project] - Ableton Live 12 Suite"
    open_daw(app)
    step(app, 60)
    OS.title = "Dos [Dos Project] - Ableton Live 12 Suite"
    app._title_t = 0
    step(app, 60)
    p = app.data["proyectos"]
    assert p["Uno"]["segundos"] == pytest.approx(60, abs=4)
    assert p["Dos"]["segundos"] == pytest.approx(60, abs=4)


def test_set_sin_guardar_va_a_sin_asignar(fresh):
    app = fresh
    OS.title = "Untitled - Ableton Live 12 Suite"
    open_daw(app)
    step(app, 60)
    assert app.project_name() == L.SIN_PROYECTO
    assert app.data["proyectos"][L.SIN_PROYECTO]["segundos"] == pytest.approx(60, abs=1)


def test_proyecto_a_mano_gana_si_se_apaga_la_deteccion(fresh):
    app = fresh
    OS.title = "Auto [Auto Project] - Ableton Live 12 Suite"
    app.set_project("Manual", auto=False)
    open_daw(app)
    step(app, 60)
    assert app.project_name() == "Manual"
    assert "Auto" not in app.data["proyectos"]


def test_proyecto_a_mano_sin_titulo(fresh):
    app = fresh
    OS.title = ""
    app.set_project("Mi idea")
    open_daw(app)
    step(app, 60)
    assert app.data["proyectos"]["Mi idea"]["segundos"] == pytest.approx(60, abs=1)


@pytest.mark.parametrize("name", ["Westing Time With U", "Mi Track (Orginal Mix)", "Canción ñ",
                                  "🎧 beat", "x" * 80, "  espacios  ", "a/b\\c:d", "\"comillas\"",
                                  "=SUMA(A1)", "Tahelly Project"])
def test_nombres_se_guardan_tal_cual(fresh, name):
    app = fresh
    app.set_project(name)
    expect = name.strip()[:60]
    assert expect in L.load_json(L.DATA_FILE)["proyectos"]
    assert L.load_json(L.CONF_FILE)["proyecto"] == expect


def test_renombrar(fresh):
    app = fresh
    app.set_project("Viejo")
    open_daw(app)
    step(app, 60)
    app.rename_project("Viejo", "Nuevo")
    recs = L.load_json(L.DATA_FILE)["proyectos"]
    assert "Viejo" not in recs and recs["Nuevo"]["segundos"] == pytest.approx(60, abs=1)
    assert app.conf["proyecto"] == "Nuevo"


def test_renombrar_une_con_existente(fresh):
    app = fresh
    for n, secs in (("A", 60), ("B", 120)):
        app.set_project(n)
        open_daw(app)
        step(app, secs)
    app.rename_project("A", "B")
    r = app.data["proyectos"]
    assert "A" not in r and r["B"]["segundos"] == pytest.approx(180, abs=2)
    assert sum(r["B"]["dias"].values()) == pytest.approx(180, abs=2)


def test_renombrar_detectado_recuerda_el_alias(fresh):
    app = fresh
    OS.title = "id3 [id3 Project] - Ableton Live 12 Suite"
    open_daw(app)
    step(app, 30)
    app.rename_project("id3", "Track Final")
    app.detected = None
    app._title_t = 0
    step(app, 30)
    assert app.project_name() == "Track Final"
    assert "id3" not in app.data["proyectos"]


def test_renombrar_dos_veces_sigue_el_alias(fresh):
    app = fresh
    OS.title = "id3 [id3 Project] - Ableton Live 12 Suite"
    open_daw(app)
    step(app, 30)
    app.rename_project("id3", "B")
    app.rename_project("B", "C")
    app.detected = None
    app._title_t = 0
    step(app, 30)
    assert app.project_name() == "C"
    assert set(app.data["proyectos"]) == {"C"}


def test_renombrar_y_volver_al_nombre_original(fresh):
    app = fresh
    OS.title = "id3 [id3 Project] - Ableton Live 12 Suite"
    open_daw(app)
    step(app, 30)
    app.rename_project("id3", "B")
    app.rename_project("B", "id3")
    app.detected = None
    app._title_t = 0
    step(app, 30)
    assert app.project_name() == "id3"
    assert set(app.data["proyectos"]) == {"id3"}


@pytest.mark.parametrize("bad", ["", "   ", None])
def test_renombrar_a_vacio_no_hace_nada(fresh, bad):
    app = fresh
    app.set_project("X")
    app.rename_project("X", bad)
    assert "X" in app.data["proyectos"]


def test_renombrar_inexistente(fresh):
    fresh.rename_project("no existe", "algo")
    assert "algo" not in fresh.data["proyectos"]


def test_eliminar(fresh):
    app = fresh
    app.set_project("Borrar")
    app.set_project("Queda")
    app.delete_project("Borrar")
    recs = L.load_json(L.DATA_FILE)["proyectos"]
    assert "Borrar" not in recs and "Queda" in recs


def test_eliminar_el_activo(fresh):
    app = fresh
    app.set_project("Activo")
    open_daw(app)
    step(app, 30)
    app.delete_project("Activo")
    assert app.conf["proyecto"] == "" and app.project_name() == L.SIN_PROYECTO
    step(app, 30)
    assert "Activo" not in app.data["proyectos"]


def test_eliminar_el_detectado_no_reaparece_al_instante(fresh):
    """Borrar el proyecto abierto en el DAW: deja de sumarse ahí hasta que se vuelva a abrir."""
    app = fresh
    OS.title = "Borrame [Borrame Project] - Ableton Live 12 Suite"
    open_daw(app)
    step(app, 30)
    app.delete_project("Borrame")
    step(app, 30)
    assert app.data["proyectos"].get("Borrame", {}).get("segundos", 0) <= 31


def test_eliminar_no_toca_las_horas_del_dia(fresh):
    app = fresh
    app.set_project("X")
    open_daw(app)
    step(app, 100)
    app.delete_project("X")
    assert app.data["dias"][today()] == pytest.approx(100, abs=1)


def test_eliminar_inexistente(fresh):
    fresh.delete_project("nada")


def test_valores_por_periodo(fresh):
    app = fresh
    d = dt.date.today()
    monday = d - dt.timedelta(days=d.weekday())
    app.data["proyectos"]["P"] = {"segundos": 1000, "sesiones": 3, "creado": None,
                                  "ultima": None, "daw": "Ableton Live",
                                  "dias": {d.isoformat(): 100,
                                           monday.isoformat(): 200 if monday != d else 0,
                                           "2000-01-01": 700}}
    v = app.project_values("P")
    assert v["total"] == 1000 and v["hoy"] == 100
    assert v["semana"] == pytest.approx(100 + (200 if monday != d else 0))
    assert v["sesiones"] == 3


# ---------------------------------------------------------------- metas
@pytest.mark.parametrize("meta", ["diaria", "semanal", "mensual"])
@pytest.mark.parametrize("segs,llevo,done", [(3600, 1800, False), (3600, 3600, True),
                                             (3600, 7200, True), (60, 61, True)])
def test_metas(fresh, meta, segs, llevo, done):
    app = fresh
    for k in ("diaria", "semanal", "mensual"):
        app.conf["metas"][k]["activa"] = k == meta
    app.conf["metas"][meta]["segundos"] = segs
    app.apply_conf()
    open_daw(app)
    step(app, llevo)
    app.render_frame(force=True)
    b = next(b for b in app.bars if b["key"] == meta)
    assert b["p"] == pytest.approx(min(1, llevo / segs), abs=0.01)
    assert b["done"] == done


@pytest.mark.parametrize("on", [(True, True, True), (False, False, False), (True, False, True),
                                (False, True, False)])
def test_metas_activas_se_dibujan(fresh, on):
    app = fresh
    for k, v in zip(("diaria", "semanal", "mensual"), on):
        app.conf["metas"][k]["activa"] = v
    app.apply_conf()
    assert [b["key"] for b in app.bars] == [k for k, v in zip(("diaria", "semanal", "mensual"),
                                                               on) if v]


def test_meta_semanal_suma_la_semana(fresh):
    app = fresh
    d = dt.date.today()
    monday = d - dt.timedelta(days=d.weekday())
    app.data["dias"] = {monday.isoformat(): 3600, (monday - dt.timedelta(days=1)).isoformat(): 9999}
    if monday != d:
        app.data["dias"][d.isoformat()] = 1800
    v = app.goal_values()
    assert v["semanal"] == 3600 + (1800 if monday != d else 0)


# ---------------------------------------------------------------- arranque y datos dañados
@pytest.mark.parametrize("conf", [
    "{}", "", "{", "null", "[]", "\"x\"",
    json.dumps({"tema": "no-existe"}),
    json.dumps({"tema": 5}),
    json.dumps({"vista": "rara"}),
    json.dumps({"orientacion": None}),
    json.dumps({"metas": None}),
    json.dumps({"metas": {"diaria": None}}),
    json.dumps({"metas": {"diaria": {"segundos": "mucho"}}}),
    json.dumps({"autonomo": "x"}),
    json.dumps({"autonomo": {"trabajo_min": 0, "break_min": -1}}),
    json.dumps({"opacidad": "x"}),
    json.dumps({"opacidad": 5}),
    json.dumps({"escala": []}),
    json.dumps({"pos": []}),
    json.dumps({"pos": {"completa": "x"}}),
    json.dumps({"x": "a", "y": None}),
    json.dumps({"x": 99999, "y": -99999}),
    json.dumps({"limite_inactividad": "x"}),
    json.dumps({"analizador": None}),
    json.dumps({"analizador": {"w": "x", "h": -5}}),
    json.dumps({"analizador": {"modulos": []}}),
    json.dumps({"personal": None}),
    json.dumps({"daws": "live"}),
    json.dumps({"daws": ["live", 5, None]}),
    json.dumps({"daws_extra": 7}),
    json.dumps({"top_escala": "x"}),
    json.dumps({"top_mode": True, "top_geom": None}),
    json.dumps({"top_mode": True, "top_geom": [1, 2]}),
    json.dumps({"proyecto": 5}),
    json.dumps({"animaciones": "si"}),
    json.dumps({"modo": "loco"}),
])
def test_arranca_con_ajustes_dañados(conf):
    OS.reset()
    os.makedirs(L.APP_DIR, exist_ok=True)
    with open(L.CONF_FILE, "w") as f:
        f.write(conf)
    try:
        os.remove(L.DATA_FILE)
    except OSError:
        pass
    app = make_app()
    try:
        open_daw(app)
        step(app, 10)
        for _ in range(3):
            app.render_frame(force=True)
        app.save_conf()
        assert app.W > 0 and app.H > 0
    finally:
        app.root.destroy()


@pytest.mark.parametrize("data", [
    "{}", "", "{", "[]",
    json.dumps({"dias": None}),
    json.dumps({"dias": [], "sesiones": {}, "proyectos": []}),
    json.dumps({"dias": {"2026-11-14": "x"}}),
    json.dumps({"proyectos": {"A": None}}),
    json.dumps({"proyectos": {"A": {"segundos": "x", "dias": None}}}),
    json.dumps({"proyectos": {"A": {}}}),
    json.dumps({"alias": None}),
    json.dumps({"sesiones": [None, 5, "x"]}),
])
def test_arranca_con_datos_dañados(data):
    OS.reset()
    os.makedirs(L.APP_DIR, exist_ok=True)
    try:
        os.remove(L.CONF_FILE)
    except OSError:
        pass
    with open(L.DATA_FILE, "w") as f:
        f.write(data)
    app = make_app()
    try:
        OS.title = "A [A Project] - Ableton Live 12 Suite"
        open_daw(app)
        step(app, 70)
        app.goal_values()
        app.project_values("A")
        OS.running = False
        app.last_proc_check = -1e9
        step(app, 1)
        saved = L.load_json(L.DATA_FILE)
        assert saved["proyectos"]["A"]["segundos"] >= 69
    finally:
        app.root.destroy()


def test_datos_reales_del_usuario_se_conservan():
    """Un archivo con el formato real (como el de tu Mac) se lee y se conserva completo."""
    OS.reset()
    data = {"dias": {"2026-11-10": 9632.8, "2026-11-11": 12236.08},
            "sesiones": [{"inicio": "2026-11-11T10:00:00", "fin": "2026-11-11T13:00:00",
                          "segundos": 10800, "proyectos": {"CRAZY SYNTHS": 10800}}],
            "proyectos": {n: {"segundos": 3600.0, "dias": {"2026-11-11": 3600.0}, "sesiones": 2,
                              "creado": "2026-11-08T01:13", "ultima": "2026-11-11T13:00",
                              "daw": "Ableton Live"}
                          for n in ("Sin asignar", "Tahelly Project", "CRAZY SYNTHS")},
            "alias": {"crazy": "CRAZY SYNTHS"}}
    os.makedirs(L.APP_DIR, exist_ok=True)
    with open(L.DATA_FILE, "w") as f:
        json.dump(data, f)
    app = make_app()
    try:
        assert app.data["proyectos"] == data["proyectos"]
        app.save_conf()
        L.save_json(L.DATA_FILE, app.data)
        again = L.load_json(L.DATA_FILE)
        for k in ("dias", "sesiones", "proyectos", "alias"):
            assert again[k] == data[k]
    finally:
        app.root.destroy()
