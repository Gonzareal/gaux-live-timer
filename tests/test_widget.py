"""El widget: todas las vistas, estilos, tamaños, Top Live y el aviso de descanso."""
import time
import types

import pytest

import live_timer as L
from conftest import OS, canvas_texts, drain, open_daw, step, visible_bbox_ok, win_xy

TEMAS = list(L.TEMAS)
VISTAS = ["completa", "compacta", "mini"]
ORIENT = ["horizontal", "vertical"]


def setup(app, tema, vista, orient, escala=None, modo="autonomo"):
    app.conf["tema"] = tema
    app.conf["vista"] = vista
    app.conf["orientacion"] = orient
    app.conf["modo"] = modo
    if escala is not None:
        app.conf["escala"] = {app.pos_key(): escala}
    app.apply_conf()
    drain(app)
    app.root.update_idletasks()


def text_overlaps(app):
    """Textos visibles que se pisan (sin contar las copias de brillo del reloj)."""
    cv = app.cv
    skip = set()
    for d in app.digits:
        skip.update(it for it, _, _ in d["glows"])
    if app.splash:
        skip.add(app.splash)                  # bienvenida: tapa todo a propósito por 2 s
    skip.update(p["it"] for p in getattr(app, "particles", []))   # chispas de meta cumplida
    digit_main = {d["main"] for d in app.digits}
    boxes = []
    for i in cv.find_all():
        if i in skip or cv.type(i) != "text" or cv.itemcget(i, "state") == "hidden":
            continue
        t = cv.itemcget(i, "text").strip()
        if not t:
            continue
        b = cv.bbox(i)
        if b:
            boxes.append((i, t, b))
    bad = []
    for n, (i, t, b) in enumerate(boxes):
        for j, u, c in boxes[n + 1:]:
            if i in digit_main and j in digit_main:
                continue
            ix = min(b[2], c[2]) - max(b[0], c[0])
            iy = min(b[3], c[3]) - max(b[1], c[1])
            if ix > 3 and iy > 3:
                bad.append((t, u, b, c, cv.itemcget(i, "font"), cv.itemcget(j, "font")))
    return bad


@pytest.mark.parametrize("tema", TEMAS)
@pytest.mark.parametrize("vista", VISTAS)
@pytest.mark.parametrize("orient", ORIENT)
@pytest.mark.parametrize("escala", ["min", 1.0, "max"])
def test_vista_dentro_de_su_ventana(fresh, tema, vista, orient, escala):
    app = fresh
    lo, hi = L.ESCALA_LIM["mini" if vista == "mini" else "otra"]
    k = lo if escala == "min" else hi if escala == "max" else escala
    setup(app, tema, vista, orient, k)
    open_daw(app)
    step(app, 5)
    app.render_frame(force=True)
    assert app.W > 10 and app.H > 10
    assert visible_bbox_ok(app) == []
    assert text_overlaps(app) == []
    geo = app.root.geometry()
    assert geo.startswith(f"{app.W}x{app.H}")


@pytest.mark.parametrize("tema", TEMAS)
@pytest.mark.parametrize("vista", VISTAS)
@pytest.mark.parametrize("orient", ORIENT)
def test_reloj_muestra_la_sesion(fresh, tema, vista, orient):
    app = fresh
    setup(app, tema, vista, orient)
    open_daw(app)
    step(app, 3725)
    shown = "".join(d["ch"] for d in app.digits)
    assert shown.replace(":", "").startswith("0102") or shown.startswith("01:02")


@pytest.mark.parametrize("tema", TEMAS)
@pytest.mark.parametrize("vista", VISTAS)
@pytest.mark.parametrize("orient", ORIENT)
def test_aviso_de_descanso_visible(fresh, tema, vista, orient, monkeypatch):
    app = fresh
    setup(app, tema, vista, orient)
    open_daw(app)
    step(app, 51 * 60)
    assert app.lvl == 2
    cv = app.cv
    before = [cv.itemcget(d["main"], "state") or "normal" for d in app.digits]
    monkeypatch.setattr(L.time, "monotonic", lambda: 1000.5)     # fase "cartel"
    app._break_flash(True)
    cv = app.cv
    assert app.brk_items, "debe dibujarse el cartel de descanso"
    for it in app.brk_items:
        assert cv.itemcget(it, "state") == "normal"
    assert all(cv.itemcget(d["main"], "state") == "hidden" for d in app.digits)
    tx = app.brk_items[1]
    assert cv.itemcget(tx, "text").replace("\n", "") in ("BREAK", "RECHARGE", "BRK")
    b = cv.bbox(tx)
    assert b[0] >= -2 and b[1] >= -2 and b[2] <= app.W + 2 and b[3] <= app.H + 2
    monkeypatch.setattr(L.time, "monotonic", lambda: 1003.0)     # fase "reloj"
    app._break_flash(True)
    # el reloj vuelve tal cual (en vertical los ':' siguen ocultos)
    assert [cv.itemcget(d["main"], "state") or "normal" for d in app.digits] == before
    assert all(cv.itemcget(it, "state") == "hidden" for it in app.brk_items)


@pytest.mark.parametrize("vista", VISTAS)
@pytest.mark.parametrize("orient", ORIENT)
def test_sin_aviso_en_modo_normal(fresh, vista, orient):
    app = fresh
    setup(app, "gaux", vista, orient, modo="normal")
    open_daw(app)
    step(app, 3 * 3600)
    assert app.lvl <= 0
    app.render_frame(force=True)
    assert not app.brk_items or all(app.cv.itemcget(i, "state") == "hidden"
                                    for i in app.brk_items)


@pytest.mark.parametrize("trabajo", [10, 25, 50, 90, 240])
@pytest.mark.parametrize("frac,lvl", [(0.5, 0), (0.79, 0), (0.81, 1), (0.99, 1), (1.0, 2),
                                      (1.5, 2)])
def test_niveles_de_descanso(fresh, trabajo, frac, lvl):
    app = fresh
    app.conf["autonomo"]["trabajo_min"] = trabajo
    app.conf["autonomo"]["max_diario_h"] = 0
    open_daw(app)
    step(app, trabajo * 60 * frac)
    assert app.lvl == lvl, (trabajo, frac, app.auto_msg)


@pytest.mark.parametrize("brk", [1, 5, 15])
def test_alejarse_el_tiempo_del_descanso_reinicia_la_racha(fresh, brk):
    app = fresh
    app.conf["autonomo"]["break_min"] = brk
    open_daw(app)
    step(app, 45 * 60)
    OS.front = "other"
    step(app, 1)
    step(app, 1)
    step(app, brk * 60 + 1)
    OS.front = "live"
    step(app, 1)
    step(app, 1)
    assert app.streak < 10


def test_alejarse_poco_no_reinicia_la_racha(fresh):
    app = fresh
    open_daw(app)
    step(app, 45 * 60)
    OS.front = "other"
    step(app, 1, 3)
    step(app, 60)
    OS.front = "live"
    step(app, 1, 2)
    assert app.streak >= 45 * 60


@pytest.mark.parametrize("brand", [True, False])
def test_tomar_break_y_volver(fresh, brand):
    app = fresh
    setup(app, "gaux" if brand else "noche", "completa", "horizontal")
    open_daw(app)
    step(app, 51 * 60)
    assert app.chip_label == "break"
    app.chip_action()
    assert app.manual == "break"
    before = app.session
    step(app, 60, 2)
    assert app.session == pytest.approx(before)
    assert app.chip_label == "volver"
    step(app, 4 * 60)
    assert app.lvl == -2 and app.chip_label == "reanudar"
    app.chip_action()
    assert app.manual is None
    step(app, 1)
    assert app.streak < 5


@pytest.mark.parametrize("horas", [1, 4, 8])
def test_aviso_maximo_diario(fresh, horas):
    app = fresh
    app.conf["autonomo"]["max_diario_h"] = horas
    app.conf["autonomo"]["trabajo_min"] = 240
    open_daw(app)
    for _ in range(horas * 4):              # trabajando con pausas cortas
        step(app, 15 * 60)
    assert app.lvl == 2
    assert "hoy" in app.auto_msg.lower() or "HOY" in app.auto_msg


# ---------------------------------------------------------------- tamaño ajustable
class Ev:
    def __init__(self, x, y):
        self.x_root, self.y_root = x, y
        self.x = self.y = 0


@pytest.mark.parametrize("vista", VISTAS)
@pytest.mark.parametrize("orient", ORIENT)
@pytest.mark.parametrize("dx,expect", [(400, "max"), (-400, "min"), (60, "up"), (-30, "down")])
def test_cambiar_tamano_arrastrando(fresh, vista, orient, dx, expect):
    app = fresh
    setup(app, "gaux", vista, orient)
    key = app.pos_key()
    lo, hi = L.ESCALA_LIM["mini" if vista == "mini" else "otra"]
    w0 = app.W
    app.resize_start(Ev(500, 500))
    for i in range(1, 11):                  # arrastre rápido (más de 30 eventos por segundo)
        app.resize_drag(Ev(500 + dx * i / 10, 500 + dx * i / 10))
    app.resize_end()
    k = app.scale_for(key)
    if expect == "max":
        assert k == pytest.approx(hi)
    elif expect == "min":
        assert k == pytest.approx(lo)
    elif expect == "up":
        assert k > 1.0 and app.W > w0
    else:
        assert k < 1.0 and app.W < w0
    assert app.conf["escala"][key] == pytest.approx(k)
    assert visible_bbox_ok(app) == []
    saved = L.load_json(L.CONF_FILE)
    assert saved["escala"][key] == pytest.approx(k)
    assert key in saved["pos"]


@pytest.mark.parametrize("vista", VISTAS)
def test_restablecer_tamano(fresh, vista):
    app = fresh
    setup(app, "noche", vista, "horizontal", 1.8 if vista != "mini" else 2.0)
    big = app.W
    app.reset_scale()
    assert app.scale_for(app.pos_key()) == 1.0 and app.W < big


@pytest.mark.parametrize("bad", ["x", None, [], {}, -5, 99, float("nan"), "1.5"])
def test_escala_guardada_rara(fresh, bad):
    app = fresh
    app.conf["escala"] = {"completa": bad}
    k = app.scale_for("completa")
    lo, hi = L.ESCALA_LIM["otra"]
    assert lo <= k <= hi
    app.apply_conf()
    assert visible_bbox_ok(app) == []


@pytest.mark.parametrize("vista", VISTAS)
@pytest.mark.parametrize("orient", ORIENT)
def test_cada_vista_recuerda_su_tamano(fresh, vista, orient):
    app = fresh
    app.conf["escala"] = {"completa": 1.5, "compacta": 0.8, "mini": 2.0,
                          "completa_v": 1.2, "compacta_v": 1.7, "mini_v": 0.7}
    setup(app, "noche", vista, orient)
    assert app.k == pytest.approx(app.conf["escala"][app.pos_key()])


# ---------------------------------------------------------------- botones del widget
@pytest.mark.parametrize("vista", ["completa", "compacta"])
def test_minimizar_y_restaurar(fresh, vista):
    app = fresh
    setup(app, "gaux", vista, "horizontal")
    app.set_vista("mini")
    assert app.conf["vista"] == "mini" and app.conf["vista_previa"] == vista
    app.set_vista(app.conf["vista_previa"])
    assert app.conf["vista"] == vista


@pytest.mark.parametrize("tema", TEMAS)
@pytest.mark.parametrize("vista", VISTAS)
def test_clic_en_cada_boton(fresh, tema, vista):
    app = fresh
    setup(app, tema, vista, "horizontal")
    open_daw(app)
    step(app, 1)
    names = {h[4] for h in app.hit}
    assert "pp" in names
    for x1, y1, x2, y2, name in list(app.hit):
        assert 0 <= x1 < x2 <= app.W + 1 and 0 <= y1 < y2 <= app.H + 1, name
    # pausa / reanudar con el botón
    x1, y1, x2, y2, _ = next(h for h in app.hit if h[4] == "pp")
    ev = types.SimpleNamespace(x=(x1 + x2) / 2, y=(y1 + y2) / 2, x_root=0, y_root=0)
    app.on_press(ev)
    assert app.manual == "pausa"
    step(app, 30)
    assert app.session == pytest.approx(1, abs=0.1)
    x1, y1, x2, y2, _ = next(h for h in app.hit if h[4] == "pp")
    app.on_press(types.SimpleNamespace(x=(x1 + x2) / 2, y=(y1 + y2) / 2, x_root=0, y_root=0))
    assert app.manual is None


@pytest.mark.parametrize("vista", VISTAS)
def test_arrastrar_mueve_y_guarda(fresh, vista):
    app = fresh
    setup(app, "noche", vista, "horizontal")
    open_daw(app)
    step(app, 1)
    app._move(300, 300)
    app.root.update()
    x0, y0 = win_xy(app)
    # clic lejos de botones y bordes
    free = None
    for yy in range(4, int(app.H) - 8, 2):
        for xx in range(4, int(app.W) - 8, 3):
            if not app.hit_test(xx, yy) and not app.in_resize(xx, yy):
                free = (xx, yy)
                break
        if free:
            break
    assert free
    app.on_press(types.SimpleNamespace(x=free[0], y=free[1], x_root=x0 + free[0],
                                       y_root=y0 + free[1]))
    app.on_drag(types.SimpleNamespace(x=0, y=0, x_root=x0 + free[0] + 120,
                                      y_root=y0 + free[1] + 80))
    app.on_release(types.SimpleNamespace(x=0, y=0, x_root=x0 + free[0] + 120,
                                         y_root=y0 + free[1] + 80))
    assert win_xy(app) == (x0 + 120, y0 + 80)
    assert L.load_json(L.CONF_FILE)["pos"][app.pos_key()] == [x0 + 120, y0 + 80]


# ---------------------------------------------------------------- pantallas
SCREENS = {
    "una": [(0, 0, 1920, 1080, 0, 25, 1920, 1055)],
    "macbook": [(0, 0, 1512, 982, 0, 38, 1512, 944)],
    "dos_lado": [(0, 0, 1512, 982, 0, 38, 1512, 944), (1512, 0, 2560, 1440, 1512, 0, 2560, 1440)],
    "izquierda": [(0, 0, 1920, 1080, 0, 0, 1920, 1080), (-1280, 200, 1280, 800, -1280, 200, 1280, 800)],
    "arriba": [(0, 0, 1920, 1080, 0, 0, 1920, 1080), (0, -1440, 2560, 1440, 0, -1440, 2560, 1440)],
    "4k": [(0, 0, 3840, 2160, 0, 0, 3840, 2120)],
    "chica": [(0, 0, 1024, 600, 0, 0, 1024, 600)],
}


@pytest.mark.parametrize("scr", list(SCREENS))
@pytest.mark.parametrize("pos", [(-5000, -5000), (99999, 99999), (100, 100), (1700, 900),
                                 (-1000, 400), (500, -1000)])
def test_nunca_queda_fuera_de_pantalla(fresh, scr, pos):
    app = fresh
    OS.screens = SCREENS[scr]
    app.screen_list(fresh=True)
    x, y = app.clamp_rect(pos[0], pos[1], app.W, app.H)
    s = app.screen_for(x, y, app.W, app.H)
    assert s[0] <= x and x + app.W <= s[0] + s[2]
    assert s[1] <= y and y + app.H <= s[1] + s[3]


@pytest.mark.parametrize("scr", list(SCREENS))
def test_franja_top_live_en_cada_pantalla(fresh, scr):
    app = fresh
    OS.screens = SCREENS[scr]
    app.screen_list(fresh=True)
    s = SCREENS[scr][-1]
    t = app.dock_target((s[0], s[5], s[2], s[7]))
    assert t is not None
    x, y, w, _ = t
    assert y == s[5] and x >= s[4] and x + w <= s[4] + s[6]


def test_franja_top_live_ventana_angosta(fresh):
    OS.screens = SCREENS["una"]
    fresh.screen_list(fresh=True)
    assert fresh.dock_target((100, 100, 400, 800)) is None


# ---------------------------------------------------------------- Top Live
class FakeWin:
    def __init__(self, x, y, w, h, fs=False):
        self.rect = [x, y, w, h]
        self.fs = fs
        self.moves = 0

    def install(self, monkeypatch):
        monkeypatch.setattr(L, "live_main_window", lambda: (1, *self.rect))
        monkeypatch.setattr(L, "live_fullscreen", lambda wid: self.fs)

        def set_fs(wid, on):
            self.fs = on
        monkeypatch.setattr(L, "set_live_fullscreen", set_fs)

        def set_win(wid, x, y, w, h):
            self.moves += 1
            self.rect = [int(x), int(y), int(w), int(h)]
        monkeypatch.setattr(L, "set_live_window", set_win)
        monkeypatch.setattr(L.time, "sleep", lambda s: None)


@pytest.mark.parametrize("tema", TEMAS)
@pytest.mark.parametrize("pct", [50, 75, 100])
def test_top_live_activar_y_desactivar(fresh, monkeypatch, tema, pct):
    app = fresh
    OS.screens = SCREENS["una"]
    app.screen_list(fresh=True)
    fw = FakeWin(0, 25, 1920, 1055)
    fw.install(monkeypatch)
    app.conf["tema"] = tema
    app.conf["top_escala"] = pct
    app.apply_conf()
    open_daw(app)
    app.enter_top_mode()
    drain(app)
    assert app.conf["top_mode"]
    assert fw.rect[1] == 25 + app.top_h, "el DAW baja justo debajo de la franja"
    assert app.H <= app.top_h + 1
    assert win_xy(app)[1] == 25
    assert visible_bbox_ok(app) == []
    assert app.analyzer is not None and app.conf["analizador"]["activo"]
    a = app.conf["analizador"]
    assert a["x"] >= app.W and a["x"] + a["w"] <= 1920 + 1
    app.exit_top_mode()
    drain(app)
    assert not app.conf.get("top_mode")
    assert fw.rect == [0, 25, 1920, 1055], "el DAW vuelve a su tamaño"


@pytest.mark.parametrize("pct", [50, 60, 70, 80, 90, 100])
def test_top_live_cambiar_alto(fresh, monkeypatch, pct):
    app = fresh
    OS.screens = SCREENS["macbook"]
    app.screen_list(fresh=True)
    fw = FakeWin(0, 38, 1512, 944)
    fw.install(monkeypatch)
    open_daw(app)
    app.enter_top_mode()
    app.set_top_scale(pct)
    drain(app)
    assert app.top_h == round(L.TOP_H * pct / 100)
    assert fw.rect[1] == 38 + app.top_h
    assert app.H <= app.top_h + 1
    assert visible_bbox_ok(app) == []
    app.exit_top_mode()


def test_top_live_desde_pantalla_completa(fresh, monkeypatch):
    app = fresh
    OS.screens = SCREENS["macbook"]
    app.screen_list(fresh=True)
    fw = FakeWin(0, 0, 1512, 982, fs=True)
    fw.install(monkeypatch)
    open_daw(app)
    app.enter_top_mode()
    assert not fw.fs and app.conf["top_mode"]
    app.exit_top_mode()
    assert fw.fs, "al salir, el DAW vuelve a pantalla completa"


def test_top_live_ventana_muy_chica_avisa(fresh, monkeypatch):
    app = fresh
    fw = FakeWin(100, 100, 900, 300)
    fw.install(monkeypatch)
    open_daw(app)
    notes = []
    monkeypatch.setattr(app, "notice", lambda t, x: notes.append(x))
    app.enter_top_mode()
    assert not app.conf.get("top_mode") and notes


def test_top_live_sin_daw_avisa(fresh, monkeypatch):
    app = fresh

    def boom():
        raise L.LiveWindowError("No encontré la ventana")
    monkeypatch.setattr(L, "live_main_window", boom)
    notes = []
    monkeypatch.setattr(app, "notice", lambda t, x: notes.append(x))
    app.enter_top_mode()
    assert not app.conf.get("top_mode") and notes


@pytest.mark.parametrize("w", [200, 300, 400, 600])
@pytest.mark.parametrize("h", [24, 32, 38])
def test_pantalla_completa_franja_de_la_camara(fresh, monkeypatch, w, h):
    """MacBook con notch: en pantalla completa el timer va a la franja junto a la cámara."""
    app = fresh
    fw = FakeWin(0, 38, 1512, 944)
    fw.install(monkeypatch)
    OS.screens = SCREENS["macbook"]
    app.screen_list(fresh=True)
    open_daw(app)
    app.enter_top_mode()
    app.fs_band = {"left": (0, 0, w, h), "right": (1512 - w, 0, w, h)}
    app.apply_conf()
    drain(app)
    assert app.H <= h
    x, _ = win_xy(app)
    assert x >= 0 and x + app.W <= w + 2, (app.W, w)
    assert visible_bbox_ok(app) == []
    app.fs_band = None
    app.exit_top_mode()


@pytest.mark.parametrize("vista", VISTAS)
def test_top_live_bloquea_vista_y_orientacion(fresh, monkeypatch, vista):
    app = fresh
    fw = FakeWin(0, 25, 1920, 1055)
    fw.install(monkeypatch)
    OS.screens = SCREENS["una"]
    app.screen_list(fresh=True)
    open_daw(app)
    app.enter_top_mode()
    app.set_vista(vista)
    app.set_orient("vertical")
    assert app.conf["orientacion"] != "vertical" or not app.vertical
    assert not app.in_resize(app.W - 1, app.H - 1)
    app.exit_top_mode()


# ---------------------------------------------------------------- visibilidad
def test_solo_se_ve_con_el_daw_al_frente(fresh):
    app = fresh
    open_daw(app)
    step(app, 1)
    assert app.visible
    OS.front = "other"
    step(app, 1)
    step(app, 1)
    assert not app.visible
    OS.front = "live"
    step(app, 1)
    assert app.visible


def test_un_parpadeo_de_otra_app_no_lo_oculta(fresh):
    app = fresh
    open_daw(app)
    step(app, 1)
    OS.front = "other"
    step(app, 1)
    assert app.visible
    OS.front = "live"
    step(app, 1)
    assert app.visible


def test_tocar_el_widget_no_pausa(fresh):
    app = fresh
    open_daw(app)
    step(app, 10)
    OS.front = "self"
    step(app, 10)
    assert app.counting and app.session == pytest.approx(20, abs=0.5)


def test_dialogo_del_daw_oculta(fresh):
    app = fresh
    open_daw(app)
    step(app, 1)
    app.ui_busy = True
    app.watch_front(reschedule=False)
    assert not app.visible


def test_sin_daw_abierto_no_se_ve(fresh):
    app = fresh
    OS.running = False
    step(app, 1)
    app.last_proc_check = -1e9
    step(app, 1)
    assert not app.live_open and not app.visible


@pytest.mark.parametrize("tema", TEMAS)
def test_textos_con_tildes(fresh, tema):
    app = fresh
    setup(app, tema, "completa", "horizontal")
    app.set_project("Canción ñandú ¿qué? ¡sí! 🎧")
    open_daw(app)
    step(app, 1)
    assert any("Canción" in t or "CANCIÓN" in t for t in canvas_texts(app))
    assert visible_bbox_ok(app) == []


@pytest.mark.parametrize("n", [1, 15, 30, 60])
@pytest.mark.parametrize("vista", ["completa", "compacta"])
def test_nombre_de_proyecto_largo_se_recorta(fresh, n, vista):
    app = fresh
    setup(app, "noche", vista, "horizontal")
    app.set_project("W" * n)
    open_daw(app)
    step(app, 1)
    assert visible_bbox_ok(app) == []
    assert text_overlaps(app) == []


def test_animaciones_apagadas(fresh):
    app = fresh
    app.conf["animaciones"] = False
    app.apply_conf()
    open_daw(app)
    step(app, 60)
    for _ in range(5):
        app.render_frame()
    assert visible_bbox_ok(app) == []


@pytest.mark.parametrize("tema", TEMAS)
def test_muchos_cuadros_sin_errores(fresh, tema):
    app = fresh
    setup(app, tema, "completa", "horizontal")
    app.conf["metas"]["diaria"]["segundos"] = 120
    open_daw(app)
    for i in range(40):
        step(app, 5)
        app.phase += 0.05
        app.render_frame()
    assert app.particles is not None
