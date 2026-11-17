"""El panel del analizador se ajusta a lo que muestra: si dejas solo Loudness (o Stereo, o los
dos) queda del ancho justo, sin una franja negra vacía; al volver a prender la onda o el
espectro recupera el ancho que tenías."""
import itertools

import numpy as np
import pytest

import gaux_analizador as G
from test_analizador import panel, play, prepare, rebuild, sine  # noqa: F401

MODS = [k for k, _ in G.MODULES]
COMBOS = [c for r in range(1, 5) for c in itertools.combinations(MODS, r)]
TAMANOS = [(900, 172), (1440, 200), (1600, 132), (700, 120), (1200, 300), (2400, 420)]


def unused_right(p):
    """Píxeles vacíos a la derecha del último módulo (sin contar el margen normal)."""
    end = max(x0 + w for (x0, y0, w, h) in p.rects.values())
    return p.W - 2 * p.PAD - end


@pytest.mark.parametrize("mods", COMBOS, ids=["+".join(c) for c in COMBOS])
@pytest.mark.parametrize("size", TAMANOS, ids=[f"{w}x{h}" for w, h in TAMANOS])
def test_sin_espacio_vacio(panel, mods, size):
    rebuild(panel, *size, list(mods), "gaux")
    panel.win.update_idletasks()
    assert set(panel.rects) == set(mods)
    assert unused_right(panel) <= 3, (mods, size, panel.W, panel.rects)
    assert panel.win.winfo_width() == panel.W
    for k, (x0, y0, w, h) in panel.rects.items():
        assert w > 0 and panel.PAD + x0 + w <= panel.W


@pytest.mark.parametrize("mods,max_w", [(("lufs",), 260), (("stereo",), 200),
                                        (("stereo", "lufs"), 420)])
@pytest.mark.parametrize("size", TAMANOS, ids=[f"{w}x{h}" for w, h in TAMANOS])
def test_solo_medidores_queda_chico(panel, mods, max_w, size):
    rebuild(panel, *size, list(mods), "noche")
    assert panel.W <= max_w, f"{mods} quedó de {panel.W} px"


def test_vuelve_al_ancho_que_tenias(panel):
    rebuild(panel, 1400, 172, MODS, "gaux")
    assert panel.W == 1400
    rebuild(panel, 1400, 172, ["lufs"], "gaux")
    assert panel.W < 300
    assert panel.app.conf["analizador"]["w"] == 1400        # se recuerda
    rebuild(panel, 1400, 172, ["spec", "lufs"], "gaux")
    assert panel.W == 1400


def test_cambiar_modulos_desde_el_menu(panel):
    rebuild(panel, 1200, 172, MODS, "gaux")
    for k in ("wave", "spec", "stereo"):
        panel.set_module(k, False)
    assert panel.W < 300 and set(panel.rects) == {"lufs"}
    panel.set_module("spec", True)
    assert panel.W == 1200


def test_arrastrar_la_esquina_con_solo_loudness(panel):
    """Con solo medidores, arrastrar la esquina cambia el alto, no estira un vacío."""
    rebuild(panel, 1100, 172, ["lufs"], "gaux")
    panel.win.update_idletasks()
    w0 = panel.W
    x, y = panel.win.winfo_x(), panel.win.winfo_y()
    ev = type("E", (), {"x_root": x + panel.W - 3, "y_root": y + panel.H - 3,
                        "x": panel.W - 3, "y": panel.H - 3})()
    panel.on_press(ev)
    e2 = type("E", (), {"x_root": ev.x_root + 600, "y_root": ev.y_root + 80, "x": 0, "y": 0})()
    panel.on_drag(e2)
    panel.win.update_idletasks()
    panel.on_release(e2)
    panel.win.update_idletasks()
    assert panel.W == w0 and panel.win.winfo_width() == w0
    assert panel.H > 172
    assert panel.app.conf["analizador"]["w"] == 1100        # el ancho ancho no se pisa


@pytest.mark.parametrize("mods", [("lufs",), ("stereo",), ("stereo", "lufs")])
def test_medidores_solos_funcionan_con_audio(panel, mods):
    rebuild(panel, 1000, 172, list(mods), "gaux")
    prepare(panel)
    play(panel, sine(997, -14, 1.5, 48000))
    assert unused_right(panel) <= 3
    if "lufs" in mods:
        assert np.isfinite(panel.loud.momentary())
