"""DAWs compatibles: reconocer cada programa y leer el proyecto del título de su ventana."""
import pytest

import live_timer as L

ALL = [k for k, _, _ in L.DAWS]

# (nombre del proceso o de la app, DAW esperado)
PROCESOS = [
    # Ableton Live
    ("Live", "Ableton Live"), ("Ableton Live 12 Suite", "Ableton Live"),
    ("Ableton Live 11 Standard", "Ableton Live"), ("Ableton Live 12 Lite", "Ableton Live"),
    ("Ableton Live 12 Suite.exe", "Ableton Live"), ("Ableton Live 10 Intro", "Ableton Live"),
    ("/Applications/Ableton Live 12 Suite.app/Contents/MacOS/Live", "Ableton Live"),
    ("ABLETON LIVE 12 SUITE", "Ableton Live"),
    # FL Studio
    ("FL Studio", "FL Studio"), ("FL Studio 2024", "FL Studio"), ("FL64.exe", "FL Studio"),
    ("FL.exe", "FL Studio"), ("fl64", "FL Studio"), ("OsxFL", "FL Studio"),
    ("/Applications/FL Studio 2024.app/Contents/MacOS/OsxFL", "FL Studio"),
    # Logic
    ("Logic Pro", "Logic Pro"), ("Logic Pro X", "Logic Pro"),
    ("/Applications/Logic Pro X.app/Contents/MacOS/Logic Pro X", "Logic Pro"),
    # Pro Tools
    ("Pro Tools", "Pro Tools"), ("ProTools.exe", "Pro Tools"), ("Pro Tools Intro", "Pro Tools"),
    # Cubase / Nuendo
    ("Cubase 14", "Cubase"), ("Cubase14.exe", "Cubase"), ("Cubase Pro 13", "Cubase"),
    ("Nuendo 13", "Nuendo"), ("Nuendo13.exe", "Nuendo"),
    # Studio One
    ("Studio One 6", "Studio One"), ("Studio One.exe", "Studio One"), ("StudioOne", "Studio One"),
    # Bitwig
    ("Bitwig Studio", "Bitwig Studio"), ("BitwigStudio.exe", "Bitwig Studio"),
    ("bitwig-studio", "Bitwig Studio"),
    # REAPER
    ("REAPER", "REAPER"), ("reaper.exe", "REAPER"), ("reaper64.exe", "REAPER"),
    ("/Applications/REAPER.app/Contents/MacOS/REAPER", "REAPER"),
    # Reason
    ("Reason", "Reason"), ("Reason 12", "Reason"), ("Reason.exe", "Reason"),
    ("/Applications/Reason 12.app/Contents/MacOS/Reason", "Reason"),
    # otros
    ("GarageBand", "GarageBand"), ("Cakewalk", "Cakewalk"), ("Cakewalk.exe", "Cakewalk"),
    ("Ardour8", "Ardour"), ("ardour-8.4", "Ardour"), ("Renoise", "Renoise"),
    ("Renoise.exe", "Renoise"), ("Digital Performer", "Digital Performer"),
    ("Digital Performer 11", "Digital Performer"),
]

NO_DAW = ["Finder", "Safari", "Google Chrome", "Spotify", "Liveshare", "LiveView",
          "Treason", "Reasonable", "Logic", "Microsoft Teams", "Bitwarden", "OBS Studio",
          "Max", "Splice", "Serum", "Terminal", "Gaux Live Timer", "Python", "Flux",
          "Discord", "zoom.us", "Music", "", "   ", "Lively", "Olive", "Delivery",
          "Studio Display", "Photoshop", "explorer.exe", "Docker", "Xcode"]


@pytest.fixture(autouse=True)
def _all_targets():
    L.configure_targets(ALL, [])
    yield
    L.configure_targets(ALL, [])


@pytest.mark.parametrize("name,daw", PROCESOS)
def test_reconoce_proceso(name, daw):
    assert L.daw_match(name) == daw


@pytest.mark.parametrize("name", NO_DAW)
def test_no_confunde_otras_apps(name):
    assert L.daw_match(name) is None


@pytest.mark.parametrize("name,daw", PROCESOS)
def test_desactivar_daw_lo_ignora(name, daw):
    key = next(k for k, n, _ in L.DAWS if n == daw)
    L.configure_targets([k for k in ALL if k != key], [])
    assert L.daw_match(name) != daw


@pytest.mark.parametrize("extra,proc,ok", [
    ("Mixbus", "Mixbus 10", True), ("Harrison Mixbus", "harrison mixbus32c", True),
    ("Waveform", "Waveform 13", True), ("waveform, mixcraft", "Mixcraft 10", True),
    ("  Tracktion  ,", "Tracktion", True), ("Mixbus", "Safari", False),
    ("", "Mixbus", False), (",,,", "Mixbus", False),
])
def test_apps_extra(extra, proc, ok):
    L.configure_targets(ALL, extra.split(","))
    assert (L.daw_match(proc) is not None) == ok


@pytest.mark.parametrize("name,daw", PROCESOS[:12])
def test_is_live_name_recuerda_el_daw(name, daw):
    L.CURRENT_DAW[0] = "x"
    assert L.is_live_name(name)
    assert L.CURRENT_DAW[0] == daw


# (título de la ventana, proyecto esperado)
TITULOS = [
    # Ableton Live (Mac y Windows; con y sin cambios sin guardar)
    ("CRAZY SYNTHS  [CRAZY SYNTHS Project] - Ableton Live 12 Suite", "CRAZY SYNTHS"),
    ("CRAZY SYNTHS* [CRAZY SYNTHS Project] - Ableton Live 12 Suite", "CRAZY SYNTHS"),
    ("Westing Time With U [Westing Time With U Project] - Ableton Live 11", "Westing Time With U"),
    ("Tahelly Project - Ableton Live 12 Suite", "Tahelly Project"),
    ("Mi Track (Orginal Mix) [Mi Track Project] - Ableton Live 12 Lite", "Mi Track (Orginal Mix)"),
    ("Canción ñandú [Canción Project] - Ableton Live 12", "Canción ñandú"),
    ("Untitled - Ableton Live 12 Suite", None),
    ("Untitled* - Ableton Live 12 Suite", None),
    ("Sin título - Ableton Live 12 Suite", None),
    ("Ableton Live 12 Suite", None),
    ("Live", None),
    ("ID 2024 v3.als - Ableton Live 12", "ID 2024 v3"),
    ("Track_01 - copia [Track_01 Project] - Ableton Live 12 Suite", "Track_01 - copia"),
    # FL Studio
    ("Mi Beat.flp - FL Studio 2024", "Mi Beat"),
    ("FL Studio 2024 - Mi Beat", "Mi Beat"),
    ("Mi Beat - FL Studio 21", "Mi Beat"),
    ("Untitled - FL Studio 21", None),
    ("FL Studio 21", None),
    # Logic Pro
    ("Mi Track - Tracks", "Mi Track"),
    ("Mi Track.logicx - Tracks", "Mi Track"),
    ("Mi Track - Mixer", "Mi Track"),
    ("Untitled - Tracks", None),
    ("Logic Pro", None),
    # Pro Tools
    ("Edit: Mi Sesión", "Mi Sesión"),
    ("Mix: Mi Sesión", "Mi Sesión"),
    ("Mi Sesión.ptx - Pro Tools", "Mi Sesión"),
    ("Pro Tools", None),
    # Cubase / Nuendo
    ("Cubase Pro Project - Mi Track", "Mi Track"),
    ("Cubase Pro Project - Mi Track.cpr", "Mi Track"),
    ("Nuendo Project - Score Final", "Score Final"),
    ("Cubase Pro 14", None),
    # Studio One
    ("Studio One - Mi Track", "Mi Track"),
    ("Mi Track.song - Studio One", "Mi Track"),
    ("Studio One 6", None),
    # Bitwig
    ("Mi Track - Bitwig Studio", "Mi Track"),
    ("Mi Track.bwproject - Bitwig Studio 5.2", "Mi Track"),
    ("Bitwig Studio", None),
    # REAPER
    ("Mi Track - REAPER v7.22 - Registered to Gaux (Licensed for personal/small business use)",
     "Mi Track"),
    ("Mi Track.rpp - REAPER v7.22", "Mi Track"),
    ("[Unsaved project] - REAPER v7.22 - Registered to Gaux", None),
    ("REAPER v7.22 - Registered to Gaux (Licensed for personal/small business use)", None),
    ("REAPER v7.22 - EVALUATION LICENSE", None),
    # Reason
    ("Mi Track - Reason", "Mi Track"),
    ("Mi Track.reason - Reason 12", "Mi Track"),
    ("Reason 12", None),
    # GarageBand
    ("Mi Canción - Tracks", "Mi Canción"),
    ("Mi Canción.band", "Mi Canción"),
    ("GarageBand", None),
    # Cakewalk (el proyecto va entre corchetes)
    ("Cakewalk by BandLab - [Mi Track.cwp - Track]", "Mi Track"),
    ("Cakewalk by BandLab - [Mi Track - Console]", "Mi Track"),
    ("Cakewalk by BandLab", None),
    # Ardour
    ("Mi Track - Ardour", "Mi Track"),
    ("Mi Track - Editor - Ardour 8.4", "Mi Track"),
    ("Ardour 8", None),
    # Renoise
    ("Mi Track.xrns - Renoise 3.4", "Mi Track"),
    ("Renoise 3.4", None),
    # Digital Performer
    ("Mi Track.dpdoc - Digital Performer", "Mi Track"),
    ("Digital Performer 11", None),
    # casos raros
    ("", None), ("   ", None), (None, None), ("- - -", None), ("[]", None),
    ("*", None), ("•", None), ("Untitled", None), ("New Project", None),
    ("Nuevo proyecto", None), ("Sans titre", None), ("Unbenannt", None),
    ("Senza titolo", None), ("A" * 200 + " - Ableton Live 12", "A" * 60),
    ("Untitled Love Song - Ableton Live 12", "Untitled Love Song"),
    ("Live Set Yez Botero - Ableton Live 12", "Live Set Yez Botero"),
    ("Mix final | Ableton Live 12", "Mix final"),
    ("Mi—Track — Ableton Live 12", "Mi—Track"),
]


@pytest.mark.parametrize("title,proj", TITULOS)
def test_proyecto_desde_titulo(title, proj):
    got = L.project_from_title(title)
    assert got == proj, (title, got)


@pytest.mark.parametrize("title,proj", [t for t in TITULOS if t[1]])
def test_proyecto_nunca_vacio_ni_largo(title, proj):
    got = L.project_from_title(title)
    assert got and got.strip() == got and len(got) <= 60
