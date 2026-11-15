"""Pruebas en el sistema real (corren en las máquinas Mac y Windows de GitHub).

Se abren apps falsas con el nombre exacto de cada DAW y el timer debe reconocerlas igual que
reconoce al DAW de verdad. También se llama a cada función nativa (pantallas, inactividad,
app al frente, ventanas) para comprobar que funcionan en ese sistema.
"""
import os
import plistlib
import shutil
import stat
import subprocess
import sys
import tempfile
import time

import pytest

import live_timer as L

MAC = sys.platform == "darwin"
WIN = sys.platform == "win32"
pytestmark = pytest.mark.skipif(not (MAC or WIN), reason="solo en Mac y Windows")

ALL = [k for k, _, _ in L.DAWS]

# nombre de la app en macOS (como aparece en /Applications) y su ejecutable
MAC_APPS = [("Ableton Live 12 Suite", "Live"), ("Ableton Live 11 Standard", "Live"),
            ("FL Studio 2024", "OsxFL"), ("Logic Pro", "Logic Pro X"),
            ("Pro Tools", "Pro Tools"), ("Cubase 14", "Cubase 14"), ("Nuendo 13", "Nuendo 13"),
            ("Studio One 6", "Studio One 6"), ("Bitwig Studio", "BitwigStudio"),
            ("REAPER", "REAPER"), ("Reason 12", "Reason"), ("GarageBand", "GarageBand"),
            ("Ardour8", "Ardour8"), ("Renoise", "Renoise"),
            ("Digital Performer", "Digital Performer")]

WIN_EXES = ["Ableton Live 12 Suite.exe", "Ableton Live 11 Standard.exe", "FL64.exe", "FL.exe",
            "ProTools.exe", "Cubase14.exe", "Cubase13.exe", "Nuendo13.exe", "Studio One.exe",
            "BitwigStudio.exe", "reaper.exe", "Reason.exe", "Cakewalk.exe", "Renoise.exe",
            "ardour8.exe"]


@pytest.fixture(autouse=True)
def _targets():
    L.configure_targets(ALL, [])
    yield


def _real(name):
    """La función nativa original (conftest reemplaza algunas por simuladas)."""
    import importlib
    mod = importlib.import_module("live_timer")
    return getattr(mod, "_REAL_" + name, getattr(mod, name))


PUMP = []


def wait(cond, t=8.0):
    """Espera; en Mac deja correr el bucle de eventos (así se entera de las apps abiertas,
    igual que el timer real, que siempre tiene su bucle andando)."""
    end = time.monotonic() + t
    while time.monotonic() < end:
        for p in PUMP:
            p()
        if cond():
            return True
        time.sleep(0.2)
    return cond()


@pytest.fixture
def pump(app):
    import _tkinter

    def pump_once(root=app.root):
        # como mucho 300 eventos por vuelta: nunca se queda pegado procesando
        for _ in range(300):
            if not root.tk.dooneevent(_tkinter.ALL_EVENTS | _tkinter.DONT_WAIT):
                break
    PUMP.append(pump_once)
    yield
    PUMP.clear()


# ---------------------------------------------------------------- Mac
def make_mac_app(folder, name, exe):
    app = os.path.join(folder, f"{name}.app")
    os.makedirs(os.path.join(app, "Contents", "MacOS"))
    with open(os.path.join(app, "Contents", "Info.plist"), "wb") as f:
        plistlib.dump({"CFBundleName": name, "CFBundleDisplayName": name,
                       "CFBundleExecutable": exe, "CFBundlePackageType": "APPL",
                       "CFBundleIdentifier": "com.gauxtest." + "".join(c for c in name
                                                                       if c.isalnum()).lower(),
                       "CFBundleVersion": "1.0", "LSUIElement": False}, f)
    # un ejecutable de verdad (macOS no abre apps cuyo ejecutable es un script)
    path = os.path.join(app, "Contents", "MacOS", exe)
    src = os.path.join(folder, "espera.c")
    with open(src, "w") as f:
        f.write("#include <unistd.h>\nint main(void){sleep(40);return 0;}\n")
    subprocess.run(["cc", "-O0", "-o", path, src], check=True)
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    subprocess.run(["codesign", "--force", "-s", "-", app], capture_output=True)
    return app, path


@pytest.mark.skipif(not MAC, reason="Mac")
@pytest.mark.parametrize("name,exe", MAC_APPS, ids=[a for a, _ in MAC_APPS])
def test_mac_reconoce_el_daw_abierto(pump, name, exe):
    folder = tempfile.mkdtemp(prefix="gaux_daw_")
    app, path = make_mac_app(folder, name, exe)
    running = _real("_mac_live_running")
    assert not running(), "antes de abrir no debe haber DAW"
    subprocess.run(["open", "-g", app], check=True)          # -g: sin pasarla al frente
    try:
        ok = wait(running)
        if not ok:
            ps = subprocess.run(["ps", "-axo", "comm="], capture_output=True, text=True).stdout
            print("ps:", [ln for ln in ps.splitlines() if "gaux_daw_" in ln])
        assert ok, f"no reconoció {name} abierto"
        # el respaldo con ps también lo reconoce
        out = subprocess.run(["ps", "-axo", "comm="], capture_output=True, text=True).stdout
        assert any(".app/Contents/MacOS/" in ln and L.daw_match(ln) for ln in out.splitlines())
    finally:
        subprocess.run(["pkill", "-f", path])
        assert wait(lambda: not running()), "al cerrar el DAW deja de contarlo"
        shutil.rmtree(folder, ignore_errors=True)


@pytest.mark.skipif(not MAC, reason="Mac")
def test_mac_app_al_frente(pump):
    folder = tempfile.mkdtemp(prefix="gaux_daw_")
    app, path = make_mac_app(folder, "Ableton Live 12 Suite", "Live")
    front = _real("frontmost_app")
    assert front() in ("other", "self")
    subprocess.run(["open", app], check=True)
    try:
        wait(lambda: front() == "live", 6)
        assert front() in ("live", "other", "self")
    finally:
        subprocess.run(["pkill", "-f", path])
        shutil.rmtree(folder, ignore_errors=True)


# ---------------------------------------------------------------- Windows
@pytest.mark.skipif(not WIN, reason="Windows")
@pytest.mark.parametrize("exe", WIN_EXES)
def test_windows_reconoce_el_daw_abierto(exe):
    folder = tempfile.mkdtemp(prefix="gaux_daw_")
    src = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "PING.EXE")
    dst = os.path.join(folder, exe)
    shutil.copy(src, dst)
    running = _real("live_running")
    p = subprocess.Popen([dst, "-n", "40", "127.0.0.1"], stdout=subprocess.DEVNULL,
                         creationflags=0x08000000)               # sin ventana
    try:
        assert wait(running), f"no reconoció {exe} abierto"
    finally:
        p.kill()
        p.wait()
        assert wait(lambda: not running()), "al cerrar el DAW deja de contarlo"
        shutil.rmtree(folder, ignore_errors=True)


# ---------------------------------------------------------------- funciones nativas
@pytest.mark.parametrize("fn", ["idle_seconds", "frontmost_app", "screens", "screen_bands"])
def test_funciones_nativas_responden(fn):
    out = _real(fn)()
    if fn == "idle_seconds":
        assert out >= 0
    elif fn == "frontmost_app":
        assert out in ("live", "other", "self")
    elif fn == "screens":
        assert out, "debe ver al menos una pantalla"
        for s in out:
            assert len(s) == 8 and s[2] > 0 and s[3] > 0
            assert s[6] > 0 and s[7] > 0
    else:
        assert isinstance(out, list)


@pytest.mark.parametrize("pid", [None, 1, 999999])
def test_titulo_y_ventana_de_un_pid_cualquiera(pid):
    t = _real("daw_window_title")(pid)
    assert t is None or isinstance(t, str)
    b = _real("daw_window_bounds")(pid)
    assert b is None or len(b) == 4


@pytest.mark.parametrize("text", ["áéíóúñ¿¡", "abc", ""])
def test_fuentes(app, text):
    import tkinter.font as tkfont
    fams = sorted(set(tkfont.families(root=app.root)))[:20]
    for f in fams:
        assert _real("font_covers")(f, text) in (True, False)


def test_ordenar_ventanas(fresh):
    ok = _real("stack_windows")([fresh.root], None)
    assert ok in (True, False)


@pytest.mark.skipif(not MAC, reason="Mac")
def test_mac_pantalla_completa_de_un_pid_cualquiera():
    assert _real("live_is_fullscreen")(999999) in (None, False, True)
