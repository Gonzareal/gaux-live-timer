"""Escenarios reales de uso, de principio a fin: ajustar el tamaño a mano mientras se trabaja,
crear y retomar proyectos en días distintos (cerrando el timer y el DAW de por medio), una
jornada con breaks de verdad, todas las animaciones en cada estilo, cada DAW en cada vista y
el analizador con una mezcla parecida a un tema real (kick, bajo, hats, pad) a varios LUFS."""
import datetime as dt
import math

import numpy as np
import pytest

import gaux_analizador as G
import live_timer as L
import reloj
from conftest import OS, TK_ERRORS, drain, make_app, open_daw, step, visible_bbox_ok
from test_analizador import panel, play, prepare, rebuild  # noqa: F401
from test_conteo import DAW_CASOS, IDS
from test_tamanos import text_overlaps
from test_widget import Ev, setup

VISTAS = ["completa", "compacta", "mini"]
ORIENT = ["horizontal", "vertical"]
TEMAS = list(L.TEMAS)


def sano(app, donde=""):
    """Nada se sale, nada se pisa, la ventana mide lo que dice y Tk no reportó errores."""
    app.render_frame(force=True)
    app.root.update_idletasks()                 # la ventana toma su tamaño nuevo
    assert visible_bbox_ok(app) == [], donde
    assert text_overlaps(app) == [], donde
    assert app.root.geometry().startswith(f"{app.W}x{app.H}"), donde
    assert not TK_ERRORS, (donde, TK_ERRORS)


def close_daw(app):
    OS.running = False
    app.last_proc_check = -1e9
    step(app, 1)


# ============================================================ 1. tamaño a mano mientras cuenta
def _arrastrar(app, pasos):
    """Arrastra la esquina como una persona: varios tramos, con el timer contando entre medio."""
    x = y = 600.0
    app.resize_start(Ev(x, y))
    for d in pasos:
        x += d
        y += d
        app.resize_drag(Ev(x, y))
    app.resize_end()


GESTOS = {
    "agrandar_despacio": [6] * 25,
    "pasarse_y_volver": [80] * 8 + [-40] * 8,
    "temblor": [12, -9, 15, -11, 8, -6, 20, -14, 3, -2] * 3,
}


@pytest.mark.parametrize("gesto", list(GESTOS))
@pytest.mark.parametrize("tema", TEMAS)
@pytest.mark.parametrize("orient", ORIENT)
@pytest.mark.parametrize("vista", VISTAS)
def test_ajustar_tamano_mientras_trabajo(fresh, vista, orient, tema, gesto):
    app = fresh
    setup(app, tema, vista, orient)
    OS.title = "Westing Time With U [Westing Time With U Project] - Ableton Live 12 Suite"
    open_daw(app)
    step(app, 1830)
    key = app.pos_key()
    lo, hi = L.ESCALA_LIM["mini" if vista == "mini" else "otra"]
    _arrastrar(app, GESTOS[gesto])
    k = app.scale_for(key)
    assert lo - 1e-6 <= k <= hi + 1e-6
    sano(app, ("tras arrastrar", k))
    step(app, 45)                              # sigue contando con el tamaño nuevo
    assert app.session == pytest.approx(1875, abs=1)
    sano(app, ("contando", k))
    assert L.load_json(L.CONF_FILE)["escala"][key] == pytest.approx(k)
    # nunca queda fuera de la pantalla después de agrandar
    app.root.update_idletasks()
    sw, sh = app.root.winfo_screenwidth(), app.root.winfo_screenheight()
    x, y = app.root.winfo_x(), app.root.winfo_y()
    assert -2 <= x and x + app.W <= sw + 2 and -2 <= y and y + app.H <= sh + 2


@pytest.mark.parametrize("orient", ORIENT)
def test_cada_vista_recuerda_su_tamano(fresh, orient):
    """Agrandar la completa no toca la mini ni la compacta, y todo vuelve tras reiniciar."""
    app = fresh
    want = {}
    for vista, gesto in zip(VISTAS, ([30] * 6, [-20] * 4, [25] * 3)):
        setup(app, "gaux", vista, orient)
        _arrastrar(app, gesto)
        want[app.pos_key()] = app.scale_for(app.pos_key())
    for vista in VISTAS:
        setup(app, "gaux", vista, orient)
        assert app.scale_for(app.pos_key()) == pytest.approx(want[app.pos_key()])
        sano(app, vista)
    b = make_app()
    try:
        for key, k in want.items():
            assert b.scale_for(key) == pytest.approx(k)
    finally:
        b.root.destroy()


@pytest.mark.parametrize("vista", VISTAS)
def test_tamano_al_cambiar_de_estilo(fresh, vista):
    """Cambiar de estilo con el widget agrandado: el tamaño se mantiene y todo cabe."""
    app = fresh
    setup(app, "noche", vista, "horizontal")
    _arrastrar(app, [40] * 5)
    k = app.scale_for(app.pos_key())
    open_daw(app)
    step(app, 600)
    for t in TEMAS:
        app.set_tema(t)
        drain(app)
        assert app.scale_for(app.pos_key()) == pytest.approx(k)
        sano(app, t)


# ============================================================ 2. crear y retomar proyectos
@pytest.mark.parametrize("reinicio", [False, True], ids=["mismo_timer", "reiniciando"])
@pytest.mark.parametrize("proc,title,proj,daw", DAW_CASOS, ids=IDS)
def test_retomar_proyecto_otro_dia(fresh, proc, title, proj, daw, reinicio):
    """Lunes 25 min, cierro el DAW (y el timer); martes abro el mismo proyecto 15 min más."""
    app = fresh
    try:
        reloj.set_now(dt.datetime(2026, 11, 16, 21, 0))
        OS.proc, OS.title = proc, title
        open_daw(app)
        step(app, 25 * 60)
        close_daw(app)
        assert app.data["proyectos"][proj]["sesiones"] == 1
        if reinicio:
            app.save_conf()
            cur = make_app()
        else:
            cur = app
        try:
            reloj.set_now(dt.datetime(2026, 11, 17, 10, 30))
            OS.running = True
            open_daw(cur)
            step(cur, 15 * 60)
            assert cur.project_name() == proj
            close_daw(cur)
            r = cur.data["proyectos"][proj]
            assert r["segundos"] == pytest.approx(40 * 60, abs=6)
            assert r["sesiones"] == 2
            assert r["dias"]["2026-11-16"] == pytest.approx(25 * 60, abs=4)
            assert r["dias"]["2026-11-17"] == pytest.approx(15 * 60, abs=4)
            assert r["daw"] == daw
            assert r["ultima"].startswith("2026-11-17T10:")
            assert len(cur.data["sesiones"]) == 2
            v = cur.project_values(proj)
            assert v["hoy"] == pytest.approx(15 * 60, abs=4)
            assert v["semana"] == pytest.approx(40 * 60, abs=6)
            disk = L.load_json(L.DATA_FILE)["proyectos"][proj]       # y quedó en el disco
            assert disk["segundos"] == pytest.approx(r["segundos"], abs=1)
        finally:
            if cur is not app:
                cur.root.destroy()
    finally:
        reloj.restore()


SETS = ["CRAZY SYNTHS", "Westing Time With U", "Orginal Mix", "Tahelly"]


@pytest.mark.parametrize("seed", range(12))
def test_jornada_saltando_entre_sets(fresh, seed):
    """Abro y cierro sets al azar durante el día: cada minuto cae en su proyecto, la lista de
    Proyectos muestra lo mismo que los datos y todo sobrevive a reiniciar el timer."""
    import random
    rnd = random.Random(seed)
    app = fresh
    want = {}
    open_daw(app)
    for _ in range(14):
        s = rnd.choice(SETS)
        OS.title = f"{s}  [{s} Project] - Ableton Live 12 Suite"
        app._title_t = -1e9
        step(app, 0.5)
        secs = rnd.choice([60, 120, 300, 900, 1500])
        step(app, secs)
        want[s] = want.get(s, 0) + secs + 0.5
    close_daw(app)
    for s, secs in want.items():
        assert app.data["proyectos"][s]["segundos"] == pytest.approx(secs, abs=8), s
    app.open_projects()
    w = app.projects_win
    app.root.update()
    assert set(want) <= set(w._row_labels)
    w.destroy()
    b = make_app()
    try:
        for s, secs in want.items():
            assert b.data["proyectos"][s]["segundos"] == pytest.approx(secs, abs=8)
    finally:
        b.root.destroy()


@pytest.mark.parametrize("modo", ["elegido_a_mano", "renombrado", "unido"])
def test_proyecto_creado_a_mano_y_retomado(fresh, modo):
    app = fresh
    app.conf["proyecto_auto"] = False
    app.set_project("Idea Nueva", auto=False)
    open_daw(app)
    step(app, 600)
    if modo == "renombrado":
        app.rename_project("Idea Nueva", "Orginal Mix")
        name = "Orginal Mix"
    elif modo == "unido":
        app.project_rec("Orginal Mix")["segundos"] = 300.0
        app.rename_project("Idea Nueva", "Orginal Mix")
        name = "Orginal Mix"
    else:
        name = "Idea Nueva"
    step(app, 300)
    close_daw(app)
    app.save_conf()
    b = make_app()
    try:
        assert b.project_name() == name
        OS.running = True
        open_daw(b)
        step(b, 120)
        extra = 300 if modo == "unido" else 0
        assert b.data["proyectos"][name]["segundos"] == pytest.approx(1020 + extra, abs=6)
        assert "Idea Nueva" not in b.data["proyectos"] or modo == "elegido_a_mano"
    finally:
        b.root.destroy()


# ============================================================ 3. jornada con breaks de verdad
@pytest.mark.parametrize("vista", VISTAS)
@pytest.mark.parametrize("brk", [5, 10])
@pytest.mark.parametrize("trabajo", [25, 50, 90])
def test_jornada_con_break(fresh, trabajo, brk, vista):
    app = fresh
    app.conf["autonomo"].update(trabajo_min=trabajo, break_min=brk, max_diario_h=0)
    setup(app, "gaux", vista, "horizontal")
    open_daw(app)
    step(app, trabajo * 60 + 5)
    assert app.lvl == 2, "toca descansar"
    sano(app, "aviso")
    before = app.session
    app.start_break()
    step(app, brk * 60 + 2)                    # descanso completo: el reloj no avanza
    assert app.state == "break"
    assert app.session == pytest.approx(before, abs=0.5)
    sano(app, "en break")
    app.resume()
    step(app, 5)
    assert app.lvl == 0 and app.streak < 10, "después del break la racha empieza de cero"
    assert app.session == pytest.approx(before + 5, abs=0.6)
    for _ in range(4):
        app.render_frame(force=True)
    assert not app.brk_items or all(app.cv.itemcget(i, "state") == "hidden"
                                    for i in app.brk_items)
    sano(app, "de vuelta")


@pytest.mark.parametrize("vista", VISTAS)
def test_break_cortado_no_reinicia_la_racha(fresh, vista):
    app = fresh
    app.conf["autonomo"].update(trabajo_min=50, break_min=10, max_diario_h=0)
    setup(app, "noche", vista, "horizontal")
    open_daw(app)
    step(app, 50 * 60 + 5)
    app.start_break()
    step(app, 60)
    app.resume()
    step(app, 2)
    assert app.lvl == 2, "un break de 1 minuto no cuenta como descanso"
    sano(app)


# ============================================================ 4. animaciones de cada estilo
@pytest.mark.parametrize("tema", TEMAS)
@pytest.mark.parametrize("orient", ORIENT)
@pytest.mark.parametrize("vista", VISTAS)
def test_dia_completo_de_animaciones(fresh, vista, orient, tema):
    """Abrir el DAW (bienvenida), cambios de minuto y de hora (glitch), meta cumplida, aviso de
    BREAK, pausa, volver y cerrar el DAW (tarjeta): cada momento se ve bien y nada se acumula."""
    app = fresh
    app.conf["metas"]["diaria"].update(activa=True, segundos=3600)
    app.conf["autonomo"].update(trabajo_min=50, max_diario_h=0)
    setup(app, tema, vista, orient)
    app.render_frame(force=True)
    base = len(app.cv.find_all())

    def frames(n, donde):
        for _ in range(n):
            app.phase += 0.033
            app.render_frame()
        sano(app, donde)

    open_daw(app)
    frames(40, "bienvenida")
    step(app, 59)
    step(app, 2)                                      # cambia el minuto
    frames(10, "glitch minuto")
    step(app, 3540)                                   # 1 h: cambia la hora y se cumple la meta
    frames(30, "hora + meta")
    if vista == "completa":                           # las otras vistas no muestran metas
        assert app.reached.get("diaria")
    assert app.lvl == 2
    frames(60, "aviso de break")
    app.toggle_pause()
    step(app, 3)
    frames(20, "pausa")
    app.toggle_pause()
    step(app, 3)
    frames(20, "de vuelta")
    close_daw(app)
    frames(40, "DAW cerrado")
    if app.card is not None:
        app.card.update_idletasks()
        cw = app.card.winfo_reqwidth()
        for c in app.card.winfo_children():
            assert c.winfo_reqwidth() <= cw + 1
        app.card.destroy()
        app.card = None
    for _ in range(300):
        app.phase += 0.033
        app.render_frame()
    assert len(app.cv.find_all()) - base <= 30, "el lienzo no acumula elementos"


@pytest.mark.parametrize("tema", ["gaux", "personal"])
@pytest.mark.parametrize("anim", [True, False])
@pytest.mark.parametrize("efectos", [True, False])
def test_animaciones_y_efectos_apagados(fresh, tema, anim, efectos):
    app = fresh
    app.conf["animaciones"] = anim
    app.conf["personal"]["efectos"] = efectos
    setup(app, tema, "completa", "horizontal")
    open_daw(app)
    for i in range(200):
        if i % 40 == 0:
            step(app, 61)
        app.phase += 0.033
        app.render_frame()
    sano(app)


# ============================================================ 5. cada DAW en cada vista
@pytest.mark.parametrize("vista", VISTAS)
@pytest.mark.parametrize("proc,title,proj,daw", DAW_CASOS, ids=IDS)
def test_cada_daw_en_cada_vista(fresh, proc, title, proj, daw, vista):
    app = fresh
    setup(app, "gaux", vista, "horizontal")
    OS.proc, OS.title = proc, title
    open_daw(app)
    step(app, 300)
    assert app.state == "sesion" and app.project_name() == proj
    sano(app, "contando")
    OS.front = "Finder"                                  # miro otra app
    step(app, 1, 3)
    held = app.session
    step(app, 120)
    assert app.state == "fondo" and app.session == pytest.approx(held)
    sano(app, "DAW atrás")
    OS.front = "live"
    step(app, 1, 2)
    step(app, 60)
    assert app.state == "sesion" and app.session > held + 55
    OS.idle = 10_000                                     # me levanto de la silla
    step(app, 1, 3)
    assert app.state == "inactivo"
    sano(app, "inactivo")
    OS.idle = 0
    step(app, 1, 2)
    assert app.state == "sesion"
    assert app.data["proyectos"][proj]["daw"] == daw


# ============================================================ 6. analizador con un tema real
def track(secs, sr, seed=0):
    """Una mezcla de tech house: kick a 124 BPM, bajo, hats y un pad."""
    rng = np.random.default_rng(seed)
    n = int(secs * sr)
    t = np.arange(n) / sr
    beat = 60 / 124
    ph = (t % beat)
    kick = np.sin(2 * np.pi * (45 + 90 * np.exp(-ph * 30)) * ph) * np.exp(-ph * 9)
    bass = 0.45 * np.sign(np.sin(2 * np.pi * 55 * t)) * (((t + beat / 2) % beat) < beat / 2)
    bass = np.convolve(bass, np.ones(24) / 24, "same")
    hat = rng.standard_normal(n) * np.exp(-(((t + beat / 2) % beat) * 60))
    hat = np.diff(hat, prepend=0) * 0.25
    pad = 0.12 * (np.sin(2 * np.pi * 220 * t) + np.sin(2 * np.pi * 277.2 * t)
                  + np.sin(2 * np.pi * 329.6 * t))
    x = kick + bass + hat + pad
    st = np.stack([x + 0.03 * np.roll(pad, 17), x - 0.03 * np.roll(pad, 17)], 1)
    return st.astype(np.float64)


def loud(x, sr):
    Lo = G.Loudness(sr)
    for i in range(0, len(x) - Lo.n + 1, Lo.n):
        Lo.push(x[i:i + Lo.n].astype(np.float32))
    return Lo


@pytest.mark.parametrize("sr", [44100, 48000, 96000])
@pytest.mark.parametrize("target", [-6, -8, -10, -14, -16, -23])
def test_lufs_de_un_tema_a_cada_nivel(sr, target):
    """Subir o bajar el master N dB mueve el integrado exactamente N LU, a cualquier nivel."""
    x = track(8, sr)
    ref = loud(x, sr).integrated()
    g = 10 ** ((target - ref) / 20)
    Lo = loud(x * g, sr)
    assert Lo.integrated() == pytest.approx(target, abs=0.1)
    assert Lo.short_term() == pytest.approx(target, abs=1.5)
    peak = 20 * math.log10(np.max(np.abs(x * g)))
    assert Lo.tp_max >= peak - 0.05, "el true peak nunca marca menos que el pico de muestra"
    assert Lo.tp_max <= peak + 3.5


@pytest.mark.parametrize("sr", [44100, 48000])
@pytest.mark.parametrize("ceil", [-1.0, -0.3, -0.1])
def test_true_peak_de_un_master_limitado(sr, ceil):
    """Master recortado al techo del limitador: true peak cerca del techo (y avisa si pasa 0)."""
    x = track(4, sr)
    x = x / np.max(np.abs(x)) * 10 ** (ceil / 20)
    Lo = loud(x, sr)
    assert ceil - 0.05 <= Lo.tp_max <= ceil + 1.0


@pytest.mark.parametrize("tema", TEMAS)
@pytest.mark.parametrize("size", [(900, 172), (1440, 200), (1600, 132), (700, 110), (460, 66),
                                  (1200, 40)], ids=lambda s: f"{s[0]}x{s[1]}")
def test_panel_con_un_tema_sonando(panel, tema, size):
    """El tema sonando en cada estilo y tamaño: espectro con más graves que agudos, onda,
    medidores y estéreo dentro de su caja y sin errores."""
    rebuild(panel, *size, [k for k, _ in G.MODULES], tema)
    prepare(panel)
    play(panel, track(1.2, 48000).astype(np.float32) * 0.5)
    cv = panel.cv
    for k, (x0, y0, w, h) in panel.rects.items():
        assert w > 0 and h > 0 and panel.PAD + x0 + w <= panel.W + 1, (k, panel.rects)
    if "spec" in panel.rects and getattr(panel, "spec_yv", None) is not None:
        X, Y, w, sh = panel.spec_geom
        yv = np.asarray(panel.spec_yv)
        assert np.all(np.isfinite(yv))
        assert yv.min() >= Y - 2 and yv.max() <= Y + sh + 2, "la curva no se sale de su caja"
        f = np.asarray(panel.fpts)
        low = yv[(f > 40) & (f < 150)].mean()
        high = yv[(f > 8000) & (f < 16000)].mean()
        assert low < high, "los graves del kick y el bajo se ven más altos que los agudos"
    for i in cv.find_all():
        if cv.type(i) == "text" and cv.itemcget(i, "state") != "hidden" and \
                cv.itemcget(i, "text").strip():
            b = cv.bbox(i)
            assert b[0] >= -1 and b[2] <= panel.W + 1 and b[1] >= -1 and b[3] <= panel.H + 1
    assert not TK_ERRORS


@pytest.mark.parametrize("tema", ["gaux", "noche", "personal"])
def test_espectrograma_marca_el_kick(panel, tema):
    """En el espectrograma se ve el kick (graves) pegando a tiempo y los hats arriba."""
    rebuild(panel, 1200, 300, ["spec"], tema)
    prepare(panel)
    from test_analizador import pixel
    bg = tuple(int(c) for c in panel.sg_lut[0])
    play(panel, track(2.0, 48000).astype(np.float32) * 0.5)
    sg = panel.sgram
    rows = np.log10(np.asarray(panel.frows))
    r_kick = int(np.argmin(np.abs(rows - math.log10(60))))
    lit = sum(pixel(sg, (sg.wp - 1 - c) % sg.w, r_kick) != bg for c in range(1, 60))
    assert lit >= 20, "el kick deja marca en los graves"


@pytest.mark.parametrize("dw,dh", [(500, 60), (-500, -100), (250, -60), (-200, 120),
                                   (3000, 3000), (-3000, -3000)])
def test_redimensionar_el_panel_con_musica(panel, dw, dh):
    rebuild(panel, 900, 172, [k for k, _ in G.MODULES], "gaux")
    panel.win.update_idletasks()
    x0, y0 = panel.win.winfo_x(), panel.win.winfo_y()
    ev = type("E", (), {"x_root": x0 + panel.W - 3, "y_root": y0 + panel.H - 3,
                        "x": panel.W - 3, "y": panel.H - 3})()
    panel.on_press(ev)
    for i in range(1, 9):                            # arrastre en varios pasos
        e2 = type("E", (), {"x_root": ev.x_root + dw * i / 8, "y_root": ev.y_root + dh * i / 8,
                            "x": 0, "y": 0})()
        panel.on_drag(e2)
    panel.on_release(e2)
    a = panel.app.conf["analizador"]
    sw, sh = panel.win.winfo_screenwidth(), panel.win.winfo_screenheight()
    assert 200 <= a["w"] <= sw + 1 and 24 <= a["h"] <= sh + 1
    prepare(panel)
    play(panel, track(0.6, 48000).astype(np.float32) * 0.5)
    for k, (x0_, y0_, w, h) in panel.rects.items():
        assert panel.PAD + x0_ + w <= panel.W + 1, (k, panel.rects)
    assert not TK_ERRORS
