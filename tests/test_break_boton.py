"""Botón de break: visible y clicable en TODAS las vistas y tamaños (también Top Live y con
el analizador abierto), el break solo empieza con el botón, cuenta hacia atrás, NO vuelve
solo al terminar (espera el botón Volver) y la sesión guarda las dos medidas: el tiempo
total (todo, sin excepción) y el trabajo real, con breaks y ausencias.

Los clics son eventos de Tk de verdad (event_generate sobre el lienzo, con su propio
tiempo para que Tk no los tome como doble clic), igual que un clic del mouse."""
import csv
import os

import pytest

import live_timer as L
from conftest import OS, drain, open_daw, step, visible_bbox_ok
from test_tamanos import text_overlaps
from test_widget import SCREENS, FakeWin, setup

VISTAS = ["completa", "compacta", "mini"]
ORIENT = ["horizontal", "vertical"]
TEMAS = list(L.TEMAS)
_T = [10_000_000]


def click(app, x, y, moved=0):
    """Un clic real sobre el lienzo (apretar y soltar)."""
    _T[0] += 5000
    cv = app.cv
    app.root.update()
    assert app.root.winfo_viewable(), "el timer debe estar a la vista"
    cv.event_generate("<Motion>", x=int(x), y=int(y), time=_T[0] - 100)
    cv.event_generate("<ButtonPress-1>", x=int(x), y=int(y), time=_T[0])
    cv.event_generate("<ButtonRelease-1>", x=int(x + moved), y=int(y), time=_T[0] + 80)
    app.root.update()
    drain(app)


def hitbox(app, name):
    boxes = [(x1, y1, x2, y2) for x1, y1, x2, y2, n in app.hit if n == name]
    assert boxes, f"falta el botón {name}"
    return boxes[-1]


def click_brk(app):
    x1, y1, x2, y2 = hitbox(app, "brk")
    click(app, (x1 + x2) / 2, (y1 + y2) / 2)


def clock(app):
    return "".join(d["ch"] for d in app.digits)


def check_button(app):
    """El botón está entero dentro del widget, se ve y no se mete en otro botón."""
    x1, y1, x2, y2 = hitbox(app, "brk")
    assert x1 >= -1 and y1 >= -1 and x2 <= app.W + 1 and y2 <= app.H + 1, (x1, y1, x2, y2, app.W, app.H)
    assert x2 - x1 >= 10 and y2 - y1 >= 10, "zona de clic muy chica"
    items = app.cv.find_withtag("btn_brk")
    assert items, "el botón no está dibujado"
    vis = [i for i in items if app.cv.itemcget(i, "state") != "hidden"]
    assert vis
    b = app.cv.bbox(*vis)
    assert b[0] >= -1 and b[1] >= -1 and b[2] <= app.W + 1 and b[3] <= app.H + 1
    # el dibujo queda dentro de su zona de clic (un poco de aire para el anillo)
    assert b[0] >= x1 - 4 and b[2] <= x2 + 4 and b[1] >= y1 - 4 and b[3] <= y2 + 4
    # la taza tiene tamaño de verdad (no un punto)
    assert b[2] - b[0] >= 6 and b[3] - b[1] >= 6
    # el centro de su zona de clic es suyo: ningún otro botón lo tapa
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    assert app.hit_test(cx, cy) == "brk"
    for ox1, oy1, ox2, oy2, n in app.hit:
        if n in ("pp", "cfg", "min", "max"):
            ix = min(x2, ox2) - max(x1, ox1)
            iy = min(y2, oy2) - max(y1, oy1)
            assert not (ix > 2 and iy > 2), f"el botón de break pisa a {n}"
    # ningún texto (título, estado, reloj…) se mete en la taza
    ghosts = {g[0] if isinstance(g, (tuple, list)) else g for g in getattr(app, "ghosts", [])}
    for i in app.cv.find_all():
        if (app.cv.type(i) != "text" or i in ghosts or i in (app.brk_items or [])
                or app.cv.itemcget(i, "state") == "hidden"
                or not app.cv.itemcget(i, "text").strip() or i == app.splash):
            continue
        t = app.cv.bbox(i)
        ix = min(b[2], t[2]) - max(b[0], t[0])
        iy = min(b[3], t[3]) - max(b[1], t[1])
        assert not (ix > 2 and iy > 2), f"«{app.cv.itemcget(i, 'text')}» pisa la taza"
    assert visible_bbox_ok(app) == []
    assert text_overlaps(app) == []


def full_cycle(app, brk_min=5):
    """Trabajar hasta el aviso, tomar el break con el botón, esperar más de la cuenta y
    volver con el botón. Comprueba cada paso."""
    app.conf["autonomo"].update(trabajo_min=50, break_min=brk_min, max_diario_h=0)
    app.refresh_text()
    step(app, 50 * 60 + 5)
    assert app.counting and app.lvl == 2, "toca descansar"
    assert app.manual is None, "el break no empieza solo"
    check_button(app)
    worked = app.session
    click_brk(app)
    assert app.manual == "break" and app.state == "break" and not app.counting
    assert clock(app).replace(":", "") == f"00{brk_min:02d}00"
    step(app, 60.5)
    assert clock(app) == L.fmt_clock(max(0, brk_min * 60 - 61)), "cuenta hacia atrás"
    assert app.lvl == (-1 if brk_min > 1 else -2)
    check_button(app)
    step(app, brk_min * 60 + 300)                   # se pasó 5 minutos: no vuelve solo
    assert app.manual == "break" and app.state == "break" and not app.counting
    assert app.lvl == -2 and clock(app) == "00:00:00"
    assert app.session == pytest.approx(worked, abs=0.5), "el break no suma al trabajo real"
    check_button(app)
    click_brk(app)                                  # Volver del break
    assert app.manual is None
    step(app, 10)
    assert app.state == "sesion" and app.counting
    assert app.session == pytest.approx(worked + 10, abs=0.6), "sigue donde iba"
    assert app.lvl == 0 and app.streak < 15
    m = app.session_metrics()
    assert m["n_breaks"] >= 1
    assert m["breaks"] == pytest.approx(60.5 + brk_min * 60 + 300, abs=2)
    check_button(app)


# ----------------------------------------------------- todas las vistas, estilos y tamaños
@pytest.mark.parametrize("tema", TEMAS)
@pytest.mark.parametrize("vista", VISTAS)
@pytest.mark.parametrize("orient", ORIENT)
@pytest.mark.parametrize("escala", ["min", 1.0, "max"])
def test_boton_visible_y_clicable(fresh, tema, vista, orient, escala):
    app = fresh
    lo, hi = L.ESCALA_LIM["mini" if vista == "mini" else "otra"]
    k = lo if escala == "min" else hi if escala == "max" else escala
    setup(app, tema, vista, orient, k)
    open_daw(app)
    step(app, 20)
    check_button(app)
    click_brk(app)
    assert app.manual == "break", "un clic en la taza inicia el break"
    check_button(app)
    click_brk(app)
    assert app.manual is None, "otro clic vuelve del break"


@pytest.mark.parametrize("vista", VISTAS)
@pytest.mark.parametrize("orient", ORIENT)
@pytest.mark.parametrize("brk", [1, 5, 15])
def test_ciclo_completo_en_cada_vista(fresh, vista, orient, brk):
    app = fresh
    setup(app, "gaux", vista, orient, 1.0)
    open_daw(app)
    full_cycle(app, brk)


@pytest.mark.parametrize("tema", ["noche", "personal", "neon"])
@pytest.mark.parametrize("vista", VISTAS)
@pytest.mark.parametrize("orient", ORIENT)
@pytest.mark.parametrize("escala", ["min", "max"])
def test_ciclo_completo_en_otros_tamanos(fresh, tema, vista, orient, escala):
    app = fresh
    lo, hi = L.ESCALA_LIM["mini" if vista == "mini" else "otra"]
    setup(app, tema, vista, orient, lo if escala == "min" else hi)
    open_daw(app)
    full_cycle(app)


# ----------------------------------------------------------------------- Top Live
def _top(app, monkeypatch, pct=100, screens="una", rect=(0, 25, 1920, 1055)):
    OS.screens = SCREENS[screens]
    app.screen_list(fresh=True)
    fw = FakeWin(*rect)
    fw.install(monkeypatch)
    app.conf["top_escala"] = pct
    app.apply_conf()
    open_daw(app)
    app.enter_top_mode()
    drain(app)
    assert app.conf["top_mode"]
    return fw


@pytest.mark.parametrize("tema", TEMAS)
@pytest.mark.parametrize("pct", [50, 60, 70, 80, 90, 100])
def test_top_live_boton_y_ciclo(fresh, monkeypatch, tema, pct):
    """La franja de Top Live (con el analizador abierto al lado) también tiene el botón."""
    app = fresh
    app.conf["tema"] = tema
    _top(app, monkeypatch, pct)
    assert app.analyzer is not None and app.conf["analizador"]["activo"]
    a = app.conf["analizador"]
    assert a["x"] >= app.W, "el analizador no tapa el botón"
    check_button(app)
    full_cycle(app)
    app.exit_top_mode()


@pytest.mark.parametrize("scr", ["macbook", "una"])
def test_top_live_tocar_el_aviso(fresh, monkeypatch, scr):
    """En Top Live (no se arrastra) tocar el cartel BREAK / VOLVER hace lo mismo que el botón."""
    app = fresh
    rect = (0, 38, 1512, 944) if scr == "macbook" else (0, 25, 1920, 1055)
    _top(app, monkeypatch, 100, scr, rect)
    app.conf["autonomo"].update(trabajo_min=50, break_min=5, max_diario_h=0)
    step(app, 50 * 60 + 5)
    assert app.lvl == 2
    d = app.digits[len(app.digits) // 2]
    click(app, d["x"], d["y"])
    assert app.manual == "break"
    step(app, 6 * 60)
    assert app.lvl == -2 and app.manual == "break"
    click(app, d["x"], d["y"])
    assert app.manual is None
    app.exit_top_mode()


# -------------------------------------------------------- con el analizador abierto
@pytest.mark.parametrize("vista", VISTAS)
@pytest.mark.parametrize("orient", ORIENT)
def test_con_analizador_activo(fresh, vista, orient):
    app = fresh
    setup(app, "gaux", vista, orient, 1.0)
    app.conf["analizador"]["activo"] = True
    app.save_conf()
    open_daw(app)
    app.apply_analyzer()
    drain(app)
    if app.analyzer and app.analyzer.visible:
        app.analyzer.win.update_idletasks()
    check_button(app)
    full_cycle(app)


# -------------------------------------------------------------------- el aviso
@pytest.mark.parametrize("vista", VISTAS)
@pytest.mark.parametrize("orient", ORIENT)
def test_el_aviso_se_quita_al_tomar_el_break(fresh, vista, orient, monkeypatch):
    """El cartel RECHARGE/BREAK desaparece apenas se toma el break (no queda para siempre)."""
    app = fresh
    setup(app, "gaux", vista, orient, 1.0)
    open_daw(app)
    step(app, 51 * 60)
    monkeypatch.setattr(L.time, "monotonic", lambda: 2000.5)      # fase con cartel
    app.render_frame(force=True)
    assert app.brk_items and app.cv.itemcget(app.brk_items[0], "state") == "normal"
    word = app.cv.itemcget(app.brk_items[1], "text").replace("\n", "")
    assert word in ("BREAK", "RECHARGE", "BRK")
    monkeypatch.undo()
    click_brk(app)
    for t in (3000.1, 3000.9, 3001.5, 3002.5, 3003.9):
        monkeypatch.setattr(L.time, "monotonic", lambda t=t: t)
        app.render_frame(force=True)
        assert not app.brk_items or all(app.cv.itemcget(i, "state") == "hidden"
                                        for i in app.brk_items), "el cartel sigue en break"
        assert all(app.cv.itemcget(d["main"], "state") != "hidden" or d["ch"] == ":"
                   for d in app.digits), "se ve la cuenta regresiva"


@pytest.mark.parametrize("vista", VISTAS)
@pytest.mark.parametrize("orient", ORIENT)
def test_al_terminar_dice_volver(fresh, vista, orient, monkeypatch):
    app = fresh
    setup(app, "noche", vista, orient, 1.0)
    open_daw(app)
    step(app, 10)
    click_brk(app)
    step(app, 5 * 60 + 2)
    monkeypatch.setattr(L.time, "monotonic", lambda: 4000.5)
    app.render_frame(force=True)
    assert app.brk_items
    word = app.cv.itemcget(app.brk_items[1], "text").replace("\n", "")
    assert word in ("VOLVER", "BACK", "▶")
    b = app.cv.bbox(app.brk_items[1])
    assert b[0] >= -2 and b[2] <= app.W + 2 and b[1] >= -2 and b[3] <= app.H + 2
    monkeypatch.undo()
    click_brk(app)
    app.render_frame(force=True)
    assert app.manual is None
    assert not app.brk_items or all(app.cv.itemcget(i, "state") == "hidden" for i in app.brk_items)


@pytest.mark.parametrize("vista", VISTAS)
@pytest.mark.parametrize("orient", ORIENT)
def test_tocar_el_reloj_con_aviso(fresh, vista, orient):
    """Con el aviso en pantalla, tocar el reloj inicia el break; arrastrar sigue moviendo."""
    app = fresh
    setup(app, "gaux", vista, orient, 1.0)
    open_daw(app)
    step(app, 51 * 60)
    d = app.digits[1]
    click(app, d["x"], d["y"], moved=30)            # arrastre: no es un clic
    assert app.manual is None
    click(app, d["x"], d["y"])
    assert app.manual == "break"
    step(app, 6 * 60)
    click(app, d["x"], d["y"])
    assert app.manual is None


def test_tocar_el_reloj_sin_aviso_no_hace_nada(fresh):
    app = fresh
    setup(app, "gaux", "completa", "horizontal", 1.0)
    open_daw(app)
    step(app, 60)
    d = app.digits[1]
    click(app, d["x"], d["y"])
    assert app.manual is None and app.counting


@pytest.mark.parametrize("vista", VISTAS)
def test_boton_late_con_el_aviso(fresh, vista):
    app = fresh
    setup(app, "gaux", vista, "horizontal", 1.0)
    open_daw(app)
    step(app, 51 * 60)
    seen = set()
    for i in range(40):
        app.phase += 0.09
        app.render_frame(force=True)
        seen.add(app.cv.itemcget(app.brk_parts["taza"], "fill"))
    assert len(seen) >= 3, "el botón de break debe latir cuando toca descansar"


# ------------------------------------------------------------- nunca automático
@pytest.mark.parametrize("vista", VISTAS)
def test_nunca_entra_en_break_solo(fresh, vista):
    app = fresh
    setup(app, "gaux", vista, "horizontal", 1.0)
    open_daw(app)
    for _ in range(6):
        step(app, 30 * 60)
        assert app.manual is None and app.state == "sesion"
    OS.front = "other"                              # se va 20 minutos
    step(app, 20 * 60)
    assert app.manual is None and app.state == "fondo"
    assert app.lvl >= 0 and "RECHARGE ·" not in app.auto_msg
    OS.idle = 99999
    OS.front = "live"
    step(app, 10 * 60)
    assert app.manual is None and app.state == "inactivo"
    OS.idle = 0
    step(app, 5)
    assert app.state == "sesion" and app.counting


def test_break_corto_vuelve_antes(fresh):
    app = fresh
    setup(app, "gaux", "compacta", "horizontal", 1.0)
    app.conf["autonomo"].update(trabajo_min=50, break_min=10, max_diario_h=0)
    open_daw(app)
    step(app, 50 * 60 + 5)
    s0 = app.streak
    click_brk(app)
    step(app, 5 * 60)
    click_brk(app)                                  # volvió a la mitad
    assert app.manual is None
    assert app.streak == pytest.approx(s0 * 0.5, abs=3), "medio break, media racha"
    step(app, 2)
    assert app.counting and app.lvl <= 1


def test_break_desde_la_pausa(fresh):
    app = fresh
    setup(app, "gaux", "completa", "horizontal", 1.0)
    open_daw(app)
    step(app, 60)
    x1, y1, x2, y2 = hitbox(app, "pp")
    click(app, (x1 + x2) / 2, (y1 + y2) / 2)
    assert app.manual == "pausa"
    step(app, 30)
    click_brk(app)
    assert app.manual == "break"
    step(app, 30)
    click(app, (x1 + x2) / 2, (y1 + y2) / 2)        # el ▶ también vuelve del break
    assert app.manual is None
    m = app.session_metrics()
    assert m["breaks"] == pytest.approx(30, abs=1.5)
    assert m["ausencias"] == pytest.approx(30, abs=1.5)


def test_menu_tomar_y_volver(fresh):
    app = fresh
    setup(app, "gaux", "mini", "horizontal", 1.0)
    open_daw(app)
    step(app, 60)
    lab = lambda: app.menu.entrycget(app._brk_idx, "label")   # noqa: E731
    app.show_menu = app.show_menu                              # (no abrir el menú de verdad)
    app.menu.tk_popup = lambda *a: None
    app.show_menu(type("E", (), {"x_root": 10, "y_root": 10})())
    assert lab() == "Tomar break"
    app.menu.invoke(app._brk_idx)
    assert app.manual == "break"
    app.show_menu(type("E", (), {"x_root": 10, "y_root": 10})())
    assert lab() == "Volver del break"
    assert app.menu.entrycget(app._met_idx, "label").startswith("Sesión total")
    assert "Breaks" in app.menu.entrycget(app._met_idx + 1, "label")
    app.menu.invoke(app._brk_idx)
    assert app.manual is None


# ------------------------------------------------------------- las dos medidas
def test_medidas_de_la_sesion(fresh, monkeypatch):
    """Total = todo el tiempo con el DAW abierto; real = lo trabajado; y el resto se separa
    en breaks (con el botón) y ausencias (fuera del DAW, inactivo o en pausa)."""
    app = fresh
    setup(app, "gaux", "completa", "horizontal", 1.0)
    app.conf["autonomo"].update(trabajo_min=50, break_min=5, max_diario_h=0)
    open_daw(app)
    step(app, 50 * 60)                       # 50 trabajo
    click_brk(app)
    step(app, 7 * 60)                        # 7 break (2 de más, esperando el botón)
    click_brk(app)
    step(app, 10 * 60)                       # 10 trabajo
    OS.front = "other"
    step(app, 7 * 60)                        # 7 fuera del DAW
    OS.front = "live"
    step(app, 3 * 60)                        # 3 trabajo
    app.toggle_pause()
    step(app, 4 * 60)                        # 4 en pausa
    app.toggle_pause()
    step(app, 60)                            # 1 trabajo
    click_brk(app)
    step(app, 2 * 60)                        # 2 break (corto)
    click_brk(app)
    m = app.session_metrics()
    assert m["real"] == pytest.approx(64 * 60, abs=6)
    assert m["breaks"] == pytest.approx(9 * 60, abs=3)
    assert m["n_breaks"] == 2
    assert m["ausencias"] == pytest.approx(11 * 60, abs=6)
    assert m["total"] == pytest.approx(84 * 60, abs=3)
    assert m["total"] == pytest.approx(m["real"] + m["breaks"] + m["ausencias"], abs=1)
    cards = []
    monkeypatch.setattr(app, "ritual", True)
    monkeypatch.setattr(app, "show_session_card", lambda s, p=None, met=None: cards.append((s, p, met)))
    OS.running = False
    app.last_proc_check = -1e9
    step(app, 1)
    rec = L.load_json(L.DATA_FILE)["sesiones"][-1]
    assert rec["segundos"] == pytest.approx(64 * 60, abs=6)
    assert rec["total"] == pytest.approx(84 * 60, abs=4)
    assert rec["breaks"] == pytest.approx(9 * 60, abs=3) and rec["n_breaks"] == 2
    assert rec["ausencias"] == pytest.approx(11 * 60, abs=6)
    assert cards and cards[0][2]["total"] == pytest.approx(84 * 60, abs=4)


def test_cerrar_el_daw_en_break(fresh):
    app = fresh
    setup(app, "gaux", "compacta", "vertical", 1.0)
    open_daw(app)
    step(app, 10 * 60)
    click_brk(app)
    step(app, 3 * 60)
    OS.running = False
    app.last_proc_check = -1e9
    step(app, 1)
    rec = L.load_json(L.DATA_FILE)["sesiones"][-1]
    assert rec["breaks"] == pytest.approx(180, abs=3) and rec["n_breaks"] == 1
    assert rec["total"] == pytest.approx(13 * 60, abs=4)
    OS.running = True
    open_daw(app)
    step(app, 5)
    assert app.manual is None and app.counting, "al volver a abrir el DAW no sigue en break"
    m = app.session_metrics()
    assert m["n_breaks"] == 0 and m["breaks"] == 0 and m["total"] == pytest.approx(5, abs=1.5)


def test_reiniciar_sesion_en_break(fresh):
    app = fresh
    open_daw(app)
    step(app, 120)
    app.start_break()
    step(app, 60)
    app.reset_session()
    step(app, 60)
    m = app.session_metrics()
    assert app.manual == "break" and m["n_breaks"] == 1
    assert m["breaks"] == pytest.approx(60, abs=1.5) and m["real"] == 0


def test_tarjeta_final_con_las_dos_medidas(fresh):
    app = fresh
    app.ritual = True
    open_daw(app)
    step(app, 30 * 60)
    app.start_break()
    step(app, 5 * 60)
    app.resume()
    step(app, 30 * 60)
    met = app.session_metrics()
    app.show_session_card(app.session, "Westing Time With U (Orginal Mix)", met)
    app.root.update()
    texts = [app.card.winfo_children()[0].itemcget(i, "text")
             for i in app.card.winfo_children()[0].find_all()
             if app.card.winfo_children()[0].type(i) == "text"]
    assert "SESIÓN TOTAL" in texts and "TRABAJO REAL" in texts and "AUSENCIAS" in texts
    assert "BREAKS (1)" in texts
    assert "1H 05M" in texts and "1H 00M" in texts and "5M" in texts
    assert any(t.upper().startswith("WESTING TIME WI") for t in texts), "el nombre tal cual"
    app.card.destroy()
    app.card = None


def test_csv_de_sesiones(fresh, monkeypatch, tmp_path):
    app = fresh
    open_daw(app)
    step(app, 20 * 60)
    app.start_break()
    step(app, 6 * 60)
    app.resume()
    step(app, 5 * 60)
    app._close_session()
    app.data["sesiones"].append({"inicio": "2026-01-01T10:00:00", "fin": "2026-01-01T11:00:00",
                                 "segundos": 1800, "proyectos": {"Viejo": 1800}})   # sin total
    monkeypatch.setattr(os.path, "expanduser", lambda p: str(tmp_path) if p == "~" else p)
    os.makedirs(tmp_path / "Desktop", exist_ok=True)
    monkeypatch.setattr(L.subprocess, "Popen", lambda *a, **k: None)
    monkeypatch.setattr(app, "notice", lambda *a: None)
    w = L.Proyectos.__new__(L.Proyectos)
    w.app = app
    w.export()
    with open(tmp_path / "Desktop" / f"{L.APP_NAME} - Sesiones.csv", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    assert rows[0][2] == "Sesión total (h:mm)" and rows[0][3] == "Trabajo real (h:mm)"
    old, new = rows[1], rows[2]
    assert old[2] == old[3] == "0:30" and old[4] == "0:00"
    assert new[2] == "0:31" and new[3] == "0:25" and new[4] == "0:06" and new[5] == "1"


# ------------------------------------------------------------- sin fugas ni CPU extra
def test_horas_de_breaks_sin_fugas(fresh):
    app = fresh
    setup(app, "gaux", "completa", "horizontal", 1.0)
    app.conf["autonomo"].update(trabajo_min=50, break_min=5, max_diario_h=0)
    open_daw(app)
    step(app, 30)
    app.render_frame(force=True)
    base = len(app.cv.find_all())
    for _ in range(8):
        step(app, 50 * 60, chunk=60)
        for _ in range(60):
            app.phase += 0.033
            app.render_frame()
        click_brk(app)
        for _ in range(7):
            step(app, 60)
            for _ in range(30):
                app.phase += 0.033
                app.render_frame()
        click_brk(app)
    grown = len(app.cv.find_all()) - base
    assert grown <= 30, f"el lienzo creció {grown} elementos"
    assert len(app._icache) < 3000, "la caché de colores no crece sin fin"


@pytest.mark.parametrize("w", [200, 300, 600])
@pytest.mark.parametrize("h", [24, 32, 38])
def test_junto_a_la_camara_tambien(fresh, monkeypatch, w, h):
    """MacBook con notch y el DAW en pantalla completa: la franja junto a la cámara es angosta
    y aun así tiene la taza (el reloj se achica, no se quita ningún botón)."""
    app = fresh
    _top(app, monkeypatch, 100, "macbook", (0, 38, 1512, 944))
    app.fs_band = {"left": (0, 0, w, h), "right": (1512 - w, 0, w, h)}
    app.apply_conf()
    drain(app)
    assert app.W <= w and app.H <= h
    for n in ("brk", "pp", "cfg"):
        hitbox(app, n)
    check_button(app)
    full_cycle(app)
    app.fs_band = None
    app.exit_top_mode()
