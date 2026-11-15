"""Proyectos tocados en plena sesión: renombrar, unir, eliminar y cambiar mientras cuenta."""
import pytest

import live_timer as L
from conftest import OS, open_daw, step


def close_daw(app):
    OS.running = False
    app.last_proc_check = -1e9
    step(app, 1)


@pytest.mark.parametrize("auto", [True, False])
def test_renombrar_en_plena_sesion(fresh, auto):
    app = fresh
    if auto:
        OS.title = "Viejo [Viejo Project] - Ableton Live 12 Suite"
    else:
        app.set_project("Viejo", auto=False)
    open_daw(app)
    step(app, 120)
    app.rename_project("Viejo", "Nuevo")
    step(app, 120)
    close_daw(app)
    recs = app.data["proyectos"]
    assert "Viejo" not in recs
    assert recs["Nuevo"]["segundos"] == pytest.approx(240, abs=5)
    assert recs["Nuevo"]["sesiones"] == 1, "la sesión cuenta para el nombre nuevo"
    s = app.data["sesiones"][-1]
    assert set(s["proyectos"]) == {"Nuevo"}
    assert s["proyectos"]["Nuevo"] == pytest.approx(240, abs=5)


def test_unir_en_plena_sesion(fresh):
    app = fresh
    app.set_project("A", auto=False)
    open_daw(app)
    step(app, 100)
    app.set_project("B", auto=False)
    step(app, 100)
    app.rename_project("A", "B")
    step(app, 100)
    close_daw(app)
    recs = app.data["proyectos"]
    assert recs["B"]["segundos"] == pytest.approx(300, abs=6)
    assert recs["B"]["sesiones"] == 1
    assert app.data["sesiones"][-1]["proyectos"] == {"B": pytest.approx(300, abs=6)}


def test_eliminar_en_plena_sesion(fresh):
    app = fresh
    app.set_project("Borrar", auto=False)
    open_daw(app)
    step(app, 100)
    app.delete_project("Borrar")
    step(app, 100)
    close_daw(app)
    recs = app.data["proyectos"]
    assert "Borrar" not in recs
    assert recs[L.SIN_PROYECTO]["segundos"] == pytest.approx(100, abs=5)
    s = app.data["sesiones"][-1]
    assert "Borrar" not in s["proyectos"], "un proyecto borrado no reaparece en el historial"
    assert s["segundos"] == pytest.approx(200, abs=5)


@pytest.mark.parametrize("n", [2, 5, 20])
def test_cambiar_de_set_muchas_veces(fresh, n):
    app = fresh
    open_daw(app)
    for i in range(n):
        OS.title = f"Set {i % 3} [x] - Ableton Live 12 Suite"
        app._title_t = -1e9
        step(app, 61)
    close_daw(app)
    recs = app.data["proyectos"]
    total = sum(r["segundos"] for r in recs.values())
    assert total == pytest.approx(61 * n, abs=2)
    s = app.data["sesiones"][-1]
    assert sum(s["proyectos"].values()) == pytest.approx(61 * n, abs=n + 2)
    for k, v in s["proyectos"].items():
        if v >= 60:
            assert recs[k]["sesiones"] == 1


@pytest.mark.parametrize("tema", list(L.TEMAS))
@pytest.mark.parametrize("confirmar", [False, True])
def test_botones_de_la_fila_se_ven_completos(fresh, tema, confirmar):
    """Usar / Renombrar / Eliminar (y '¿Eliminar…? Sí, eliminar · No') nunca quedan cortados."""
    app = fresh
    app.conf["tema"] = tema
    app.apply_conf()
    for i, n in enumerate(["CRAZY SYNTHS", "Westing Time With U (Orginal Mix) extendida", "x"]):
        r = app.project_rec(n)
        r["segundos"] = 999 * 3600 + 59 * 60
        r["daw"] = "Digital Performer"
    app.open_projects()
    w = app.projects_win
    app.root.update()
    if confirmar:
        for k in list(w._row_labels):
            acts = [c for c in w.rows.winfo_children() if c.winfo_children()]
        for row in w.rows.winfo_children():
            kids = row.winfo_children()
            if kids:
                acts = kids[-1]
                btns = [b for b in acts.winfo_children() if b.cget("text") == "Eliminar"]
                if btns:
                    btns[0].event_generate("<Button-1>")
        app.root.update()
    cw = w.canvas.winfo_width()
    for row in w.rows.winfo_children():
        for b in (row.winfo_children()[-1].winfo_children() if row.winfo_children() else []):
            right = b.winfo_rootx() + b.winfo_width() - w.canvas.winfo_rootx()
            assert right <= cw + 1, (b.cget("text"), right, cw)
    w.destroy()
