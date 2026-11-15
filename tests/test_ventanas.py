"""Ventanas: Ajustes (todas las páginas y controles), Proyectos, menú, diálogos y tarjetas."""
import csv
import os
import tkinter as tk

import pytest

import live_timer as L
from conftest import OS, TK_ERRORS, drain, open_daw, step, visible_bbox_ok

PAGES = [k for k, _, _ in L.Ajustes.PAGES]
TEMAS = list(L.TEMAS)


@pytest.fixture
def safe(fresh, monkeypatch):
    """Sin menús flotantes, sin abrir el Finder y sin cerrar el timer de verdad."""
    calls = {"popen": [], "quit": 0, "popup": 0}
    monkeypatch.setattr(tk.Menu, "tk_popup",
                        lambda self, *a, **k: calls.__setitem__("popup", calls["popup"] + 1))
    monkeypatch.setattr(L.subprocess, "Popen", lambda *a, **k: calls["popen"].append(a))
    monkeypatch.setattr(fresh, "quit", lambda: calls.__setitem__("quit", calls["quit"] + 1))
    monkeypatch.setattr(L, "install_autostart", lambda quiet=False: None)
    from tkinter import colorchooser
    monkeypatch.setattr(colorchooser, "askcolor",
                        lambda **k: ((34, 197, 94), "#22c55e"))   # el selector del sistema
    monkeypatch.setattr(L, "remove_autostart", lambda quiet=False: None)
    fresh._calls = calls
    yield fresh


def clickables(root):
    out = []

    def walk(w):
        for c in w.winfo_children():
            try:
                if "<Button-1>" in c.bind() or "<ButtonPress-1>" in c.bind():
                    out.append(c)
            except tk.TclError:
                pass
            walk(c)
    walk(root)
    return out


def text_of(w):
    try:
        return w.cget("text")
    except tk.TclError:
        return ""


def click(w):
    """Clic real: presionar y soltar (los botones de Tk responden a cualquiera de los dos)."""
    w.winfo_toplevel().update()             # en Windows la ventana debe estar ya dibujada
    w.event_generate("<ButtonPress-1>", x=3, y=3)
    if w.winfo_exists():
        w.event_generate("<ButtonRelease-1>", x=3, y=3)


def texts_in(w):
    out = [text_of(w)]
    for c in w.winfo_children():
        out += texts_in(c)
    return out


def open_settings(app, page="metas"):
    app.open_settings()
    s = app.settings
    s.update()
    s.show(page)
    s.update()
    return s


# ---------------------------------------------------------------- Ajustes
@pytest.mark.parametrize("tema", TEMAS)
@pytest.mark.parametrize("page", PAGES)
def test_abrir_cada_pagina(safe, tema, page):
    app = safe
    app.conf["tema"] = tema
    app.apply_conf()
    s = open_settings(app, page)
    assert s.winfo_exists()
    s.save()
    assert not s.winfo_exists()
    assert not TK_ERRORS


@pytest.mark.parametrize("page", PAGES)
def test_guardar_sin_cambios_no_cambia_nada(safe, page):
    app = safe
    before = L.load_json(L.CONF_FILE) or app.conf
    before = {k: v for k, v in before.items() if k not in ("x", "y", "pos")}
    s = open_settings(app, page)
    s.save()
    after = {k: v for k, v in app.conf.items() if k not in ("x", "y", "pos")}
    for k, v in before.items():
        assert after.get(k) == v, k


@pytest.mark.parametrize("page", PAGES)
def test_cancelar_no_guarda(safe, page):
    app = safe
    s = open_settings(app, page)
    s.work_step.setv(120)
    s.op_step.setv(40)
    s.destroy()
    assert app.conf["autonomo"]["trabajo_min"] == 50
    assert app.conf["opacidad"] == L.DEFAULT_CONF["opacidad"]


@pytest.mark.parametrize("page", PAGES)
def test_tocar_cada_control_de_la_pagina(safe, page):
    """Se hace clic en cada botón, interruptor, chip y stepper de la página y se guarda."""
    app = safe
    s = open_settings(app, page)
    skip = ("Guardar", "Cancelar", "Salir de")
    n = 0
    for w in clickables(s.pages[page]):
        if not w.winfo_exists():
            continue
        if any(text_of(w).startswith(x) for x in skip):
            continue
        click(w)
        drain(app)
        n += 1
        if not s.winfo_exists():
            break
    assert n > 0
    for extra in list(app.root.winfo_children()):
        if isinstance(extra, tk.Toplevel) and extra is not s and \
                not (app.analyzer and extra is app.analyzer.win):
            extra.destroy()
    if s.winfo_exists():
        s.save()
    app.render_frame(force=True)
    assert not TK_ERRORS, TK_ERRORS
    assert visible_bbox_ok(app) == []


@pytest.mark.parametrize("page", PAGES)
def test_navegar_por_la_barra_lateral(safe, page):
    app = safe
    s = open_settings(app)
    row, bar, lab = s.nav[page]
    click(lab)
    s.update()
    assert s.pages[page].winfo_ismapped()


@pytest.mark.parametrize("trabajo", [10, 50, 240])
@pytest.mark.parametrize("brk", [1, 5, 60])
def test_guardar_descansos(safe, trabajo, brk):
    app = safe
    s = open_settings(app, "descansos")
    s.work_step.setv(trabajo)
    s.brk_step.setv(brk)
    s.save()
    c = L.load_json(L.CONF_FILE)
    assert c["autonomo"]["trabajo_min"] == trabajo and c["autonomo"]["break_min"] == brk


@pytest.mark.parametrize("v,expect", [(0, 10), (9999, 240), (55, 55)])
def test_stepper_respeta_limites(safe, v, expect):
    s = open_settings(safe, "descansos")
    s.work_step.setv(v)
    assert s.work_step.st["v"] == expect
    s.destroy()


@pytest.mark.parametrize("meta", ["diaria", "semanal", "mensual"])
@pytest.mark.parametrize("horas", [1, 6, 40])
def test_guardar_metas(safe, meta, horas):
    app = safe
    app.conf["metas"][meta]["activa"] = True
    s = open_settings(app, "metas")
    s.goal_ui[meta]["step"].setv(horas * 3600)
    s.goal_ui[meta]["name"].delete(0, "end")
    s.goal_ui[meta]["name"].insert(0, "Mi meta ñ")
    s.save()
    g = L.load_json(L.CONF_FILE)["metas"][meta]
    assert g["nombre"] == "Mi meta ñ"
    assert g["segundos"] == min(horas * 3600, g["segundos"]) and g["segundos"] >= 60


@pytest.mark.parametrize("name", ["", "   ", "x" * 50])
def test_nombre_de_meta_vacio_o_largo(safe, name):
    app = safe
    s = open_settings(app, "metas")
    e = s.goal_ui["diaria"]["name"]
    e.delete(0, "end")
    e.insert(0, name)
    s.save()
    n = app.conf["metas"]["diaria"]["nombre"]
    assert n and len(n) <= 14


@pytest.mark.parametrize("op", [40, 70, 100])
def test_guardar_opacidad(safe, op):
    app = safe
    s = open_settings(app, "apariencia")
    s.op_step.setv(op)
    s.save()
    assert app.conf["opacidad"] == pytest.approx(op / 100)


@pytest.mark.parametrize("hexv,ok", [("#22C55E", True), ("22c55e", True), ("#12", False),
                                     ("rojo", False), ("", False), ("#GGGGGG", False)])
def test_color_personal(safe, hexv, ok):
    app = safe
    app.conf["tema"] = "personal"
    app.apply_conf()
    s = open_settings(app, "apariencia")
    s.hex_e.delete(0, "end")
    s.hex_e.insert(0, hexv)
    s.save()
    c = app.conf["personal"]["color"]
    if ok:
        assert c.lower() == "#" + hexv.lstrip("#").lower()
    else:
        assert c == L.DEFAULT_CONF["personal"]["color"]
    assert visible_bbox_ok(app) == []


@pytest.mark.parametrize("field,val", [("nombre", ""), ("nombre", "Aleksander Gaux"),
                                       ("nombre", "x" * 100), ("inicio", ""),
                                       ("inicio", "VAMOS 🎧"), ("cierre", "GG WP"),
                                       ("nombre", "Ñandú ¿?¡!")])
def test_textos_modo_personal(safe, field, val):
    app = safe
    app.conf["tema"] = "personal"
    app.apply_conf()
    s = open_settings(app, "apariencia")
    e = s.p_entries[field]
    e.delete(0, "end")
    e.insert(0, val)
    s.save()
    stored = app.conf["personal"][field]
    assert len(stored) <= 60
    open_daw(app)
    step(app, 2)
    for _ in range(3):
        app.render_frame(force=True)
    assert visible_bbox_ok(app) == []


@pytest.mark.parametrize("extra", ["", "Mixbus", "Mixbus, Waveform", " , ,"])
def test_guardar_apps_extra(safe, extra):
    app = safe
    s = open_settings(app, "daw")
    s.e_extra.delete(0, "end")
    s.e_extra.insert(0, extra)
    s.save()
    assert app.conf["daws_extra"] == extra.strip()
    OS.proc = "Mixbus 10"
    open_daw(app)
    assert app.live_open == ("Mixbus" in extra)


def test_desmarcar_todos_los_daws(safe):
    app = safe
    s = open_settings(app, "daw")
    s.daw_sel.clear()
    s.save()
    assert app.conf["daws"] == []
    open_daw(app)
    assert not app.live_open


def test_ajustes_dos_veces_no_duplica(safe):
    app = safe
    app.open_settings()
    first = app.settings
    app.open_settings()
    assert app.settings is first
    wins = [w for w in app.root.winfo_children() if isinstance(w, L.Ajustes)]
    assert len(wins) == 1


def test_selector_de_color_del_sistema(safe):
    app = safe
    app.conf["tema"] = "personal"
    app.apply_conf()
    s = open_settings(app, "apariencia")
    click(labels(s, "Más…")[0])
    assert s.winfo_exists() and s.attributes("-topmost")
    s.save()
    assert app.conf["personal"]["color"].lower() == "#22c55e"


def test_salir_desde_ajustes(safe):
    app = safe
    s = open_settings(app, "general")
    btn = next(w for w in clickables(s.pages["general"]) if text_of(w).startswith("Salir de"))
    click(btn)
    assert app._calls["quit"] == 1


def test_ajustes_abierto_mantiene_el_conteo(safe):
    """Con Ajustes al frente el timer sigue visible (y no cuenta como tiempo de DAW)."""
    app = safe
    open_daw(app)
    step(app, 5)
    open_settings(app)
    OS.front = "self"
    step(app, 10)
    assert app.visible


# ---------------------------------------------------------------- Proyectos
def seed(app, n=5):
    for i in range(n):
        app.set_project(f"Proyecto {i}")
        app.data["proyectos"][f"Proyecto {i}"]["segundos"] = 3600 * (i + 1)


def open_projects(app):
    app.open_projects()
    w = app.projects_win
    w.update()
    return w


def labels(w, text):
    out = []

    def rec(x):
        for c in x.winfo_children():
            if isinstance(c, tk.Label) and c.cget("text") == text:
                out.append(c)
            rec(c)
    rec(w)
    return out


@pytest.mark.parametrize("n", [0, 1, 5, 40])
def test_lista_de_proyectos(safe, n):
    app = safe
    seed(app, n)
    w = open_projects(app)
    assert len(labels(w, "Eliminar")) == n
    w.destroy()


@pytest.mark.parametrize("tema", TEMAS)
def test_proyectos_en_cada_estilo(safe, tema):
    app = safe
    app.conf["tema"] = tema
    app.apply_conf()
    seed(app, 3)
    w = open_projects(app)
    assert len(labels(w, "Usar")) == 3
    w.destroy()


@pytest.mark.parametrize("i", [0, 2, 4])
def test_eliminar_desde_la_ventana(safe, i):
    app = safe
    seed(app)
    w = open_projects(app)
    name = f"Proyecto {i}"
    rows = labels(w, "Eliminar")
    order = sorted(app.data["proyectos"], key=lambda k: w._sort_key(k)) if hasattr(w, "_sort_key") else None
    # localizar la fila del proyecto
    target = None
    for b in rows:
        row = b.master.master
        if name in texts_in(row):
            target = b
    assert target is not None, order
    click(target)
    w.update()
    yes = labels(w, "Sí, eliminar")
    assert len(yes) == 1
    click(yes[0])
    w.update()
    assert name not in app.data["proyectos"]
    assert name not in L.load_json(L.DATA_FILE)["proyectos"]
    assert len(labels(w, "Eliminar")) == 4
    w.destroy()


def test_eliminar_y_luego_no(safe):
    app = safe
    seed(app, 2)
    w = open_projects(app)
    click(labels(w, "Eliminar")[0])
    w.update()
    click(labels(w, "No")[0])
    w.update()
    assert len(app.data["proyectos"]) == 2 and len(labels(w, "Eliminar")) == 2
    w.destroy()


def test_eliminar_todos(safe):
    app = safe
    seed(app, 6)
    w = open_projects(app)
    for _ in range(6):
        click(labels(w, "Eliminar")[0])
        w.update()
        click(labels(w, "Sí, eliminar")[0])
        w.update()
    assert app.data["proyectos"] == {}
    w.destroy()


def test_usar_desde_la_ventana(safe):
    app = safe
    seed(app, 3)
    w = open_projects(app)
    for i in range(3):
        click(labels(w, "Usar")[i])
        w.update()
        assert app.conf["proyecto"].startswith("Proyecto")
    assert len(labels(w, "Usar")) == 3
    w.destroy()


@pytest.mark.parametrize("new", ["Track Final", "Proyecto 1", "", "Westing Time With U"])
def test_renombrar_desde_la_ventana(safe, new):
    app = safe
    seed(app, 3)
    w = open_projects(app)
    click(labels(w, "Renombrar")[0])
    w.update()
    dlg = [x for x in app.root.winfo_children() if isinstance(x, tk.Toplevel)
           and x is not w and any(isinstance(c, tk.Entry) for c in x.winfo_children())]
    assert dlg, "debe abrir la ventana para escribir el nombre"
    e = next(c for c in dlg[-1].winfo_children() if isinstance(c, tk.Entry))
    e.delete(0, "end")
    e.insert(0, new)
    click(labels(dlg[-1], "Aceptar")[0])
    w.update()
    total = sum(r["segundos"] for r in app.data["proyectos"].values())
    assert total == pytest.approx(3600 * 6)
    if new.strip():
        assert new in app.data["proyectos"]
    w.destroy()


@pytest.mark.parametrize("col", ["nombre", "total", "hoy", "semana", "mes", "sesiones",
                                 "ultima", "daw"])
def test_ordenar_por_columna(safe, col):
    app = safe
    seed(app, 4)
    w = open_projects(app)
    w.set_sort(col)
    w.update()
    w.set_sort(col)
    w.update()
    assert len(labels(w, "Eliminar")) == 4
    w.destroy()


def test_exportar_csv(safe):
    app = safe
    seed(app, 3)
    app.data["proyectos"]["=SUMA(A1)"] = {"segundos": 60, "dias": {}, "sesiones": 0,
                                          "creado": None, "ultima": None, "daw": ""}
    w = open_projects(app)
    w.export()
    path = os.path.join(os.path.expanduser("~"), f"{L.APP_NAME} - Proyectos.csv")
    if not os.path.exists(path):
        path = os.path.join(os.path.expanduser("~"), "Desktop", f"{L.APP_NAME} - Proyectos.csv")
    with open(path, encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    assert rows[0][0] == "Proyecto" and len(rows) == 5
    names = [r[0] for r in rows[1:]]
    assert "Proyecto 2" in names
    assert "=SUMA(A1)" in names, "los nombres se exportan idénticos"
    w.destroy()


def test_proyectos_se_actualiza_solo(safe):
    app = safe
    seed(app, 2)
    w = open_projects(app)
    app.set_project("Nuevo")
    w.refresh()
    w.update()
    assert len(labels(w, "Eliminar")) == 3
    w.destroy()


def test_detectar_automatico_desde_la_ventana(safe):
    app = safe
    w = open_projects(app)
    before = app.conf["proyecto_auto"]
    w.toggle_auto()
    assert app.conf["proyecto_auto"] != before
    w.toggle_auto()
    assert app.conf["proyecto_auto"] == before
    w.destroy()


def test_sin_asignar_corto_se_oculta(safe):
    app = safe
    app.project_rec(L.SIN_PROYECTO)["segundos"] = 30
    w = open_projects(app)
    assert len(labels(w, "Eliminar")) == 0
    w.destroy()


# ---------------------------------------------------------------- menú del widget
def menu_entries(m):
    out = []
    end = m.index("end")
    for i in range(0, (end or 0) + 1):
        t = m.type(i)
        if t in ("command", "radiobutton", "checkbutton"):
            out.append((m, i, m.entrycget(i, "label")))
        elif t == "cascade":
            sub = m.nametowidget(m.entrycget(i, "menu"))
            out += menu_entries(sub)
    return out


def test_menu_cada_opcion(safe, monkeypatch):
    app = safe
    monkeypatch.setattr(L, "live_main_window",
                        lambda: (_ for _ in ()).throw(L.LiveWindowError("sin DAW")))
    monkeypatch.setattr(app, "notice", lambda *a: None)
    seed(app, 3)
    open_daw(app)
    step(app, 5)
    app._fill_project_menu(app.proj_menu)
    for m, i, label in menu_entries(app.menu):
        if label.startswith("Cerrar") or m.entrycget(i, "state") == "disabled":
            continue
        m.invoke(i)
        drain(app)
        for x in list(app.root.winfo_children()):
            if isinstance(x, tk.Toplevel) and not (app.analyzer and x is app.analyzer.win):
                x.destroy()
        app.settings = None
        app.projects_win = None
        app.render_frame(force=True)
    assert not TK_ERRORS, TK_ERRORS


def test_menu_cerrar_guarda_y_cierra(safe, monkeypatch):
    app = safe
    open_daw(app)
    step(app, 90)
    closed = []
    monkeypatch.setattr(app.root, "destroy", lambda: closed.append(1))
    m, i, _ = next(e for e in menu_entries(app.menu) if e[2].startswith("Cerrar"))
    m.invoke(i)
    assert closed == [1]
    assert L.load_json(L.DATA_FILE)["sesiones"][-1]["segundos"] == pytest.approx(90, abs=2)
    app.live_open = False


@pytest.mark.parametrize("n", [0, 3, 15])
def test_menu_de_proyectos(safe, n):
    app = safe
    seed(app, n)
    app._fill_project_menu(app.proj_menu)
    labels_ = [e[2] for e in menu_entries(app.proj_menu)]
    assert L.SIN_PROYECTO in labels_
    assert len([x for x in labels_ if x.startswith("Proyecto ")]) == min(n, 10)


def test_menu_nuevo_proyecto(safe):
    app = safe
    w = app.ask_text("Nuevo proyecto", "Nombre", on_ok=lambda v: app.set_project(v))
    e = next(c for c in w.winfo_children() if isinstance(c, tk.Entry))
    e.insert(0, "Desde el menú")
    click(labels(w, "Aceptar")[0])
    assert app.conf["proyecto"] == "Desde el menú"


def test_dialogo_cancelar(safe):
    app = safe
    got = []
    w = app.ask_text("x", "y", on_ok=got.append)
    click(labels(w, "Cancelar")[0])
    assert got == [] and not w.winfo_exists()


def test_dialogo_vacio_no_llama(safe):
    app = safe
    got = []
    w = app.ask_text("x", "y", on_ok=got.append)
    click(labels(w, "Aceptar")[0])
    assert got == []


# ---------------------------------------------------------------- rituales
@pytest.mark.parametrize("tema", ["gaux", "personal"])
@pytest.mark.parametrize("secs", [30, 61, 3600, 5 * 3600])
def test_tarjeta_al_cerrar_el_daw(safe, tema, secs):
    app = safe
    app.conf["tema"] = tema
    app.apply_conf()
    open_daw(app)
    step(app, secs)
    OS.running = False
    app.last_proc_check = -1e9
    step(app, 1)
    if secs >= 60:
        assert app.card is not None
        app.card.update()
    else:
        assert app.card is None


@pytest.mark.parametrize("tema", ["noche", "cristal", "neon"])
def test_sin_tarjeta_en_estilos_normales(safe, tema):
    app = safe
    app.conf["tema"] = tema
    app.apply_conf()
    open_daw(app)
    step(app, 120)
    OS.running = False
    app.last_proc_check = -1e9
    step(app, 1)
    assert app.card is None


@pytest.mark.parametrize("first", [True, False])
def test_bienvenida(safe, first):
    safe.show_welcome(first)
    drain(safe)


def test_aviso_generico(safe):
    safe.notice("Título", "Texto largo " * 40)
