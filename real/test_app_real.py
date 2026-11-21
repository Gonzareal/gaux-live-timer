"""Pruebas REALES: la app instalada de verdad (la misma que descargas), abierta en una Mac y en un
Windows de verdad, con DAWs falsos que son ventanas reales al frente. Nada simulado por dentro:
se lee lo que la app guarda en ~/.live_timer, se le habla por sus puertos y se mide su CPU y
memoria como lo vería el Monitor de Actividad.

Se corren después de instalar el instalador (workflow Instaladores)."""
import glob
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time

import psutil
import pytest

MAC = sys.platform == "darwin"
WIN = sys.platform == "win32"
pytestmark = pytest.mark.skipif(not (MAC or WIN), reason="solo en Mac y Windows")

HERE = os.path.dirname(os.path.abspath(__file__))
SHOTS = os.path.join(HERE, "capturas")
APP_DIR = os.path.join(os.path.expanduser("~"), ".live_timer")
CONF = os.path.join(APP_DIR, "config.json")
DATA = os.path.join(APP_DIR, "datos.json")
LOG = os.path.join(APP_DIR, "registro.txt")
LOCK_PORT, LINK_PORT = 47653, 47654
if MAC:
    APP_EXE = "/Applications/Gaux Live Timer.app/Contents/MacOS/Gaux Live Timer"
else:
    APP_EXE = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"),
                           "Gaux", "Gaux Live Timer", "Gaux Live Timer.exe")

# (nombre de la app o del .exe, ejecutable dentro del .app en Mac, título de la ventana,
#  DAW que debe anotar, proyecto que debe leer del título)
MAC_DAWS = [
    ("Ableton Live 12 Suite", "Live", "Divine  [Divine Project] - Ableton Live 12 Suite",
     "Ableton Live", "Divine"),
    ("Ableton Live 11 Standard", "Live", "Westing Time With U [Westing Time With U Project] - "
     "Ableton Live 11 Standard", "Ableton Live", "Westing Time With U"),
    ("FL Studio 2024", "OsxFL", "Tahelly.flp - FL Studio 2024", "FL Studio", "Tahelly"),
    ("Logic Pro", "Logic Pro X", "CRAZY SYNTHS - Tracks", "Logic Pro", "CRAZY SYNTHS"),
    ("Pro Tools", "Pro Tools", "Edit: Sesión Final", "Pro Tools", "Sesión Final"),
    ("Cubase 14", "Cubase 14", "Cubase Pro 14 Project - Remix.cpr", "Cubase", "Remix"),
    ("Nuendo 13", "Nuendo 13", "Nuendo Project - Score Film", "Nuendo", "Score Film"),
    ("Studio One 6", "Studio One 6", "Studio One - Demo.song", "Studio One", "Demo"),
    ("Bitwig Studio", "BitwigStudio", "Groove.bwproject - Bitwig Studio 5.2", "Bitwig Studio",
     "Groove"),
    ("REAPER", "REAPER", "Mi Track.rpp - REAPER v7.22", "REAPER", "Mi Track"),
    ("Reason 12", "Reason", "Rack.reason - Reason 12", "Reason", "Rack"),
    ("GarageBand", "GarageBand", "Idea - Tracks", "GarageBand", "Idea"),
    ("Ardour8", "Ardour8", "Club Mix.ardour - Ardour 8.4", "Ardour", "Club Mix"),
    ("Renoise", "Renoise", "Chip.xrns - Renoise 3.4", "Renoise", "Chip"),
    ("Digital Performer", "Digital Performer", "Film.dpdoc - Digital Performer",
     "Digital Performer", "Film"),
]
WIN_DAWS = [
    ("Ableton Live 12 Suite.exe", None, "Divine  [Divine Project] - Ableton Live 12 Suite",
     "Ableton Live", "Divine"),
    ("Ableton Live 11 Standard.exe", None, "Westing Time With U [Westing Time With U Project] - "
     "Ableton Live 11 Standard", "Ableton Live", "Westing Time With U"),
    ("FL64.exe", None, "Tahelly.flp - FL Studio 2024", "FL Studio", "Tahelly"),
    ("FL.exe", None, "Mi Beat - FL Studio 21", "FL Studio", "Mi Beat"),
    ("ProTools.exe", None, "Edit: Sesión Final", "Pro Tools", "Sesión Final"),
    ("Cubase14.exe", None, "Cubase Pro 14 Project - Remix.cpr", "Cubase", "Remix"),
    ("Cubase13.exe", None, "Cubase Pro Project - Club Edit", "Cubase", "Club Edit"),
    ("Nuendo13.exe", None, "Nuendo Project - Score Film", "Nuendo", "Score Film"),
    ("Studio One.exe", None, "Studio One - Demo.song", "Studio One", "Demo"),
    ("BitwigStudio.exe", None, "Groove.bwproject - Bitwig Studio 5.2", "Bitwig Studio", "Groove"),
    ("reaper.exe", None, "Mi Track - REAPER v7.22 - Registered to Gaux", "REAPER", "Mi Track"),
    ("Reason.exe", None, "Rack.reason - Reason 12", "Reason", "Rack"),
    ("Cakewalk.exe", None, "Cakewalk by BandLab - [Rock.cwp - Track]", "Cakewalk", "Rock"),
    ("Renoise.exe", None, "Chip.xrns - Renoise 3.4", "Renoise", "Chip"),
    ("ardour8.exe", None, "Club Mix.ardour - Ardour 8.4", "Ardour", "Club Mix"),
]
DAWS = MAC_DAWS if MAC else WIN_DAWS
TEMAS = ["gaux", "noche", "cristal", "neon", "atardecer", "medianoche", "personal"]


# ------------------------------------------------------------------ DAWs falsos (ventanas reales)
class Fakes:
    def __init__(self):
        self.dir = os.path.realpath(tempfile.mkdtemp(prefix="gaux_fake_"))
        if MAC:
            self.bin = os.path.join(self.dir, "fake_daw")
            subprocess.run(["clang", "-fobjc-arc", "-framework", "Cocoa", "-o", self.bin,
                            os.path.join(HERE, "fake_daw.m")], check=True)
        else:
            csc = sorted(glob.glob(r"C:\Windows\Microsoft.NET\Framework64\v4*\csc.exe"))[-1]
            self.bin = os.path.join(self.dir, "fake_daw.exe")
            subprocess.run([csc, "/nologo", "/target:winexe", "/out:" + self.bin,
                            os.path.join(HERE, "FakeDaw.cs")], check=True)
        self.running = []

    def _mac_bundle(self, name, exe):
        app = os.path.join(self.dir, f"{name}.app")
        if not os.path.exists(app):
            import plistlib
            os.makedirs(os.path.join(app, "Contents", "MacOS"))
            ident = "com.gauxprueba." + "".join(c for c in name if c.isalnum()).lower()
            with open(os.path.join(app, "Contents", "Info.plist"), "wb") as f:
                plistlib.dump({"CFBundleName": name, "CFBundleDisplayName": name,
                               "CFBundleExecutable": exe, "CFBundlePackageType": "APPL",
                               "CFBundleIdentifier": ident, "CFBundleVersion": "1.0",
                               "NSHighResolutionCapable": True}, f)
            shutil.copy(self.bin, os.path.join(app, "Contents", "MacOS", exe))
            subprocess.run(["codesign", "--force", "-s", "-", app], capture_output=True)
        return app, os.path.join(app, "Contents", "MacOS", exe)

    def open(self, name, exe, title, secs=300):
        """Abre la 'app' con su ventana al frente. Devuelve el ejecutable (para cerrarla)."""
        if MAC:
            app, path = self._mac_bundle(name, exe)
            subprocess.run(["open", "-n", app, "--args", title, str(secs)], check=True)
        else:
            path = os.path.join(self.dir, name)
            if not os.path.exists(path):
                shutil.copy(self.bin, path)
            subprocess.Popen([path, title, str(secs)])
        self.running.append(path)
        assert wait(lambda: any(_is(p, path) for p in psutil.process_iter(["exe", "name", "cmdline"])),
                    10), f"no se abrió {name}"
        time.sleep(1.0)
        return path

    def close(self, path):
        for p in psutil.process_iter(["exe", "name", "cmdline"]):
            if _is(p, path):
                try:
                    p.terminate()
                except psutil.Error:
                    pass
        assert wait(lambda: not any(_is(p, path) for p in psutil.process_iter(["exe", "name",
                                                                                "cmdline"])), 10), \
            f"no se cerró {path}"
        if path in self.running:
            self.running.remove(path)

    def close_all(self):
        for p in list(self.running):
            self.close(p)


def _norm(p):
    return os.path.normcase(os.path.realpath(p)) if p else ""


def _is(proc, path):
    try:
        exe = proc.info.get("exe") or ""
        cmd = proc.info.get("cmdline") or []
        want = _norm(path)
        return _norm(exe) == want or bool(cmd and _norm(cmd[0]) == want)
    except Exception:
        return False


# ------------------------------------------------------------------ la app
def wait(cond, t=10.0, step=0.25):
    end = time.monotonic() + t
    while time.monotonic() < end:
        try:
            if cond():
                return True
        except Exception:
            pass
        time.sleep(step)
    try:
        return bool(cond())
    except Exception:
        return False


def port_open(port=LOCK_PORT):
    try:
        socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
        return True
    except OSError:
        return False


def write_conf(**over):
    """Ajustes para la máquina de pruebas: sin pausa por inactividad (nadie toca el teclado)."""
    os.makedirs(APP_DIR, exist_ok=True)
    try:
        with open(CONF, encoding="utf-8") as f:
            c = json.load(f)
    except Exception:
        c = {}
    c["limite_inactividad"] = 24 * 3600
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(c.get(k), dict):
            c[k].update(v)
        else:
            c[k] = v
    with open(CONF, "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False)


def data():
    try:
        with open(DATA, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def total(d=None):
    d = data() if d is None else d
    return sum((d.get("dias") or {}).values())


def log_size():
    try:
        return os.path.getsize(LOG)
    except OSError:
        return 0


def new_log(since):
    try:
        with open(LOG, encoding="utf-8", errors="replace") as f:
            f.seek(since)
            return f.read()
    except OSError:
        return ""


ARRANQUES = []


def holder(port=LOCK_PORT):
    """Quién tiene tomado el puerto del timer (para entender un cierre que no soltó)."""
    out = []
    for p in psutil.process_iter(["pid", "name", "exe", "ppid", "create_time", "status"]):
        try:
            for c in p.net_connections(kind="tcp"):
                if c.laddr and c.laddr.port == port and c.status == psutil.CONN_LISTEN:
                    i = p.info
                    out.append(f"pid {i['pid']} {i['name']} ({i['exe']}) padre {i['ppid']} "
                               f"estado {i['status']} hace {time.time() - i['create_time']:.0f} s")
        except (psutil.Error, OSError):
            continue
    return out or ["nadie"]


class App:
    def __init__(self):
        self.proc = None

    def start(self):
        assert os.path.exists(APP_EXE), APP_EXE
        t0 = time.monotonic()
        self.proc = subprocess.Popen([APP_EXE], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ok = wait(port_open, 45)
        took = time.monotonic() - t0
        ARRANQUES.append(took)
        if not ok:
            raise AssertionError(f"la app no abrió en 45 s (¿sigue viva? {self.alive()}); "
                                 f"puerto tomado por: {holder()}; "
                                 f"registro: {new_log(max(0, log_size() - 1500))}")
        time.sleep(2.0)
        assert self.alive(), "la app se cerró sola al abrir"
        return self

    def alive(self):
        return self.proc is not None and self.proc.poll() is None

    def quit(self, t=15):
        if not self.alive():
            return
        try:
            c = socket.create_connection(("127.0.0.1", LOCK_PORT), timeout=2)
            c.sendall(b"QUIT")
            c.close()
        except OSError:
            pass
        try:
            self.proc.wait(t)
        except subprocess.TimeoutExpired:
            info = holder()
            self.proc.kill()
            raise AssertionError(f"la app no se cerró con QUIT; puerto: {info}")
        if not wait(lambda: not port_open(), 8):
            raise AssertionError(f"la app salió pero el puerto sigue tomado por: {holder()}")

    def kill(self):
        if self.alive():
            self.proc.kill()
            self.proc.wait(10)

    @property
    def ps(self):
        return psutil.Process(self.proc.pid)


def shot(name):
    os.makedirs(SHOTS, exist_ok=True)
    path = os.path.join(SHOTS, name + ".png")
    if MAC:
        subprocess.run(["screencapture", "-x", path], capture_output=True)
    else:
        from PIL import ImageGrab
        ImageGrab.grab().save(path)
    return path


# ------------------------------------------------------------------ fixtures
@pytest.fixture(scope="session")
def fakes():
    f = Fakes()
    yield f
    f.close_all()
    shutil.rmtree(f.dir, ignore_errors=True)


@pytest.fixture(scope="session", autouse=True)
def limpio():
    """Arranca de cero (en la máquina de pruebas no hay datos de nadie)."""
    for p in psutil.process_iter(["exe"]):
        if _is(p, APP_EXE):
            p.kill()
    if os.path.isdir(APP_DIR):
        shutil.rmtree(APP_DIR, ignore_errors=True)
    write_conf()
    yield


@pytest.fixture(scope="module")
def app():
    a = App()
    write_conf()
    a.start()
    yield a
    a.quit()


def mtime():
    try:
        return os.path.getmtime(DATA)
    except OSError:
        return 0.0


def esperar_guardado_al_cerrar(t_close, t=15):
    """La app guarda cuando nota que el DAW se cerró (lo revisa cada 3 s): se espera ESE
    guardado (posterior al cierre), no uno automático de mitad de sesión."""
    wait(lambda: mtime() > t_close + 0.2, t)
    time.sleep(1.0)


def contar_con(fakes, name, exe, title, secs=16):
    """Abre el DAW al frente 'secs' segundos y lo cierra. Devuelve los datos antes y después."""
    before = data()
    path = fakes.open(name, exe, title)
    time.sleep(secs)
    fakes.close(path)
    esperar_guardado_al_cerrar(time.time())
    return before, data()


# ================================================================== 1. abrir
def test_la_app_instalada_abre_y_queda_abierta(app):
    assert app.alive()
    assert port_open()


def test_crea_su_carpeta_y_sus_ajustes(app):
    assert os.path.isdir(APP_DIR)
    assert wait(lambda: os.path.exists(CONF), 10)
    with open(CONF, encoding="utf-8") as f:
        c = json.load(f)
    assert isinstance(c, dict)


def test_sin_daw_no_cuenta(app):
    t0 = total()
    time.sleep(10)
    assert total() == pytest.approx(t0, abs=0.5)


# ================================================================== 2. cada DAW, de verdad
@pytest.mark.parametrize("name,exe,title,daw,proj", DAWS, ids=[d[0] for d in DAWS])
def test_cuenta_con_cada_daw(app, fakes, name, exe, title, daw, proj):
    before, after = contar_con(fakes, name, exe, title)
    got = total(after) - total(before)
    assert 11 <= got <= 23, f"{name}: contó {got:.1f} s (estuvo ~17 s al frente)"
    # el tiempo cayó en un proyecto, con su DAW
    grown = {k: v["segundos"] - (before.get("proyectos", {}).get(k, {}).get("segundos", 0))
             for k, v in after.get("proyectos", {}).items()}
    k = max(grown, key=grown.get)
    assert grown[k] == pytest.approx(got, abs=3)
    assert after["proyectos"][k]["daw"] == daw
    if WIN:                                   # en Windows el título siempre se puede leer
        assert k == proj, f"leyó el proyecto «{k}» del título «{title}»"
    elif k != proj:                           # en Mac leer títulos pide un permiso del sistema
        print(f"[Mac] proyecto «{k}» (el título necesita permiso de Accesibilidad)")
    assert app.alive()


def test_dos_sesiones_de_verdad_del_mismo_proyecto(app, fakes):
    """Dos sesiones de más de un minuto (las más cortas no se anotan como sesión)."""
    name, exe, title, daw, proj = DAWS[0]
    n0 = len(data().get("sesiones", []))
    contar_con(fakes, name, exe, title, 66)
    assert wait(lambda: len(data().get("sesiones", [])) == n0 + 1, 10)
    # leer DESPUÉS de que se anotó la sesión (un guardado automático de cada 30 s puede caer
    # justo tras el cierre del DAW y antes de que el timer lo note)
    mid = data()
    _, after = contar_con(fakes, name, exe, title, 66)
    assert wait(lambda: len(data().get("sesiones", [])) == n0 + 2, 10)
    after = data()
    k = max(after["proyectos"], key=lambda n: after["proyectos"][n].get("ultima") or "")
    assert after["proyectos"][k]["segundos"] >= mid["proyectos"][k]["segundos"] + 55
    assert after["proyectos"][k]["sesiones"] == mid["proyectos"][k]["sesiones"] + 1
    s = after["sesiones"][-1]
    assert 58 <= s["segundos"] <= 75 and s["inicio"] < s["fin"]


# ================================================================== 3. solo cuenta lo real
def test_otra_app_al_frente_no_cuenta(app, fakes):
    other = ("Notas", "Notas", "Lista de compras") if MAC else ("Notas.exe", None, "Lista de compras")
    t0 = total()
    p = fakes.open(*other)
    time.sleep(10)
    fakes.close(p)
    time.sleep(2)
    assert total() == pytest.approx(t0, abs=1.0)


def test_daw_abierto_pero_detras_no_cuenta(app, fakes):
    """6 s con el DAW al frente y 14 s con otra app tapándolo: suma ~6 s, no 20."""
    name, exe, title, _, _ = DAWS[0]
    t0 = total()
    d = fakes.open(name, exe, title)
    time.sleep(6)
    other = ("Notas", "Notas", "Correo") if MAC else ("Notas.exe", None, "Correo")
    n = fakes.open(*other)                            # otra app pasa al frente
    time.sleep(14)
    fakes.close(d)                                    # se cierra el DAW mientras está detrás
    esperar_guardado_al_cerrar(time.time())
    fakes.close(n)
    got = total() - t0
    assert 2 <= got <= 12, f"con el DAW detrás siguió contando: sumó {got:.1f} s"


# ================================================================== 4. guardado real
def test_cerrar_con_quit_guarda_y_sale(fakes):
    a = App()
    write_conf()
    a.start()
    time.sleep(3)                               # que el timer termine de abrir antes del DAW
    t0 = total()
    name, exe, title, _, _ = DAWS[0]
    p = fakes.open(name, exe, title)
    time.sleep(14)
    a.quit()                                    # se cierra el timer con el DAW abierto
    fakes.close(p)
    assert not a.alive()
    assert total() - t0 >= 6, "al salir guardó lo que llevaba"


def test_reinicio_conserva_las_horas(fakes):
    t0 = total()
    a = App().start()
    time.sleep(4)
    assert total() == pytest.approx(t0, abs=0.5)
    a.quit()
    assert total() == pytest.approx(t0, abs=0.5)


def test_abrirla_otra_vez_reemplaza_a_la_anterior(fakes):
    a = App().start()
    b = App()
    b.proc = subprocess.Popen([APP_EXE], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    assert wait(lambda: not a.alive(), 15), "la primera debía cerrarse"
    assert wait(port_open, 20) and b.alive(), "la nueva queda abierta"
    time.sleep(2)
    assert b.alive()
    b.quit()


@pytest.mark.parametrize("modo", ["quit_y_abrir", "abrir_encima"])
def test_reabrir_enseguida_siempre_abre(fakes, modo):
    """Como al instalar una actualización: se cierra el timer y se vuelve a abrir al instante,
    5 veces seguidas. Antes, en Mac, el puerto quedaba 30 s ocupado y no reabría."""
    a = App().start()
    for i in range(5):
        if modo == "quit_y_abrir":
            a.quit()
            a = App().start()
        else:                                   # abrir otra mientras la anterior sigue abierta
            b = App()
            b.proc = subprocess.Popen([APP_EXE], stdout=subprocess.DEVNULL,
                                      stderr=subprocess.DEVNULL)
            assert wait(lambda: not a.alive(), 15), "la anterior debía cerrarse"
            assert wait(lambda: port_open() and b.alive(), 20), f"vuelta {i}: la nueva no abrió"
            a = b
        time.sleep(1.5)
        assert a.alive(), f"vuelta {i}"
    a.quit()


def test_ajustes_cambiados_sobreviven(fakes):
    write_conf(tema="noche", vista="compacta")
    a = App().start()
    time.sleep(3)
    a.quit()
    with open(CONF, encoding="utf-8") as f:
        c = json.load(f)
    assert c["tema"] == "noche" and c["vista"] == "compacta"
    write_conf(tema="gaux", vista="completa")


def test_archivo_danado_no_pierde_tus_horas(fakes):
    with open(DATA, "w", encoding="utf-8") as f:
        f.write('{"dias": {"2026-11-10": 3600, "2026-11')          # corte de luz a mitad
    a = App().start()
    try:
        assert glob.glob(DATA + ".dañado-*"), "guardó aparte el archivo dañado"
        name, exe, title, _, _ = DAWS[0]
        _, after = contar_con(fakes, name, exe, title, 10)
        assert total(after) >= 5, "sigue contando después"
    finally:
        a.quit()


def test_si_se_cuelga_el_sistema_se_guarda_lo_ultimo(fakes):
    """Apagón: matar la app de golpe a mitad de sesión. Se guarda solo cada 30 s."""
    a = App()
    write_conf()
    a.start()
    t0 = total()
    name, exe, title, _, _ = DAWS[0]
    p = fakes.open(name, exe, title)
    time.sleep(40)
    a.kill()
    fakes.close(p)
    assert total() - t0 >= 15, f"tras 40 s y un cierre de golpe quedó {total() - t0:.1f} s"
    b = App().start()                             # y abre bien después
    time.sleep(3)
    assert b.alive()
    b.quit()


# ================================================================== 5. Gaux Link de verdad
def gxhi(inst, sr, host, track):
    return b"GXHI" + bytes([1, 0, 0, 0]) + struct.pack("<II", inst, sr) + f"{host}\n{track}".encode()


def gxlk(inst, seq, sr, frames, ch=2):
    import math
    hdr = b"GXLK" + bytes([1, ch, 0, 0]) + struct.pack("<IIII", inst, seq, sr, frames)
    body = b"".join(struct.pack("<f", 0.5 * math.sin(2 * math.pi * 997 * (seq * frames + i) / sr))
                    for i in range(frames) for _ in range(ch))
    return hdr + body


@pytest.fixture(scope="module")
def con_analizador(fakes):
    write_conf(analizador={"activo": True})
    a = App().start()
    name, exe, title, _, _ = DAWS[0]
    p = fakes.open(name, exe, title)
    assert wait(lambda: _link_ack() is not None, 25), "el analizador no respondió a Gaux Link"
    yield a
    fakes.close(p)
    a.quit()
    write_conf(analizador={"activo": False})


def _link_ack(inst=7):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(1.0)
    try:
        s.sendto(gxhi(inst, 48000, "Ableton Live", "Master"), ("127.0.0.1", LINK_PORT))
        msg, _ = s.recvfrom(64)
        return msg if msg.startswith(b"GXAK") else None
    except OSError:
        return None
    finally:
        s.close()


def test_link_saluda_y_responde(con_analizador):
    msg = _link_ack(9)
    assert msg and len(msg) == 8


def test_link_recibe_audio_del_plugin(con_analizador):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    for i in range(1500):                         # ~4 s de audio a 48 kHz en bloques de 128
        s.sendto(gxlk(9, i, 48000, 128), ("127.0.0.1", LINK_PORT))
        if i % 40 == 0:
            time.sleep(0.1)
    s.close()
    time.sleep(1)
    assert con_analizador.alive() and _link_ack(9)


def test_link_aguanta_basura(con_analizador):
    import random
    rnd = random.Random(5)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    for _ in range(3000):
        s.sendto(bytes(rnd.getrandbits(8) for _ in range(rnd.randint(0, 1400))),
                 ("127.0.0.1", LINK_PORT))
    for bad in (b"GXLK", b"GXLK" + b"\xff" * 30, b"GXHI", b"GXHI" + b"\x00" * 12):
        s.sendto(bad, ("127.0.0.1", LINK_PORT))
    s.close()
    time.sleep(1)
    assert con_analizador.alive()
    assert _link_ack(11), "sigue respondiendo después de la basura"


def test_link_varios_plugins_a_la_vez(con_analizador):
    acks = [_link_ack(i) for i in (21, 22, 23)]
    assert all(acks)


def test_analizador_abierto_sigue_contando(con_analizador):
    t0 = total()
    time.sleep(35)                               # pasa al menos un guardado automático (30 s)
    assert total() - t0 >= 5


# ================================================================== 6. rendimiento real
@pytest.fixture(scope="module")
def medida(fakes):
    write_conf(bienvenida_vista=True)           # como en el uso diario
    a = App().start()
    yield a
    a.quit()


def _cpu(proc, secs):
    proc.cpu_percent(None)
    time.sleep(secs)
    return proc.cpu_percent(None)


def _perfil(pid):
    """Dónde gasta CPU la app (para el registro de la prueba)."""
    if MAC:
        p = psutil.Process(pid)
        c0 = p.cpu_times()
        time.sleep(5)
        c1 = p.cpu_times()
        print(f"usuario {(c1.user - c0.user) * 20:.1f} %  sistema {(c1.system - c0.system) * 20:.1f} %")
        out = subprocess.run(["sample", str(pid), "4", "-mayDie"], capture_output=True,
                             text=True).stdout
        i = out.find("Call graph:")
        j = out.find("Total number in stack")
        print(out[i:j if j > i else i + 9000][:9000])
    try:
        th = sorted(psutil.Process(pid).threads(), key=lambda t: -(t.user_time + t.system_time))
        print("hilos:", [(t.id, round(t.user_time + t.system_time, 2)) for t in th[:6]])
    except psutil.Error:
        pass


def _arbol(pid):
    p = psutil.Process(pid)
    return [p] + p.children(recursive=True)


def _cpu_total(procs):
    t = 0.0
    for q in procs:
        try:
            c = q.cpu_times()
            t += c.user + c.system
        except psutil.Error:
            pass
    return t


def _cpu_de(pid, secs=20):
    """CPU de la app y sus procesos hijos (en Windows la app corre en un proceso hijo)."""
    procs = _arbol(pid)
    c0, t0 = _cpu_total(procs), time.monotonic()
    time.sleep(secs)
    return 100 * (_cpu_total(procs) - c0) / (time.monotonic() - t0)


def _rss(pid):
    return sum(q.memory_info().rss for q in _arbol(pid)) / 2 ** 20


def _idle_tk_cpu():
    """Lo que gasta en esta máquina una ventana Tk vacía y oculta (la base de comparación)."""
    q = subprocess.Popen([sys.executable, "-c",
                          "import tkinter as t; r=t.Tk(); r.withdraw(); "
                          "r.after(250, lambda f=None: None); r.mainloop()"])
    try:
        time.sleep(6)
        return _cpu_de(q.pid, 20)
    finally:
        q.kill()


def _tk_script_cpu(code):
    q = subprocess.Popen([sys.executable, "-c", code])
    try:
        time.sleep(6)
        return _cpu_de(q.pid, 15)
    finally:
        q.kill()


def test_cpu_diagnostico_ventanas_tk():
    """Diagnóstico (no falla): cuánto gasta en esta máquina cada tipo de ventana Tk quieta."""
    base = "import tkinter as t; r=t.Tk(); r.withdraw(); "
    casos = {
        "Tk oculta": base + "r.mainloop()",
        "ventana normal": base + "w=t.Toplevel(r); t.Label(w,text='hola').pack(); r.mainloop()",
        "sin bordes + encima": base + "w=t.Toplevel(r); w.overrideredirect(True); "
                               "w.attributes('-topmost', True); t.Label(w,text='hola').pack(); "
                               "r.mainloop()",
        "sin bordes + encima + mano": base + "w=t.Toplevel(r); w.overrideredirect(True); "
                                      "w.attributes('-topmost', True); "
                                      "t.Label(w,text='hola',cursor='hand2').pack(); r.mainloop()",
        "after cada 250 ms": base + "f=lambda: r.after(250, f); f(); r.mainloop()",
        "after cada 400 ms + 1 s": base + "f=lambda: r.after(400, f); g=lambda: r.after(1000, g); "
                                   "f(); g(); r.mainloop()",
    }
    for k, code in casos.items():
        print(f"CPU {k}: {_tk_script_cpu(code):.1f} %")


def test_cpu_contando_sin_animaciones(fakes):
    """Diagnóstico: cuánto de la CPU contando es por las animaciones."""
    write_conf(bienvenida_vista=True, animaciones=False)
    a = App().start()
    name, exe, title, _, _ = DAWS[0]
    p = fakes.open(name, exe, title)
    try:
        time.sleep(5)
        print(f"CPU contando sin animaciones: {_cpu_de(a.proc.pid, 20):.1f} %")
    finally:
        fakes.close(p)
        a.quit()
        write_conf(animaciones=True)


@pytest.mark.parametrize("fps", ["30", "15"])
def test_cpu_contando_con_menos_cuadros(fakes, fps):
    """Elegir menos cuadros por segundo en Ajustes baja la CPU mientras cuenta."""
    write_conf(bienvenida_vista=True, animaciones=True, fps_timer=fps)
    a = App().start()
    name, exe, title, _, _ = DAWS[0]
    p = fakes.open(name, exe, title)
    try:
        time.sleep(5)
        print(f"CPU contando a {fps} fps: {_cpu_de(a.proc.pid, 20):.1f} %")
        assert a.alive()
    finally:
        fakes.close(p)
        a.quit()
        write_conf(fps_timer="auto")


def test_cpu_con_la_bienvenida_abierta():
    """La primera vez la bienvenida queda abierta hasta que tocas Listo: no debe gastar CPU."""
    write_conf(bienvenida_vista=False)
    a = App().start()
    try:
        time.sleep(8)
        cpu = _cpu_de(a.proc.pid, 20)
        print(f"CPU sin DAW (bienvenida abierta): {cpu:.1f} %")
        assert cpu < 6, cpu
    finally:
        a.quit()
        write_conf(bienvenida_vista=True)


def test_cpu_sin_daw_tras_la_bienvenida():
    """Como lo usa la gente: la bienvenida ya se vio una vez (el aviso corto se cierra solo)."""
    write_conf(bienvenida_vista=True)
    a = App().start()
    try:
        time.sleep(10)                         # el aviso "está activo" se cierra a los 7 s
        cpu = _cpu_de(a.proc.pid, 20)
        print(f"CPU sin DAW (bienvenida ya vista): {cpu:.1f} %")
        assert cpu < 6, cpu
    finally:
        a.quit()


def test_cpu_recien_abierto_y_con_otra_app():
    """CPU del timer sin DAW con el timer como app activa y con otra
    app (Finder / Explorador) al frente, que es lo normal mientras produces."""
    write_conf(bienvenida_vista=True)
    a = App().start()
    try:
        time.sleep(10)
        if MAC:
            print("al frente:", subprocess.run(["lsappinfo", "info", "-only", "name",
                                                subprocess.run(["lsappinfo", "front"],
                                                               capture_output=True, text=True
                                                               ).stdout.strip()],
                                               capture_output=True, text=True).stdout.strip())
        al_frente = _cpu_de(a.proc.pid, 15)
        if MAC:
            subprocess.run(["open", "-a", "Finder"])
        else:
            subprocess.Popen(["explorer.exe"])
        time.sleep(4)
        otra = _cpu_de(a.proc.pid, 15)
        print(f"CPU sin DAW: recién abierto {al_frente:.1f} %  ·  otra app al frente {otra:.1f} %")
        if max(al_frente, otra) >= 6:
            _perfil(a.proc.pid)
        assert otra < 6, (al_frente, otra)
    finally:
        a.quit()


def test_cpu_sin_daw_es_minima(medida):
    """Sin DAW el timer no dibuja nada: debe gastar casi lo mismo que una ventana Tk vacía."""
    time.sleep(8)
    cpu = _cpu_de(medida.proc.pid, 20)
    base = _idle_tk_cpu()
    print(f"CPU sin DAW: timer {cpu:.1f} %  ·  ventana Tk vacía en esta máquina {base:.1f} %")
    if cpu >= base + 4:
        _perfil(medida.proc.pid)
    assert cpu < max(6.0, base * 1.3 + 4), (cpu, base)


def test_cpu_y_memoria_contando(medida, fakes):
    name, exe, title, _, _ = DAWS[0]
    p = fakes.open(name, exe, title)
    try:
        time.sleep(4)
        cpu = _cpu_de(medida.proc.pid, 20)
        rss = _rss(medida.proc.pid)
        print(f"CPU contando: {cpu:.1f} %  memoria: {rss:.0f} MB")
        if cpu >= 25:
            _perfil(medida.proc.pid)
        assert cpu < 40, "no debe robarle CPU al DAW"
        assert rss < 400
        shot("contando")
    finally:
        fakes.close(p)


def test_memoria_no_crece(medida, fakes):
    name, exe, title, _, _ = DAWS[0]
    p = fakes.open(name, exe, title)
    try:
        time.sleep(5)
        m0 = _rss(medida.proc.pid)
        time.sleep(90)
        m1 = _rss(medida.proc.pid)
        print(f"memoria: {m0:.0f} -> {m1:.0f} MB en 90 s")
        assert m1 - m0 < 25
    finally:
        fakes.close(p)


# ================================================================== 7. cada estilo y vista en pantalla real
CASOS = [(t, v) for t in TEMAS for v in ("completa", "compacta", "mini")]


@pytest.mark.parametrize("tema,vista", CASOS, ids=[f"{t}-{v}" for t, v in CASOS])
def test_cada_estilo_y_vista_en_pantalla(fakes, tema, vista):
    write_conf(tema=tema, vista=vista, analizador={"activo": False})
    since = log_size()
    a = App().start()
    name, exe, title, _, _ = DAWS[0]
    p = fakes.open(name, exe, title)
    try:
        time.sleep(5)
        assert a.alive()
        if vista == "completa" or tema in ("gaux", "personal"):
            shot(f"{tema}-{vista}")
    finally:
        fakes.close(p)
        a.quit()
    log = new_log(since)
    assert "Traceback" not in log, log[-2000:]


def test_registro_sin_errores():
    with open(LOG, encoding="utf-8", errors="replace") if os.path.exists(LOG) else open(os.devnull) as f:
        log = f.read()
    assert "Traceback" not in log, log[-3000:]
    write_conf(tema="gaux", vista="completa")


# ================================================================== 8. dónde gasta CPU (diagnóstico)
def test_perfil_cpu_sin_daw():
    """Corre el mismo código de la app con un perfilador 25 s sin DAW y deja el informe en
    capturas/perfil_sin_daw.txt (no falla: es para ver qué consume)."""
    import textwrap
    os.makedirs(SHOTS, exist_ok=True)
    out = os.path.join(SHOTS, "perfil_sin_daw.txt")
    src = os.path.dirname(HERE)
    code = textwrap.dedent(f"""
        import cProfile, pstats, io, socket, sys, threading, time, os
        sys.path.insert(0, {src!r}); sys.argv = ["live_timer.py"]
        import live_timer as L
        import psutil
        me = psutil.Process()
        def stop():
            time.sleep(5); c0 = me.cpu_times(); t0 = time.time()
            time.sleep(25); c1 = me.cpu_times()
            used = (c1.user - c0.user) + (c1.system - c0.system)
            open({out!r} + ".cpu", "w").write(f"CPU (con perfilador) {{100 * used / (time.time() - t0):.1f}} %\\n")
            s = socket.create_connection(("127.0.0.1", 47653)); s.sendall(b"QUIT"); s.close()
        threading.Thread(target=stop, daemon=True).start()
        pr = cProfile.Profile(); pr.enable()
        try:
            L.main()
        except SystemExit:
            pass
        pr.disable()
        b = io.StringIO(); pstats.Stats(pr, stream=b).sort_stats("tottime").print_stats(30)
        b2 = io.StringIO(); pstats.Stats(pr, stream=b2).sort_stats("cumulative").print_stats(30)
        open({out!r}, "w").write(b.getvalue() + "\\n\\n" + b2.getvalue())
    """)
    for p in psutil.process_iter(["exe"]):
        if _is(p, APP_EXE):
            p.kill()
    write_conf()
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    print(r.stdout[-2000:], r.stderr[-3000:])
    assert os.path.exists(out)


def test_arranca_rapido():
    """Cuánto tarda en abrir la app instalada (se midió en cada arranque de estas pruebas)."""
    assert ARRANQUES
    print("arranques (s):", [round(x, 1) for x in ARRANQUES])
    med = sorted(ARRANQUES)[len(ARRANQUES) // 2]
    assert med < 12, f"la mitad de los arranques tardó más de {med:.1f} s"


# ================================================================== 9. Top Live: Accesibilidad directa
@pytest.mark.skipif(not MAC, reason="solo en Mac")
def test_top_live_mueve_la_ventana_con_accesibilidad(fakes):
    """El chequeo del permiso funciona en un Mac real y, si la máquina lo permite, Top Live
    mueve y redimensiona la ventana de un DAW sin osascript."""
    sys.path.insert(0, os.path.dirname(HERE))
    import live_timer as L
    t = L.mac_ax_trusted()
    assert t in (True, False), "el chequeo del permiso de Accesibilidad responde"
    name, exe, title, _, _ = DAWS[0]
    path = fakes.open(name, exe, title)
    try:
        pid = next(p.pid for p in psutil.process_iter(["exe", "name", "cmdline"]) if _is(p, path))
        if not t:
            pytest.skip("esta Mac de pruebas no le da Accesibilidad a Python")
        wins = L.ax_live_windows(pid)
        assert wins, "lee las ventanas del DAW"
        n = max(wins, key=lambda w: w[3] * w[4])[0]
        L.ax_set_live_window(pid, n, 120, 160, 760, 480)
        time.sleep(0.6)
        _, x, y, w, h = [v for v in L.ax_live_windows(pid) if v[0] == n][0]
        print(f"ventana movida a {x},{y} {w}x{h}")
        assert abs(x - 120) <= 4 and abs(y - 160) <= 4 and abs(w - 760) <= 4 and abs(h - 480) <= 4
    finally:
        fakes.close(path)


# ================================================================== 10. break con el mouse de verdad
def _mouse_ok():
    """En Mac, mandar clics del sistema pide Accesibilidad para quien corre las pruebas."""
    if not MAC:
        return True
    import ctypes
    ax = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
    ax.AXIsProcessTrusted.restype = ctypes.c_bool
    return bool(ax.AXIsProcessTrusted())


def mouse_click(x, y):
    """Un clic real del sistema (el mismo que hace el mouse) en (x, y) de la pantalla."""
    import ctypes
    x, y = int(round(x)), int(round(y))
    if WIN:
        u = ctypes.windll.user32
        u.SetCursorPos(x, y)
        time.sleep(0.25)
        u.mouse_event(0x0002, 0, 0, 0, 0)          # botón izquierdo abajo
        time.sleep(0.06)
        u.mouse_event(0x0004, 0, 0, 0, 0)          # arriba
    else:
        cg = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")

        class CGPoint(ctypes.Structure):
            _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]
        cg.CGEventCreateMouseEvent.restype = ctypes.c_void_p
        cg.CGEventCreateMouseEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint32, CGPoint,
                                               ctypes.c_uint32]
        cg.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
        cg.CFRelease.argtypes = [ctypes.c_void_p]
        for kind, pause in ((5, 0.25), (1, 0.06), (2, 0.0)):    # mover, abajo, arriba
            ev = cg.CGEventCreateMouseEvent(None, kind, CGPoint(x, y), 0)
            cg.CGEventPost(0, ev)
            cg.CFRelease(ev)
            time.sleep(pause)
    time.sleep(0.5)


def _boton_break(since, vista):
    """Dónde dibujó la app el botón de break (lo anota en su registro al armar la vista)."""
    import re
    pat = re.compile(r"vista: (\S+) (\d+)x(\d+) break=(-?\d+),(-?\d+)")
    found = None
    for m in pat.finditer(new_log(since)):
        if m.group(1) == vista:
            found = m
    assert found, f"la app no anotó la vista {vista}: {new_log(since)[-1500:]}"
    W, H, cx, cy = (int(found.group(i)) for i in (2, 3, 4, 5))
    assert 0 < cx < W and 0 < cy < H, "el botón queda dentro del timer"
    return cx, cy


VISTAS_BREAK = [("completa", "horizontal"), ("compacta", "horizontal"), ("mini", "horizontal"),
                ("completa", "vertical"), ("compacta", "vertical"), ("mini", "vertical")]


@pytest.mark.parametrize("vista,orient", VISTAS_BREAK, ids=[f"{v}-{o}" for v, o in VISTAS_BREAK])
def test_break_con_el_mouse(fakes, vista, orient):
    """Con el DAW al frente: clic real en la taza → empieza el break (el tiempo del proyecto
    se detiene), el break termina y NO vuelve solo, clic en la taza otra vez → vuelve. La
    sesión guardada trae las dos medidas: total y trabajo real, con su break."""
    if not _mouse_ok():
        pytest.skip("esta Mac de pruebas no deja mandar clics del sistema (Accesibilidad)")
    key = vista + ("_v" if orient == "vertical" else "")
    X, Y = 420, 120
    largo = vista == "completa" and orient == "horizontal"     # el ciclo entero, una vez
    write_conf(tema="gaux", vista=vista, orientacion=orient, modo="autonomo",
               pos={key: [X, Y]}, escala={key: 1.0}, analizador={"activo": False},
               autonomo={"trabajo_min": 50, "break_min": 1, "max_diario_h": 0},
               animaciones=True)
    since = log_size()
    a = App().start()
    name, exe, title, _, _ = DAWS[0]
    n0 = len(data().get("sesiones", []))
    p = fakes.open(name, exe, title)
    try:
        time.sleep(63)                                   # trabajo (la sesión dura más de 1 min)
        cx, cy = _boton_break(since, key)
        mouse_click(X + cx, Y + cy)                      # ☕ tomar el break
        t_brk = time.monotonic()
        time.sleep(3)
        shot(f"break-{key}-en-curso")
        time.sleep(72 if largo else 5)                   # el break de 1 min termina (largo)
        if largo:
            shot(f"break-{key}-terminado-espera-volver")
        mouse_click(X + cx, Y + cy)                      # volver del break
        brk = time.monotonic() - t_brk
        time.sleep(6)
        shot(f"break-{key}-de-vuelta")
    finally:
        fakes.close(p)
    esperar_guardado_al_cerrar(time.time())
    assert wait(lambda: len(data().get("sesiones", [])) == n0 + 1, 10), "no se guardó la sesión"
    s = data()["sesiones"][-1]
    a.quit()
    print(f"{key}: {s}")
    assert s.get("n_breaks") == 1, f"el clic en la taza no inició el break: {s}"
    assert s["breaks"] == pytest.approx(brk, abs=4), f"break medido {s['breaks']} s, real {brk:.0f} s"
    # trabajo real: 63 s antes + 6 s después (si hubiera vuelto solo, sumaría ~15 s más)
    assert 62 <= s["segundos"] <= 76, f"trabajo real {s['segundos']} s"
    assert s["total"] >= s["segundos"] + s["breaks"] - 1
    assert s["total"] == pytest.approx(s["segundos"] + s["breaks"] + s["ausencias"], abs=2)
    log = new_log(since)
    assert "Traceback" not in log, log[-2000:]
