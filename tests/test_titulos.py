"""Títulos reales de la ventana de cada DAW (Mac y Windows, en varios idiomas y versiones):
el timer debe sacar el nombre del proyecto tal cual, sin inventar ni 'corregir' nada."""
import pytest

import live_timer as L

TITULOS = [
    # ---- Ableton Live (Mac y Windows; * = sin guardar)
    ("CRAZY SYNTHS  [CRAZY SYNTHS Project] - Ableton Live 12 Suite", "CRAZY SYNTHS"),
    ("CRAZY SYNTHS*  [CRAZY SYNTHS Project] - Ableton Live 12 Suite", "CRAZY SYNTHS"),
    ("Westing Time With U [Westing Time With U Project] - Ableton Live 11 Standard",
     "Westing Time With U"),
    ("Orginal Mix [Orginal Mix Project] - Ableton Live 12 Lite", "Orginal Mix"),
    ("Tahelly Project - Ableton Live 12 Suite", "Tahelly Project"),
    ("Untitled - Ableton Live 12 Suite", None),
    ("Untitled*  [Untitled Project] - Ableton Live 12 Suite", None),
    ("Sin título - Ableton Live 12 Suite", None),
    ("Ableton Live 12 Suite", None),
    ("Live", None),
    ("Track 2 v3 FINAL  [Track 2 Project] - Ableton Live 12 Suite", "Track 2 v3 FINAL"),
    ("Remix (Gaux Edit) [Remix Project] - Ableton Live 12 Suite", "Remix (Gaux Edit)"),
    ("Song - Copy [Song Project] - Ableton Live 12 Suite", "Song - Copy"),
    ("Mi Canción ñ  [Mi Canción ñ Project] - Ableton Live 12 Suite", "Mi Canción ñ"),
    ("Bass.als - Ableton Live 10 Suite", "Bass"),
    # ---- FL Studio
    ("Mi Beat.flp - FL Studio 2024", "Mi Beat"),
    ("Mi Beat - FL Studio 21", "Mi Beat"),
    ("FL Studio 2024 - Mi Beat", "Mi Beat"),
    ("FL Studio 2024", None),
    ("Untitled - FL Studio 2024", None),
    ("Trap 140 bpm.flp - FL Studio 20", "Trap 140 bpm"),
    # ---- Logic Pro / GarageBand
    ("Mi Track - Tracks", "Mi Track"),
    ("Mi Track.logicx - Tracks", "Mi Track"),
    ("Untitled - Tracks", None),
    ("Mi Track - Mixer", "Mi Track"),
    ("Idea - Tracks", "Idea"),
    ("Logic Pro", None),
    # ---- Pro Tools
    ("Edit: Sesión Final", "Sesión Final"),
    ("Mix: Sesión Final", "Sesión Final"),
    ("Edit: Film Score v2", "Film Score v2"),
    ("Pro Tools", None),
    # ---- Cubase / Nuendo
    ("Cubase Pro Project - Remix", "Remix"),
    ("Cubase Pro 14 Project - Remix.cpr", "Remix"),
    ("Nuendo Project - Score Film", "Score Film"),
    ("Cubase Pro 13", None),
    # ---- Studio One
    ("Studio One - Demo", "Demo"),
    ("Studio One - Demo.song", "Demo"),
    ("Studio One 6", None),
    # ---- Bitwig
    ("Groove - Bitwig Studio", "Groove"),
    ("Groove.bwproject - Bitwig Studio 5.2", "Groove"),
    ("Bitwig Studio", None),
    # ---- REAPER
    ("Mi Track - REAPER v7.22 - Registered to Gaux", "Mi Track"),
    ("Mi Track [C:\\Proyectos\\Mi Track.rpp] - REAPER v7.22", "Mi Track"),
    ("Mi Track.rpp - REAPER v7.22", "Mi Track"),
    ("[Unsaved project] - REAPER v7.22", None),
    ("REAPER v7.22 - Evaluation License", None),
    # ---- Reason
    ("Rack - Reason", "Rack"),
    ("Rack.reason - Reason 12", "Rack"),
    # ---- Cakewalk
    ("Cakewalk by BandLab - [Rock.cwp - Track]", "Rock"),
    ("Cakewalk - [Rock - Console]", "Rock"),
    # ---- otros
    ("Club Mix - Ardour", "Club Mix"),
    ("Club Mix.ardour - Ardour 8.4", "Club Mix"),
    ("Chip.xrns - Renoise 3.4", "Chip"),
    ("Film.dpdoc - Digital Performer", "Film"),
    # ---- casos raros
    ("", None), ("   ", None), (None, None), (" - ", None), ("[]", None), ("[ ]", None),
    ("-", None), ("*", None), ("Ableton Live 12 Suite - Ableton Live 12 Suite", None),
    ("x" * 300 + " - Ableton Live 12 Suite", "x" * 60),
    ("🔥🔥 [🔥🔥 Project] - Ableton Live 12 Suite", "🔥🔥"),
    ("日本語の曲 - Ableton Live 12 Suite", "日本語の曲"),
    ("A - B - C - Ableton Live 12 Suite", "A"),
    ("Mix: ", None), ("Edit:", None),
]


@pytest.mark.parametrize("title,expected", TITULOS, ids=[f"{i:02d}" for i in range(len(TITULOS))])
def test_proyecto_desde_el_titulo(title, expected):
    got = L.project_from_title(title)
    assert got == expected, (title, got)
    if got:
        assert got == got.strip() and len(got) <= 60
        assert not got.lower().endswith((".als", ".flp", ".rpp", ".cpr", ".song"))


@pytest.mark.parametrize("title,expected", [t for t in TITULOS if t[1]],
                         ids=[f"{i:02d}" for i, t in enumerate(TITULOS) if t[1]])
def test_titulo_detectado_suma_al_proyecto(fresh, title, expected):
    """El título real llega al conteo: el tiempo cae en ese proyecto."""
    from conftest import OS, open_daw, step
    app = fresh
    OS.title = title
    open_daw(app)
    step(app, 20)
    assert app.project_name() == expected
    assert app.data["proyectos"][expected]["segundos"] == pytest.approx(20, abs=4.5)
