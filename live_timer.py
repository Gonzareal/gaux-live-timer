#!/usr/bin/env python3
"""
Gaux Live Timer — contador de tiempo REAL de trabajo en Ableton Live.

- Aparece solo cuando Ableton Live está abierto y se oculta al cerrarlo.
- Cuenta únicamente con Live (o sus plugins) en primer plano y con actividad
  de teclado/mouse. Minimizado sigue contando con la misma regla.
- Metas diaria / semanal / mensual personalizables.
- Modo autónomo: vigila tu racha de trabajo y te pide un break.
- Historial en ~/.live_timer/

Uso:
    python3 live_timer.py                    -> ejecutar
    python3 live_timer.py --demo             -> vista previa sin Live
    python3 live_timer.py --demo --rapido    -> vista previa con el tiempo x60
    python3 live_timer.py --instalar-inicio  -> arrancar con el sistema
    python3 live_timer.py --quitar-inicio    -> quitar del arranque
"""
import copy
import functools
import datetime as dt
import json
import math
import os
import platform
import random
import re
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont

try:
    import psutil
except ImportError:
    psutil = None

APP_NAME = "Gaux Live Timer"
VERSION = "1.0"
SYSTEM = platform.system()          # "Darwin", "Windows", "Linux"
# ¿Corre como app empaquetada (Gaux Live Timer.app / .exe) o como script en la Terminal?
FROZEN = bool(getattr(sys, "frozen", False))
# A quién le da macOS los permisos (Micrófono, Accesibilidad, Grabación de pantalla)
HOST_APP = APP_NAME if FROZEN else ("Terminal" if SYSTEM == "Darwin" else "Python")
AT_LOGIN = "--login" in sys.argv     # lo abrió el arranque automático al iniciar sesión
DEMO = "--demo" in sys.argv
SPEED = 60.0 if "--rapido" in sys.argv else 1.0
APP_DIR = os.path.join(os.path.expanduser("~"), ".live_timer")
DATA_FILE = os.path.join(APP_DIR, "datos_demo.json" if DEMO else "datos.json")
CONF_FILE = os.path.join(APP_DIR, "config.json")
LOCK_PORT = 47653
# tamaño del widget al arrastrar su borde: (mínimo, máximo) por vista
ESCALA_LIM = {"mini": (0.6, 2.2), "otra": (0.75, 2.0)}
MIN_FONT = 8                    # ningún texto baja de 8 pt al achicar
TOP_H = 132                     # alto de la franja del modo Top Live Performance
TOP_DESC = ("Top Live Performance acopla el timer y el analizador en una franja arriba de "
            "tu DAW y baja su ventana justo debajo, para que ningún botón, el navegador "
            "ni las pistas queden tapados. Al desactivarlo, la ventana vuelve a su tamaño. "
            "Ideal para producir viendo tu tiempo y tus medidores a la vez.")
FULLSCREEN_MAC = ("Tu DAW está en pantalla completa de macOS y su ventana no se puede mover.\n\n"
                  "Sal de pantalla completa (ctrl + cmd + F), maximiza la ventana con doble "
                  "clic en su barra de título y activa el modo otra vez.")

DEFAULT_CONF = {
    "tema": "noche",
    "opacidad": 0.95,
    "animaciones": True,
    "vista": "completa",            # completa | compacta | mini
    "vista_previa": "completa",
    "orientacion": "horizontal",    # horizontal | vertical
    "modo": "autonomo",             # normal | autonomo
    "fuente_titulo": None,
    "fuente_reloj": None,
    "limite_inactividad": 300,      # segundos sin tocar nada antes de pausar
    "metas": {
        "diaria": {"activa": True, "nombre": "Hoy", "segundos": 4 * 3600},
        "semanal": {"activa": True, "nombre": "Semana", "segundos": 20 * 3600},
        "mensual": {"activa": False, "nombre": "Mes", "segundos": 80 * 3600},
    },
    "autonomo": {
        "trabajo_min": 50,          # minutos de trabajo seguido antes del break
        "break_min": 5,             # duración del break
        "max_diario_h": 8,          # alerta al llegar a estas horas en el día
    },
    "x": None,
    "y": None,
    "pos": {},                      # posición guardada por vista
    "proyecto": "",                 # proyecto elegido a mano ("" = Sin asignar)
    "proyecto_auto": True,          # detectar el proyecto desde el título del DAW
    "daws": None,                   # DAWs vigilados (None = todos los conocidos)
    "daws_extra": "",               # otras apps, separadas por comas
    "escala": {},                   # tamaño del widget por vista (1.0 = original)
    "top_escala": 100,              # tamaño de la franja Top Live, en %
    "analizador": {
        "activo": False,
        "dispositivo": "auto",
        "color_onda": "tema",           # tema | rgb
        "rendimiento": "equilibrado",   # maximo | equilibrado | ahorro
        "modulos": {"wave": True, "spec": True, "stereo": True, "lufs": True},
        "x": None, "y": None, "w": 900, "h": 172,
    },
    "personal": {
        "nombre": "Tu nombre",          # título del timer
        "inicio": "LET'S GO",           # frase al abrir el DAW (sin restricciones)
        "cierre": "GG",                 # titular de la tarjeta al cerrar el DAW
        "color": "#3B82F6",
        "forma": "redondeada",          # redondeada | angular
        "efectos": True,                # rayos, glitch del título y barrido
    },
}

# --------------------------------------------------------------------------
# Estilos
# --------------------------------------------------------------------------
TEMAS = {
    "gaux": dict(nombre="Gaux Mode", bg="#08080A", bg2="#2B0A0F",
                 borde="#E0242F", acento="#D71E2B", acento2="#FF3B47",
                 texto="#F4F4F5", dim="#8E8E96", pista="#1E1E22", alpha=0.95,
                 alerta="#FFFFFF", marca=True,
                 onda=("#FF2233", "#7A7A82", "#D8D8DE"),
                 espectrograma=[(.3, "#3A060B"), (.55, "#9E0F1C"), (.78, "#FF2E3D"),
                                (.92, "#FF9AA2"), (1, "#FFFFFF")]),
    "personal": dict(nombre="Personal", personal=True, bg="#0A0A0E", bg2="#0F1E3D",
                     borde="#3B82F6", acento="#3575DD", acento2="#6A9EF7", texto="#F4F4F5",
                     dim="#8E8E99", pista="#1E1E24", alpha=0.95),
    "noche": dict(nombre="Noche morada", bg="#0D0817", bg2="#2A1550",
                  borde="#8B5CF6", acento="#A855F7", acento2="#E879F9",
                  texto="#F6F0FF", dim="#9A8BB8", pista="#251A3D", alpha=0.95),
    "cristal": dict(nombre="Cristal", bg="#120B22", bg2="#33195E",
                    borde="#C4B5FD", acento="#C084FC", acento2="#F0ABFC",
                    texto="#FFFFFF", dim="#BBAEDB", pista="#33255A", alpha=0.72),
    "neon": dict(nombre="Neón", bg="#05030A", bg2="#1F0838",
                 borde="#D946EF", acento="#D946EF", acento2="#22D3EE",
                 texto="#F5F5FF", dim="#8C84A8", pista="#1E1333", alpha=0.95),
    "atardecer": dict(nombre="Atardecer", bg="#140A1A", bg2="#44153F",
                      borde="#F472B6", acento="#EC4899", acento2="#FB923C",
                      texto="#FFF3EC", dim="#B79AAE", pista="#3A1C34", alpha=0.94),
    "medianoche": dict(nombre="Medianoche", bg="#000000", bg2="#110A1F",
                       borde="#4C2F85", acento="#8B5CF6", acento2="#A78BFA",
                       texto="#EDE9FE", dim="#7D7390", pista="#1A1426", alpha=0.9),
}
WARN = "#FBBF24"
MODE_DESC = {
    "autonomo": "Autónomo vigila tu racha de trabajo seguido. El timer se pone "
                "ámbar cuando se acerca el break y rojo cuando toca descansar. "
                "Ajusta los tiempos abajo.",
    "normal": "Normal solo cuenta tu tiempo real y el avance de tus metas. "
              "No te indicará cuándo descansar.",
}
WELLBEING_TEXT = (
    "Sin recordatorios es fácil pasarse. Tras horas escuchando sin pausa, el oído "
    "se fatiga: percibes menos los agudos, tiendes a subir el volumen y tus "
    "decisiones de mezcla pierden precisión. A largo plazo, el volumen alto "
    "sostenido puede dañar tu audición de forma permanente.\n\n"
    "Estar mucho tiempo sentado también carga cuello, espalda, hombros y muñecas.\n\n"
    "Recomendado: pausa de 5–10 min cada hora, volumen moderado y estirar.")
# Gaux Mode: vocabulario propio (estado, línea de racha y botón de acción)
GAUX_STATUS = {"sesion": "LOCKED IN", "fondo": "HOLD · OFF DAW", "inactivo": "HOLD · IDLE",
               "pausa": "HOLD", "break": "RECHARGE", "espera": "STANDBY"}
CHIP_TXT = {False: {"break": "Tomar break", "volver": "Volver", "reanudar": "Reanudar"},
            True: {"break": "RECHARGE", "volver": "BACK", "reanudar": "LET'S GO"}}
NORMAL_TIPS = [
    "Tip: pausa tus oídos cada hora",
    "Tip: mezcla a volumen moderado",
    "Tip: estira cuello y hombros",
    "Tip: ¿todo suena opaco? Pausa",
    "Tip: mira lejos unos segundos",
]
ALERT = "#F43F5E"
GOLD = "#FACC15"

TITLE_FONTS = ["Snell Roundhand", "Savoye LET", "Apple Chancery", "Bradley Hand",
               "Noteworthy", "Marker Felt", "Chalkboard SE", "Futura",
               "Avenir Next", "Segoe Script", "Segoe Print", "Lucida Handwriting",
               "Gabriola", "Segoe UI", "DejaVu Serif"]
TITLE_SIZES = {"Snell Roundhand": 19, "Savoye LET": 24, "Apple Chancery": 16,
               "Bradley Hand": 16, "Noteworthy": 15, "Marker Felt": 16,
               "Chalkboard SE": 15, "Segoe Script": 15, "Segoe Print": 14,
               "Lucida Handwriting": 13, "Gabriola": 20}
TITLE_NO_BOLD = {"Savoye LET", "Apple Chancery", "Bradley Hand", "Gabriola"}
CLOCK_FONTS = ["Avenir Next", "Futura", "Chalkboard SE", "Optima", "Gill Sans",
               "Menlo", "Bahnschrift", "Segoe UI", "Consolas", "DejaVu Sans"]
CLOCK_SIZES = {"Menlo": 26, "Consolas": 26, "Chalkboard SE": 28, "Segoe UI": 28}
# Gaux Mode: tipografía de marca fija (condensada, industrial)
ACCENTS = "áéíóúñüÁÉÍÓÚÑÜ¿¡"            # letras que toda fuente de texto debe tener
BRAND_FONTS = ["DIN Condensed", "Avenir Next Condensed", "Bahnschrift SemiBold Condensed",
               "Bahnschrift Condensed",
               "Bahnschrift", "Impact", "Arial Narrow", "Helvetica Neue", "DejaVu Sans"]
BRAND_TITLE = {"DIN Condensed": 21, "Avenir Next Condensed": 17, "Impact": 15,
               "Arial Narrow": 16}
BRAND_CLOCK = {"DIN Condensed": 42, "Bahnschrift SemiBold Condensed": 36,
               "Bahnschrift Condensed": 36, "Bahnschrift": 32, "Impact": 32,
               "Arial Narrow": 34}
BRAND_NAME = "GAUX MODE"
SANS_FONTS = ["Avenir Next", "Helvetica Neue", "Segoe UI", "DejaVu Sans"]


PERSONAL_COLORS = ["#3B82F6", "#22C55E", "#F59E0B", "#EF4444", "#EC4899", "#A855F7",
                   "#06B6D4", "#F4F4F5"]


def build_personal_theme(pc):
    """Tema del Modo Personal a partir del color que elija el usuario."""
    c = pc.get("color") or "#3B82F6"
    if not re.match(r"^#[0-9a-fA-F]{6}$", c):
        c = "#3B82F6"
    return dict(nombre="Personal", personal=True, bg="#0A0A0E", bg2=mix(c, "#000000", .72),
                borde=c, acento=mix(c, "#000000", .1), acento2=mix(c, "#FFFFFF", .22),
                texto="#F4F4F5", dim="#8E8E99", pista="#1E1E24", alpha=0.95,
                onda=(c, mix(c, "#FFFFFF", .45), "#E5E7EB"),
                espectrograma=[(.3, mix(c, "#000000", .8)), (.55, mix(c, "#000000", .45)),
                               (.78, c), (.92, mix(c, "#FFFFFF", .55)), (1, "#FFFFFF")])


def hex2rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


@functools.lru_cache(maxsize=8192)
def mix(a, b, t):
    t = max(0.0, min(1.0, t))
    ra, rb = hex2rgb(a), hex2rgb(b)
    return "#%02x%02x%02x" % tuple(round(ra[i] + (rb[i] - ra[i]) * t) for i in range(3))


def chamfer(cv, x1, y1, x2, y2, c, **kw):
    """Rectángulo con dos esquinas cortadas en diagonal (forma de marca Gaux)."""
    c = min(c, (x2 - x1) / 3, (y2 - y1) / 2)
    pts = [x1, y1, x2 - c, y1, x2, y1 + c, x2, y2, x1 + c, y2, x1, y2 - c]
    return cv.create_polygon(pts, **kw)


def rrect(cv, x1, y1, x2, y2, r, **kw):
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
           x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return cv.create_polygon(pts, smooth=True, splinesteps=24, **kw)


# --------------------------------------------------------------------------
# Detección por sistema operativo -> frontmost_app() devuelve live/self/other
# --------------------------------------------------------------------------
# DAWs que el timer reconoce: clave, nombre visible y patrones (en minúsculas) que se buscan
# en el nombre de la app al frente y en la ruta/nombre del proceso.
DAWS = [
    ("live", "Ableton Live", [r"^live$", r"ableton live"]),
    ("fl", "FL Studio", [r"fl studio", r"^fl(64)?(\.exe)?$", r"osxfl"]),
    ("logic", "Logic Pro", [r"logic pro"]),
    ("protools", "Pro Tools", [r"pro ?tools"]),
    ("cubase", "Cubase", [r"cubase"]),
    ("nuendo", "Nuendo", [r"nuendo"]),
    ("studioone", "Studio One", [r"studio ?one"]),
    ("bitwig", "Bitwig Studio", [r"bitwig"]),
    ("reaper", "REAPER", [r"^reaper", r"reaper\.app", r"^reaper(64)?\.exe$"]),
    ("reason", "Reason", [r"^reason( \d+)?$", r"/reason( \d+)?\.app/", r"^reason\.exe$"]),
    ("garageband", "GarageBand", [r"garageband"]),
    ("cakewalk", "Cakewalk", [r"cakewalk"]),
    ("ardour", "Ardour", [r"ardour"]),
    ("renoise", "Renoise", [r"renoise"]),
    ("dp", "Digital Performer", [r"digital performer"]),
]
DAW_NAMES = {k: n for k, n, _ in DAWS}
_DAW_RX = {}
TARGET = {"keys": {k for k, _, _ in DAWS}, "custom": []}   # lo configura la app
CURRENT_DAW = ["tu DAW"]                                   # nombre del DAW detectado


def configure_targets(keys, custom):
    TARGET["keys"] = set(keys)
    TARGET["custom"] = [c.strip().lower() for c in custom if c.strip()]


def daw_match(text):
    """Nombre del DAW si 'text' (nombre de app o ruta del proceso) es uno de los vigilados."""
    t = (text or "").strip().lower()
    if not t:
        return None
    for k, name, pats in DAWS:
        if k not in TARGET["keys"]:
            continue
        rx = _DAW_RX.get(k)
        if rx is None:
            rx = _DAW_RX[k] = [re.compile(p_) for p_ in pats]
        if any(r.search(t) for r in rx):
            return name
    for c in TARGET["custom"]:
        if c in t:
            return c.title()
    return None


def is_live_name(name):
    """True si la app es un DAW vigilado (antes solo Ableton Live)."""
    d = daw_match(name)
    if d:
        CURRENT_DAW[0] = d
    return d is not None


if SYSTEM == "Windows":
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.windll.user32
    _kernel32 = ctypes.windll.kernel32

    class _LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

    def idle_seconds():
        lii = _LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(lii)
        if not _user32.GetLastInputInfo(ctypes.byref(lii)):
            return 0.0
        return ((_kernel32.GetTickCount() - lii.dwTime) & 0xFFFFFFFF) / 1000.0

    def live_ui_state(pid, check_menu=True):
        return False, False          # en Windows los menús están dentro de la ventana de Live

    def click_count():
        return 0

    def mouse_down():
        return bool(_user32.GetAsyncKeyState(0x01) & 0x8000)

    def font_covers(family, text):
        return True                     # las fuentes de Windows traen tildes y ñ

    def daw_window_title(pid):
        """Título de la ventana visible más grande del DAW."""
        if not pid:
            return None
        found = {"t": None, "a": 0}
        cb_t = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

        def cb(hwnd, lp):
            if not _user32.IsWindowVisible(hwnd):
                return True
            p_ = wintypes.DWORD()
            _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p_))
            if p_.value != pid:
                return True
            r = wintypes.RECT()
            _user32.GetWindowRect(hwnd, ctypes.byref(r))
            a = (r.right - r.left) * (r.bottom - r.top)
            if a > found["a"]:
                buf = ctypes.create_unicode_buffer(512)
                _user32.GetWindowTextW(hwnd, buf, 512)
                found["t"], found["a"] = buf.value, a
            return True

        _user32.EnumWindows(cb_t(cb), 0)
        return found["t"]

    def frontmost_app():
        hwnd = _user32.GetForegroundWindow()
        pid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == os.getpid():
            return "self"
        try:
            if is_live_name(psutil.Process(pid.value).name()):
                LIVE_PID[0] = pid.value
                return "live"
            return "other"
        except Exception:
            return "other"

    class _MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

    def screens():
        """[(x, y, w, h, vx, vy, vw, vh)] de cada monitor; v* = área útil (sin barra de tareas)."""
        out = []
        cb_t = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HMONITOR, wintypes.HDC,
                                  ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)

        def cb(hm, hdc, rc, lp):
            mi = _MONITORINFO()
            mi.cbSize = ctypes.sizeof(mi)
            if _user32.GetMonitorInfoW(hm, ctypes.byref(mi)):
                m, w = mi.rcMonitor, mi.rcWork
                out.append((m.left, m.top, m.right - m.left, m.bottom - m.top,
                            w.left, w.top, w.right - w.left, w.bottom - w.top))
            return 1
        try:
            _user32.EnumDisplayMonitors(None, None, cb_t(cb), 0)
        except Exception:
            return []
        return out

    _GWL_EXSTYLE, _GWLP_HWNDPARENT = -20, -8
    _WS_EX_NOACTIVATE, _WS_EX_TOPMOST = 0x08000000, 0x00000008
    try:
        _SetWLP = _user32.SetWindowLongPtrW
        _GetWLP = _user32.GetWindowLongPtrW
    except AttributeError:                       # Python de 32 bits
        _SetWLP, _GetWLP = _user32.SetWindowLongW, _user32.GetWindowLongW
    _SetWLP.restype = ctypes.c_ssize_t
    _SetWLP.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    _GetWLP.restype = ctypes.c_ssize_t
    _GetWLP.argtypes = [wintypes.HWND, ctypes.c_int]

    def _main_hwnd(pid):
        best = {"h": None, "a": 0}
        cb_t = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

        def cb(hwnd, lp):
            if not _user32.IsWindowVisible(hwnd):
                return True
            p_ = wintypes.DWORD()
            _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p_))
            if p_.value != pid:
                return True
            r = wintypes.RECT()
            _user32.GetWindowRect(hwnd, ctypes.byref(r))
            a = (r.right - r.left) * (r.bottom - r.top)
            if a > best["a"]:
                best["h"], best["a"] = hwnd, a
            return True
        _user32.EnumWindows(cb_t(cb), 0)
        return best["h"]

    def stack_windows(tkwins, owner_pid=None):
        """Las ventanas del timer pasan a ser 'hijas' de la ventana del DAW: quedan sobre
        ella pero nunca tapan sus plugins, y un clic no le quita el foco al DAW."""
        owner = _main_hwnd(owner_pid) if owner_pid else None
        if not owner:
            return False
        done = False
        for t in tkwins:
            try:
                if t is None or not t.winfo_ismapped():
                    continue
                hwnd = int(t.wm_frame(), 16)
                if _GetWLP(hwnd, _GWLP_HWNDPARENT) != owner:
                    t.attributes("-topmost", False)
                    _SetWLP(hwnd, _GWLP_HWNDPARENT, owner)
                ex = _GetWLP(hwnd, _GWL_EXSTYLE)
                if not ex & _WS_EX_NOACTIVATE:
                    _SetWLP(hwnd, _GWL_EXSTYLE, ex | _WS_EX_NOACTIVATE)
                done = True
            except Exception:
                pass
        return done

    def daw_window_bounds(pid):
        """(x, y, ancho, alto) de la ventana visible más grande del DAW, o None."""
        if not pid:
            return None
        found = {"r": None, "a": 0}
        cb_t = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

        def cb(hwnd, lp):
            if not _user32.IsWindowVisible(hwnd) or _user32.IsIconic(hwnd):
                return True
            p_ = wintypes.DWORD()
            _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p_))
            if p_.value != pid:
                return True
            r = wintypes.RECT()
            _user32.GetWindowRect(hwnd, ctypes.byref(r))
            a = (r.right - r.left) * (r.bottom - r.top)
            if a > found["a"]:
                found["r"], found["a"] = (r.left, r.top, r.right - r.left, r.bottom - r.top), a
            return True
        _user32.EnumWindows(cb_t(cb), 0)
        return found["r"]

elif SYSTEM == "Darwin":
    # Sin dependencias externas: CoreGraphics vía ctypes + lsappinfo/pgrep.
    import ctypes
    import re

    _cg = ctypes.cdll.LoadLibrary(
        "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
    _cg.CGEventSourceSecondsSinceLastEventType.restype = ctypes.c_double
    _cg.CGEventSourceSecondsSinceLastEventType.argtypes = [ctypes.c_int32,
                                                            ctypes.c_uint32]

    def idle_seconds():
        return _cg.CGEventSourceSecondsSinceLastEventType(0, 0xFFFFFFFF)

    _cg.CGEventSourceCounterForEventType.restype = ctypes.c_uint32
    _cg.CGEventSourceCounterForEventType.argtypes = [ctypes.c_int32, ctypes.c_uint32]

    def click_count():
        """Clics izquierdos acumulados en la sesión (para saber si se abrió/cerró un menú)."""
        return _cg.CGEventSourceCounterForEventType(0, 1)

    _cg.CGEventSourceButtonState.restype = ctypes.c_bool
    _cg.CGEventSourceButtonState.argtypes = [ctypes.c_int32, ctypes.c_uint32]

    def mouse_down():
        """True mientras el botón izquierdo está presionado (arrastrando algo)."""
        return bool(_cg.CGEventSourceButtonState(0, 0))

    def _run(cmd):
        try:
            return subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=2).stdout
        except Exception:
            return ""

    # App al frente vía NSWorkspace (objc por ctypes): sin lanzar procesos cada 0.4 s.
    try:
        ctypes.cdll.LoadLibrary("/System/Library/Frameworks/AppKit.framework/AppKit")
        _objc = ctypes.cdll.LoadLibrary("/usr/lib/libobjc.A.dylib")
        _objc.objc_getClass.restype = ctypes.c_void_p
        _objc.objc_getClass.argtypes = [ctypes.c_char_p]
        _objc.sel_registerName.restype = ctypes.c_void_p
        _objc.sel_registerName.argtypes = [ctypes.c_char_p]
        _msg = ctypes.cast(_objc.objc_msgSend, ctypes.c_void_p).value
        _send_p = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(_msg)
        _send_i = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)(_msg)
        _send_s = ctypes.CFUNCTYPE(ctypes.c_char_p, ctypes.c_void_p, ctypes.c_void_p)(_msg)
        _NSWS = _objc.objc_getClass(b"NSWorkspace")
        _SEL = {k: _objc.sel_registerName(k) for k in
                (b"sharedWorkspace", b"frontmostApplication", b"processIdentifier",
                 b"localizedName", b"UTF8String")}
        _OBJC_OK = bool(_NSWS)
    except Exception:
        _OBJC_OK = False

    try:
        # cada consulta a AppKit se envuelve en su propio pool: sin fugas de memoria aunque
        # el timer esté abierto días enteros
        _objc.objc_autoreleasePoolPush.restype = ctypes.c_void_p
        _objc.objc_autoreleasePoolPop.argtypes = [ctypes.c_void_p]
        _POOL_OK = True
    except Exception:
        _POOL_OK = False

    class _Pool:
        def __enter__(self):
            self.p = _objc.objc_autoreleasePoolPush() if _POOL_OK else None
            return self

        def __exit__(self, *a):
            if self.p:
                _objc.objc_autoreleasePoolPop(self.p)
            return False

    def _front_objc():
        with _Pool():
            ws = _send_p(_NSWS, _SEL[b"sharedWorkspace"])
            app = _send_p(ws, _SEL[b"frontmostApplication"]) if ws else None
            if not app:
                return None, ""
            pid = _send_i(app, _SEL[b"processIdentifier"])
            ns = _send_p(app, _SEL[b"localizedName"])
            raw = _send_s(ns, _SEL[b"UTF8String"]) if ns else b""
            return pid, (raw or b"").decode("utf-8", "ignore")

    def frontmost_app():
        global _OBJC_OK
        if _OBJC_OK:
            try:
                pid, name = _front_objc()
                if pid is not None:
                    if pid == os.getpid():
                        return "self"
                    if is_live_name(name):
                        LIVE_PID[0] = pid
                        return "live"
                    return "other"
            except Exception:
                _OBJC_OK = False                   # respaldo: lsappinfo
        asn = _run(["lsappinfo", "front"]).strip()
        if not asn:
            return "other"
        info = _run(["lsappinfo", "info", asn])
        m = re.search(r"pid\s*=\s*(\d+)", info)
        if m and int(m.group(1)) == os.getpid():
            return "self"
        first = info.splitlines()[0] if info else ""
        n = re.search(r'"([^"]+)"', first)
        if is_live_name(n.group(1) if n else ""):
            if m:
                LIVE_PID[0] = int(m.group(1))
            return "live"
        return "other"

    # Accesibilidad por ctypes (sin lanzar procesos): ¿Live tiene un menú o un diálogo abierto?
    try:
        _AX = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
        _CF = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        _vp = ctypes.c_void_p
        _AX.AXUIElementCreateApplication.restype = _vp
        _AX.AXUIElementCreateApplication.argtypes = [ctypes.c_int]
        _AX.AXUIElementCopyAttributeValue.restype = ctypes.c_int32
        _AX.AXUIElementCopyAttributeValue.argtypes = [_vp, _vp, ctypes.POINTER(_vp)]
        _AX.AXUIElementSetMessagingTimeout.restype = ctypes.c_int32
        _AX.AXUIElementSetMessagingTimeout.argtypes = [_vp, ctypes.c_float]
        _CF.CFStringCreateWithCString.restype = _vp
        _CF.CFStringCreateWithCString.argtypes = [_vp, ctypes.c_char_p, ctypes.c_uint32]
        _CF.CFStringGetCString.restype = ctypes.c_bool
        _CF.CFStringGetCString.argtypes = [_vp, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32]
        _CF.CFGetTypeID.restype = ctypes.c_ulong
        _CF.CFGetTypeID.argtypes = [_vp]
        _CF.CFStringGetTypeID.restype = ctypes.c_ulong
        _CF.CFBooleanGetTypeID.restype = ctypes.c_ulong
        _CF.CFBooleanGetValue.restype = ctypes.c_bool
        _CF.CFBooleanGetValue.argtypes = [_vp]
        _CF.CFArrayGetCount.restype = ctypes.c_long
        _CF.CFArrayGetCount.argtypes = [_vp]
        _CF.CFArrayGetValueAtIndex.restype = _vp
        _CF.CFArrayGetValueAtIndex.argtypes = [_vp, ctypes.c_long]
        _CF.CFRelease.argtypes = [_vp]
        _UTF8 = 0x08000100
        _CFKEYS = {}
        _AX_OK = True
    except Exception:
        _AX_OK = False

    def _cfs(text):
        k = _CFKEYS.get(text)
        if k is None:
            k = _CFKEYS[text] = _CF.CFStringCreateWithCString(None, text.encode(), _UTF8)
        return k

    def _ax_get(el, attr):
        out = _vp()
        if _AX.AXUIElementCopyAttributeValue(el, _cfs(attr), ctypes.byref(out)) != 0:
            return None
        return out.value

    def _ax_value(el, attr):
        """Lee un atributo de texto o sí/no y libera la memoria."""
        v = _ax_get(el, attr)
        if not v:
            return None
        try:
            tid = _CF.CFGetTypeID(v)
            if tid == _CF.CFBooleanGetTypeID():
                return bool(_CF.CFBooleanGetValue(v))
            if tid == _CF.CFStringGetTypeID():
                buf = ctypes.create_string_buffer(512)
                if _CF.CFStringGetCString(v, buf, 512, _UTF8):
                    return buf.value.decode("utf-8", "ignore")
            return None
        finally:
            _CF.CFRelease(v)

    DIALOG_TITLES = ("export", "settings", "preferences", "preferencias", "ajustes",
                     "configuración", "configuracion", "guardar", "save", "abrir", "open")

    def live_ui_state(pid, check_menu=True):
        """(menú abierto, diálogo abierto) en Live. Sin permiso de Accesibilidad: (False, False)."""
        if not _AX_OK or not pid:
            return False, False
        app = _AX.AXUIElementCreateApplication(int(pid))
        if not app:
            return False, False
        menu = dialog = False
        try:
            _AX.AXUIElementSetMessagingTimeout(app, 0.25)   # nunca bloquear si Live está ocupado
            if check_menu:
                foc = _ax_get(app, "AXFocusedUIElement")
                if foc:
                    menu = _ax_value(foc, "AXRole") in ("AXMenu", "AXMenuItem", "AXMenuBarItem")
                    _CF.CFRelease(foc)
                if not menu:
                    bar = _ax_get(app, "AXMenuBar")
                    if bar:
                        kids = _ax_get(bar, "AXChildren")
                        if kids:
                            for i in range(_CF.CFArrayGetCount(kids)):
                                if _ax_value(_CF.CFArrayGetValueAtIndex(kids, i), "AXSelected"):
                                    menu = True
                                    break
                            _CF.CFRelease(kids)
                        _CF.CFRelease(bar)
            win = _ax_get(app, "AXFocusedWindow")
            if win:
                if _ax_value(win, "AXModal"):
                    dialog = True
                elif _ax_value(win, "AXSubrole") in ("AXDialog", "AXSystemDialog"):
                    dialog = True
                else:
                    title = (_ax_value(win, "AXTitle") or "").strip().lower()
                    dialog = title.startswith(DIALOG_TITLES)
                    if not dialog:                       # hojas (sheets) dentro de la ventana
                        kids = _ax_get(win, "AXChildren")
                        if kids:
                            for i in range(min(_CF.CFArrayGetCount(kids), 40)):
                                if _ax_value(_CF.CFArrayGetValueAtIndex(kids, i),
                                             "AXRole") == "AXSheet":
                                    dialog = True
                                    break
                            _CF.CFRelease(kids)
                _CF.CFRelease(win)
        except Exception:
            return False, False
        finally:
            _CF.CFRelease(app)
        return menu, dialog

    # Título de la ventana principal del DAW, para detectar el proyecto. Se lee del servidor
    # de ventanas de macOS (como hace el Monitor de Actividad), nunca del DAW: no lo interrumpe.
    try:
        class _CGRect(ctypes.Structure):
            _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double),
                        ("w", ctypes.c_double), ("h", ctypes.c_double)]
        _cg.CGWindowListCopyWindowInfo.restype = ctypes.c_void_p
        _cg.CGWindowListCopyWindowInfo.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
        _cg.CGRectMakeWithDictionaryRepresentation.restype = ctypes.c_bool
        _cg.CGRectMakeWithDictionaryRepresentation.argtypes = [ctypes.c_void_p,
                                                               ctypes.POINTER(_CGRect)]
        _CF.CFDictionaryGetValue.restype = ctypes.c_void_p
        _CF.CFDictionaryGetValue.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        _CF.CFNumberGetValue.restype = ctypes.c_bool
        _CF.CFNumberGetValue.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
        _TITLE_OK = _AX_OK
    except Exception:
        _TITLE_OK = False

    def _cf_text(v):
        if not v or _CF.CFGetTypeID(v) != _CF.CFStringGetTypeID():
            return ""
        buf = ctypes.create_string_buffer(1024)
        if _CF.CFStringGetCString(v, buf, 1024, _UTF8):
            return buf.value.decode("utf-8", "ignore")
        return ""

    def _cf_int(v):
        n = ctypes.c_int64(0)
        if v and _CF.CFNumberGetValue(v, 4, ctypes.byref(n)):
            return n.value
        return None

    def _daw_window(pid, want_title):
        """(x, y, ancho, alto) y título de la ventana más grande del DAW, leídos del servidor
        de ventanas de macOS (no se le pregunta nada al DAW). La posición no necesita permisos;
        el título necesita el permiso de Grabación de pantalla."""
        if not _TITLE_OK or not pid:
            return None, None
        arr = _cg.CGWindowListCopyWindowInfo(1 | 16, 0)      # en pantalla, sin escritorio
        if not arr:
            return None, None
        best, rect, area = None, None, 0.0
        try:
            for i in range(_CF.CFArrayGetCount(arr)):
                d = _CF.CFArrayGetValueAtIndex(arr, i)
                if _cf_int(_CF.CFDictionaryGetValue(d, _cfs("kCGWindowOwnerPID"))) != pid:
                    continue
                if _cf_int(_CF.CFDictionaryGetValue(d, _cfs("kCGWindowLayer"))) != 0:
                    continue
                r = _CGRect()
                b = _CF.CFDictionaryGetValue(d, _cfs("kCGWindowBounds"))
                if not b or not _cg.CGRectMakeWithDictionaryRepresentation(b, ctypes.byref(r)):
                    continue
                if r.w * r.h > area:
                    area = r.w * r.h
                    rect = (int(r.x), int(r.y), int(r.w), int(r.h))
                    if want_title:
                        best = _cf_text(_CF.CFDictionaryGetValue(d, _cfs("kCGWindowName")))
        except Exception:
            return None, None
        finally:
            _CF.CFRelease(arr)
        return rect, best

    def daw_window_title(pid):
        """Título de la ventana más grande del DAW. '' si macOS no deja leerlo."""
        return _daw_window(pid, True)[1]

    def daw_window_bounds(pid):
        """(x, y, ancho, alto) de la ventana principal del DAW (en pantalla), o None."""
        return _daw_window(pid, False)[0]

    # Pantallas (NSScreen): tamaño real y área útil bajo la barra de menú, en cualquier
    # resolución, escalado o monitor externo.
    try:
        _arm = platform.machine() not in ("x86_64", "i386")
        _rect_fn = ctypes.CFUNCTYPE(_CGRect, ctypes.c_void_p, ctypes.c_void_p)(
            ctypes.cast(_objc.objc_msgSend if _arm else _objc.objc_msgSend_stret,
                        ctypes.c_void_p).value)
        _send_u = ctypes.CFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p, ctypes.c_void_p)(_msg)
        _send_pi = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                    ctypes.c_ulong)(_msg)
        _NSScreen = _objc.objc_getClass(b"NSScreen")
        for _k in (b"screens", b"count", b"objectAtIndex:", b"frame", b"visibleFrame",
                   b"runningApplications"):
            _SEL[_k] = _objc.sel_registerName(_k)
        _SCREENS_OK = bool(_NSScreen) and _OBJC_OK
    except Exception:
        _SCREENS_OK = False

    def screens():
        """[(x, y, w, h, vx, vy, vw, vh)] por pantalla, con el origen arriba a la izquierda
        (como Tk). v* = área útil: sin la barra de menú ni el Dock."""
        if not _SCREENS_OK:
            return []
        raw = []
        try:
            with _Pool():
                arr = _send_p(_NSScreen, _SEL[b"screens"])
                n = _send_u(arr, _SEL[b"count"]) if arr else 0
                for i in range(min(int(n), 8)):
                    sc = _send_pi(arr, _SEL[b"objectAtIndex:"], i)
                    f = _rect_fn(sc, _SEL[b"frame"])
                    v = _rect_fn(sc, _SEL[b"visibleFrame"])
                    raw.append(((f.x, f.y, f.w, f.h), (v.x, v.y, v.w, v.h)))
        except Exception:
            return []
        if not raw:
            return []
        h0 = raw[0][0][3]                        # la primera es la de la barra de menú
        out = []
        for (fx, fy, fw, fh), (vx, vy, vw, vh) in raw:
            out.append((int(fx), int(round(h0 - fy - fh)), int(fw), int(fh),
                        int(vx), int(round(h0 - vy - vh)), int(vw), int(vh)))
        return out

    def _running_daw_objc():
        """¿Hay un DAW vigilado abierto? (NSWorkspace, sin lanzar procesos)"""
        with _Pool():
            ws = _send_p(_NSWS, _SEL[b"sharedWorkspace"])
            arr = _send_p(ws, _SEL[b"runningApplications"]) if ws else None
            n = _send_u(arr, _SEL[b"count"]) if arr else 0
            for i in range(int(n)):
                app = _send_pi(arr, _SEL[b"objectAtIndex:"], i)
                ns = _send_p(app, _SEL[b"localizedName"]) if app else None
                raw = _send_s(ns, _SEL[b"UTF8String"]) if ns else None
                if raw and daw_match(raw.decode("utf-8", "ignore")):
                    return True
        return False

    # ¿La fuente tiene tildes y ñ? Si no, macOS las toma de otra fuente y se ven más chicas.
    try:
        _CT = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreText.framework/CoreText")
        _CT.CTFontCreateWithName.restype = ctypes.c_void_p
        _CT.CTFontCreateWithName.argtypes = [ctypes.c_void_p, ctypes.c_double, ctypes.c_void_p]
        _CT.CTFontGetGlyphsForCharacters.restype = ctypes.c_bool
        _CT.CTFontGetGlyphsForCharacters.argtypes = [ctypes.c_void_p,
                                                     ctypes.POINTER(ctypes.c_uint16),
                                                     ctypes.POINTER(ctypes.c_uint16), ctypes.c_long]
        _CT.CTFontCopyFamilyName.restype = ctypes.c_void_p
        _CT.CTFontCopyFamilyName.argtypes = [ctypes.c_void_p]
        _CT_OK = _AX_OK
    except Exception:
        _CT_OK = False
    _COVER = {}

    def font_covers(family, text):
        """True si la fuente tiene todas las letras no ASCII del texto (tildes, ñ, ¿, ¡…)."""
        chars = "".join(sorted({ch for ch in (text or "") if 127 < ord(ch) < 0x10000}))
        if not chars or not _CT_OK or not family:
            return True
        key = (family, chars)
        if key in _COVER:
            return _COVER[key]
        ok = True
        name = _CF.CFStringCreateWithCString(None, family.encode("utf-8"), _UTF8)
        try:
            f = _CT.CTFontCreateWithName(name, 12.0, None)
            if f:
                famref = _CT.CTFontCopyFamilyName(f)
                fam = _cf_text(famref)
                if famref:
                    _CF.CFRelease(famref)
                if fam.lower() == family.lower():          # es la fuente pedida
                    n = len(chars)
                    uni = (ctypes.c_uint16 * n)(*[ord(c) for c in chars])
                    gl = (ctypes.c_uint16 * n)()
                    ok = bool(_CT.CTFontGetGlyphsForCharacters(f, uni, gl, n))
                _CF.CFRelease(f)
        except Exception:
            ok = True
        finally:
            if name:
                _CF.CFRelease(name)
        _COVER[key] = ok
        return ok

    # ---- capa de las ventanas del timer (macOS) ---------------------------------------
    # Las ventanas de plugins de Live son "flotantes" (nivel 3). Tk pone las ventanas
    # "siempre encima" en un nivel más alto (19) y así taparía la barra de título de los
    # plugins (no se podrían mover ni cerrar). El timer y el analizador se ponen en el mismo
    # nivel flotante y al fondo de él: siempre sobre la ventana principal del DAW, siempre
    # debajo de sus plugins. Además no activan la app al hacer clic, así el DAW no pierde
    # el foco ni esconde sus plugins.
    try:
        _send_v = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long)(_msg)
        _send_vv = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long,
                                    ctypes.c_long)(_msg)
        _send_b = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(_msg)
        _send_bp = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p,
                                    ctypes.c_void_p)(_msg)
        _send_ppi = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                     ctypes.c_int)(_msg)
        _NSApp_cls = _objc.objc_getClass(b"NSApplication")
        _NSRunApp = _objc.objc_getClass(b"NSRunningApplication")
        for _k in (b"sharedApplication", b"windows", b"isVisible", b"setLevel:",
                   b"orderWindow:relativeTo:", b"setHidesOnDeactivate:",
                   b"_setPreventsActivation:", b"respondsToSelector:",
                   b"activateIgnoringOtherApps:", b"runningApplicationWithProcessIdentifier:",
                   b"activateWithOptions:", b"setCanHide:"):
            _SEL[_k] = _objc.sel_registerName(_k)
        _LEVEL_OK = bool(_NSApp_cls) and _SCREENS_OK
    except Exception:
        _LEVEL_OK = False
    FLOAT_LEVEL = 3              # NSFloatingWindowLevel: el mismo de los plugins
    NO_ACTIVATE = [None]         # ¿macOS deja que una ventana no active la app?

    def _ns_windows():
        app = _send_p(_NSApp_cls, _SEL[b"sharedApplication"])
        arr = _send_p(app, _SEL[b"windows"]) if app else None
        n = _send_u(arr, _SEL[b"count"]) if arr else 0
        out = []
        for i in range(int(n)):
            w = _send_pi(arr, _SEL[b"objectAtIndex:"], i)
            if w:
                f = _rect_fn(w, _SEL[b"frame"])
                out.append((w, f))
        return out

    def stack_windows(tkwins, owner_pid=None):
        """tkwins: ventanas del timer, de la de más arriba a la de más abajo. Las deja
        flotando al fondo de la capa de plugins."""
        if not _LEVEL_OK:
            return False
        geoms = []
        for t in tkwins:
            try:
                if t is not None and t.winfo_ismapped():
                    geoms.append((t.winfo_x(), t.winfo_y(), t.winfo_width(), t.winfo_height()))
            except Exception:
                pass
        scr = screens()
        if not scr:
            return False
        h0 = scr[0][3]
        try:
            with _Pool():
                found = []
                wins = _ns_windows()
                for g in geoms:
                    x, y, w, h = g
                    hit = None
                    for nw, f in wins:
                        top = h0 - f.y - f.h
                        if abs(f.x - x) <= 3 and abs(top - y) <= 3 and abs(f.w - w) <= 3 \
                                and abs(f.h - h) <= 3:
                            hit = nw
                            break
                    if hit is None:                 # respaldo: la única con ese tamaño
                        same = [nw for nw, f in wins if abs(f.w - w) <= 1 and abs(f.h - h) <= 1
                                and nw not in found]
                        if len(same) == 1:
                            hit = same[0]
                    if hit is not None:
                        found.append(hit)
                for nw in reversed(found):            # la de más abajo primero
                    _send_v(nw, _SEL[b"setLevel:"], FLOAT_LEVEL)
                    # en todos los escritorios y también sobre apps en pantalla completa
                    # (1 = todos los Spaces, 64 = fuera de ⌘`, 256 = auxiliar de pantalla completa)
                    _send_v(nw, _SEL[b"setCollectionBehavior:"], 1 | 64 | 256)
                    _send_v(nw, _SEL[b"setHidesOnDeactivate:"], 0)
                    if NO_ACTIVATE[0] is None:
                        NO_ACTIVATE[0] = bool(_send_bp(nw, _SEL[b"respondsToSelector:"],
                                                       _SEL[b"_setPreventsActivation:"]))
                    if NO_ACTIVATE[0]:
                        _send_v(nw, _SEL[b"_setPreventsActivation:"], 1)
                    _send_vv(nw, _SEL[b"orderWindow:relativeTo:"], -1, 0)   # al fondo
                return bool(found)
        except Exception:
            return False

    try:
        for _k in (b"safeAreaInsets", b"auxiliaryTopLeftArea", b"auxiliaryTopRightArea",
                   b"setCollectionBehavior:"):
            _SEL[_k] = _objc.sel_registerName(_k)
    except Exception:
        _LEVEL_OK = False

    def screen_bands():
        """Por pantalla (mismo orden que screens()): None, o (alto, izquierda, derecha) de la
        franja negra que deja la cámara (notch) cuando una app está en pantalla completa.
        izquierda/derecha = (x, y, ancho, alto) en coordenadas de Tk."""
        if not _LEVEL_OK:
            return []
        out = []
        try:
            with _Pool():
                arr = _send_p(_NSScreen, _SEL[b"screens"])
                n = _send_u(arr, _SEL[b"count"]) if arr else 0
                h0 = None
                for i in range(min(int(n), 8)):
                    sc = _send_pi(arr, _SEL[b"objectAtIndex:"], i)
                    f = _rect_fn(sc, _SEL[b"frame"])
                    if h0 is None:
                        h0 = f.h
                    if not _send_bp(sc, _SEL[b"respondsToSelector:"], _SEL[b"safeAreaInsets"]):
                        out.append(None)
                        continue
                    ins = _rect_fn(sc, _SEL[b"safeAreaInsets"])     # top, left, bottom, right
                    top = ins.x
                    if top < 20:
                        out.append(None)
                        continue
                    L = _rect_fn(sc, _SEL[b"auxiliaryTopLeftArea"])
                    R = _rect_fn(sc, _SEL[b"auxiliaryTopRightArea"])
                    conv = lambda r: (int(r.x), int(round(h0 - r.y - r.h)), int(r.w), int(r.h))
                    out.append((int(top), conv(L), conv(R)))
        except Exception:
            return []
        return out

    def live_is_fullscreen(pid):
        """True/False si el DAW está en pantalla completa (Accesibilidad); None si no se sabe."""
        if not _AX_OK or not pid:
            return None
        app = _AX.AXUIElementCreateApplication(int(pid))
        if not app:
            return None
        try:
            _AX.AXUIElementSetMessagingTimeout(app, 0.3)
            win = _ax_get(app, "AXMainWindow") or _ax_get(app, "AXFocusedWindow")
            if not win:
                return None
            try:
                return _ax_value(win, "AXFullScreen")
            finally:
                _CF.CFRelease(win)
        finally:
            _CF.CFRelease(app)

    def activate_self():
        """Para ventanas donde se escribe (Ajustes, nombres): el teclado va al timer."""
        if not _LEVEL_OK:
            return
        try:
            with _Pool():
                app = _send_p(_NSApp_cls, _SEL[b"sharedApplication"])
                _send_v(app, _SEL[b"activateIgnoringOtherApps:"], 1)
        except Exception:
            pass

    def activate_pid(pid):
        """Devuelve el foco al DAW (si macOS no permite ventanas que no activan)."""
        if not _LEVEL_OK or not pid:
            return
        try:
            with _Pool():
                ra = _send_ppi(_NSRunApp, _SEL[b"runningApplicationWithProcessIdentifier:"],
                               int(pid))
                if ra:
                    _send_v(ra, _SEL[b"activateWithOptions:"], 2)   # ignorar otras apps
        except Exception:
            pass

    def _mac_live_running():
        global _SCREENS_OK
        if _SCREENS_OK:
            try:
                return _running_daw_objc()
            except Exception:
                _SCREENS_OK = False                # respaldo: ps
        out = _run(["ps", "-axo", "comm="])
        for line in out.splitlines():
            if ".app/Contents/MacOS/" in line and daw_match(line):
                return True
        return False
else:
    def idle_seconds():
        return 0.0

    def frontmost_app():
        return "live" if DEMO else "other"

    def live_ui_state(pid, check_menu=True):
        return False, False

    def click_count():
        return 0

    def mouse_down():
        return False

    def daw_window_title(pid):
        return None

    def daw_window_bounds(pid):
        return None

    def screens():
        return []

    def font_covers(family, text):
        return True

if SYSTEM != "Darwin":
    NO_ACTIVATE = [False]

    def screen_bands():
        return []

    def live_is_fullscreen(pid):
        return None

    def activate_self():
        pass

    def activate_pid(pid):
        pass

if SYSTEM not in ("Darwin", "Windows"):
    def stack_windows(tkwins, owner_pid=None):
        return False


LIVE_PID = [None]
SIN_PROYECTO = "Sin asignar"
_UNTITLED = re.compile(r"^(untitled|sin t[ií]tulo|new project|nuevo proyecto|sans titre|"
                       r"unbenannt|senza titolo)\b", re.I)
_TITLE_JUNK = re.compile(
    r"^(ableton live.*|live|fl studio.*|logic pro.*|tracks|mixer|edit|mix|pro tools.*|"
    r"cubase.*|nuendo.*|studio one.*|bitwig.*|reaper.*|reason.*|garageband|cakewalk.*|"
    r"ardour.*|renoise.*|digital performer.*)$", re.I)
_PROJECT_EXT = re.compile(r"\.(als|flp|logicx|logic|ptx|ptf|cpr|npr|song|bwproject|rpp|"
                          r"rpp-bak|reason|band|cwp|ardour|xrns|dpdoc)$", re.I)


def project_from_title(title):
    """Nombre del proyecto a partir del título de la ventana del DAW (o None)."""
    t = re.sub(r"\[[^\]]*\]", "", (title or "")).strip()
    if not t:
        return None
    parts = [x.strip(" *•·") for x in re.split(r"\s+[-–—|]\s+", t)]
    parts = [x for x in parts if x and not _TITLE_JUNK.match(x)]
    if not parts:
        return None
    name = _PROJECT_EXT.sub("", parts[0]).strip(" *•·")
    if not name or _UNTITLED.match(name):
        return None
    return name[:60]


def live_running():
    if DEMO:
        return True
    if SYSTEM == "Darwin":
        return _mac_live_running()
    if psutil is None:
        return False
    for p in psutil.process_iter(["name"]):
        try:
            if is_live_name(p.info["name"]):
                return True
        except Exception:
            pass
    return False


# --------------------------------------------------------------------------
# Ventana principal de Live (para el modo Top Live Performance)
# --------------------------------------------------------------------------
class LiveWindowError(Exception):
    """Mensaje listo para mostrar al usuario."""


PERMISO_MAC = ("Para mover la ventana de tu DAW, macOS necesita un permiso:\n\n"
               "Ajustes del Sistema → Privacidad y seguridad → Accesibilidad → activa "
               f"{HOST_APP}.\n"
               f"Si aparece un aviso de \"{HOST_APP} quiere controlar System Events\", "
               "dale Permitir.\n\nLuego activa el modo otra vez.")


def _proc():
    pid = LIVE_PID[0]
    return f'(first process whose unix id is {int(pid)})' if pid else 'process "Live"'


def _osa(script):
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True,
                       timeout=6)
    if r.returncode != 0:
        err = r.stderr or ""
        if any(c in err for c in ("-1719", "-25211", "-1743", "-10004", "assistive",
                                  "not allowed", "no tiene permiso")):
            raise LiveWindowError(PERMISO_MAC)
        raise LiveWindowError("No se pudo controlar la ventana de tu DAW.\n\n" + err[:200])
    return r.stdout.strip()


def live_main_window():
    """Devuelve (id, x, y, ancho, alto) de la ventana más grande de Live."""
    if SYSTEM == "Darwin":
        out = _osa(f'tell application "System Events" to tell {_proc()}\n'
                   'set out to ""\nset i to 0\n'
                   'repeat with w in windows\nset i to i + 1\ntry\n'
                   'set p to position of w\nset z to size of w\n'
                   'set out to out & i & "," & (item 1 of p) & "," & (item 2 of p) & "," '
                   '& (item 1 of z) & "," & (item 2 of z) & ";"\n'
                   'end try\nend repeat\nreturn out\nend tell')
        wins = []
        for part in out.split(";"):
            try:
                i, x, y, w, h = (int(float(v)) for v in part.split(","))
                wins.append((i, x, y, w, h))
            except ValueError:
                pass
    elif SYSTEM == "Windows":
        wins = []
        cb_t = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

        def cb(hwnd, lp):
            if not _user32.IsWindowVisible(hwnd):
                return True
            pid = wintypes.DWORD()
            _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            try:
                if not is_live_name(psutil.Process(pid.value).name()):
                    return True
            except Exception:
                return True
            r = wintypes.RECT()
            _user32.GetWindowRect(hwnd, ctypes.byref(r))
            wins.append((hwnd, r.left, r.top, r.right - r.left, r.bottom - r.top))
            return True

        _user32.EnumWindows(cb_t(cb), 0)
    else:
        raise LiveWindowError("Este modo funciona en macOS y Windows.")
    if not wins:
        raise LiveWindowError("No encontré la ventana de tu DAW. Ábrelo y vuelve a intentar.")
    return max(wins, key=lambda t: t[3] * t[4])


def live_fullscreen(wid):
    """True si la ventana de Live está en pantalla completa de macOS."""
    if SYSTEM != "Darwin":
        return False
    out = _osa(f'tell application "System Events" to tell {_proc()} to '
               f'get value of attribute "AXFullScreen" of window {wid}')
    return out.strip().lower() == "true"


def set_live_fullscreen(wid, on):
    if SYSTEM == "Darwin":
        _osa(f'tell application "System Events" to tell {_proc()} to '
             f'set value of attribute "AXFullScreen" of window {wid} to {"true" if on else "false"}')


def set_live_window(wid, x, y, w, h):
    x, y, w, h = int(x), int(y), int(w), int(h)
    if SYSTEM == "Darwin":
        _osa(f'tell application "System Events" to tell {_proc()}\n'
             f'set size of window {wid} to {{{w}, {h}}}\n'
             f'set position of window {wid} to {{{x}, {y}}}\n'
             f'set size of window {wid} to {{{w}, {h}}}\nend tell')
    elif SYSTEM == "Windows":
        if _user32.IsZoomed(wid):
            _user32.ShowWindow(wid, 9)          # SW_RESTORE: una ventana maximizada no se mueve
        _user32.MoveWindow(wid, x, y, w, h, True)


# --------------------------------------------------------------------------
# Persistencia y formato
# --------------------------------------------------------------------------
def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_json(path, data):
    os.makedirs(APP_DIR, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def deep_merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def fmt_clock(s):
    s = int(s)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def fmt_short(s):
    s = int(s)
    h, m = s // 3600, s % 3600 // 60
    return f"{h}h {m:02d}m" if h else f"{m}m"


def fmt_goal(s):
    s = int(s)
    h, m = s // 3600, s % 3600 // 60
    if h and m:
        return f"{h}h {m}m"
    return f"{h}h" if h else f"{m}m"


def fmt_ceil(s):
    return fmt_short(math.ceil(max(0, s) / 60) * 60)


def fmt_mmss(s):
    s = int(max(0, s))
    return f"{s // 60}:{s % 60:02d}"


# --------------------------------------------------------------------------
# Widget
# --------------------------------------------------------------------------
class GauxTimer:
    MARGIN = 6

    def __init__(self):
        self.conf = deep_merge(DEFAULT_CONF, load_json(CONF_FILE))
        self.data = deep_merge({"dias": {}, "sesiones": [], "proyectos": {}},
                               load_json(DATA_FILE))
        self.detected = None              # proyecto detectado en el título del DAW
        self.title_seen = None            # None = sin dato; False = macOS no deja leerlo
        self.session_proj = {}            # segundos por proyecto en la sesión actual
        self._title_t = 0.0

        self.session = 0.0
        self.session_start = None
        self.live_open = False
        self.counting = False
        self.state = "espera"
        self.last_front_live = False
        self.streak = 0.0
        self.vclock = 0.0
        self.last_count_v = None
        self.lvl, self.auto_msg = 0, ""
        self.last_tick = time.monotonic()
        self.last_proc_check = -10.0
        self.last_save = time.monotonic()
        self.last_frame = time.monotonic()
        self.phase = 0.0
        self.frame_n = 0
        self.particles = []
        self.reached = {}
        self.bars = []
        self.settings = None
        self._drag = None
        self._resize = None
        self._last_btn = 0.0
        self.front = "other"
        self.visible = False
        self.peek = False                 # franja apartada para dejar ver la barra de macOS
        self.fs_band = None               # DAW en pantalla completa: franja junto a la cámara
        self.ui_busy = False              # Live tiene un diálogo abierto (Exportar, Ajustes…)
        self._menu_t = 0.0                # última vez que se vio un menú de Live abierto
        self.pending_splash = False       # "LET'S GAUUUUX" pendiente al abrir Live
        self.card = None                  # tarjeta de resumen al cerrar Live
        self.analyzer = None
        self.manual = None          # None | "pausa" | "break"
        self.break_start_v = 0.0
        self.hit = []               # zonas clicables: (x1, y1, x2, y2, nombre)
        self.hover = None
        self.chip_label = None
        self.chip_items = []
        self.pp_c = None

        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title(APP_NAME)
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.clear = None
        if SYSTEM == "Darwin":
            try:
                self.root.attributes("-transparent", True)
                self.clear = "systemTransparent"
            except tk.TclError:
                pass
        elif SYSTEM == "Windows":
            try:
                self.root.attributes("-transparentcolor", "#010203")
                self.clear = "#010203"
            except tk.TclError:
                pass
        self.fams = set(tkfont.families())
        self.cv = tk.Canvas(self.root, highlightthickness=0, bd=0)
        self.cv.pack()
        self._bind()
        self._hide_from_dock()
        self._build_menu()
        self.apply_conf(first=True)
        self.root.after(200, self.tick)
        self.root.after(250, self.anim)
        self.root.after(300, self.watch_front)
        self.root.after(500, self.watch_peek)
        self.root.after(1500, self.watch_screen)

    # ---- utilidades -------------------------------------------------------
    def pick(self, cands, pref=None, text=None):
        """Primera fuente instalada; si hay 'text', solo una que tenga todas sus letras."""
        def ok(c):
            return c in self.fams and (not text or font_covers(c, text))
        if pref and ok(pref):
            return pref
        for c in cands:
            if ok(c):
                return c
        for c in ("Avenir Next", "Helvetica Neue", "Helvetica", "Segoe UI", "Arial"):
            if ok(c):
                return c
        return "Helvetica"

    def save_conf(self):
        save_json(CONF_FILE, self.conf)

    def _hide_from_dock(self):
        if SYSTEM != "Darwin":
            return
        try:
            objc = ctypes.cdll.LoadLibrary("/usr/lib/libobjc.A.dylib")
            objc.objc_getClass.restype = ctypes.c_void_p
            objc.objc_getClass.argtypes = [ctypes.c_char_p]
            objc.sel_registerName.restype = ctypes.c_void_p
            objc.sel_registerName.argtypes = [ctypes.c_char_p]
            addr = ctypes.cast(objc.objc_msgSend, ctypes.c_void_p).value
            send0 = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p,
                                     ctypes.c_void_p)(addr)
            send1 = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_void_p,
                                     ctypes.c_void_p, ctypes.c_long)(addr)
            app = send0(objc.objc_getClass(b"NSApplication"),
                        objc.sel_registerName(b"sharedApplication"))
            send1(app, objc.sel_registerName(b"setActivationPolicy:"), 1)
        except Exception:
            pass

    # ---- configuración aplicada ------------------------------------------
    def apply_targets(self):
        keys = self.conf.get("daws")
        if keys is None:
            keys = [k for k, _, _ in DAWS]
        configure_targets(keys, (self.conf.get("daws_extra") or "").split(","))

    def apply_conf(self, first=False):
        self.apply_targets()
        TEMAS["personal"] = build_personal_theme(self.conf.get("personal", {}))
        prev = getattr(self, "T", None)
        self.T = TEMAS.get(self.conf["tema"], TEMAS["noche"])
        ritual_now = bool(self.T.get("marca") or self.T.get("personal"))
        ritual_prev = bool((prev or {}).get("marca") or (prev or {}).get("personal"))
        if not first and ritual_now and (not ritual_prev or
                                         prev.get("nombre") != self.T.get("nombre")):
            self.splash_until = time.monotonic() + 2.2      # Let's Gauuuux / tu frase
        try:
            self.root.attributes("-alpha", self.conf["opacidad"])
        except tk.TclError:
            pass
        old = None if first else (self.root.winfo_x(), self.root.winfo_y(), self.W)
        self.layout()
        saved = self.conf.get("pos", {}).get(self.pos_key())
        fb = getattr(self, "fs_band", None)
        if self.top and self.conf.get("top_geom") and fb and fb.get("left"):
            # DAW en pantalla completa: todo va a la franja negra junto a la cámara
            lx, ly, lw, lh = fb["left"]
            rx, ry, rw, rh = fb["right"]
            self.root.update_idletasks()
            tx, ty = lx + 10, ly + max(0, (lh - self.H) // 2)
            self._dock_pos = (tx, ty)
            self._move(tx, ty)
            self.root.after(80, lambda: self._move(tx, ty))
            a = self.conf["analizador"]
            if rw >= 360:
                a["x"], a["w"] = rx + 10, rw - 20
            else:
                a["x"], a["w"] = tx + self.W + 8, max(200, lw - self.W - 28)
            a["y"], a["h"] = ry + 2, max(24, rh - 4)
        elif self.top and self.conf.get("top_geom"):
            gx, gy, gw = self.conf["top_geom"]
            self.root.update_idletasks()        # aplicar el tamaño nuevo antes de fijar la posición
            self._dock_pos = (gx, gy)
            self._move(gx, gy)
            self.root.after(80, lambda: self._move(gx, gy))
            a = self.conf["analizador"]
            a["x"], a["y"] = gx + self.W + 4, gy
            a["w"], a["h"] = max(460, gw - self.W - 4), self.top_h
        elif saved:
            self._move(*saved)
        elif first:
            self._place()
        else:
            x, y, old_w = old
            if x + old_w / 2 > self.root.winfo_screenwidth() / 2:
                x = x + old_w - self.W          # anclar al borde derecho
            self._move(x, y)
        self.v_tema.set(self.conf["tema"])
        self.v_modo.set(self.conf["modo"])
        self.v_vista.set(self.conf["vista"])
        self.v_orient.set(self.conf.get("orientacion", "horizontal"))
        if self.analyzer and not first:
            self.analyzer.build()
        if not first:
            self.restack_soon(80)
        self.refresh_text()
        self.render_frame(force=True)

    def _place(self):
        self.root.update_idletasks()
        x, y = self.conf.get("x"), self.conf.get("y")
        if x is None or y is None:
            x, y = self.root.winfo_screenwidth() - self.W - 20, 40
        self._move(x, y)

    def _move(self, x, y):
        x, y = self.clamp_rect(int(x), int(y), self.W, self.H)
        self.root.geometry(f"{self.W}x{self.H}+{x}+{y}")

    # ---- pantallas (cualquier resolución, escalado o monitor externo) ------------
    def screen_list(self, fresh=False):
        now = time.monotonic()
        c = getattr(self, "_scr_cache", None)
        if fresh or not c or now - c[0] > 1.0:
            lst = []
            try:
                lst = screens()
            except Exception:
                lst = []
            if not lst:
                sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
                lst = [(0, 0, sw, sh, 0, 0, sw, sh)]
            c = self._scr_cache = (now, lst)
        return c[1]

    def screen_for(self, x, y, w, h):
        """La pantalla que contiene la mayor parte del rectángulo (o la más cercana)."""
        best, area = None, 0
        lst = self.screen_list()
        for s in lst:
            ix = min(x + w, s[0] + s[2]) - max(x, s[0])
            iy = min(y + h, s[1] + s[3]) - max(y, s[1])
            if ix > 0 and iy > 0 and ix * iy > area:
                best, area = s, ix * iy
        if best is None:
            cx, cy = x + w / 2, y + h / 2
            best = min(lst, key=lambda s: (max(s[0] - cx, 0, cx - s[0] - s[2]) ** 2
                                           + max(s[1] - cy, 0, cy - s[1] - s[3]) ** 2))
        return best

    def clamp_rect(self, x, y, w, h):
        """Deja la ventana dentro de su pantalla (p. ej. después de cambiar la resolución)."""
        sx, sy, sw, sh = self.screen_for(x, y, w, h)[:4]
        x = max(sx, min(int(x), sx + sw - int(w)))
        y = max(sy, min(int(y), sy + sh - int(h)))
        return x, y

    def dock_target(self, b):
        """(x, y, ancho, pantalla) de la franja Top Live para la ventana del DAW 'b'."""
        bx, by, bw, bh = b
        scr = self.screen_for(bx, by, bw, bh)
        vx, vy, vw, vh = scr[4:]
        x = max(bx, vx)
        w = min(bx + bw, vx + vw) - x
        if w < 560:
            return None
        return x, vy, w, scr                       # siempre pegada arriba (bajo la barra de menú)

    def _reclamp(self):
        try:
            x, y = self.root.winfo_x(), self.root.winfo_y()
            if (x, y) != self.clamp_rect(x, y, self.W, self.H):
                self._move(x, y)
        except tk.TclError:
            pass

    def watch_screen(self):
        try:
            self._watch_screen()
        except Exception:
            pass
        self.root.after(1500, self.watch_screen)

    def _watch_screen(self):
        """Cada 1.5 s: si cambia la resolución o la ventana del DAW, todo se reacomoda."""
        lst = tuple(self.screen_list(fresh=True))
        changed = getattr(self, "_scr_sig", lst) != lst
        self._scr_sig = lst
        g = self.conf.get("top_mode") and self.conf.get("top_geom")
        if not g:
            if changed:                              # modo libre: nada fuera de pantalla
                self.apply_conf()
                self.root.after(250, self._reclamp)
            return
        if not (self.live_open and self.visible) or self.peek or self._drag \
                or getattr(self, "_resize", None) or mouse_down():
            return
        b = daw_window_bounds(LIVE_PID[0])
        if not b:
            return
        scr = self.screen_for(*b)
        bands = screen_bands()
        idx = lst.index(scr) if scr in lst else -1
        band = bands[idx] if 0 <= idx < len(bands) else None
        inset = band[0] if band else 0
        covers = (abs(b[0] - scr[0]) <= 2 and abs(b[2] - scr[2]) <= 2
                  and b[1] <= scr[1] + inset + 2 and b[1] + b[3] >= scr[1] + scr[3] - 2)
        fs = False
        if covers:
            # ¿pantalla completa o solo maximizada? Accesibilidad lo dice (en otro hilo)
            r = self._bg_take("fs", "nada")
            if r != "nada":
                self._fs_ax = r if isinstance(r, bool) else None
            self._bg("fs", lambda: live_is_fullscreen(LIVE_PID[0]))
            fs = getattr(self, "_fs_ax", None)
            if fs is None:
                fs = True              # sin Accesibilidad no se puede mover el DAW de todos modos
        else:
            self._fs_ax = None
        new_band = None
        if fs:
            new_band = {"left": band[1], "right": band[2]} if band else {"overlay": True}
        if new_band != getattr(self, "fs_band", None):
            self.fs_band = new_band
            self._overlap_n = self._move_tries = 0
            self.apply_conf()
        if fs:
            return                     # en pantalla completa el DAW no se mueve
        t = self.dock_target(b)
        if not t:
            return
        x, gy, w, scr = t
        gx0, gy0, gw0 = self.conf["top_geom"]
        if changed or abs(x - gx0) > 2 or abs(gy - gy0) > 2 or abs(w - gw0) > 2:
            self.conf["top_geom"] = [x, gy, w]   # la franja sigue al DAW y a la pantalla
            self.save_conf()
            self.apply_conf()
        # ¿el DAW tapa la franja o se sale de la pantalla? se le vuelve a hacer espacio
        th = self.top_h
        bx, by, bw, bh = b
        bottom_ok = scr[5] + scr[7]
        bad = by < gy + th - 4 or by + bh > bottom_ok + 4
        if not bad:
            self._overlap_n = self._move_tries = 0
            return
        self._overlap_n = getattr(self, "_overlap_n", 0) + 1
        now = time.monotonic()
        if self._overlap_n >= (1 if changed else 2) and now - getattr(self, "_live_move_t", 0.0) > 4 \
                and getattr(self, "_move_tries", 0) < 3:
            self._live_move_t = now
            self._move_tries = getattr(self, "_move_tries", 0) + 1   # si no se mueve: 3 intentos
            top_y = max(by, gy + th)
            bottom = min(by + bh, bottom_ok)
            if bottom - top_y < 300:
                bottom = bottom_ok
            nx, nw = max(bx, scr[4]), min(bw, scr[6])

            def move():
                wid = live_main_window()[0]
                set_live_window(wid, nx, top_y, nw, bottom - top_y)
            self._bg("move", move)                # osascript en otro hilo: nada se congela

    @property
    def dock_h(self):
        """Alto del timer acoplado: el de la franja, o el de la franja de la cámara en
        pantalla completa."""
        fb = getattr(self, "fs_band", None)
        if fb and fb.get("left"):
            return max(24, fb["left"][3] - 4)
        return self.top_h

    def _bg(self, name, fn):
        """Corre fn() en otro hilo (osascript, Accesibilidad): el timer nunca se congela.
        El resultado queda en self._bg_res[name]."""
        jobs = self.__dict__.setdefault("_jobs", {})
        res = self.__dict__.setdefault("_bg_res", {})
        if jobs.get(name):
            return False
        jobs[name] = True

        def run():
            try:
                out = fn()
            except Exception as e:
                out = e
            res[name] = out
            jobs[name] = False
        threading.Thread(target=run, daemon=True).start()
        return True

    def _bg_take(self, name, default=None):
        return self.__dict__.setdefault("_bg_res", {}).pop(name, default)

    @property
    def top_h(self):
        pct = max(50, min(100, int(self.conf.get("top_escala", 100))))
        return int(round(TOP_H * pct / 100))

    def set_top_scale(self, pct):
        """Cambia el tamaño de la franja; si está acoplada, reacomoda Live al instante."""
        old_h = self.top_h
        self.conf["top_escala"] = int(pct)
        new_h = self.top_h
        if self.conf.get("top_mode") and self.conf.get("top_geom") and new_h != old_h:
            gx, gy, gw = self.conf["top_geom"]
            try:
                wid, x, y, w, h = live_main_window()
                bottom = y + h
                set_live_window(wid, x, gy + new_h, w, bottom - (gy + new_h))
            except Exception:
                pass
        self.save_conf()
        self.apply_conf()
        self.apply_analyzer()
        if hasattr(self, "v_escala"):
            self.v_escala.set(int(pct))

    def pos_key(self):
        return self.conf["vista"] + ("_v" if self.conf.get("orientacion") == "vertical"
                                     else "")

    def set_orient(self, o):
        if self.conf.get("top_mode"):
            self.v_orient.set("horizontal")
            return
        self.conf["orientacion"] = o
        self.save_conf()
        self.apply_conf()

    def set_tema(self, k):
        self.conf["tema"] = k
        self.conf["opacidad"] = TEMAS[k]["alpha"]
        self.save_conf()
        self.apply_conf()

    def set_modo(self, m):
        self.conf["modo"] = m
        self.save_conf()
        self.apply_conf()

    def set_vista(self, v):
        if self.conf.get("top_mode"):
            self.v_vista.set("compacta")
            return
        if v == "mini" and self.conf["vista"] != "mini":
            self.conf["vista_previa"] = self.conf["vista"]
        self.conf["vista"] = v
        self.save_conf()
        self.apply_conf()

    # ---- dibujo -----------------------------------------------------------
    def layout(self):
        prev_disp = {b["key"]: b["disp"] for b in self.bars}
        T, cv = self.T, self.cv
        cv.delete("all")
        self._icache, self._ccache = {}, {}
        self.particles = []
        base = self.clear or T["bg"]
        cv.config(bg=base)
        self.root.config(bg=base)

        self.f_sans = self.pick(SANS_FONTS, text=ACCENTS)
        self.brand = bool(T.get("marca"))                 # Gaux Mode
        self.personal = bool(T.get("personal"))           # Modo Personal
        pc = self.conf.get("personal", {})
        self.ritual = self.brand or self.personal         # bienvenida y tarjeta de cierre
        self.fx = self.brand or (self.personal and pc.get("efectos", True))
        self.angular = self.brand or (self.personal and pc.get("forma") == "angular")
        self.splash_text = "LET'S GAUUUUX" if self.brand else (pc.get("inicio") or "")
        self.card_head = "GG" if self.brand else (pc.get("cierre") or "")
        if self.brand:                      # tipografía única, no editable
            bf = self.pick(BRAND_FONTS)                   # reloj: solo números
            bt = self.pick(BRAND_FONTS, text=ACCENTS)     # textos: con tildes y ñ
            self.f_title = (bt, BRAND_TITLE.get(bt, 15), "bold")
            self.f_clock_family = bf
            self.csize = BRAND_CLOCK.get(bf, 32)
            self.f_label = (bt, 11 if bt == "DIN Condensed" else
                            10 if bt == "Avenir Next Condensed" else 9, "bold")
            self.title_text = BRAND_NAME
            self.f_display = self.pick([bf, bt], text=self.splash_text + self.card_head)
        else:
            title = (pc.get("nombre") or APP_NAME) if self.personal else APP_NAME
            tf = self.pick(TITLE_FONTS, self.conf.get("fuente_titulo"), text=title)
            cf = self.pick(CLOCK_FONTS, self.conf.get("fuente_reloj"))
            self.f_title = (tf, TITLE_SIZES.get(tf, 14),
                            "normal" if tf in TITLE_NO_BOLD else "bold")
            self.f_clock_family = cf
            self.csize = CLOCK_SIZES.get(cf, 30)
            self.f_label = (self.f_sans, 10)
            self.title_text = title
            self.f_display = self.pick([cf] + SANS_FONTS,
                                       text=self.splash_text + self.card_head + ACCENTS)
        self.ghosts, self.scan, self.splash, self.bolts = [], None, None, []
        self.top = bool(self.conf.get("top_mode"))
        self.vertical = self.conf.get("orientacion") == "vertical" and not self.top
        self.goals = [k for k in ("diaria", "semanal", "mensual")
                      if self.conf["metas"][k]["activa"]]
        self.prev_disp = prev_disp
        self.bars, self.hit = [], []
        self.chip_label, self.chip_items = None, []
        self.title_it = self.status_it = self.auto_it = None
        self.proj_it = None
        self.status_font = None
        self.chip_y = None
        if not hasattr(self, "_font_cache"):
            self._font_cache = {}

        vista = "compacta" if self.top else self.conf["vista"]
        mini = vista == "mini"
        self.k = 1.0
        if self.top:
            W, H, R, m = self._layout_dock()
        elif self.vertical:
            W, H, R, m = self._layout_vertical(vista)
        else:
            W, H, R, m = self._layout_horizontal(vista)
        k = 1.0 if self.top else self.scale_for(self.pos_key())
        if abs(k - 1.0) > 0.001:
            W, H, R, m = self._apply_scale(k, W, H, R, m)
        self.W, self.H, self.m_cur = W, H, m
        cv.config(width=W, height=H)
        self._draw_bg(W, H, R, m, mini)
        if self.fx or self.ritual:
            self._brand_fx(W, H, m, mini)
        self._draw_grip(W, H, m)

    # ---- tamaño ajustable --------------------------------------------------
    def scale_for(self, key):
        lo, hi = ESCALA_LIM["mini" if key.startswith("mini") else "otra"]
        try:
            v = float(self.conf.get("escala", {}).get(key, 1.0))
        except (TypeError, ValueError):
            v = 1.0
        return max(lo, min(hi, v))

    def _font_scaled(self, spec, k):
        """Escala una fuente de Tk con piso de legibilidad."""
        parts = list(self.cv.tk.splitlist(spec)) if isinstance(spec, str) else list(spec)
        if len(parts) < 2:
            return spec
        try:
            size = int(float(parts[1]))
        except ValueError:
            return spec
        neg = size < 0
        size = abs(size)
        new = max(int(round(size * k)), min(size, MIN_FONT))
        parts[1] = -new if neg else new
        return tuple(parts)

    def _apply_scale(self, k, W, H, R, m):
        """Escala todo lo dibujado (posiciones, letras, grosores) y la geometría guardada."""
        cv = self.cv
        self.k = k
        cv.scale("all", 0, 0, k, k)
        for it in cv.find_all():
            typ = cv.type(it)
            if typ == "text":
                cv.itemconfig(it, font=self._font_scaled(cv.itemcget(it, "font"), k))
                w = cv.itemcget(it, "width")
                if w and float(w) > 0:
                    cv.itemconfig(it, width=float(w) * k)
            elif typ in ("line", "polygon", "rectangle", "oval"):
                try:
                    w = float(cv.itemcget(it, "width") or 0)
                    if w > 0:
                        cv.itemconfig(it, width=max(1.0, w * k))
                except (tk.TclError, ValueError):
                    pass
        self.hit = [(x1 * k, y1 * k, x2 * k, y2 * k, n) for x1, y1, x2, y2, n in self.hit]
        if self.pp_c:
            self.pp_c = (self.pp_c[0] * k, self.pp_c[1] * k)
        self.pp_s *= k
        self.halo_amp *= k
        self.dot_c = (self.dot_c[0] * k, self.dot_c[1] * k)
        self.dot_r *= k
        for d in self.digits:
            d["x"] *= k
            d["y"] *= k
        for b in self.bars:
            b["x1"] *= k
            b["x2"] *= k
            b["y"] *= k
        if self.chip_y is not None:
            self.chip_y *= k
        self.f_title = self._font_scaled(self.f_title, k)
        self.f_label = self._font_scaled(self.f_label, k)
        self.csize = max(int(self.csize * k), 12)
        self.draw_pp()
        return int(round(W * k)), int(round(H * k)), R * k, m * k

    RZ = 7                                    # ancho de la zona de los bordes

    def in_resize(self, x, y):
        if self.conf.get("top_mode"):
            return False
        return x >= self.W - self.RZ or y >= self.H - self.RZ

    def _draw_grip(self, W, H, m):
        """Asa de la esquina inferior derecha; aparece al pasar el mouse."""
        cv = self.cv
        if self.conf.get("top_mode"):
            self.grip = []
            return
        col = mix(self.T["dim"], self.T["bg"], .25)
        small = H <= 40                         # cápsula: asa mínima, en la esquina
        x2, y2 = (W - 2, H - 2) if small else (W - m - 3, H - m - 3)
        n, st = (2, 3) if small else (3, 4)
        self.grip = [cv.create_line(x2 - st * i, y2, x2, y2 - st * i, fill=col, width=1,
                                    state="hidden") for i in range(1, n + 1)]

    def _show_grip(self, on):
        for it in getattr(self, "grip", []):
            self._ic(it, state="normal" if on else "hidden")

    def resize_start(self, e):
        self._resize = (e.x_root, e.y_root, self.W, self.H, self.scale_for(self.pos_key()))
        self._last_rs = 0.0

    def resize_drag(self, e):
        x0, y0, w0, h0, k0 = self._resize
        rx = (w0 + e.x_root - x0) / w0
        ry = (h0 + e.y_root - y0) / h0
        ratio = rx if abs(rx - 1) >= abs(ry - 1) else ry
        key = self.pos_key()
        lo, hi = ESCALA_LIM["mini" if key.startswith("mini") else "otra"]
        k = max(lo, min(hi, round(k0 * ratio / 0.025) * 0.025))
        if abs(k - self.scale_for(key)) < 0.001:
            return
        now = time.monotonic()
        if now - self._last_rs < 0.03:             # no rehacer más de ~30 veces por segundo
            return
        self._last_rs = now
        self.conf.setdefault("escala", {})[key] = k
        self.relayout()

    def resize_end(self):
        self._resize = None
        x, y = self.root.winfo_x(), self.root.winfo_y()
        self.conf.setdefault("pos", {})[self.pos_key()] = [x, y]
        self.save_conf()

    def reset_scale(self):
        self.conf.setdefault("escala", {}).pop(self.pos_key(), None)
        self.save_conf()
        self.relayout()

    def relayout(self):
        """Redibuja el widget en su sitio (sin tocar el analizador)."""
        x, y = self.root.winfo_x(), self.root.winfo_y()
        self.layout()
        self._move(x, y)
        self.refresh_text()
        self.render_frame(force=True)
        self._show_grip(True)

    def _brand_fx(self, W, H, m, mini):
        """Capas animadas del Gaux Mode: glitch del título, barrido y bienvenida."""
        T, cv = self.T, self.cv
        if self.fx:
            self._fx_layers(W, H, m)
        if self.ritual and self.splash_text:
            self._splash_layer(W, H, m)

    def _fx_layers(self, W, H, m):
        T, cv = self.T, self.cv
        if self.title_it:
            x, y = cv.coords(self.title_it)
            kw = dict(text=self.title_text, font=self.f_title, state="hidden",
                      anchor=cv.itemcget(self.title_it, "anchor"),
                      justify=cv.itemcget(self.title_it, "justify"),
                      width=cv.itemcget(self.title_it, "width"))
            self.ghosts = [cv.create_text(x, y, fill=T["acento2"], **kw),
                           cv.create_text(x, y, fill="#FFFFFF", **kw)]
            for g in self.ghosts:
                cv.tag_lower(g, self.title_it)
            self.title_xy = (x, y)
        self.glitch_next = time.monotonic() + random.uniform(2, 4)
        self.glitch_end = 0.0
        self.scan = cv.create_line(-10, m + 3, -10, H - m - 3, width=2,
                                   fill=mix(T["acento2"], T["bg"], .55))
        cv.tag_lower(self.scan)
        cv.tag_raise(self.scan, self.layers[-1][0])
        # rayos: halo rojo + núcleo blanco, con una rama opcional
        self.bolts = []
        for _ in range(2):
            glow = cv.create_line(0, 0, 0, 0, width=5, fill=mix(T["acento2"], T["bg"], .35),
                                  state="hidden", joinstyle="miter")
            core = cv.create_line(0, 0, 0, 0, width=1.6, fill="#FFFFFF", state="hidden",
                                  joinstyle="miter")
            for it in (core, glow):
                cv.tag_lower(it)
                cv.tag_raise(it, self.scan)
            self.bolts.append((glow, core))
        self.bolt_next = time.monotonic() + random.uniform(1.5, 3.5)
        self.bolt_end = 0.0
        self.bolt_m = m

    def _splash_layer(self, W, H, m):
        T, cv = self.T, self.cv
        shape = chamfer if self.angular else rrect
        self.splash_bg = shape(cv, m + 1, m + 1, W - m - 1, H - m - 1, 12,
                               fill=T["bg"], outline="", state="hidden")
        size = max(10, int(self.csize * .62))
        words = self.splash_text.split()
        text = ("\n".join([" ".join(words[:len(words) // 2 or 1]),
                           " ".join(words[len(words) // 2 or 1:])]).strip()
                if self.vertical and len(words) > 1 else self.splash_text)
        self.splash = cv.create_text(W / 2, H / 2, text=text, justify="center",
                                     font=(self.f_display, size, "bold"),
                                     fill=T["acento2"], state="hidden")
        lines = cv.itemcget(self.splash, "text").split("\n")
        while size > 9:                                  # que quepa en cualquier vista
            f = tkfont.Font(family=self.f_display, size=size, weight="bold")
            if max(f.measure(t) for t in lines) <= W - 2 * m - 12 \
                    and f.metrics("linespace") * len(lines) <= H - 2 * m - 2:
                break
            size -= 1
        cv.itemconfig(self.splash, font=(self.f_display, size, "bold"))

    def _draw_bg(self, W, H, R, m, mini):
        """Resplandor, fondo degradado y borde; se dibuja al final y se manda atrás."""
        T, cv = self.T, self.cv
        if self.angular:
            c = R * (0.6 if mini else 0.9)
            shape = lambda x1, y1, x2, y2, r, **kw: chamfer(cv, x1, y1, x2, y2, c, **kw)
        else:
            shape = lambda *a, **kw: rrect(cv, *a, **kw)
        self.glows = []
        for i, t in (((1, .5),) if mini else ((3, .86), (2, .72), (1, .5))):
            it = shape( m - i, m - i, W - m + i, H - m + i, R + i, fill="",
                       outline=mix(T["borde"], T["bg"], t), width=1, tags=("bg",))
            self.glows.append((it, t))
        self.layers = []
        n = 3 if mini else 9
        for i in range(n):
            t = i / (n - 1)
            y2 = H - m if mini else max(H - m - (H - 2 * m) * 0.8 * t, m + 2 * R + 2)
            it = shape(m, m, W - m, y2, R, outline="", tags=("bg",),
                       fill=mix(T["bg"], T["bg2"], t * 0.9))
            self.layers.append((it, t))
        self.border = shape(m, m, W - m, H - m, R, fill="", tags=("bg",),
                            outline=T["borde"], width=1 if mini else 1.5)
        for it, _ in reversed(self.layers):
            cv.tag_lower(it)
        cv.tag_lower(self.border)
        cv.tag_raise(self.border, self.layers[-1][0])
        for it, _ in self.glows:
            cv.tag_lower(it)

    def _goal_bar(self, k, x1, x2, by, lbl, val):
        T, cv = self.T, self.cv
        cap, bw = ("butt", 5) if self.angular else ("round", 6)
        track = cv.create_line(x1, by, x2, by, width=bw, capstyle=cap, fill=T["pista"])
        fill = cv.create_line(x1, by, x1, by, width=bw, capstyle=cap,
                              fill=T["acento"], state="hidden")
        shine = cv.create_line(x1, by, x1, by, width=2, capstyle=cap,
                               fill="#ffffff", state="hidden")
        self.bars.append(dict(key=k, lbl=lbl, val=val, track=track, fill=fill,
                              shine=shine, x1=x1, x2=x2, y=by, p=0.0,
                              disp=self.prev_disp.get(k, 0.0), done=False))

    def _dot(self, cx, cy, r, halo_w=1.5):
        self.dot_c, self.dot_r = (cx, cy), r
        mk = self.cv.create_rectangle if self.angular else self.cv.create_oval
        self.halo = mk(0, 0, 0, 0, outline="", width=halo_w)
        self.dot = mk(0, 0, 0, 0, fill=self.T["dim"], outline="")

    def _layout_dock(self):
        """Timer acoplado en la franja Top Live: se reacomoda según su altura."""
        T, cv = self.T, self.cv
        H = self.dock_h
        k = H / TOP_H
        m = 6 if k >= 0.8 else 4
        R = max(8, int(16 * k))
        self.halo_amp, self.pp_s = 4.0 * k, max(0.62, k)
        show_title = H >= 92
        show_status = H >= 112
        x0 = m + max(8, int(14 * k))
        tf = self.f_title
        tsize = max(9, int(tf[1] * k))
        tfont = (tf[0], tsize, tf[2])
        dsize = int(min(self.csize * max(k, 0.62), H * (0.34 if show_title else 0.5)))
        dsize = max(15, dsize)
        dfont = (self.f_clock_family, dsize, "bold")
        f = tkfont.Font(family=dfont[0], size=dsize, weight="bold")
        dig_w = 6 * max(f.measure(d) for d in "0123456789") + 2 * (f.measure(":") + max(2, dsize // 7))
        btn = max(18, int(24 * k))
        bsize = max(11, int(14 * k))
        if show_title:
            title_w = tkfont.Font(family=tfont[0], size=tsize, weight=tfont[2]).measure(self.title_text)
            lead = 0 if show_status else 14
            W = int(max(dig_w + 2 * x0, x0 + lead + title_w + 2 * btn + 14))
            ty = m + max(11, int(20 * k))
        else:
            W = int(x0 + 16 + dig_w + 2 * btn + 12)
            ty = H / 2
        # botones (pausa y ajustes)
        by = ty
        self.button(W - m - btn * 0.7, by, "⚙", "cfg", bsize, pad=btn // 2)
        self.pp_c = (W - m - btn * 1.75, by)
        self.hit.append((W - m - btn * 2.25, by - btn / 2, W - m - btn * 1.25, by + btn / 2, "pp"))
        self.draw_pp()
        # título / estado
        if show_status:
            self.title_it = cv.create_text(x0, ty, text=self.title_text, anchor="w",
                                           font=tfont, fill=T["acento2"])
            sy = ty + max(18, int(26 * k))
            self._dot(x0 + 4, sy, max(2.5, 3.5 * k))
            self.status_it = cv.create_text(x0 + 15, sy, text="", anchor="w",
                                            font=(self.f_label[0], max(8, int(self.f_label[1] * k)),
                                                  *self.f_label[2:]),
                                            fill=T["dim"])
            self.status_font = cv.itemcget(self.status_it, "font")
            top_used = sy + 8
        elif show_title:
            self._dot(x0 + 4, ty, max(2.5, 3.5 * k))
            self.title_it = cv.create_text(x0 + 14, ty, text=self.title_text, anchor="w",
                                           font=tfont, fill=T["acento2"])
            top_used = ty + tsize * 0.6
        else:
            self._dot(x0 + 4, H / 2, max(2.5, 3.5 * k))
            top_used = m
        if show_title:
            dy = (top_used + (H - m)) / 2
            self.digits = self.draw_digits(x0 - 2, dy, dfont, glow=True)
        else:
            self.digits = self.draw_digits(x0 + 14, H / 2, dfont, glow=dsize >= 20)
        return W, H, R, m

    def _layout_horizontal(self, vista):
        T, cv = self.T, self.cv
        cf, csize, goals = self.f_clock_family, self.csize, self.goals
        if vista == "mini":                # cápsula para la barra de Live: lo justo
            m, H, R = 1, 26, 11
            self.halo_amp, self.pp_s = 2.0, 0.7
            cy = H / 2
            font = (cf, 15, "bold")
            f = tkfont.Font(family=cf, size=15, weight="bold")
            dig_w = 6 * max(f.measure(d) for d in "0123456789") + 2 * (f.measure(":") + 2)
            x_dig = m + 17
            x_pp = x_dig + dig_w + 11
            W = int(x_pp + 27)
            self._dot(m + 9, cy, 3, 1)
            self.digits = self.draw_digits(x_dig, cy, font, glow=False)
            self.pp_c = (x_pp, cy)
            self.hit.append((x_pp - 9, 0, x_pp + 8, H, "pp"))
            self.draw_pp()
            self.button(W - m - 12, cy, "□", "max", 10, pad=7)
            return W, H, R, m

        m, W, R = self.MARGIN, 304, 16
        self.halo_amp, self.pp_s = 4.0, 1.0
        H = 132 if vista == "compacta" else 132 + 14 + 16 + 32 * len(goals) + 26
        x0 = m + 14
        self.title_it = cv.create_text(x0, m + 20, text=self.title_text, anchor="w",
                                       font=self.f_title, fill=T["acento2"])
        limit = W - m - 84                  # no pisar los botones
        while cv.bbox(self.title_it)[2] > limit and self.f_title[1] > 9:
            self.f_title = (self.f_title[0], self.f_title[1] - 1, self.f_title[2])
            cv.itemconfig(self.title_it, font=self.f_title)
        self.button(W - m - 18, m + 20, "⚙", "cfg", 14)
        if not self.top:                    # acoplado: no se minimiza
            self.button(W - m - 42, m + 18, "–", "min", 16)
        self.pp_c = (W - m - 66, m + 20)
        self.hit.append((W - m - 78, m + 8, W - m - 54, m + 32, "pp"))
        self.draw_pp()

        cy = m + 46
        self._dot(x0 + 4, cy, 3.5)
        self.status_it = cv.create_text(x0 + 15, cy, text="", anchor="w",
                                        font=self.f_label, fill=T["dim"])
        self.digits = self.draw_digits(x0 - 2, m + 87, (cf, csize, "bold"), glow=True)
        if vista != "completa":
            return W, H, R, m
        self._proj_row(x0, m + 124, W - m - 14 - x0, "w")
        y = m + 140
        cv.create_line(x0, y, W - m - 14, y, fill=mix(T["borde"], T["bg"], .78))
        y += 8
        for k in goals:
            g = self.conf["metas"][k]
            lbl = cv.create_text(x0, y + 6, anchor="w", text=g["nombre"].upper() if self.brand else g["nombre"],
                                 font=self.f_label if self.brand else (self.f_sans, 10, "bold"),
                                 fill=T["texto"])
            val = cv.create_text(W - m - 14, y + 6, anchor="e", text="",
                                 font=(self.f_sans, 10), fill=T["dim"])
            self._goal_bar(k, x0 + 3, W - m - 17, y + 21, lbl, val)
            y += 32
        self.auto_it = cv.create_text(x0, y + 9, anchor="w", text="",
                                      font=self.f_label if self.brand else (self.f_sans, 10, "italic"),
                                      fill=T["dim"])
        return W, H, R, m

    def _layout_vertical(self, vista):
        T, cv = self.T, self.cv
        cf, csize, goals = self.f_clock_family, self.csize, self.goals
        if vista == "mini":                # columna fina
            m, W, R = 1, 44, 15
            self.halo_amp, self.pp_s = 2.5, 0.78
            cx = W / 2
            self._dot(cx, m + 15, 3.5, 1)
            self.digits = self.draw_digits_v(cx, m + 38, (cf, 15, "bold"), 23, glow=False)
            self.pp_c = (cx, m + 112)
            self.hit.append((m, m + 100, W - m, m + 124, "pp"))
            self.draw_pp()
            self.button(cx, m + 134, "□", "max", 12, pad=11)
            return W, m + 152, R, m

        m, W, R = self.MARGIN, 168, 16
        self.halo_amp, self.pp_s = 4.0, 1.0
        cx, x0 = W / 2, m + 14
        t = cv.create_text(cx, m + 12, text=self.title_text, anchor="n", justify="center",
                           width=W - 2 * m - 16, font=self.f_title, fill=T["acento2"])
        self.title_it = t
        y = cv.bbox(t)[3] + 14
        self.pp_c = (cx - 26, y)
        self.hit.append((cx - 38, y - 12, cx - 14, y + 12, "pp"))
        self.draw_pp()
        self.button(cx, y - 1, "–", "min", 16)
        self.button(cx + 26, y, "⚙", "cfg", 14)
        y += 22
        self._dot(cx, y, 3.5)
        self.status_it = cv.create_text(cx, y + 9, text="", anchor="n", justify="center",
                                        width=W - 2 * m - 16,
                                        font=self.f_label, fill=T["dim"])
        y += 46
        step = int(csize * 1.3)
        self.digits = self.draw_digits_v(cx - 6, y + csize * 0.6, (cf, csize, "bold"),
                                         step, glow=True)
        for i, u in enumerate("hms"):
            cv.create_text(cx + csize * 0.75, y + csize * 0.6 + i * step + csize * 0.2,
                           text=u, anchor="w", font=(self.f_sans, 10), fill=T["dim"])
        y += 3 * step + 8
        if vista != "completa":
            return W, y + m, R, m
        self._proj_row(W / 2, y + 2, W - 2 * m - 20, "center")
        y += 18
        cv.create_line(x0, y, W - m - 14, y, fill=mix(T["borde"], T["bg"], .78))
        y += 10
        for k in goals:
            g = self.conf["metas"][k]
            lbl = cv.create_text(x0, y + 6, anchor="w", text=g["nombre"].upper() if self.brand else g["nombre"],
                                 font=self.f_label if self.brand else (self.f_sans, 10, "bold"),
                                 fill=T["texto"])
            val = cv.create_text(x0, y + 35, anchor="w", text="",
                                 font=(self.f_sans, 9), fill=T["dim"])
            self._goal_bar(k, x0 + 3, W - m - 17, y + 21, lbl, val)
            y += 50
        self.auto_it = cv.create_text(cx, y + 2, anchor="n", text="", justify="center",
                                      width=W - 2 * m - 20,
                                      font=self.f_label if self.brand else (self.f_sans, 10, "italic"),
                                      fill=T["dim"])
        self.chip_y = y + 46
        return W, y + 66 + m, R, m

    def _proj_row(self, x, y, maxw, anchor):
        """Fila con el proyecto activo y su tiempo total."""
        f = self.f_label if self.brand else (self.f_sans, 10)
        self.proj_it = self.cv.create_text(x, y, text="", anchor=anchor, font=f,
                                           fill=self.T["dim"],
                                           justify="center" if anchor == "center" else "left")
        self.proj_w = maxw
        self.hit.append((x - (maxw / 2 if anchor == "center" else 0), y - 9,
                         x + (maxw / 2 if anchor == "center" else maxw), y + 9, "proj"))

    def fit_text(self, text, font, maxw):
        """Recorta el texto con '…' para que quepa en maxw píxeles."""
        key = (font, )
        fobj = self._font_cache.get(key)
        if fobj is None:
            spec = font if isinstance(font, (tuple, list)) else self.cv.tk.splitlist(font)
            fobj = tkfont.Font(family=spec[0], size=abs(int(spec[1])),
                               weight="bold" if "bold" in spec[2:] else "normal")
            self._font_cache[key] = fobj
        if fobj.measure(text) <= maxw:
            return text
        while text and fobj.measure(text + "…") > maxw:
            text = text[:-1]
        return text.rstrip() + "…"

    def proj_text(self, maxw, font):
        pn = self.project_name()
        tot = self.project_values(pn)["total"]
        auto = self.conf.get("proyecto_auto", True) and self.detected == pn
        label = pn.upper() if self.brand else pn
        tail = f" · {fmt_short(tot)}" + (" · auto" if auto and not self.brand else "")
        if self.brand and auto:
            tail += " · AUTO"
        head = "▸ "
        name = self.fit_text(label, font, maxw - self.fit_w(head + tail, font))
        return head + name + tail

    def fit_w(self, text, font):
        self.fit_text("", font, 1)                       # asegura la fuente en caché
        return self._font_cache[(font, )].measure(text)

    def button(self, x, y, glyph, name, size, pad=12):
        self.cv.create_text(x, y, text=glyph, font=(self.f_sans, size, "bold"),
                            fill=self.T["dim"], tags=("btn_" + name,))
        self.hit.append((x - pad, y - pad, x + pad, y + pad, name))

    def draw_pp(self):
        """Botón pausa/reanudar dibujado con formas (no depende de la fuente)."""
        cv, T = self.cv, self.T
        cv.delete("btn_pp")
        if not self.pp_c:
            return
        cx, cy = self.pp_c
        k = self.pp_s
        if self.manual:      # mostrar ▶ resaltado para invitar a reanudar
            col = "#FFFFFF" if self.hover == "pp" else T["acento2"]
            cv.create_polygon(cx - 4 * k, cy - 6 * k, cx - 4 * k, cy + 6 * k, cx + 6 * k, cy,
                              fill=col, outline="", tags=("btn_pp",))
        else:
            col = T["acento2"] if self.hover == "pp" else T["dim"]
            for x1 in (cx - 5 * k, cx + 1.5 * k):
                cv.create_rectangle(x1, cy - 6 * k, x1 + 3.5 * k, cy + 6 * k, fill=col,
                                    outline="", tags=("btn_pp",))

    def update_chip(self, label):
        """Botón de acción junto a la línea del modo autónomo."""
        if label == self.chip_label:
            return
        self.chip_label = label
        cv, T, m = self.cv, self.T, self.MARGIN
        for it in self.chip_items:
            cv.delete(it)
        self.chip_items = []
        self.hit = [h for h in self.hit if h[4] != "chip"]
        if not label or not self.auto_it:
            return
        label = CHIP_TXT[bool(self.brand)][label]
        k = getattr(self, "k", 1.0)
        f = (self.f_label[0], max(9, abs(int(self.f_label[1]))), "bold") if self.brand \
            else self._font_scaled((self.f_sans, 10, "bold"), k)
        tw = tkfont.Font(family=f[0], size=f[1], weight=f[2]).measure(label)
        pad, hh = 18 * k, 10 * k
        if self.chip_y is not None:          # vertical: centrado debajo
            y = self.chip_y
            x1 = self.W / 2 - (tw + pad) / 2
            x2 = x1 + tw + pad
        else:
            y = cv.coords(self.auto_it)[1]
            x2 = self.W - (m + 14) * k
            x1 = x2 - tw - pad
        bg = rrect(cv, x1, y - hh, x2, y + hh, 9 * k, outline="", fill=T["pista"],
                   tags=("chip",))
        tx = cv.create_text((x1 + x2) / 2, y, text=label, font=f, fill="#FFFFFF",
                            tags=("chip",))
        self.chip_items = [bg, tx]
        self.hit.append((x1, y - hh - 1, x2, y + hh + 1, "chip"))

    def draw_digits(self, x, yc, font, glow):
        f = tkfont.Font(family=font[0], size=font[1], weight=font[2])
        dw = max(f.measure(d) for d in "0123456789")
        cw = f.measure(":") + max(2, font[1] // 7)
        items, cx = [], x
        for ch in "00:00:00":
            w = cw if ch == ":" else dw
            px = cx + w / 2
            gl = []
            if glow:
                for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (0, 2)):
                    gl.append((self.cv.create_text(px + dx, yc + dy, text=ch, font=font,
                                                   fill=self.T["bg2"]), dx, dy))
            main = self.cv.create_text(px, yc, text=ch, font=font, fill=self.T["texto"])
            items.append(dict(main=main, glows=gl, x=px, y=yc, ch=ch, off=0.0))
            cx += w
        return items

    def draw_digits_v(self, cx, y0, font, step, glow):
        """Reloj apilado: HH / MM / SS (los dos puntos quedan ocultos)."""
        f = tkfont.Font(family=font[0], size=font[1], weight=font[2])
        dw = max(f.measure(d) for d in "0123456789")
        rows = {0: (0, -1), 1: (0, 1), 2: (0, None), 3: (1, -1), 4: (1, 1),
                5: (1, None), 6: (2, -1), 7: (2, 1)}
        items = []
        for i, ch in enumerate("00:00:00"):
            row, side = rows[i]
            px = cx + (side or 0) * dw / 2
            py = y0 + row * step
            state = "hidden" if side is None else "normal"
            gl = []
            if glow:
                for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (0, 2)):
                    gl.append((self.cv.create_text(px + dx, py + dy, text=ch, font=font,
                                                   fill=self.T["bg2"], state=state), dx, dy))
            main = self.cv.create_text(px, py, text=ch, font=font,
                                       fill=self.T["texto"], state=state)
            items.append(dict(main=main, glows=gl, x=px, y=py, ch=ch, off=0.0))
        return items

    def set_clock(self, text):
        anim = self.conf["animaciones"]
        for d, ch in zip(self.digits, text):
            if d["ch"] != ch:
                d["ch"] = ch
                self.cv.itemconfig(d["main"], text=ch)
                for it, _, _ in d["glows"]:
                    self.cv.itemconfig(it, text=ch)
                if anim:
                    d["off"] = -6.0
                    if self.fx:
                        d["flash"] = 1.0

    # ---- texto (1 vez por segundo) ---------------------------------------
    def goal_values(self):
        dias = self.data["dias"]
        today = dt.date.today()
        monday = (today - dt.timedelta(days=today.weekday())).isoformat()
        month = today.replace(day=1).isoformat()
        return {"diaria": dias.get(today.isoformat(), 0),
                "semanal": sum(v for k, v in dias.items() if k >= monday),
                "mensual": sum(v for k, v in dias.items() if k >= month)}

    def _v(self, normal, gaux):
        return gaux if self.brand else normal

    def fatigue(self):
        a = self.conf["autonomo"]
        work, brk = a["trabajo_min"] * 60, a["break_min"] * 60
        if self.manual == "break":
            left = brk - (self.vclock - self.break_start_v)
            if left > 0:
                return -1, self._v(f"En break · quedan {fmt_mmss(left)}", f"RECHARGE · {fmt_mmss(left)}")
            return -2, self._v("Break completo", "RECHARGED")
        if self.conf["modo"] != "autonomo":
            return 0, NORMAL_TIPS[int(time.time() // 45) % len(NORMAL_TIPS)]
        rested = (self.vclock - self.last_count_v) if self.last_count_v is not None else None
        streak = 0 if (rested is not None and rested >= brk) else self.streak
        today_s = self.goal_values()["diaria"]
        if self.counting:
            if a["max_diario_h"] > 0 and today_s >= a["max_diario_h"] * 3600:
                return 2, self._v(f"{fmt_short(today_s)} hoy · descansa", f"{fmt_short(today_s)} HOY · RECHARGE")
            if streak >= work:
                return 2, self._v("¡Hora de un break!", "TIME TO RECHARGE")
            rem = work - streak
            if streak >= work * 0.8:
                return 1, self._v(f"Break en {fmt_ceil(rem)}", f"RECHARGE IN {fmt_ceil(rem)}")
            return 0, self._v(f"Racha {fmt_short(streak)} · break en {fmt_ceil(rem)}", f"STREAK {fmt_short(streak)} · RECHARGE IN {fmt_ceil(rem)}")
        if self.manual == "pausa":
            return 0, self._v(f"Racha {fmt_short(streak)} · pausado", f"STREAK {fmt_short(streak)} · HOLD")
        if streak <= 0:
            return 0, self._v("Energía al 100% · listo para crear", "FULL POWER · LET'S GAUUUUX")
        if streak >= work * 0.8:
            return -1, self._v(f"Descansando {fmt_mmss(rested or 0)} / {fmt_mmss(brk)}", f"RECHARGE · {fmt_mmss(rested or 0)} / {fmt_mmss(brk)}")
        return 0, self._v(f"Racha {fmt_short(streak)} · en pausa", f"STREAK {fmt_short(streak)} · HOLD")

    def refresh_text(self):
        self.set_clock(fmt_clock(self.session))
        if self.status_it:
            txt = GAUX_STATUS[self.state] if self.brand else {"sesion": "En sesión",
                   "fondo": "Pausa · fuera del DAW",
                   "inactivo": "Pausa · sin actividad",
                   "pausa": "Pausado",
                   "break": "En break",
                   "espera": "Esperando a tu DAW…"}[self.state]
            if self.top and getattr(self, "status_font", None) is not None:
                maxw = self.W - self.cv.coords(self.status_it)[0] - self.m_cur - 6
                pn = self.project_name()
                if pn != SIN_PROYECTO:
                    txt = txt + " · " + (pn.upper() if self.brand else pn)
                txt = self.fit_text(txt, self.status_font, maxw)
            self.cv.itemconfig(self.status_it, text=txt)
        if self.proj_it:
            f = self.cv.itemcget(self.proj_it, "font")
            self._ic(self.proj_it, text=self.proj_text(self.proj_w, f))
        vals = self.goal_values()
        for b in self.bars:
            g = self.conf["metas"][b["key"]]
            cur, tgt = vals[b["key"]], max(60, g["segundos"])
            b["p"] = min(1.0, cur / tgt)
            done = cur >= tgt
            if done and self.reached.get(b["key"]) is False:
                self.burst(b)
            self.reached[b["key"]] = done
            b["done"] = done
            if done:
                if self.brand:
                    vt = "✦ CRUSHED" if self.vertical else f"✦ {fmt_short(cur)} · GOAL CRUSHED"
                else:
                    vt = (f"✦ {fmt_short(cur)} · cumplida" if self.vertical
                          else f"✦ {fmt_short(cur)} · ¡meta cumplida!")
            else:
                vt = f"{fmt_short(cur)} / {fmt_goal(tgt)}"
            self.cv.itemconfig(b["val"], text=vt)
        self.lvl, self.auto_msg = self.fatigue()
        if self.auto_it:
            self.cv.itemconfig(self.auto_it, text=self.auto_msg)
            if self.manual == "break":
                chip = "volver" if self.lvl == -1 else "reanudar"
            elif self.counting and self.lvl >= 1:
                chip = "break"
            else:
                chip = None
            self.update_chip(chip)
        self.draw_pp()

    # ---- animación --------------------------------------------------------
    def burst(self, b):
        if not self.conf["animaciones"]:
            return
        x, y = b["x2"], b["y"]
        for _ in range(12):
            ang = random.uniform(math.pi * 1.05, math.pi * 1.95)
            sp = random.uniform(35, 85)
            it = self.cv.create_text(x, y, text=random.choice("✦✧*·"),
                                     font=(self.f_sans, random.randint(9, 14), "bold"),
                                     fill=GOLD)
            self.particles.append(dict(it=it, x=x, y=y, vx=math.cos(ang) * sp,
                                       vy=math.sin(ang) * sp, life=1.4, max=1.4))

    def _ic(self, item, **kw):
        """itemconfig solo si algo cambió (ahorra redibujos y CPU)."""
        if self._icache.get(item) != kw:
            self.cv.itemconfig(item, **kw)
            self._icache[item] = kw

    def _co(self, item, *c):
        """coords solo si cambió (lectura si no se pasan coordenadas)."""
        if not c:
            return self.cv.coords(item)
        c = tuple(round(v, 1) for v in c)
        if self._ccache.get(item) != c:
            self.cv.coords(item, *c)
            self._ccache[item] = c

    def render_frame(self, force=False):
        T, cv = self.T, self.cv
        anim = self.conf["animaciones"]
        now = time.monotonic()
        dtf = min(0.1, now - self.last_frame)
        self.last_frame = now
        self._dtf = dtf
        f20 = dtf * 20                                   # 1.0 = un cuadro de los 20 fps de antes
        self.frame_n += 1
        ph = self.phase
        q = 10.0                                    # 10 niveles: colores que se repiten
        s = round((math.sin(ph * 2.4) + 1) / 2 * q) / q if anim else 0.7
        slow = round((math.sin(ph * 0.9) + 1) / 2 * q) / q if anim else 0.5
        fast = round((math.sin(ph * 7.0) + 1) / 2 * q) / q if anim else 1.0
        lvl = self.lvl
        # colores ≤ 30 veces/s (los pulsos son lentos); el movimiento va a fps completos
        style = force or not anim or now - getattr(self, "_style_t", 0.0) >= 1 / 30
        if style:
            self._style_t = now
        heavy = style

        if lvl == 2 and self.counting:
            key, p = self.T.get("alerta", ALERT), fast
        elif lvl == 1 and self.counting:
            key, p = WARN, s
        elif self.counting:
            key, p = T["borde"], s
        elif lvl == -2:
            key, p = T["acento2"], s
        else:
            key, p = mix(T["borde"], T["bg"], .45), 0.3

        if style:
            self._ic(self.border, outline=mix(key, T["bg"], 0.4 * (1 - p)))
            for it, t in self.glows:
                self._ic(it, outline=mix(key, T["bg"], t + (1 - p) * (1 - t) * 0.6))
        if heavy:
            tint = T["bg2"] if lvl <= 0 or not self.counting else mix(T["bg2"], key, .3)
            breath = 0.75 + 0.25 * slow
            for it, t in self.layers:
                self._ic(it, fill=mix(T["bg"], tint, t * 0.9 * breath))

        # punto de estado
        if self.counting:
            dot = T["acento2"] if lvl <= 0 else key
        elif lvl in (-1, -2):
            dot = T["acento2"]
        else:
            dot = T["dim"]
        (cx, cy), r = self.dot_c, self.dot_r
        if style:
            self._co(self.dot, cx - r, cy - r, cx + r, cy + r)
            self._ic(self.dot, fill=dot)
            if self.counting and anim:
                hr = r + self.halo_amp * (0.5 + s)
                self._co(self.halo, cx - hr, cy - hr, cx + hr, cy + hr)
                self._ic(self.halo, outline=mix(dot, T["bg"], 0.3 + 0.65 * s))
            else:
                self._ic(self.halo, outline="")
            if self.title_it:
                self._ic(self.title_it, fill=mix(T["acento"], T["acento2"], slow))

        # dígitos con rebote y resplandor
        if self.counting:
            main = mix(T["texto"], self.T.get("alerta", ALERT), 0.4 * fast) if lvl == 2 else T["texto"]
            glow = mix(self.T.get("alerta", ALERT) if lvl == 2 else T["acento"], T["bg"], 0.5 - 0.2 * s)
        else:
            main = mix(T["texto"], T["bg"], 0.42)
            glow = mix(T["acento"], T["bg"], 0.82)
        for d in self.digits:
            if heavy:
                self._ic(d["main"], fill=main)
                for it, _, _ in d["glows"]:
                    self._ic(it, fill=glow)
            if d["off"] != 0.0:
                d["off"] *= 0.7 ** f20
                if abs(d["off"]) < 0.3:
                    d["off"] = 0.0
                self._co(d["main"], d["x"], d["y"] + d["off"])
                for it, dx, dy in d["glows"]:
                    self._co(it, d["x"] + dx, d["y"] + dy + d["off"])

        # barras de metas
        for b in self.bars:
            b["disp"] += (b["p"] - b["disp"]) * ((1 - 0.88 ** f20) if anim and not force else 1.0)
            x1, x2, y = b["x1"], b["x2"], b["y"]
            w = (x2 - x1) * b["disp"]
            col = GOLD if b["done"] else mix(T["acento"], T["acento2"], b["disp"])
            if w < 1:
                self._ic(b["fill"], state="hidden")
            else:
                self._co(b["fill"], x1, y, x1 + w, y)
                self._ic(b["fill"], state="normal", fill=col)
            if heavy:
                self._ic(b["val"], fill=GOLD if b["done"] else T["dim"])
            if anim and w > 24:
                pos = x1 + (ph * 55) % w
                self._co(b["shine"], max(x1, pos - 12), y, pos, y)
                self._ic(b["shine"], state="normal", fill=mix(col, "#ffffff", .55))
            else:
                self._ic(b["shine"], state="hidden")

        if self.chip_items and style:
            bg_it = self.chip_items[0]
            if self.chip_label == "break":
                self._ic(bg_it, fill=mix(self.T.get("alerta", ALERT) if lvl == 2 else WARN, T["bg"],
                                              0.15 + 0.3 * (1 - s)))
            elif self.chip_label == "reanudar":
                self._ic(bg_it, fill=mix(T["acento"], T["bg"], 0.3 * (1 - s)))
            else:
                self._ic(bg_it, fill=T["acento"] if self.hover == "chip"
                              else T["pista"])

        if self.auto_it and style:
            if lvl == 2 and self.counting:
                c = mix(self.T.get("alerta", ALERT), T["texto"], 0.35 * fast)
            elif lvl == 1 and self.counting:
                c = WARN
            elif lvl in (-1, -2):
                c = T["acento2"]
            else:
                c = T["dim"]
            self._ic(self.auto_it, fill=c)

        if self.fx or self.ritual:
            self._brand_frame(now, anim)

        # partículas de meta cumplida
        alive = []
        for pt in self.particles:
            pt["life"] -= dtf
            if pt["life"] <= 0:
                cv.delete(pt["it"])
                continue
            pt["vy"] += 60 * dtf
            pt["x"] += pt["vx"] * dtf
            pt["y"] += pt["vy"] * dtf
            self._co(pt["it"], pt["x"], pt["y"])
            self._ic(pt["it"], fill=mix(GOLD, T["bg"], 1 - pt["life"] / pt["max"]))
            alive.append(pt)
        self.particles = alive

    def watch_front(self, reschedule=True):
        """Muestra el widget solo con Live al frente (o mientras lo usas)."""
        if self.live_open and self.visible and self.conf.get("top_mode") \
                and self.conf.get("top_geom") and not self._drag:
            self._keep_docked()
        if self.live_open:
            # Solo se consulta al sistema qué app está al frente (no a Live): nada de esto
            # pasa por el hilo de Live, así que no puede afectar arrastres ni clics.
            self.front = "live" if DEMO else frontmost_app()
            if self.front == "live":
                self._other_n = 0
                self.last_front_live = True
            elif self.front == "other":
                # confirmar dos lecturas seguidas antes de ocultarse (evita parpadeos)
                self._other_n = getattr(self, "_other_n", 0) + 1
                if self._other_n >= 2:
                    self.last_front_live = False
                    self.ui_busy = False
            self.set_visible((self.last_front_live or self._settings_open()) and not self.ui_busy)
        else:
            self.set_visible(False)
        if reschedule:
            self.root.after(400, self.watch_front)

    def raise_timer(self):
        """El timer queda sobre el analizador; los dos, debajo de los plugins del DAW."""
        if not self.visible:
            return
        if self.stack():
            return
        try:
            self.root.lift()
        except tk.TclError:
            pass

    def stack(self):
        """Pone el timer y el analizador en la capa de los plugins, al fondo: sobre la
        ventana del DAW, debajo de los plugins (se pueden mover y cerrar libremente)."""
        try:
            self.root.update_idletasks()
            an = self.analyzer
            wins = [self.root] + ([an.win] if an and an.visible else [])
            ok = stack_windows(wins, LIVE_PID[0])
        except Exception:
            ok = False
        self._stacked = ok
        return ok

    def restack_soon(self, ms=60):
        if getattr(self, "_restack_id", None):
            try:
                self.root.after_cancel(self._restack_id)
            except tk.TclError:
                pass
        self._restack_id = self.root.after(ms, self._restack_now)

    def _restack_now(self):
        self._restack_id = None
        self.raise_timer()

    def watch_peek(self):
        """Top Live: si el mouse toca el borde superior de la pantalla, la franja se aparta
        para que macOS muestre la barra de menú y los botones de pantalla completa."""
        delay = 500
        if self.conf.get("top_mode") and self.live_open and self.conf.get("top_geom"):
            delay = 120
            try:
                px, py = self.root.winfo_pointerxy()
                gx, gy, gw = self.conf["top_geom"]
                inside_x = gx - 2 <= px <= gx + gw + 2
                if not self.peek and py <= 2 and inside_x and not mouse_down():
                    self.peek = True
                    self._menu_t = time.monotonic()           # margen para abrir un menú
                    self._clicks = click_count()
                    self._menu_armed = 0.0
                    self._ax_state, self._ax_t = (False, False), 0.0
                    self.set_visible(False, force=True)
                elif self.peek:
                    now = time.monotonic()
                    r = self._bg_take("ax")
                    if isinstance(r, tuple):
                        self._ax_state = r
                    if now - getattr(self, "_ax_t", 0.0) >= 0.25:     # ≤ 4 consultas por segundo
                        self._ax_t = now
                        self._bg("ax", lambda: live_ui_state(LIVE_PID[0], check_menu=True))
                    menu, dlg = getattr(self, "_ax_state", (False, False))
                    # respaldo sin Accesibilidad: un clic en la barra de menú abre un menú;
                    # el siguiente clic (elegir una opción o cerrarlo) lo cierra
                    c = click_count()
                    if c != self._clicks:
                        self._clicks = c
                        if self._menu_armed:
                            self._menu_armed = 0.0
                        elif py <= gy + 45:
                            self._menu_armed = now
                    if self._menu_armed and now - self._menu_armed > 20:
                        self._menu_armed = 0.0                # por si se perdió un clic
                    if menu or dlg or self._menu_armed or py <= max(self.top_h, 90) + gy + 24:
                        self._menu_t = now                    # menú abierto o mouse arriba
                    self.ui_busy = dlg
                    if now - self._menu_t > 0.6 and not dlg:  # menú cerrado y mouse abajo
                        self.peek = False
                        self.set_visible((self.last_front_live or self._settings_open())
                                         and not self.ui_busy)
                        if not getattr(self, "fs_band", None):  # por si Live cambió de tamaño
                            self.root.after(150, lambda: self._bg("reapply", self.reapply_top))
            except tk.TclError:
                pass
        elif self.peek:
            self.peek = False
        self.root.after(delay, self.watch_peek)

    def set_visible(self, show, force=False):
        if self.peek and not force:
            show = False
        if self.analyzer:
            was = self.analyzer.visible
            self.analyzer.set_visible(show and self.conf["analizador"]["activo"])
            if self.analyzer.visible and not was:
                self.root.after(30, self.raise_timer)
        if show == self.visible:
            return
        self.visible = show
        if show:
            self.root.deiconify()
            if not getattr(self, "_stacked", False):
                self.root.attributes("-topmost", True)
            self.restack_soon(40)
            if self.pending_splash:
                self.pending_splash = False
                if self.ritual:                        # ritual de inicio de sesión
                    self.splash_until = time.monotonic() + 2.2
            self.render_frame(force=True)
        else:
            self._drag = None
            self.root.withdraw()

    def _brand_frame(self, now, anim):
        T, cv = self.T, self.cv
        # destello rojo en el dígito que acaba de cambiar
        for d in self.digits:
            fl = d.get("flash", 0.0)
            if fl > 0.01:
                d["flash"] = fl * 0.86 ** (getattr(self, "_dtf", 0.05) * 20)
                self._ic(d["main"], fill=mix(T["texto"], T["acento2"], fl))
            elif fl:
                d["flash"] = 0.0
                self._ic(d["main"], fill=T["texto"] if self.counting
                              else mix(T["texto"], T["bg"], 0.42))
        if not anim:
            return
        # glitch del título: desplazamiento rojo / blanco unas décimas de segundo
        if self.ghosts:
            if now >= self.glitch_next:
                self.glitch_end = now + random.uniform(0.14, 0.3)
                self.glitch_next = now + random.uniform(4.5, 8.0)
            x, y = self.title_xy
            if now < self.glitch_end:
                for g, sx in zip(self.ghosts, (-1, 1)):
                    self._co(g, x + sx * random.choice((1, 2, 3)), y + random.choice((-1, 0, 1)))
                    self._ic(g, state="normal")
                self._co(self.title_it, x + random.choice((-1, 0, 1)), y)
                self._ic(self.title_it, fill=random.choice(("#FFFFFF", T["acento2"])))
            else:
                for g in self.ghosts:
                    self._ic(g, state="hidden")
                self._co(self.title_it, x, y)
        # rayos blancos aleatorios
        if self.bolts:
            if now >= self.bolt_next:
                self._new_bolt()
                self.bolt_end = now + random.uniform(0.09, 0.2)
                self.bolt_next = now + random.uniform(2.5, 7.0)
            if now < self.bolt_end:
                b30 = int(now * 30)                      # parpadeo eléctrico, ~30 veces/s
                if b30 != getattr(self, "_bolt_b", None):
                    self._bolt_b, self._bolt_on = b30, random.random() > 0.25
                on = self._bolt_on
                for glow, core in self.bolts:
                    st = "normal" if on and self._co(core) else "hidden"
                    self._ic(glow, state=st)
                    self._ic(core, state=st)
                if on:
                    self._ic(self.border, outline="#FFFFFF")
            else:
                for glow, core in self.bolts:
                    self._ic(glow, state="hidden")
                    self._ic(core, state="hidden")

        # barrido tipo playhead
        if self.scan:
            span = self.W * 2.6
            xs = (now * 70) % span
            if xs < self.W:
                self._co(self.scan, xs, self.m_cur + 3, xs, self.H - self.m_cur - 3)
                self._ic(self.scan, state="normal")
            else:
                self._ic(self.scan, state="hidden")
        # bienvenida "LET'S GAUUUUX"
        if self.splash:
            left = getattr(self, "splash_until", 0) - now
            if left > 0:
                k = min(1.0, left / 0.5)                 # se apaga en el último medio segundo
                self._ic(self.splash_bg, state="normal")
                self._ic(self.splash, state="normal",
                              fill=mix(T["bg"], random.choice((T["acento2"], T["acento2"],
                                                               "#FFFFFF")), k))
                cv.tag_raise(self.splash_bg)
                cv.tag_raise(self.splash)
                random.seed(int(now * 30))
                jx = random.choice((0, 0, -2, 2))
                random.seed()
                self._co(self.splash, self.W / 2 + jx, self.H / 2)
            else:
                self._ic(self.splash_bg, state="hidden")
                self._ic(self.splash, state="hidden")

    def show_session_card(self, sess, proj=None):
        """Ritual de cierre: resumen de la sesión al cerrar el DAW (Gaux Mode y Personal)."""
        if self.card is not None:
            try:
                self.card.destroy()
            except tk.TclError:
                pass
        T = self.T
        vals = self.goal_values()
        g = self.conf["metas"]["diaria"]
        crushed = g["activa"] and vals["diaria"] >= max(60, g["segundos"])
        lab_s, lab_h, lab_w = (("SESSION", "HOY", "SEMANA") if self.brand
                               else ("SESIÓN", "HOY", "SEMANA"))
        rows = [(lab_s, fmt_short(sess).upper()), (lab_h, fmt_short(vals["diaria"]).upper())]
        if proj and proj != SIN_PROYECTO:
            pt = self.project_values(proj)["total"]
            pname = proj.upper() if self.brand else proj
            rows.append((pname if len(pname) <= 16 else pname[:15] + "…",
                         fmt_short(pt).upper()))
        if not crushed:
            rows.append((lab_w, fmt_short(vals["semanal"]).upper()))
        head = self.card_head
        W, m = 300, 6
        top = m + (66 if head else 30)
        H = top + 28 * len(rows) + (28 if crushed else 0) + 6
        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        base = self.clear or T["bg"]
        if self.clear == "systemTransparent":
            try:
                win.attributes("-transparent", True)
            except tk.TclError:
                pass
        elif self.clear:
            try:
                win.attributes("-transparentcolor", self.clear)
            except tk.TclError:
                pass
        win.configure(bg=base)
        cv = tk.Canvas(win, width=W, height=H, bg=base, highlightthickness=0, bd=0)
        cv.pack()
        bf = self.f_clock_family
        lab = (self.f_label[0], max(10, abs(int(self.f_label[1])) + 1), "bold")
        val = (bf, 15, "bold")
        shape = chamfer if self.angular else rrect
        shape(cv, m, m, W - m, H - m, 14, fill=T["bg"], outline="")
        border = shape(cv, m, m, W - m, H - m, 14, fill="", outline="#FFFFFF", width=1.5)
        if head:
            hf = 30
            df = self.f_display                          # fuente con las letras de la frase
            while hf > 12 and tkfont.Font(family=df, size=hf, weight="bold").measure(head) > W - 40:
                hf -= 1
            cv.create_text(W / 2, m + 30, text=head, font=(df, hf, "bold"), fill=T["acento2"])
        y = top
        for k, v in rows:
            cv.create_text(m + 34, y, text=k, anchor="w", font=lab, fill=T["dim"])
            cv.create_text(W - m - 34, y, text=v, anchor="e", font=val, fill=T["texto"])
            y += 28
        if crushed:                                      # meta del día cumplida
            cv.create_text(W / 2, y, text="GOAL CRUSHED" if self.brand else "META CUMPLIDA",
                           font=val, fill=GOLD)
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        win.geometry(f"{W}x{H}+{(sw - W) // 2}+{max(40, sh // 3 - H // 2)}")
        self.card = win
        t0 = time.monotonic()
        life = 6.0

        def close(_e=None):
            try:
                win.destroy()
            except tk.TclError:
                pass
            if self.card is win:
                self.card = None

        def step():
            if self.card is not win:
                return
            t = time.monotonic() - t0
            if t >= life:
                return close()
            a = min(1.0, t / 0.25, (life - t) / 0.6)
            try:
                win.attributes("-alpha", max(0.0, a) * 0.97)
                cv.itemconfig(border, outline=mix("#FFFFFF", T["borde"], min(1.0, t / 0.6)))
            except tk.TclError:
                return
            win.after(33, step)

        cv.bind("<Button-1>", close)
        step()

    def _new_bolt(self):
        """Traza un rayo en zigzag de arriba hacia abajo, a veces con una rama."""
        cv, W, H, m = self.cv, self.W, self.H, self.bolt_m
        x = random.uniform(W * 0.15, W * 0.85)
        y = m + 2
        pts = [x, y]
        seg = max(6, (H - 2 * m) / random.randint(5, 9))
        drift = random.choice((-1, 1)) * random.uniform(0.2, 0.9)
        while y < H - m - 4:
            y = min(H - m - 2, y + seg * random.uniform(0.6, 1.3))
            x = max(m + 2, min(W - m - 2, x + seg * (drift + random.uniform(-1.2, 1.2))))
            pts += [x, y]
        glow, core = self.bolts[0]
        self._co(glow, *pts)
        self._co(core, *pts)
        glow2, core2 = self.bolts[1]
        if random.random() < 0.6 and len(pts) >= 6:
            k = random.randrange(1, len(pts) // 2 - 1) * 2
            bx, by = pts[k], pts[k + 1]
            br = [bx, by]
            for _ in range(random.randint(2, 4)):
                bx = max(m + 2, min(W - m - 2, bx + random.choice((-1, 1)) * seg * random.uniform(.5, 1.2)))
                by = min(H - m - 2, by + seg * random.uniform(.4, .9))
                br += [bx, by]
            self._co(glow2, *br)
            self._co(core2, *br)
        else:
            self._co(glow2, 0, 0, 0, 0)
            self._co(core2, 0, 0, 0, 0)

    def anim_fps(self):
        """Fluidez del timer: 120 fps solo en el modo 120; en Equilibrado y 60 fps, 60
        (el reloj cambia una vez por segundo: más cuadros solo gastan CPU)."""
        return 120 if self.conf["analizador"].get("rendimiento") == "maximo" else 60

    def anim(self):
        anim = self.conf["animaciones"]
        now = time.perf_counter()
        dt = min(0.1, now - getattr(self, "_anim_last", now))
        self._anim_last = now
        if not (self.live_open and self.visible):
            # oculto (otra app al frente o DAW cerrado): no se dibuja nada
            self._anim_next = now
            self.root.after(250, self.anim)
            return
        if anim:
            self.phase += dt                             # animaciones según el tiempo real
            if dt > 0:
                self.fps_meas = 0.95 * getattr(self, "fps_meas", 60.0) + 0.05 / dt
        self.render_frame()
        if not anim:
            self.root.after(250, self.anim)
            return
        nxt = getattr(self, "_anim_next", now) + 1 / self.anim_fps()
        t = time.perf_counter()
        if nxt < t:
            nxt = t
        self._anim_next = nxt
        self.root.after(max(1, int((nxt - t) * 1000)), self.anim)

    # ---- lógica (1 vez por segundo) --------------------------------------
    def _today(self):
        return dt.date.today().isoformat()

    # ---- proyectos ------------------------------------------------------------
    def project_name(self):
        if self.conf.get("proyecto_auto", True) and self.detected:
            return self.detected
        return self.conf.get("proyecto") or SIN_PROYECTO

    def project_rec(self, name):
        recs = self.data.setdefault("proyectos", {})
        r = recs.get(name)
        if r is None:
            now = dt.datetime.now().isoformat(timespec="minutes")
            r = recs[name] = {"segundos": 0.0, "dias": {}, "sesiones": 0,
                              "creado": now, "ultima": None, "daw": ""}
        return r

    def project_values(self, name):
        r = self.data.get("proyectos", {}).get(name) or {}
        dias = r.get("dias", {})
        today = dt.date.today()
        monday = (today - dt.timedelta(days=today.weekday())).isoformat()
        month = today.replace(day=1).isoformat()
        return {"total": r.get("segundos", 0.0), "hoy": dias.get(today.isoformat(), 0.0),
                "semana": sum(v for k, v in dias.items() if k >= monday),
                "mes": sum(v for k, v in dias.items() if k >= month),
                "sesiones": r.get("sesiones", 0), "ultima": r.get("ultima"),
                "creado": r.get("creado"), "daw": r.get("daw", "")}

    def set_project(self, name, auto=None):
        """Elegir el proyecto activo (a mano). auto=False desactiva la detección."""
        name = (name or "").strip()[:60]
        self.conf["proyecto"] = "" if name == SIN_PROYECTO else name
        if auto is not None:
            self.conf["proyecto_auto"] = auto
        if name and name != SIN_PROYECTO:
            self.project_rec(name)
        self.save_conf()
        save_json(DATA_FILE, self.data)
        self.refresh_text()

    def rename_project(self, old, new):
        new = (new or "").strip()[:60]
        recs = self.data.get("proyectos", {})
        if not new or old not in recs or new == old:
            return
        a = recs.pop(old)
        if new in recs:                                   # unir con el que ya existe
            b = recs[new]
            b["segundos"] += a.get("segundos", 0)
            b["sesiones"] += a.get("sesiones", 0)
            for k, v in a.get("dias", {}).items():
                b["dias"][k] = b["dias"].get(k, 0) + v
            b["ultima"] = max(filter(None, [a.get("ultima"), b.get("ultima")]), default=None)
            b["creado"] = min(filter(None, [a.get("creado"), b.get("creado")]), default=None)
        else:
            recs[new] = a
        if self.conf.get("proyecto") == old:
            self.conf["proyecto"] = new
        if self.detected == old:
            self.detected = new
        self.data.setdefault("alias", {})[old.lower()] = new   # el título viejo apunta al nuevo
        self.save_conf()
        save_json(DATA_FILE, self.data)
        self.refresh_text()

    def delete_project(self, name):
        self.data.get("proyectos", {}).pop(name, None)
        if self.conf.get("proyecto") == name:
            self.conf["proyecto"] = ""
        self.save_conf()
        save_json(DATA_FILE, self.data)
        self.refresh_text()

    def _detect_project(self):
        """Lee el título de la ventana del DAW cada 3 s (solo si la detección está activa)."""
        now = time.monotonic()
        if now - self._title_t < 3 or not self.conf.get("proyecto_auto", True):
            return
        self._title_t = now
        t = daw_window_title(LIVE_PID[0])
        if t is None:
            return
        self.title_seen = bool(t)
        name = project_from_title(t)
        if name:
            name = self.data.get("alias", {}).get(name.lower(), name)
        if name != self.detected:
            self.detected = name
            if name:
                self.project_rec(name)
            self.refresh_text()

    def _close_session(self):
        if self.session >= 60 and self.session_start:
            self.data["sesiones"].append({
                "inicio": self.session_start,
                "fin": dt.datetime.now().isoformat(timespec="seconds"),
                "segundos": int(self.session),
                "proyectos": {k: int(v) for k, v in self.session_proj.items() if v >= 1},
            })
            self.data["sesiones"] = self.data["sesiones"][-500:]
        for name, secs in self.session_proj.items():
            if secs >= 60 and name in self.data.get("proyectos", {}):
                self.data["proyectos"][name]["sesiones"] += 1
        self.session_proj = {}
        self.session = 0.0
        save_json(DATA_FILE, self.data)

    def _settings_open(self):
        return self.settings is not None and self.settings.winfo_exists()

    def tick(self):
        if getattr(self, "quit_requested", False):     # otra versión pidió el relevo
            self.quit()
            return
        now = time.monotonic()
        raw = (now - self.last_tick) * SPEED
        self.last_tick = now
        delta = 0.0 if raw > 5 * SPEED else raw     # equipo suspendido
        self.vclock += raw

        if now - self.last_proc_check > 3:
            self.last_proc_check = now
            running = live_running()
            if running and not self.live_open:
                self.live_open = True
                self.manual = None
                self.pending_splash = True
                self._title_t = 0.0                        # leer el proyecto ya mismo
                if self.conf.get("top_mode"):
                    self.root.after(2500, lambda: self._bg("reapply", self.reapply_top))
                self.session = 0.0
                self.session_start = dt.datetime.now().isoformat(timespec="seconds")
                if self.conf["analizador"]["activo"] and self.ensure_analyzer():
                    self.analyzer.start_audio()
                self.watch_front(reschedule=False)
            elif not running and self.live_open:
                self.live_open = False
                self.counting = False
                self.state = "espera"
                sess = self.session
                sess_proj = self.project_name()
                self._close_session()
                self.detected = None
                if self.ritual and sess >= 60:
                    self.show_session_card(sess, sess_proj)
                self.set_visible(False)
                if self.analyzer:
                    self.analyzer.stop_audio()

        if self.live_open:
            front = self.front
            if front == "self":       # tocando el widget: hereda el estado anterior
                front_live = self.last_front_live and not self._settings_open()
            else:
                front_live = front == "live"
            idle = 0.0 if DEMO else idle_seconds()

            if self.manual:
                self.state, self.counting = self.manual, False
            elif not front_live:
                self.state, self.counting = "fondo", False
            elif idle >= self.conf["limite_inactividad"]:
                self.state, self.counting = "inactivo", False
            else:
                self.state, self.counting = "sesion", True

            if self.front == "live":
                self._detect_project()
            if self.counting:
                brk = self.conf["autonomo"]["break_min"] * 60
                if self.last_count_v is not None and self.vclock - self.last_count_v >= brk:
                    self.streak = 0.0
                self.streak += delta
                self.last_count_v = self.vclock
                self.session += delta
                d = self._today()
                self.data["dias"][d] = self.data["dias"].get(d, 0) + delta
                pn = self.project_name()
                rec = self.project_rec(pn)
                rec["segundos"] += delta
                rec["dias"][d] = rec["dias"].get(d, 0) + delta
                rec["ultima"] = dt.datetime.now().isoformat(timespec="minutes")
                rec["daw"] = CURRENT_DAW[0]
                self.session_proj[pn] = self.session_proj.get(pn, 0.0) + delta
            self.refresh_text()

        if now - self.last_save > 30:
            self.last_save = now
            save_json(DATA_FILE, self.data)
        self.root.after(1000, self.tick)

    # ---- interacción ------------------------------------------------------
    def _bind(self):
        cv = self.cv
        cv.bind("<ButtonPress-1>", self.on_press)
        cv.bind("<B1-Motion>", self.on_drag)
        cv.bind("<ButtonRelease-1>", self.on_release)
        cv.bind("<Double-Button-1>", self.on_double)
        cv.bind("<Motion>", self.on_motion)
        cv.bind("<Leave>", self.on_leave)
        for seq in ("<Button-2>", "<Button-3>", "<Control-Button-1>"):
            cv.bind(seq, self.show_menu)

    def on_leave(self, e):
        if self._resize:
            return
        self.set_hover(None)
        self.cv.config(cursor="")
        self._show_grip(False)

    def hit_test(self, x, y):
        for x1, y1, x2, y2, name in reversed(self.hit):
            if x1 <= x <= x2 and y1 <= y <= y2:
                return name
        return None

    def on_motion(self, e):
        if self._drag or self._resize:
            return
        self._show_grip(not self.conf.get("top_mode"))
        if self.in_resize(e.x, e.y):
            self.set_hover(None)
            try:
                self.cv.config(cursor="bottom_right_corner")
            except tk.TclError:
                self.cv.config(cursor="sizing")
            return
        self.set_hover(self.hit_test(e.x, e.y))
        if not self.hover:
            self.cv.config(cursor="")

    def set_hover(self, name):
        if name == self.hover:
            return
        self.hover = name
        self.cv.config(cursor="hand2" if name else "")
        for tag in ("btn_cfg", "btn_min", "btn_max"):
            self.cv.itemconfig(tag, fill=self.T["acento2"] if tag == "btn_" + (name or "")
                               else self.T["dim"])
        self.draw_pp()

    def on_press(self, e):
        if self.in_resize(e.x, e.y):
            self._drag = None
            self.resize_start(e)
            return
        name = self.hit_test(e.x, e.y)
        if name:
            self._drag = None
            self._last_btn = time.monotonic()
            if name == "min":
                self.set_vista("mini")
            elif name == "max":
                self.set_vista(self.conf.get("vista_previa") or "completa")
            elif name == "cfg":
                self.open_settings()
            elif name == "pp":
                self.toggle_pause()
            elif name == "chip":
                self.chip_action()
            elif name == "proj":
                self.show_project_menu(e)
            return
        if self.conf.get("top_mode"):
            return
        self._drag = (e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y())

    # ---- pausa y break manuales -------------------------------------------
    # ---- analizador de audio ------------------------------------------------
    def ensure_analyzer(self):
        if self.analyzer:
            return True
        try:
            if not FROZEN:
                sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import gaux_analizador
        except Exception as e:
            self.show_install_help(e)
            return False
        self.analyzer = gaux_analizador.AnalyzerPanel(self)
        return True

    def toggle_analyzer(self):
        a = self.conf["analizador"]
        a["activo"] = not a["activo"]
        self.save_conf()
        self.apply_analyzer()

    def apply_analyzer(self, restart=False):
        a = self.conf["analizador"]
        if a["activo"]:
            if not self.ensure_analyzer():
                a["activo"] = False
                self.save_conf()
            else:
                if restart or not self.analyzer.running:
                    if self.live_open:
                        self.analyzer.start_audio()
                else:
                    self.analyzer.build()
                self.analyzer.set_visible(self.visible)
        elif self.analyzer:
            self.analyzer.set_visible(False)
            self.analyzer.stop_audio()
        if hasattr(self, "v_anal"):
            self.v_anal.set(a["activo"])

    def notice(self, title, text):
        w = tk.Toplevel(self.root)
        w.title(f"{APP_NAME} · {title}")
        w.configure(bg=self.T["bg"])
        w.attributes("-topmost", True)
        tk.Label(w, text=title, font=(self.f_title[0], self.f_title[1] + 2, "bold"),
                 fg=self.T["acento2"], bg=self.T["bg"]).pack(anchor="w", padx=20, pady=(14, 0))
        tk.Label(w, text=text, font=(self.f_sans, 11), fg=self.T["texto"], bg=self.T["bg"],
                 justify="left", wraplength=440).pack(padx=20, pady=(6, 10), anchor="w")
        b = tk.Label(w, text="Entendido", font=(self.f_sans, 11, "bold"), padx=14, pady=4,
                     bg=self.T["acento"], fg="#FFFFFF", cursor="hand2")
        b.bind("<Button-1>", lambda e: w.destroy())
        b.pack(anchor="e", padx=20, pady=(0, 14))
        w.update_idletasks()
        sw, sh = w.winfo_screenwidth(), w.winfo_screenheight()
        w.geometry(f"+{(sw - w.winfo_reqwidth()) // 2}+{(sh - w.winfo_reqheight()) // 3}")

    # ---- modo Top Live Performance ------------------------------------------
    def toggle_top_mode(self):
        if self.conf.get("top_mode"):
            self.exit_top_mode()
        else:
            self.enter_top_mode()
        if hasattr(self, "v_top"):
            self.v_top.set(bool(self.conf.get("top_mode")))

    def enter_top_mode(self):
        was_fs = False
        try:
            wid, x, y, w, h = live_main_window()
            if live_fullscreen(wid):
                # macOS no deja mover una ventana en pantalla completa: se sale de ella
                # y la ventana se deja ocupando toda la pantalla (igual de grande).
                was_fs = True
                set_live_fullscreen(wid, False)
                for _ in range(20):                       # esperar la animación
                    time.sleep(0.15)
                    self.root.update()
                    try:
                        if not live_fullscreen(live_main_window()[0]):
                            break
                    except LiveWindowError:
                        pass
                time.sleep(0.35)
                wid = live_main_window()[0]
                set_live_window(wid, x, 0, w, h)          # macOS la deja bajo la barra de menú
                time.sleep(0.2)
                wid, x2, y2, w2, h2 = live_main_window()
                set_live_window(wid, x, y2, w, (y + h) - y2)
                wid, x, y, w, h = live_main_window()
            if h < self.top_h + 300:
                raise LiveWindowError("La ventana de Live es muy pequeña para hacerle espacio. "
                                      "Maximízala y activa el modo otra vez.")
            a = self.conf["analizador"]
            prev = {"live": [x, y, w, h], "fullscreen": was_fs, "vista": self.conf["vista"],
                    "orient": self.conf.get("orientacion", "horizontal"),
                    "anal": {k: a.get(k) for k in ("x", "y", "w", "h", "activo")}}
            # la franja va pegada arriba en la pantalla del DAW; el DAW, justo debajo y sin
            # salirse del área útil (sirve para cualquier resolución o monitor)
            t = self.dock_target((x, y, w, h))
            if t:
                sx = t[3]
                top_y = t[1] + self.top_h
                bottom = min(y + h, sx[5] + sx[7])
                nx, nw = max(x, sx[4]), min(w, sx[6])
            else:
                top_y, bottom, nx, nw = y + self.top_h, y + h, x, w
            set_live_window(wid, nx, top_y, nw, bottom - top_y)
            time.sleep(0.25)
            _, x2, y2, w2, h2 = live_main_window()
            if y2 < top_y - 6:                          # no se movió
                set_live_window(wid, x, y, w, h)
                raise LiveWindowError(FULLSCREEN_MAC if SYSTEM == "Darwin" else
                                      "No pude mover la ventana de Live. Sal de pantalla "
                                      "completa y activa el modo otra vez.")
        except LiveWindowError as e:
            self.notice("Top Live Performance", str(e))
            return
        except Exception as e:
            self.notice("Top Live Performance", f"No se pudo activar el modo.\n\n{e}")
            return
        self.conf["top_prev"] = prev
        self.conf["top_mode"] = True
        self.conf["top_geom"] = None
        t = self.dock_target((x, y, w, h))
        self.conf["top_geom"] = [t[0], t[1], t[2]] if t else [x, y, w]
        self._move_fail = 0
        self.conf["analizador"]["activo"] = True
        self.save_conf()
        self.apply_conf()
        self.apply_analyzer()

    def exit_top_mode(self, restore_live=True):
        prev = self.conf.get("top_prev") or {}
        if restore_live and prev.get("live"):
            try:
                wid = live_main_window()[0]
                set_live_window(wid, *prev["live"])
                if prev.get("fullscreen"):                # volver a pantalla completa
                    time.sleep(0.2)
                    set_live_fullscreen(live_main_window()[0], True)
            except Exception:
                pass                                      # Live cerrado: nada que mover
        self.conf["top_mode"] = False
        self.conf["vista"] = prev.get("vista", self.conf["vista"])
        self.conf["orientacion"] = prev.get("orient", self.conf.get("orientacion"))
        a = self.conf["analizador"]
        for k, v in (prev.get("anal") or {}).items():
            a[k] = v
        self.save_conf()
        self.apply_conf()
        self.apply_analyzer()

    def _keep_docked(self):
        """Mantiene la franja en su sitio aunque el sistema mueva alguna ventana."""
        gx, gy = getattr(self, "_dock_pos", None) or self.conf["top_geom"][:2]
        try:
            if (self.root.winfo_x(), self.root.winfo_y()) != (gx, gy):
                self._move(gx, gy)
            an = self.analyzer
            if an and an.visible:
                a = self.conf["analizador"]
                if (an.win.winfo_x(), an.win.winfo_y()) != (a["x"], a["y"]):
                    an.win.geometry(f"+{int(a['x'])}+{int(a['y'])}")
        except tk.TclError:
            pass

    def reapply_top(self):
        """Al reabrir Live con el modo activo, vuelve a dejarle espacio a la franja."""
        if not (self.conf.get("top_mode") and self.live_open and self.conf.get("top_geom")):
            return
        gx, gy, gw = self.conf["top_geom"]
        try:
            wid, x, y, w, h = live_main_window()
            th = self.top_h
            if y < gy + th - 6:
                set_live_window(wid, x, gy + th, w, h - (gy + th - y))
        except Exception:
            pass

    def show_install_help(self, err):
        w = tk.Toplevel(self.root)
        w.title(f"{APP_NAME} · Analizador")
        w.configure(bg=self.T["bg"])
        w.attributes("-topmost", True)
        txt = ("El analizador necesita dos librerías. Abre la Terminal y ejecuta:\n\n"
               "python3 -m pip install numpy sounddevice\n\n"
               "Luego cierra y vuelve a abrir el timer.\n\n"
               f"(Detalle: {err})")
        tk.Label(w, text=txt, font=(self.f_sans, 11), fg=self.T["texto"], bg=self.T["bg"],
                 justify="left", wraplength=420).pack(padx=20, pady=16)
        w.update_idletasks()
        sw, sh = w.winfo_screenwidth(), w.winfo_screenheight()
        w.geometry(f"+{(sw - w.winfo_reqwidth()) // 2}+{(sh - w.winfo_reqheight()) // 3}")

    def toggle_pause(self):
        if self.manual:
            self.resume()
        else:
            self.manual = "pausa"
            self._after_manual()

    def start_break(self):
        self.manual = "break"
        self.break_start_v = self.vclock
        self._after_manual()

    def resume(self):
        if self.manual == "break":
            brk = self.conf["autonomo"]["break_min"] * 60
            if self.vclock - self.break_start_v >= brk:
                self.streak = 0.0        # break completo: racha desde cero
        self.manual = None
        self._after_manual()

    def chip_action(self):
        if self.manual == "break":
            self.resume()
        else:
            self.start_break()

    def _after_manual(self):
        if self.live_open:
            self.state = self.manual or self.state
            self.counting = False if self.manual else self.counting
        self.refresh_text()
        self.render_frame(force=True)

    def on_drag(self, e):
        if self._resize:
            self.resize_drag(e)
            return
        if self._drag:
            self._move(e.x_root - self._drag[0], e.y_root - self._drag[1])

    def on_release(self, e):
        if self._resize:
            self.resize_end()
            return
        if self._drag:
            x, y = self.root.winfo_x(), self.root.winfo_y()
            self.conf["x"], self.conf["y"] = x, y
            self.conf.setdefault("pos", {})[self.pos_key()] = [x, y]
            self.save_conf()
        self._drag = None
        self.restack_soon(150)            # que los plugins sigan por encima del timer
        if NO_ACTIVATE[0] is False and self.last_front_live:
            # macOS sin ventanas "que no activan": se le devuelve el foco al DAW
            self.root.after(400, self._give_focus_back)

    def _give_focus_back(self):
        if self._settings_open() or getattr(self, "_dialog_open", False):
            return
        if frontmost_app() == "self":
            activate_pid(LIVE_PID[0])

    def on_double(self, e):
        """Doble clic en cualquier parte del timer: abre el menú de opciones."""
        if time.monotonic() - self._last_btn < 0.6:    # fue un doble clic sobre un botón
            return
        self._drag = self._resize = None
        self.show_menu(e)

    def _build_menu(self):
        m = tk.Menu(self.root, tearoff=0)
        m.add_command(label="Fluidez: —", state="disabled")
        m.add_separator()
        m.add_command(label="Pausar / reanudar", command=self.toggle_pause)
        m.add_command(label="Tomar break", command=self.start_break)
        m.add_command(label="Reiniciar sesión", command=self.reset_session)
        m.add_separator()
        self.proj_menu = tk.Menu(m, tearoff=0)
        m.add_cascade(label="Proyecto", menu=self.proj_menu)
        self._proj_idx = m.index("end")
        m.add_command(label="Ver proyectos…", command=self.open_projects)
        m.add_separator()
        self.v_tema = tk.StringVar()
        self.v_modo = tk.StringVar()
        self.v_vista = tk.StringVar()
        m.add_command(label="Ajustes…", command=self.open_settings)
        sub = tk.Menu(m, tearoff=0)
        for k, t in TEMAS.items():
            sub.add_radiobutton(label=t["nombre"], value=k, variable=self.v_tema,
                                command=lambda k=k: self.set_tema(k))
        m.add_cascade(label="Estilo", menu=sub)
        sub = tk.Menu(m, tearoff=0)
        for k, t in (("normal", "Normal"), ("autonomo", "Autónomo")):
            sub.add_radiobutton(label=t, value=k, variable=self.v_modo,
                                command=lambda k=k: self.set_modo(k))
        m.add_cascade(label="Modo", menu=sub)
        sub = tk.Menu(m, tearoff=0)
        for k, t in (("completa", "Completa"), ("compacta", "Compacta"),
                     ("mini", "Minimizada")):
            sub.add_radiobutton(label=t, value=k, variable=self.v_vista,
                                command=lambda k=k: self.set_vista(k))
        sub.add_separator()
        self.v_orient = tk.StringVar()
        for k, t in (("horizontal", "Horizontal"), ("vertical", "Vertical")):
            sub.add_radiobutton(label=t, value=k, variable=self.v_orient,
                                command=lambda k=k: self.set_orient(k))
        sub.add_separator()
        sub.add_command(label="Tamaño original", command=self.reset_scale)
        m.add_cascade(label="Vista", menu=sub)
        m.add_separator()
        self.v_anal = tk.BooleanVar(value=self.conf["analizador"]["activo"])
        m.add_checkbutton(label="Analizador de audio", variable=self.v_anal,
                          command=self.toggle_analyzer)
        self.v_top = tk.BooleanVar(value=bool(self.conf.get("top_mode")))
        m.add_checkbutton(label="Top Live Performance", variable=self.v_top,
                          command=self.toggle_top_mode)
        self.v_escala = tk.IntVar(value=int(self.conf.get("top_escala", 100)))
        sub = tk.Menu(m, tearoff=0)
        for pct in (100, 90, 80, 70, 60, 50):
            sub.add_radiobutton(label=f"{pct} %", value=pct, variable=self.v_escala,
                                command=lambda p=pct: self.set_top_scale(p))
        m.add_cascade(label="Tamaño de la franja Top Live", menu=sub)
        m.add_separator()
        m.add_command(label=f"Cerrar {APP_NAME}", command=self.quit)
        self.menu = m

    def show_menu(self, e):
        t = getattr(self, "fps_meas", None)
        an = self.analyzer
        a = getattr(an, "fps_meas", None) if an and an.visible else None
        if t:
            t = min(t, self.anim_fps())                 # sin picos del arranque
        txt = "Fluidez: timer " + (f"{t:.0f} fps" if t else "—")
        if a:
            txt += f" · analizador {a:.0f} fps"
        try:
            self.menu.entryconfig(0, label=txt)
            pn = self.project_name()
            self.menu.entryconfig(self._proj_idx,
                                  label=f"Proyecto: {pn if len(pn) < 28 else pn[:27] + '…'}")
        except tk.TclError:
            pass
        self._fill_project_menu(self.proj_menu)
        self.menu.tk_popup(e.x_root, e.y_root)

    def _recent_projects(self, n=10):
        recs = self.data.get("proyectos", {})
        names = sorted((k for k in recs if k != SIN_PROYECTO),
                       key=lambda k: recs[k].get("ultima") or recs[k].get("creado") or "",
                       reverse=True)
        return names[:n]

    def _fill_project_menu(self, menu):
        menu.delete(0, "end")
        pn = self.project_name()
        auto_on = self.conf.get("proyecto_auto", True)
        if auto_on and self.detected:
            menu.add_command(label=f"Detectado en {CURRENT_DAW[0]}: {self.detected}",
                             state="disabled")
        elif auto_on and self.title_seen is False and SYSTEM == "Darwin":
            menu.add_command(label="Detección automática: falta permiso (ver proyectos…)",
                             state="disabled")
        self._v_proj = tk.StringVar(value=pn)
        for name in self._recent_projects():
            menu.add_radiobutton(label=name, value=name, variable=self._v_proj,
                                 command=lambda n=name: self.set_project(n, auto=False))
        menu.add_radiobutton(label=SIN_PROYECTO, value=SIN_PROYECTO, variable=self._v_proj,
                             command=lambda: self.set_project(SIN_PROYECTO, auto=False))
        menu.add_separator()
        menu.add_command(label="Nuevo proyecto…", command=self.ask_new_project)
        self._v_auto = tk.BooleanVar(value=auto_on)
        menu.add_checkbutton(label="Detectar desde el título del DAW", variable=self._v_auto,
                             command=lambda: self.set_project(self.conf.get("proyecto", ""),
                                                              auto=self._v_auto.get()))
        menu.add_command(label="Ver proyectos…", command=self.open_projects)

    def show_project_menu(self, e):
        m = tk.Menu(self.root, tearoff=0)
        self._fill_project_menu(m)
        m.tk_popup(e.x_root, e.y_root)

    def ask_text(self, title, prompt, initial="", on_ok=None):
        """Pequeña ventana para escribir un nombre."""
        T = self.T
        activate_self()
        w = tk.Toplevel(self.root)
        w.title(f"{APP_NAME} · {title}")
        w.configure(bg=T["bg"])
        w.attributes("-topmost", True)
        w.resizable(False, False)
        tk.Label(w, text=prompt, font=(self.f_sans, 11, "bold"), fg=T["texto"],
                 bg=T["bg"]).pack(anchor="w", padx=18, pady=(14, 6))
        e = tk.Entry(w, width=34, font=(self.f_sans, 12), bg=T["pista"], fg=T["texto"],
                     insertbackground=T["texto"], relief="flat", highlightthickness=1,
                     highlightbackground=T["pista"], highlightcolor=T["acento"])
        e.insert(0, initial)
        e.pack(padx=18, ipady=4)
        e.select_range(0, "end")

        def ok(_e=None):
            v = e.get().strip()
            w.destroy()
            if v and on_ok:
                on_ok(v)

        f = tk.Frame(w, bg=T["bg"])
        f.pack(fill="x", padx=18, pady=12)
        for text, cmd, prim in (("Aceptar", ok, True), ("Cancelar", w.destroy, False)):
            b = tk.Label(f, text=text, font=(self.f_sans, 10, "bold"), padx=14, pady=4,
                         cursor="hand2", bg=T["acento"] if prim else T["pista"],
                         fg="#FFFFFF" if prim else T["texto"])
            b.bind("<Button-1>", lambda _e, c=cmd: c())
            b.pack(side="right", padx=(6, 0))
        w.bind("<Return>", ok)
        w.bind("<Escape>", lambda _e: w.destroy())
        w.update_idletasks()
        sw, sh = w.winfo_screenwidth(), w.winfo_screenheight()
        w.geometry(f"+{(sw - w.winfo_reqwidth()) // 2}+{(sh - w.winfo_reqheight()) // 3}")
        w.after(80, e.focus_force)
        return w

    def ask_new_project_then(self, after):
        def go():
            self.ask_text("Nuevo proyecto", "Nombre del proyecto",
                          on_ok=lambda v: (self.set_project(v, auto=False), after()))
        return go

    def ask_new_project(self):
        self.ask_text("Nuevo proyecto", "Nombre del proyecto",
                      on_ok=lambda v: self.set_project(v, auto=False))

    def open_projects(self):
        activate_self()
        w = getattr(self, "projects_win", None)
        if w is not None and w.winfo_exists():
            w.lift()
            return
        self.projects_win = Proyectos(self)

    def open_settings(self):
        activate_self()                    # para poder escribir en los campos
        if self._settings_open():
            self.settings.lift()
            return
        self.settings = Ajustes(self)

    def reset_session(self):
        self._close_session()
        self.session_start = dt.datetime.now().isoformat(timespec="seconds")
        self.refresh_text()

    def quit(self):
        if self.conf.get("top_mode") and self.live_open:      # devolver el espacio a Live
            prev = (self.conf.get("top_prev") or {}).get("live")
            if prev:
                try:
                    set_live_window(live_main_window()[0], *prev)
                except Exception:
                    pass
        if self.analyzer:
            self.analyzer.stop_audio()
        try:
            self.lock.close()
        except Exception:
            pass
        self._close_session()
        self.root.destroy()

    # ---- como app de macOS -----------------------------------------------------
    def app_hooks(self):
        """Abrir la app otra vez (Launchpad, Aplicaciones, Spotlight) muestra Ajustes;
        Salir desde el sistema cierra limpio. Al abrirla a mano, un aviso dice que está activa."""
        r = self.root
        r.report_callback_exception = self._tk_error
        if SYSTEM == "Darwin":
            try:
                r.createcommand("::tk::mac::ReopenApplication", self.on_reopen)
                r.createcommand("::tk::mac::ShowPreferences", self.open_settings)
                r.createcommand("::tk::mac::Quit", self.quit)
            except tk.TclError:
                pass
        if FROZEN and not AT_LOGIN and not DEMO:
            first = not self.conf.get("bienvenida_vista")
            r.after(900, lambda: self.show_welcome(first))

    def _tk_error(self, exc, val, tb):
        import traceback
        traceback.print_exception(exc, val, tb)

    def on_reopen(self, *a):
        self.open_settings()

    def show_welcome(self, first):
        """Primera vez: qué es y qué permisos pedirá macOS. Después: aviso corto de que está
        activa (el timer solo aparece con el DAW al frente)."""
        if self.live_open and self.visible and not first:
            return
        T = self.T
        w = tk.Toplevel(self.root)
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.configure(bg=T["bg"], highlightthickness=1, highlightbackground=T["acento"])
        sans = self.f_sans
        tf = self.f_title
        tk.Label(w, text=APP_NAME, font=(tf[0], tf[1] + 4, tf[2]), fg=T["acento2"],
                 bg=T["bg"]).pack(anchor="w", padx=22, pady=(18, 2))
        msg = ("Está activo. Aparece solo cuando tu DAW está al frente y cuenta el tiempo que "
               "trabajas de verdad.")
        tk.Label(w, text=msg, font=(sans, 12), fg=T["texto"], bg=T["bg"], wraplength=420,
                 justify="left").pack(anchor="w", padx=22)
        if first:
            tips = ("Es normal que macOS te pida permisos para Gaux Live Timer:\n"
                    "•  Micrófono: para el analizador (BlackHole cuenta como micrófono).\n"
                    "•  Accesibilidad y \"controlar System Events\": para Top Live.\n"
                    "•  Grabación de pantalla (opcional): para leer el nombre del proyecto.\n\n"
                    "Para volver a ver los Ajustes, abre Gaux Live Timer otra vez desde "
                    "Aplicaciones, o haz doble clic sobre el timer.")
            tk.Label(w, text=tips, font=(sans, 11), fg=T["dim"], bg=T["bg"], wraplength=420,
                     justify="left").pack(anchor="w", padx=22, pady=(10, 0))
        row = tk.Frame(w, bg=T["bg"])
        row.pack(fill="x", padx=22, pady=(14, 18))
        if SYSTEM in ("Darwin", "Windows"):
            st = {"on": autostart_enabled()}
            lab = tk.Label(row, font=(sans, 11), bg=T["bg"], fg=T["texto"], cursor="hand2")

            def paint():
                lab.config(text=("☑" if st["on"] else "☐") + "  Abrir al iniciar sesión")

            def flip(e=None):
                st["on"] = not st["on"]
                (install_autostart if st["on"] else remove_autostart)(quiet=True)
                paint()
            lab.bind("<Button-1>", flip)
            lab.pack(side="left")
            paint()

        def close(e=None):
            self.conf["bienvenida_vista"] = True
            self.save_conf()
            if w.winfo_exists():
                w.destroy()
        for txt, cmd, main in (("Listo", close, True),
                               ("Ajustes", lambda: (close(), self.open_settings()), False)):
            b = tk.Label(row, text=txt, font=(sans, 11, "bold"), padx=14, pady=5,
                         cursor="hand2", bg=T["acento"] if main else T["pista"],
                         fg="#FFFFFF" if main else T["texto"])
            b.bind("<Button-1>", lambda e, c=cmd: c())
            b.pack(side="right", padx=(8, 0))
        w.update_idletasks()
        sw = w.winfo_screenwidth()
        w.geometry(f"+{(sw - w.winfo_reqwidth()) // 2}+{90}")
        activate_self()
        if not first:
            w.after(7000, close)

    def run(self):
        try:
            self.root.mainloop()
        finally:
            try:
                save_json(DATA_FILE, self.data)
            except Exception:
                pass


# --------------------------------------------------------------------------
# Ventana de proyectos: tiempo invertido en cada proyecto
# --------------------------------------------------------------------------
def fmt_hm(s):
    s = int(s)
    return f"{s // 3600}:{s % 3600 // 60:02d}"


def fmt_when(iso):
    if not iso:
        return "—"
    try:
        d = dt.datetime.fromisoformat(iso)
    except ValueError:
        return iso
    days = (dt.date.today() - d.date()).days
    if days == 0:
        return "hoy " + d.strftime("%H:%M")
    if days == 1:
        return "ayer"
    if days < 7:
        return f"hace {days} días"
    return d.strftime("%d/%m/%Y")


class Proyectos(tk.Toplevel):
    COLS = [("Proyecto", 230, "w"), ("Total", 70, "e"), ("Hoy", 60, "e"),
            ("Semana", 64, "e"), ("Mes", 64, "e"), ("Sesiones", 66, "e"),
            ("Última vez", 96, "e"), ("DAW", 96, "w")]

    def __init__(self, app):
        super().__init__(app.root)
        self.app, T = app, app.T
        self.T = T
        sans = app.f_sans
        self.sans = sans
        self.title(f"{APP_NAME} · Proyectos")
        self.configure(bg=T["bg"])
        self.attributes("-topmost", True)
        self.sort = "ultima"
        head = tk.Frame(self, bg=T["bg"])
        head.pack(fill="x", padx=18, pady=(12, 4))
        tf = app.f_title
        tk.Label(head, text="Proyectos", font=(tf[0], tf[1] + 3, tf[2]), fg=T["acento2"],
                 bg=T["bg"]).pack(side="left")
        self.sum_lbl = tk.Label(head, font=(sans, 10), fg=T["dim"], bg=T["bg"])
        self.sum_lbl.pack(side="left", padx=12, pady=(6, 0))

        bar = tk.Frame(self, bg=T["bg"])
        bar.pack(fill="x", padx=18, pady=(2, 6))
        self.cur_lbl = tk.Label(bar, font=(sans, 11, "bold"), fg=T["texto"], bg=T["bg"])
        self.cur_lbl.pack(side="left")
        self.btn(bar, "Exportar CSV", False, self.export).pack(side="right")
        self.btn(bar, "Nuevo proyecto", True, app.ask_new_project_then(self.refresh)
                 ).pack(side="right", padx=6)

        auto = tk.Frame(self, bg=T["bg"])
        auto.pack(fill="x", padx=18, pady=(0, 6))
        self.auto_btn = tk.Label(auto, font=(sans, 9, "bold"), padx=6, pady=1, cursor="hand2",
                                 width=3)
        self.auto_btn.bind("<Button-1>", lambda e: self.toggle_auto())
        self.auto_btn.pack(side="left")
        tk.Label(auto, text="Detectar el proyecto desde el título de la ventana del DAW",
                 font=(sans, 10), fg=T["texto"], bg=T["bg"]).pack(side="left", padx=6)
        self.hint = tk.Label(self, font=(sans, 9), fg=T["dim"], bg=T["bg"], justify="left",
                             wraplength=820)
        self.hint.pack(anchor="w", padx=18)

        # encabezado de columnas (clic para ordenar)
        hdr = tk.Frame(self, bg=T["pista"])
        hdr.pack(fill="x", padx=18, pady=(8, 0))
        keys = {"Proyecto": "nombre", "Total": "total", "Hoy": "hoy", "Semana": "semana",
                "Mes": "mes", "Sesiones": "sesiones", "Última vez": "ultima", "DAW": "daw"}
        for name, w, a in self.COLS:
            l = self.cell(hdr, name, w, a, (sans, 9, "bold"), T["dim"], T["pista"])
            l.config(cursor="hand2")
            l.bind("<Button-1>", lambda e, k=keys[name]: self.set_sort(k))
        self.cell(hdr, "", 190, "w", (sans, 9), T["dim"], T["pista"])

        wrap = tk.Frame(self, bg=T["bg"])
        wrap.pack(fill="both", expand=True, padx=18, pady=(0, 6))
        self.canvas = tk.Canvas(wrap, bg=T["bg"], highlightthickness=0, height=330,
                                width=sum(w for _, w, _ in self.COLS) + 196)
        sb = tk.Scrollbar(wrap, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=sb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.rows = tk.Frame(self.canvas, bg=T["bg"])
        self.canvas.create_window(0, 0, window=self.rows, anchor="nw")
        self.rows.bind("<Configure>",
                       lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<MouseWheel>",
                         lambda e: self.canvas.yview_scroll(-1 if e.delta > 0 else 1, "units"))

        f = tk.Frame(self, bg=T["bg"])
        f.pack(fill="x", padx=18, pady=(4, 12))
        tk.Label(f, text="Clic en una columna para ordenar. El tiempo se guarda solo en "
                         "~/.live_timer/datos.json.", font=(sans, 9), fg=T["dim"],
                 bg=T["bg"]).pack(side="left")
        self.btn(f, "Cerrar", False, self.destroy).pack(side="right")
        self.refresh()
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"+{max(0, (sw - self.winfo_reqwidth()) // 2)}+"
                      f"{max(30, (sh - self.winfo_reqheight()) // 3)}")
        self._tick()

    def cell(self, parent, text, w, anchor, font, fg, bg):
        """Celda de ancho fijo en píxeles (encabezado y filas quedan alineados)."""
        f = tk.Frame(parent, width=w, height=24, bg=bg)
        f.pack_propagate(False)
        f.pack(side="left")
        l = tk.Label(f, text=text, font=font, fg=fg, bg=bg, anchor=anchor, padx=4)
        l.pack(fill="both", expand=True)
        return l

    def btn(self, parent, text, primary, cmd):
        T = self.T
        bg = T["acento"] if primary else T["pista"]
        b = tk.Label(parent, text=text, font=(self.sans, 10, "bold"), padx=12, pady=4,
                     cursor="hand2", bg=bg, fg="#FFFFFF" if primary else T["texto"])
        b.bind("<Button-1>", lambda e: cmd())
        return b

    def set_sort(self, k):
        self.sort = k
        self.refresh()

    def toggle_auto(self):
        app = self.app
        app.set_project(app.conf.get("proyecto", ""), auto=not app.conf.get("proyecto_auto", True))
        self.refresh()

    def _tick(self):
        if not self.winfo_exists():
            return
        self.refresh(light=True)
        self.after(5000, self._tick)

    def refresh(self, light=False):
        app, T = self.app, self.T
        auto = app.conf.get("proyecto_auto", True)
        self.auto_btn.config(text="ON" if auto else "OFF", bg=T["acento"] if auto else T["pista"],
                             fg="#FFFFFF" if auto else T["dim"])
        cur = app.project_name()
        src = " (detectado)" if auto and app.detected == cur else ""
        self.cur_lbl.config(text=f"Proyecto activo: {cur}{src}")
        if not auto:
            hint = "Detección apagada: el tiempo se suma al proyecto que elijas."
        elif app.detected:
            hint = f"Detectado en {CURRENT_DAW[0]}: el título de la ventana dice “{app.detected}”."
        elif app.title_seen is False and SYSTEM == "Darwin":
            hint = ("macOS no deja leer el título de la ventana del DAW. Para la detección "
                    f"automática, activa {HOST_APP} en Ajustes del Sistema → Privacidad y "
                    "seguridad → Grabación de pantalla y audio del sistema. Mientras tanto, "
                    "el tiempo se suma al proyecto que elijas.")
        else:
            hint = ("Abre o guarda tu proyecto en el DAW y aparecerá aquí solo. Un proyecto "
                    "sin nombre (“Sin título”) usa el que elijas a mano.")
        self.hint.config(text=hint)
        recs = {k: v for k, v in app.data.get("proyectos", {}).items()
                if not (k == SIN_PROYECTO and v.get("segundos", 0) < 60)}
        vals = {k: app.project_values(k) for k in recs}
        total = sum(v["total"] for v in vals.values())
        self.sum_lbl.config(text=f"{len(recs)} proyectos · {fmt_short(total)} en total")
        if light and getattr(self, "_last_keys", None) == (tuple(sorted(recs)), self.sort):
            for k, labels in self._row_labels.items():          # solo actualizar números
                v = vals.get(k)
                if v:
                    for lbl, txt in zip(labels, self._cells(k, v)[1:]):
                        lbl.config(text=txt)
            return
        self._last_keys = (tuple(sorted(recs)), self.sort)
        for w in self.rows.winfo_children():
            w.destroy()
        self._row_labels = {}
        sort = self.sort
        keyf = {"nombre": lambda k: k.lower(), "daw": lambda k: vals[k]["daw"],
                "ultima": lambda k: vals[k]["ultima"] or ""}.get(sort, lambda k: vals[k][sort])
        names = sorted(recs, key=keyf, reverse=sort not in ("nombre", "daw"))
        if not names:
            tk.Label(self.rows, text="Todavía no hay proyectos. Empieza a producir y el tiempo "
                                     "aparecerá aquí.", font=(self.sans, 10), fg=T["dim"],
                     bg=T["bg"]).pack(anchor="w", pady=20)
            return
        for i, k in enumerate(names):
            bg = mix(T["bg"], T["pista"], .55) if i % 2 else T["bg"]
            row = tk.Frame(self.rows, bg=bg)
            row.pack(fill="x")
            labels = []
            is_cur = k == cur
            for j, ((name, w, a), txt) in enumerate(zip(self.COLS, self._cells(k, vals[k]))):
                fnt = (self.sans, 10, "bold") if (j == 0 and is_cur) else (self.sans, 10)
                l = self.cell(row, txt, w, a, fnt, T["acento2"] if (j == 0 and is_cur) else
                              (T["texto"] if j < 2 else T["dim"]), bg)
                if j:
                    labels.append(l)
            self._row_labels[k] = labels
            acts = tk.Frame(row, bg=bg)
            acts.pack(side="left", padx=(8, 0))
            for text, cmd in (("Usar", lambda n=k: self.use(n)),
                              ("Renombrar", lambda n=k: self.rename(n)),
                              ("Eliminar", lambda n=k: self.delete(n))):
                b = tk.Label(acts, text=text, font=(self.sans, 9), padx=6, pady=1,
                             cursor="hand2", bg=T["pista"], fg=T["texto"])
                b.bind("<Button-1>", lambda e, c=cmd: c())
                b.pack(side="left", padx=2)

    def _cells(self, k, v):
        name = k if len(k) <= 30 else k[:29] + "…"
        return [name, fmt_hm(v["total"]), fmt_hm(v["hoy"]), fmt_hm(v["semana"]),
                fmt_hm(v["mes"]), str(v["sesiones"]), fmt_when(v["ultima"]), v["daw"] or "—"]

    def use(self, name):
        self.app.set_project(name, auto=False)
        self._last_keys = None
        self.refresh()

    def rename(self, name):
        def done(new):
            self.app.rename_project(name, new)
            self._last_keys = None
            self.refresh()
        self.app.ask_text("Renombrar proyecto", f"Nuevo nombre para “{name}”\n"
                          "(si ya existe, se unen sus horas)", initial=name, on_ok=done)

    def delete(self, name):
        from tkinter import messagebox
        v = self.app.project_values(name)
        if messagebox.askyesno("Eliminar proyecto",
                               f"¿Eliminar “{name}” y sus {fmt_short(v['total'])} registradas?\n"
                               "Esto no se puede deshacer.", parent=self):
            self.app.delete_project(name)
            self._last_keys = None
            self.refresh()

    def export(self):
        import csv
        app = self.app
        folder = os.path.join(os.path.expanduser("~"), "Desktop")
        if not os.path.isdir(folder):
            folder = os.path.expanduser("~")
        path = os.path.join(folder, f"{APP_NAME} - Proyectos.csv")
        recs = app.data.get("proyectos", {})
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["Proyecto", "Horas totales", "Total (h:mm)", "Hoy (h:mm)",
                        "Semana (h:mm)", "Mes (h:mm)", "Sesiones", "Primera vez",
                        "Última vez", "DAW"])
            for k in sorted(recs, key=lambda k: -recs[k].get("segundos", 0)):
                v = app.project_values(k)
                w.writerow([k, round(v["total"] / 3600, 2), fmt_hm(v["total"]), fmt_hm(v["hoy"]),
                            fmt_hm(v["semana"]), fmt_hm(v["mes"]), v["sesiones"],
                            v["creado"] or "", v["ultima"] or "", v["daw"]])
        if SYSTEM == "Darwin":
            subprocess.Popen(["open", "-R", path])
        elif SYSTEM == "Windows":
            subprocess.Popen(["explorer", "/select,", path])
        app.notice("Proyectos exportados", f"Guardé el archivo en:\n{path}\n\n"
                                          "Lo puedes abrir con Numbers, Excel o Google Sheets.")


# --------------------------------------------------------------------------
# Ventana de ajustes
# --------------------------------------------------------------------------
class Ajustes(tk.Toplevel):
    """Ajustes con secciones a la izquierda: cada página explica en una línea qué hace."""
    PAGES = [("metas", "Metas", "Cuántas horas quieres producir. El timer te muestra el avance."),
             ("descansos", "Descansos", "Si quieres que el timer te avise cuándo parar."),
             ("apariencia", "Apariencia", "Estilo, tamaño y cómo se ve el timer."),
             ("toplive", "Top Live", "Timer y analizador en una franja arriba de tu DAW."),
             ("daw", "DAW y proyectos", "En qué apps cuenta y a qué proyecto suma el tiempo."),
             ("analizador", "Analizador", "Onda, espectro, stereo y loudness de lo que suena."),
             ("general", "General", "Arranque, datos y versión.")]
    PRESETS = {"diaria": [1, 2, 3, 4, 6, 8], "semanal": [5, 10, 15, 20, 30, 40],
               "mensual": [20, 40, 60, 80, 120, 160]}
    STEP = {"diaria": 15 * 60, "semanal": 3600, "mensual": 3600}
    PERIOD = {"diaria": ("Hoy llevas", "al día"), "semanal": ("Esta semana llevas", "a la semana"),
              "mensual": ("Este mes llevas", "al mes")}

    def __init__(self, app, page="metas"):
        super().__init__(app.root)
        self.app, T = app, app.T
        self.T = T
        self.c = copy.deepcopy(app.conf)
        sans = self.sans = app.f_sans
        self.fs, self.fb = (sans, 11), (sans, 11, "bold")
        self.title(f"{APP_NAME} · Ajustes")
        self.configure(bg=T["bg"])
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.side_bg = mix(T["bg"], T["bg2"], 0.35)
        self.card_bg = mix(T["bg"], T["pista"], 0.75)

        main = tk.Frame(self, bg=T["bg"])
        main.pack(fill="both", expand=True)
        # ---- barra lateral
        side = tk.Frame(main, bg=self.side_bg, width=200)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        tf = app.f_title
        tsz = 15
        while tsz > 9 and tkfont.Font(family=tf[0], size=tsz, weight=tf[2]).measure(APP_NAME) > 168:
            tsz -= 1
        tk.Label(side, text=APP_NAME, font=(tf[0], tsz, tf[2]), fg=T["acento2"],
                 bg=self.side_bg).pack(anchor="w", padx=16, pady=(18, 2))
        tk.Label(side, text="Ajustes", font=(sans, 10), fg=T["dim"],
                 bg=self.side_bg).pack(anchor="w", padx=17, pady=(0, 14))
        self.nav = {}
        for key, name, _ in self.PAGES:
            row = tk.Frame(side, bg=self.side_bg, cursor="hand2")
            row.pack(fill="x")
            bar = tk.Frame(row, bg=self.side_bg, width=3)
            bar.pack(side="left", fill="y")
            lab = tk.Label(row, text=name, font=(sans, 12), anchor="w", padx=14, pady=7,
                           bg=self.side_bg, fg=T["texto"], cursor="hand2")
            lab.pack(side="left", fill="x", expand=True)
            for w in (row, lab):
                w.bind("<Button-1>", lambda e, k=key: self.show(k))
            self.nav[key] = (row, bar, lab)

        # ---- contenido: todas las páginas en la misma celda; se muestra una
        right = tk.Frame(main, bg=T["bg"])
        right.pack(side="left", fill="both", expand=True)
        stack = tk.Frame(right, bg=T["bg"])
        stack.pack(fill="both", expand=True, padx=26, pady=(18, 0))
        self.pages = {}
        for key, name, sub in self.PAGES:
            f = tk.Frame(stack, bg=T["bg"])
            f.grid(row=0, column=0, sticky="nsew")
            tk.Label(f, text=name, font=(sans, 19, "bold"), fg=T["texto"],
                     bg=T["bg"]).pack(anchor="w")
            tk.Label(f, text=sub, font=(sans, 11), fg=T["dim"], bg=T["bg"]).pack(anchor="w",
                                                                              pady=(0, 12))
            self.pages[key] = f
        stack.grid_columnconfigure(0, weight=1)
        stack.grid_rowconfigure(0, weight=1)

        self._page_metas(self.pages["metas"])
        self._page_descansos(self.pages["descansos"])
        self._page_apariencia(self.pages["apariencia"])
        self._page_toplive(self.pages["toplive"])
        self._page_daw(self.pages["daw"])
        self._page_analizador(self.pages["analizador"])
        self._page_general(self.pages["general"])

        # ---- pie
        tk.Frame(right, bg=T["pista"], height=1).pack(fill="x", padx=26, pady=(12, 0))
        foot = tk.Frame(right, bg=T["bg"])
        foot.pack(fill="x", padx=26, pady=12)
        tk.Label(foot, text="Los cambios se aplican al pulsar Guardar.", font=(sans, 10),
                 fg=T["dim"], bg=T["bg"]).pack(side="left")
        self.button(foot, "Guardar", True, self.save).pack(side="right")
        self.button(foot, "Cancelar", False, self.destroy).pack(side="right", padx=8)
        self.bind("<Escape>", lambda e: self.destroy())

        self.show(page if page in self.pages else "metas")
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"+{max(0, (sw - w) // 2)}+{max(30, (sh - h) // 3)}")
        self.lift()
        self.after(100, self.focus_force)
        self.after(1000, self._tick)

    def show(self, key):
        T = self.T
        self.page = key
        self.pages[key].tkraise()
        for k, (row, bar, lab) in self.nav.items():
            on = k == key
            bg = mix(self.side_bg, T["acento"], 0.18) if on else self.side_bg
            row.config(bg=bg)
            lab.config(bg=bg, fg=T["texto"] if on else T["dim"],
                       font=(self.sans, 12, "bold" if on else "normal"))
            bar.config(bg=T["acento"] if on else bg)

    # ------------------------------------------------------------------ piezas
    def get(self, path):
        d = self.c
        for k in path:
            d = d[k]
        return d

    def set(self, path, v):
        d = self.c
        for k in path[:-1]:
            d = d[k]
        d[path[-1]] = v

    def heading(self, parent, text, pady=(14, 4)):
        tk.Label(parent, text=text, font=(self.sans, 12, "bold"), fg=self.T["texto"],
                 bg=parent["bg"]).pack(anchor="w", pady=pady)

    def note(self, parent, text, width=520, pady=(0, 2)):
        l = tk.Label(parent, text=text, font=(self.sans, 10), fg=self.T["dim"], bg=parent["bg"],
                     wraplength=width, justify="left")
        l.pack(anchor="w", pady=pady)
        return l

    def line(self, parent, label, width=26):
        r = tk.Frame(parent, bg=parent["bg"])
        r.pack(fill="x", pady=3)
        if label:
            tk.Label(r, text=label, font=self.fs, fg=self.T["texto"], bg=parent["bg"],
                     width=width, anchor="w").pack(side="left")
        return r

    def lbl(self, parent, text, dim=False):
        tk.Label(parent, text=text, font=self.fs, bg=parent["bg"],
                 fg=self.T["dim"] if dim else self.T["texto"]).pack(side="left", padx=(6, 0))

    def entry(self, parent, w, value, justify="left"):
        T = self.T
        e = tk.Entry(parent, width=w, font=self.fs, bg=T["pista"], fg=T["texto"],
                     insertbackground=T["texto"], relief="flat", justify=justify,
                     highlightthickness=1, highlightbackground=T["pista"],
                     highlightcolor=T["acento"])
        e.insert(0, str(value))
        e.pack(side="left", padx=(4, 0), ipady=3)
        return e

    def switch(self, parent, path=None, on_change=None, value=None):
        """Interruptor tipo iPhone. Con 'path' guarda en la configuración."""
        T = self.T
        bg = parent["bg"]
        cv = tk.Canvas(parent, width=40, height=22, bg=bg, highlightthickness=0, bd=0,
                       cursor="hand2")
        state = {"on": bool(self.get(path)) if path else bool(value)}

        def paint():
            cv.delete("all")
            on = state["on"]
            col = T["acento"] if on else mix(T["pista"], T["dim"], 0.25)
            cv.create_oval(1, 1, 21, 21, fill=col, outline="")
            cv.create_oval(19, 1, 39, 21, fill=col, outline="")
            cv.create_rectangle(11, 1, 29, 21, fill=col, outline="")
            x = 29 if on else 11
            cv.create_oval(x - 8, 3, x + 8, 19, fill="#FFFFFF", outline="")

        def flip(e=None):
            state["on"] = not state["on"]
            if path:
                self.set(path, state["on"])
            paint()
            if on_change:
                on_change(state["on"])

        cv.bind("<Button-1>", flip)
        cv.pack(side="left", padx=(0, 8))
        paint()
        cv.state = state
        return cv

    def chips(self, parent, opts, path, on_change=None, per_row=None, var=None):
        T, labels = self.T, []
        box = tk.Frame(parent, bg=parent["bg"])
        box.pack(side="left")

        def cur():
            return var["v"] if var is not None else self.get(path)

        def paint():
            for val, l in labels:
                sel = cur() == val
                l.config(bg=T["acento"] if sel else T["pista"],
                         fg="#FFFFFF" if sel else T["texto"])

        def pick(v):
            if var is not None:
                var["v"] = v
            else:
                self.set(path, v)
            if on_change:
                on_change(v)
            paint()

        for i, (val, text) in enumerate(opts):
            l = tk.Label(box, text=text, font=(self.sans, 10), padx=10, pady=4,
                         cursor="hand2")
            l.bind("<Button-1>", lambda e, v=val: pick(v))
            if per_row:
                l.grid(row=i // per_row, column=i % per_row, sticky="we", padx=(0, 5), pady=2)
            else:
                l.pack(side="left", padx=(0, 5))
            labels.append((val, l))
        paint()
        box.repaint = paint
        return box

    def stepper(self, parent, value, step, lo, hi, fmt, width=9, on_change=None):
        """[−]  valor  [+]  — un clic cambia; mantener presionado repite."""
        T = self.T
        st = {"v": value, "rep": None}
        box = tk.Frame(parent, bg=parent["bg"])
        box.pack(side="left")
        val = tk.Label(box, font=(self.sans, 13, "bold"), fg=T["texto"], bg=T["pista"],
                       width=width, pady=3)

        def paint():
            val.config(text=fmt(st["v"]))

        def change(d):
            nv = max(lo, min(hi, st["v"] + d))
            if nv != st["v"]:
                st["v"] = nv
                paint()
                if on_change:
                    on_change(nv)

        def press(d):
            change(d)
            st["rep"] = self.after(420, lambda: hold(d))

        def hold(d):
            change(d)
            st["rep"] = self.after(90, lambda: hold(d))

        def release(e=None):
            if st["rep"]:
                self.after_cancel(st["rep"])
                st["rep"] = None

        for txt, d in (("−", -step), (None, 0), ("+", step)):
            if txt is None:
                val.pack(side="left", padx=1)
                continue
            b = tk.Label(box, text=txt, font=(self.sans, 14, "bold"), width=2, pady=1,
                         bg=T["pista"], fg=T["acento2"], cursor="hand2")
            b.bind("<ButtonPress-1>", lambda e, d=d: press(d))
            b.bind("<ButtonRelease-1>", release)
            b.bind("<Leave>", release)
            b.pack(side="left", padx=1)
        val.bind("<MouseWheel>", lambda e: change(step if e.delta > 0 else -step))
        paint()
        box.st = st

        def setv(v):
            st["v"] = max(lo, min(hi, v))
            paint()
            if on_change:
                on_change(st["v"])
        box.setv = setv
        return box

    def card(self, parent, pady=(0, 10)):
        f = tk.Frame(parent, bg=self.card_bg, highlightthickness=1,
                     highlightbackground=mix(self.card_bg, self.T["borde"], 0.25))
        f.pack(fill="x", pady=pady)
        inner = tk.Frame(f, bg=self.card_bg)
        inner.pack(fill="x", padx=14, pady=10)
        return f, inner

    # ------------------------------------------------------------------ Metas
    def _page_metas(self, pg):
        T = self.T
        self.goal_ui = {}
        vals = self.app.goal_values()
        for k in ("diaria", "semanal", "mensual"):
            g = self.c["metas"][k]
            outer, cd = self.card(pg)
            top = tk.Frame(cd, bg=self.card_bg)
            top.pack(fill="x")
            ui = {"outer": outer, "cd": cd}
            ui["sw"] = self.switch(top, ("metas", k, "activa"),
                                   on_change=lambda on, k=k: self._goal_enabled(k))
            name = tk.Entry(top, width=14, font=(self.sans, 13, "bold"), bg=self.card_bg,
                            fg=T["texto"], insertbackground=T["texto"], relief="flat",
                            highlightthickness=0)
            name.insert(0, g["nombre"])
            name.pack(side="left")
            ui["name"] = name
            tk.Label(top, text="✎", font=(self.sans, 11), fg=T["dim"],
                     bg=self.card_bg).pack(side="left")
            ui["prog"] = tk.Label(top, text="", font=(self.sans, 10), fg=T["dim"],
                                  bg=self.card_bg)
            ui["prog"].pack(side="right")
            mid = tk.Frame(cd, bg=self.card_bg)
            mid.pack(fill="x", pady=(8, 4))
            ui["step"] = self.stepper(mid, int(g["segundos"]), self.STEP[k], 15 * 60,
                                      999 * 3600, self._fmt_goal,
                                      on_change=lambda v, k=k: self._goal_changed(k))
            tk.Label(mid, text=self.PERIOD[k][1], font=self.fs, fg=T["dim"],
                     bg=self.card_bg).pack(side="left", padx=(8, 14))
            pre = tk.Frame(mid, bg=self.card_bg)
            pre.pack(side="left")
            ui["presets"] = []
            for hh in self.PRESETS[k]:
                l = tk.Label(pre, text=f"{hh} h", font=(self.sans, 10), padx=7, pady=3,
                             cursor="hand2")
                l.bind("<Button-1>", lambda e, k=k, hh=hh: self.goal_ui[k]["step"].setv(hh * 3600))
                l.pack(side="left", padx=(0, 4))
                ui["presets"].append((hh * 3600, l))
            ui["bar"] = tk.Canvas(cd, height=6, bg=self.card_bg, highlightthickness=0, bd=0)
            ui["bar"].pack(fill="x", pady=(6, 0))
            ui["bar"].bind("<Configure>", lambda e, k=k: self._goal_changed(k))
            ui["done"] = vals.get(k, 0)
            self.goal_ui[k] = ui
            self._goal_changed(k)
            self._goal_enabled(k)
        self.heading(pg, "Cuándo cuenta", pady=(6, 2))
        r = self.line(pg, "Pausar si no toco nada durante", width=28)
        self.idle_step = self.stepper(r, max(1, self.c["limite_inactividad"] // 60), 1, 1, 60,
                                      lambda v: f"{v} min", width=7)
        self.note(pg, "Solo cuenta mientras tu DAW está al frente y usas el teclado o el mouse. "
                      "Si te alejas más de este tiempo, el contador se pausa solo.")

    def _fmt_goal(self, s):
        h, m = s // 3600, s % 3600 // 60
        return f"{h} h {m:02d} min" if m else f"{h} h"

    def _goal_changed(self, k):
        ui = self.goal_ui.get(k)
        if not ui:
            return
        T = self.T
        goal = ui["step"].st["v"]
        done = ui["done"]
        on = bool(self.c["metas"][k]["activa"])
        for secs, l in ui["presets"]:
            sel = secs == goal
            bg = T["acento"] if sel else T["pista"]
            fg = "#FFFFFF" if sel else T["texto"]
            if not on:
                bg, fg = mix(bg, self.card_bg, 0.6), mix(fg, self.card_bg, 0.55)
            l.config(bg=bg, fg=fg)
            l._fg_on = "#FFFFFF" if sel else T["texto"]
        left = goal - done
        lead = self.PERIOD[k][0]
        ui["prog"].config(text=f"{lead} {fmt_goal(done)} · " +
                          ("¡meta cumplida!" if left <= 0 else f"faltan {fmt_goal(left)}"),
                          fg=GOLD if left <= 0 else T["dim"])
        bar = ui["bar"]
        bar.delete("all")
        w = max(1, bar.winfo_width())
        bar.create_rectangle(0, 0, w, 6, fill=T["pista"], outline="")
        frac = max(0.0, min(1.0, done / max(1, goal)))
        if frac > 0:
            bar.create_rectangle(0, 0, max(3, w * frac), 6, outline="",
                                 fill=GOLD if frac >= 1 else T["acento"])

    def _goal_enabled(self, k):
        ui = self.goal_ui[k]
        on = bool(self.c["metas"][k]["activa"])
        self._set_enabled(ui["cd"], on, skip=(ui["sw"],) + tuple(l for _, l in ui["presets"]))
        self._goal_changed(k)

    # ------------------------------------------------------------------ Descansos
    def _page_descansos(self, pg):
        T = self.T
        opts = tk.Frame(pg, bg=T["bg"])
        opts.pack(fill="x")
        self.mode_cards = {}
        for m, title, desc in (("autonomo", "Avisarme cuándo descansar",
                                "El timer se pone ámbar cuando se acerca el descanso y rojo "
                                "cuando toca parar. Sin notificaciones: solo colores."),
                               ("normal", "Solo contar mi tiempo",
                                "Cuenta tus horas y tus metas, sin avisos de descanso.")):
            f = tk.Frame(opts, bg=self.card_bg, highlightthickness=2, cursor="hand2")
            f.pack(side="left", fill="both", expand=True, padx=(0, 10))
            inner = tk.Frame(f, bg=self.card_bg)
            inner.pack(fill="both", padx=14, pady=12)
            t = tk.Label(inner, text=title, font=(self.sans, 12, "bold"), fg=T["texto"],
                         bg=self.card_bg, anchor="w")
            t.pack(anchor="w")
            d = tk.Label(inner, text=desc, font=(self.sans, 10), fg=T["dim"], bg=self.card_bg,
                         wraplength=230, justify="left")
            d.pack(anchor="w", pady=(4, 0))
            for w in (f, inner, t, d):
                w.bind("<Button-1>", lambda e, m=m: self._on_modo(m))
            self.mode_cards[m] = f
        self.auto_box = tk.Frame(pg, bg=T["bg"])
        a = self.c["autonomo"]
        self.heading(self.auto_box, "Tus tiempos", pady=(16, 4))
        r = self.line(self.auto_box, "Descansar cada")
        self.work_step = self.stepper(r, int(a["trabajo_min"]), 5, 10, 240,
                                      lambda v: f"{v} min", width=8)
        self.lbl(r, "de trabajo seguido", dim=True)
        r = self.line(self.auto_box, "El descanso dura")
        self.brk_step = self.stepper(r, int(a["break_min"]), 1, 1, 60,
                                     lambda v: f"{v} min", width=8)
        r = self.line(self.auto_box, "Avisarme si en el día paso de")
        self.max_step = self.stepper(r, int(a["max_diario_h"] or 0), 1, 0, 16,
                                     lambda v: "Nunca" if v == 0 else f"{v} h", width=8)
        self.note(self.auto_box, "Si te alejas del DAW el tiempo que dura el descanso, la racha "
                                 "vuelve a cero sola.", pady=(8, 0))
        # aviso de bienestar (modo normal)
        self.warn_box = tk.Frame(pg, bg=mix(WARN, T["bg"], 0.88))
        tk.Frame(self.warn_box, bg=WARN, width=3).pack(side="left", fill="y")
        wb = tk.Frame(self.warn_box, bg=mix(WARN, T["bg"], 0.88))
        wb.pack(side="left", fill="both", padx=(12, 12), pady=10)
        tk.Label(wb, text="⚠  Cuida tu cuerpo y tus oídos", font=(self.sans, 11, "bold"),
                 fg=WARN, bg=wb["bg"]).pack(anchor="w")
        tk.Label(wb, text=WELLBEING_TEXT, font=(self.sans, 10), fg=T["texto"], bg=wb["bg"],
                 wraplength=500, justify="left").pack(anchor="w", pady=(4, 0))
        self._on_modo(self.c["modo"])

    def _on_modo(self, m):
        T = self.T
        self.c["modo"] = m
        for k, f in self.mode_cards.items():
            f.config(highlightbackground=T["acento"] if k == m else self.card_bg,
                     highlightcolor=T["acento"] if k == m else self.card_bg)
        if m == "autonomo":
            self.warn_box.pack_forget()
            self.auto_box.pack(fill="x")
        else:
            self.auto_box.pack_forget()
            self.warn_box.pack(fill="x", pady=(16, 0))

    # ------------------------------------------------------------------ Apariencia
    def _page_apariencia(self, pg):
        T, app = self.T, self.app
        r = self.line(pg, "Estilo", width=16)
        self.estilo_row = r
        self.chips(r, [(k, v["nombre"]) for k, v in TEMAS.items()], ("tema",),
                   on_change=self._on_tema, per_row=4)
        self.body = pg
        self.theme_desc = tk.Frame(pg, bg=T["bg"])
        tk.Label(self.theme_desc, text="LET'S GAUUUUX", font=(app.pick(BRAND_FONTS), 15, "bold"),
                 fg="#FF3B47", bg=T["bg"]).pack(anchor="w")
        tk.Label(self.theme_desc, text="Modo único. Solo para los más audaces.",
                 font=(self.sans, 11, "bold"), fg="#FFFFFF", bg=T["bg"]).pack(anchor="w")
        tk.Label(self.theme_desc, text="Tipografía fija: este modo no se personaliza, se vive.",
                 font=(self.sans, 10), fg=T["dim"], bg=T["bg"]).pack(anchor="w", pady=(1, 0))
        self._build_personal_box()
        self.after_theme = tk.Frame(pg, bg=T["bg"], height=1)
        self.after_theme.pack(fill="x")

        # tamaño de la vista actual (se aplica al instante)
        key = app.pos_key()
        lo, hi = ESCALA_LIM["mini" if key.startswith("mini") else "otra"]
        vname = {"completa": "Completa", "compacta": "Compacta", "mini": "Minimizada"}.get(
            app.conf.get("vista"), "Completa")
        r = self.line(pg, "Tamaño del timer", width=16)
        self.size_step = self.stepper(r, int(round(app.scale_for(key) * 100)), 5,
                                      int(lo * 100), int(hi * 100), lambda v: f"{v} %",
                                      width=7, on_change=self._size_live)
        b = self.button(r, "Original", False, lambda: self.size_step.setv(100))
        b.pack(side="left", padx=(12, 0))
        if app.conf.get("top_mode"):
            self._set_enabled(r, False)
            self.note(pg, "En Top Live el tamaño lo da la franja (página Top Live).")
        else:
            self.note(pg, f"Vista actual: {vname}. Se ve al instante. La vista Minimizada se "
                          "puede achicar hasta 60 % para que quepa en la barra de título de Live.")
        r = self.line(pg, "Vista", width=16)
        self.chips(r, [("completa", "Completa"), ("compacta", "Compacta"),
                       ("mini", "Minimizada")], ("vista",))
        r = self.line(pg, "Orientación", width=16)
        self.chips(r, [("horizontal", "Horizontal"), ("vertical", "Vertical")],
                   ("orientacion",))
        r = self.line(pg, "Opacidad", width=16)
        self.op_step = self.stepper(r, int(round(self.c["opacidad"] * 100)), 5, 40, 100,
                                    lambda v: f"{v} %", width=7)
        r = self.line(pg, "Animaciones", width=16)
        self.switch(r, ("animaciones",))
        r = self.line(pg, "Fluidez", width=16)
        self.chips(r, [("maximo", "120 fps"), ("equilibrado", "Equilibrado"),
                       ("ahorro", "60 fps")], ("analizador", "rendimiento"))
        self.font_rows = []
        r = self.line(pg, "Letra del título", width=16)
        self.font_rows.append(self.fontmenu(r, TITLE_FONTS, "fuente_titulo",
                                            self.c.get("fuente_titulo") or app.f_title[0]))
        r = self.line(pg, "Letra del reloj", width=16)
        self.font_rows.append(self.fontmenu(r, CLOCK_FONTS, "fuente_reloj",
                                            self.c.get("fuente_reloj") or app.f_clock_family))
        self._on_tema(self.c["tema"], init=True)

    def _size_live(self, v):
        app = self.app
        if app.conf.get("top_mode"):
            return
        k = int(v) / 100
        key = app.pos_key()
        if abs(app.scale_for(key) - k) < 0.001:
            return
        app.conf.setdefault("escala", {})[key] = k
        app.relayout()
        app.save_conf()

    # ------------------------------------------------------------------ Top Live
    def _page_toplive(self, pg):
        T, app = self.T, self.app
        self.note(pg, TOP_DESC, pady=(0, 10))
        on = bool(app.conf.get("top_mode"))
        _, cd = self.card(pg)
        r = tk.Frame(cd, bg=self.card_bg)
        r.pack(fill="x")
        tk.Label(r, text="Activo ahora" if on else "Apagado", font=(self.sans, 12, "bold"),
                 fg=T["acento2"] if on else T["dim"], bg=self.card_bg).pack(side="left")
        self.button(r, "Desactivar Top Live" if on else "Activar Top Live", not on,
                    self._toggle_top).pack(side="right")
        r = self.line(pg, "Alto de la franja", width=16)
        self.chips(r, [(p_, f"{p_} %") for p_ in (100, 90, 80, 70, 60, 50)], ("top_escala",))
        self.note(pg, "Se adapta solo a tu pantalla y a la ventana de tu DAW. Lleva el mouse al "
                      "borde superior para ver la barra de menú.", pady=(10, 0))

    # ------------------------------------------------------------------ DAW y proyectos
    def _page_daw(self, pg):
        T, app = self.T, self.app
        self.heading(pg, "Cuenta tiempo en", pady=(0, 4))
        keys = self.c.get("daws")
        self.daw_sel = set(keys if keys is not None else [k for k, _, _ in DAWS])
        self.multichips(pg, [(k, n) for k, n, _ in DAWS], self.daw_sel)
        r = self.line(pg, "Otras apps", width=12)
        self.e_extra = self.entry(r, 30, self.c.get("daws_extra", ""))
        self.note(pg, "Nombres separados por comas, tal como aparecen en el Dock o en el "
                      "Administrador de tareas.")
        self.heading(pg, "Proyectos")
        r = self.line(pg, "")
        self.switch(r, ("proyecto_auto",))
        tk.Label(r, text="Detectar el proyecto desde el título del DAW", font=self.fs,
                 fg=T["texto"], bg=T["bg"]).pack(side="left")
        self.note(pg, "Si no hay título (o está apagado), el tiempo se suma al proyecto que "
                      "elijas en el menú del timer.")
        self.button(pg, "Ver proyectos…", False, app.open_projects).pack(anchor="w", pady=(8, 0))

    # ------------------------------------------------------------------ Analizador
    def _page_analizador(self, pg):
        T, app = self.T, self.app
        r = self.line(pg, "")
        self.switch(r, ("analizador", "activo"))
        tk.Label(r, text="Mostrar el analizador", font=self.fb, fg=T["texto"],
                 bg=T["bg"]).pack(side="left")
        r = self.line(pg, "Entrada de audio", width=16)
        self.devmenu(r)
        self.note(pg, "Recomendado: pon el plugin Gaux Link al final del Master de tu DAW y deja "
                      "\"Automático\". Sin plugin, en Mac sirve BlackHole 2ch (la salida del DAW "
                      "debe ser un Dispositivo de salida múltiple) y en Windows VB-Cable.")
        r = self.line(pg, "Color de la onda", width=16)
        self.chips(r, [("tema", "Del estilo"), ("rgb", "RGB estándar")],
                   ("analizador", "color_onda"))
        self.heading(pg, "Módulos")
        grid = tk.Frame(pg, bg=T["bg"])
        grid.pack(anchor="w")
        for i, (k, name) in enumerate((("wave", "Waveform"), ("spec", "Spectrum"),
                                       ("stereo", "Stereo"), ("lufs", "Loudness"))):
            cell = tk.Frame(grid, bg=T["bg"])
            cell.grid(row=i // 2, column=i % 2, sticky="w", padx=(0, 30), pady=3)
            self.switch(cell, ("analizador", "modulos", k))
            tk.Label(cell, text=name, font=self.fs, fg=T["texto"], bg=T["bg"]).pack(side="left")
        an = app.analyzer
        if an is not None:
            self.button(pg, "Diagnóstico de audio…", False, an.open_diag).pack(anchor="w",
                                                                               pady=(14, 0))

    # ------------------------------------------------------------------ General
    def _page_general(self, pg):
        T, app = self.T, self.app
        if SYSTEM in ("Darwin", "Windows"):
            r = self.line(pg, "")
            self.switch(r, value=autostart_enabled(),
                        on_change=lambda on: (install_autostart if on else remove_autostart)(
                            quiet=True))
            tk.Label(r, text="Abrir al iniciar sesión", font=self.fb, fg=T["texto"],
                     bg=T["bg"]).pack(side="left")
            self.note(pg, "Se aplica al instante. Queda esperando en segundo plano y aparece "
                          "cuando abres tu DAW.")
        self.heading(pg, "Tus datos")
        self.note(pg, "Tus horas, proyectos y ajustes se guardan en tu computador, en la "
                      "carpeta .live_timer de tu usuario. Nada sale de tu equipo.")
        r = self.line(pg, "")
        self.button(r, "Abrir carpeta de datos", False, self._open_data).pack(side="left")
        self.button(r, "Exportar proyectos (CSV)", False,
                    lambda: app.open_projects()).pack(side="left", padx=(8, 0))
        self.heading(pg, "Acerca de")
        self.note(pg, f"{APP_NAME} {VERSION} · por Aleksander Gaux"
                      + ("" if FROZEN else " · corriendo desde la Terminal"))
        r = self.line(pg, "")
        self.button(r, f"Salir de {APP_NAME}", False,
                    lambda: (self.destroy(), app.quit())).pack(side="left", pady=(10, 0))
        self.note(pg, "Al salir deja de contar hasta que lo vuelvas a abrir.", pady=(6, 0))

    def _open_data(self):
        os.makedirs(APP_DIR, exist_ok=True)
        try:
            if SYSTEM == "Darwin":
                subprocess.Popen(["open", APP_DIR])
            elif SYSTEM == "Windows":
                os.startfile(APP_DIR)
            else:
                subprocess.Popen(["xdg-open", APP_DIR])
        except Exception:
            pass

    # ------------------------------------------------------------------ comunes
    def _tick(self):
        """Mientras está abierto, el avance de las metas se mantiene al día."""
        if not self.winfo_exists():
            return
        try:
            vals = self.app.goal_values()
            for k, ui in self.goal_ui.items():
                ui["done"] = vals.get(k, 0)
                self._goal_changed(k)
        except Exception:
            pass
        self.after(5000, self._tick)

    def _set_enabled(self, w, on, skip=()):
        T = self.T
        for ch in w.winfo_children():
            if ch in skip:
                continue
            if isinstance(ch, tk.Entry):
                ch.config(state="normal" if on else "disabled",
                          disabledbackground=ch.cget("bg"),
                          disabledforeground=mix(T["dim"], T["bg"], .35))
            elif isinstance(ch, tk.Label):
                if not hasattr(ch, "_fg_on"):
                    ch._fg_on = ch.cget("fg")
                ch.config(fg=ch._fg_on if on else mix(ch._fg_on, T["bg"], .55))
            self._set_enabled(ch, on, skip)

    def fontmenu(self, parent, cands, key, current):
        T = self.T
        avail = [f for f in cands if f in self.app.fams] or [current]
        var = tk.StringVar(value=current)
        om = tk.OptionMenu(parent, var, *avail,
                           command=lambda v: self.c.__setitem__(key, v))
        om.config(bg=T["pista"], fg=T["texto"], activebackground=T["acento"],
                  activeforeground="#FFFFFF", highlightthickness=0, relief="flat",
                  font=self.fs, width=13)
        menu = om["menu"]
        for i, f in enumerate(avail):
            try:
                menu.entryconfig(i, font=(f, 12))
            except tk.TclError:
                pass
        om.pack(side="left")
        lock = tk.Label(parent, text="Fija en Gaux Mode", font=(self.app.f_sans, 9, "italic"),
                        fg=T["dim"], bg=T["bg"])
        return om, lock

    def devmenu(self, parent):
        T = self.T
        try:
            if not FROZEN:
                sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import gaux_analizador
            names = [gaux_analizador.LINK_NAME] + [n for _, n in gaux_analizador.list_inputs()]
        except Exception:
            tk.Label(parent, text="Instala numpy y sounddevice (ver LEEME)",
                     font=(self.app.f_sans, 9, "italic"), fg=T["dim"],
                     bg=T["bg"]).pack(side="left")
            return
        cur = self.c["analizador"].get("dispositivo", "auto")
        opts = ["Automático"] + names
        var = tk.StringVar(value="Automático" if cur == "auto" or cur not in names else cur)

        def pick(v):
            self.c["analizador"]["dispositivo"] = "auto" if v == "Automático" else v

        om = tk.OptionMenu(parent, var, *opts, command=pick)
        om.config(bg=T["pista"], fg=T["texto"], activebackground=T["acento"],
                  activeforeground="#FFFFFF", highlightthickness=0, relief="flat",
                  font=self.fs, width=18)
        om.pack(side="left")

    def button(self, parent, text, primary, cmd):
        T = self.T
        bg = T["acento"] if primary else T["pista"]
        b = tk.Label(parent, text=text, font=self.fb, padx=14, pady=4, cursor="hand2",
                     bg=bg, fg="#FFFFFF" if primary else T["texto"])
        b.bind("<Button-1>", lambda e: cmd())
        b.bind("<Enter>", lambda e: b.config(bg=T["acento2"] if primary else T["bg2"]))
        b.bind("<Leave>", lambda e: b.config(bg=bg))
        return b


    def _toggle_top(self):
        app = self.app
        self.save()                      # guarda lo que hayas cambiado y cierra Ajustes
        app.toggle_top_mode()

    def _build_personal_box(self):
        T, sans, pc = self.T, self.app.f_sans, self.c["personal"]
        box = self.personal_box = tk.Frame(self.body, bg=T["bg"])
        tk.Label(box, text="Modo Personal: tu timer, tu nombre, tu frase.",
                 font=(sans, 10, "bold"), fg=T["texto"], bg=T["bg"]).pack(anchor="w")
        self.p_entries = {}
        for key, label, w in (("nombre", "Tu nombre (título)", 24),
                              ("inicio", "Frase de inicio", 24),
                              ("cierre", "Frase de cierre", 24)):
            r = tk.Frame(box, bg=T["bg"])
            r.pack(fill="x", pady=2)
            tk.Label(r, text=label, font=self.fs, fg=T["texto"], bg=T["bg"], width=19,
                     anchor="w").pack(side="left")
            e = self.entry(r, w, pc.get(key, ""))
            self.p_entries[key] = e
        tk.Label(box, text="La frase de inicio aparece cada vez que abres tu DAW; la de cierre, "
                           "en la tarjeta con el resumen al cerrarlo. Escribe lo que quieras.",
                 font=(sans, 9), fg=T["dim"], bg=T["bg"], wraplength=430,
                 justify="left").pack(anchor="w", pady=(0, 3))
        r = tk.Frame(box, bg=T["bg"])
        r.pack(fill="x", pady=2)
        tk.Label(r, text="Color", font=self.fs, fg=T["texto"], bg=T["bg"], width=19,
                 anchor="w").pack(side="left")
        self.swatches = []

        def pick(c):
            pc["color"] = c
            self.hex_e.delete(0, "end")
            self.hex_e.insert(0, c)
            paint()

        def paint():
            for c, l in self.swatches:
                sel = c.lower() == (pc.get("color") or "").lower()
                l.config(highlightbackground="#FFFFFF" if sel else T["bg"])

        for c in PERSONAL_COLORS:
            l = tk.Label(r, text="  ", bg=c, cursor="hand2", width=2, highlightthickness=2,
                         highlightbackground=T["bg"])
            l.bind("<Button-1>", lambda e, c=c: pick(c))
            l.pack(side="left", padx=2)
            self.swatches.append((c, l))
        self.hex_e = self.entry(r, 8, pc.get("color", "#3B82F6"), justify="center")

        def more():
            from tkinter import colorchooser
            res = colorchooser.askcolor(color=pc.get("color"), parent=self,
                                        title="Color del Modo Personal")
            if res and res[1]:
                pick(res[1].upper())

        b = tk.Label(r, text="Más…", font=(sans, 9), padx=6, pady=1, cursor="hand2",
                     bg=T["pista"], fg=T["texto"])
        b.bind("<Button-1>", lambda e: more())
        b.pack(side="left", padx=4)
        paint()
        r = tk.Frame(box, bg=T["bg"])
        r.pack(fill="x", pady=2)
        tk.Label(r, text="Forma", font=self.fs, fg=T["texto"], bg=T["bg"], width=19,
                 anchor="w").pack(side="left")
        self.chips(r, [("redondeada", "Redondeada"), ("angular", "Angular")],
                   ("personal", "forma"))
        r = tk.Frame(box, bg=T["bg"])
        r.pack(fill="x", pady=(2, 6))
        tk.Label(r, text="Efectos (rayos, glitch)", font=self.fs, fg=T["texto"], bg=T["bg"],
                 width=19, anchor="w").pack(side="left")
        self.switch(r, ("personal", "efectos"))

    def multichips(self, parent, opts, selected, per_row=4):
        """Botones que se encienden y apagan de forma independiente (varios a la vez)."""
        T = self.T
        grid = tk.Frame(parent, bg=T["bg"])
        grid.pack(anchor="w", pady=2)
        for i, (val, text) in enumerate(opts):
            l = tk.Label(grid, text=text, font=(self.app.f_sans, 9), padx=6, pady=2,
                         cursor="hand2")

            def paint(l=l, v=val):
                on = v in selected
                l.config(bg=T["acento"] if on else T["pista"], fg="#FFFFFF" if on else T["dim"])

            def flip(e, v=val, paint=paint):
                selected.symmetric_difference_update({v})
                paint()

            l.bind("<Button-1>", flip)
            l.grid(row=i // per_row, column=i % per_row, sticky="we", padx=(0, 4), pady=2)
            paint()

    def _on_tema(self, k, init=False):
        if not init:
            self.op_step.setv(int(round(TEMAS[k]["alpha"] * 100)))
        brand = bool(TEMAS[k].get("marca"))
        if brand:
            self.theme_desc.pack(fill="x", pady=(2, 8), before=self.after_theme)
        else:
            self.theme_desc.pack_forget()
        if TEMAS[k].get("personal"):
            self.personal_box.pack(fill="x", pady=(4, 8), before=self.after_theme)
        else:
            self.personal_box.pack_forget()
        for om, lock in getattr(self, "font_rows", []):
            if brand:
                om.pack_forget()
                lock.pack(side="left")
            else:
                lock.pack_forget()
                om.pack(side="left")

    def save(self):
        c, app = self.c, self.app
        c["opacidad"] = self.op_step.st["v"] / 100
        names = {"diaria": "Hoy", "semanal": "Semana", "mensual": "Mes"}
        for k, ui in self.goal_ui.items():
            c["metas"][k]["nombre"] = ui["name"].get().strip()[:14] or names[k]
            c["metas"][k]["segundos"] = max(60, int(ui["step"].st["v"]))
        a = c["autonomo"]
        a["trabajo_min"] = int(self.work_step.st["v"])
        a["break_min"] = int(self.brk_step.st["v"])
        a["max_diario_h"] = int(self.max_step.st["v"])
        c["limite_inactividad"] = int(self.idle_step.st["v"]) * 60
        pc = c["personal"]
        for key, e in self.p_entries.items():
            v = e.get().strip()
            if key == "nombre":
                v = v or "Tu nombre"
            pc[key] = v[:60]
        hx = self.hex_e.get().strip()
        if re.match(r"^#?[0-9a-fA-F]{6}$", hx):
            pc["color"] = ("#" + hx.lstrip("#")).upper()
        all_keys = [k for k, _, _ in DAWS]
        c["daws"] = None if self.daw_sel >= set(all_keys) else [k for k in all_keys
                                                                if k in self.daw_sel]
        c["daws_extra"] = self.e_extra.get().strip()
        new_vista = c.get("vista")
        for k in ("x", "y", "pos", "vista", "vista_previa", "top_mode", "top_geom", "top_prev",
                  "proyecto", "escala"):
            c[k] = app.conf.get(k)
        new_pct = c.get("top_escala", 100)
        c["top_escala"] = app.conf.get("top_escala", 100)    # se aplica abajo, moviendo Live
        old_a = app.conf["analizador"]
        for k in ("x", "y", "w", "h"):               # el panel pudo moverse
            c["analizador"][k] = old_a.get(k)
        restart = old_a.get("dispositivo") != c["analizador"].get("dispositivo")
        app.conf = c
        app.save_conf()
        app.apply_conf()
        app.apply_analyzer(restart=restart)
        if new_pct != app.conf.get("top_escala", 100):
            app.set_top_scale(new_pct)
        if new_vista and new_vista != app.conf.get("vista"):
            app.set_vista(new_vista)
        self.destroy()


# --------------------------------------------------------------------------
# Arranque automático con el sistema
# --------------------------------------------------------------------------
LAUNCH_LABEL = "com.aleksandergaux.livetimer"
OLD_LAUNCH = os.path.expanduser("~/Library/LaunchAgents/com.livetimer.app.plist")
LAUNCH_PLIST = os.path.expanduser(f"~/Library/LaunchAgents/{LAUNCH_LABEL}.plist")
WIN_STARTUP = os.path.join(os.environ.get("APPDATA", ""),
                           r"Microsoft\Windows\Start Menu\Programs\Startup", "GauxLiveTimer.vbs")


def _launch_cmd():
    """Qué se ejecuta al iniciar sesión: la app empaquetada o el script con Python."""
    if FROZEN:
        return [sys.executable, "--login"]
    exe = sys.executable
    if SYSTEM == "Windows":
        exe = exe.replace("python.exe", "pythonw.exe")
    return [exe, os.path.abspath(__file__), "--login"]


def autostart_enabled():
    if SYSTEM == "Darwin":
        return os.path.exists(LAUNCH_PLIST) or os.path.exists(OLD_LAUNCH)
    if SYSTEM == "Windows":
        return os.path.exists(WIN_STARTUP)
    return False


def install_autostart(quiet=False):
    cmd = _launch_cmd()
    if SYSTEM == "Windows":
        with open(WIN_STARTUP, "w", encoding="utf-8") as f:
            args = " ".join(f'""{c}""' for c in cmd)
            f.write(f'CreateObject("WScript.Shell").Run "{args}", 0\n')
        path = WIN_STARTUP
    elif SYSTEM == "Darwin":
        if os.path.exists(OLD_LAUNCH):              # el arranque viejo (script) se reemplaza
            os.remove(OLD_LAUNCH)
        os.makedirs(os.path.dirname(LAUNCH_PLIST), exist_ok=True)
        esc = lambda t: t.replace("&", "&amp;").replace("<", "&lt;")
        args = "".join(f"<string>{esc(c)}</string>" for c in cmd)
        with open(LAUNCH_PLIST, "w", encoding="utf-8") as f:
            f.write(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>{LAUNCH_LABEL}</string>
  <key>ProgramArguments</key><array>{args}</array>
  <key>RunAtLoad</key><true/>
  <key>ProcessType</key><string>Interactive</string>
</dict></plist>
""")
        path = LAUNCH_PLIST
    else:
        if not quiet:
            print("Arranque automático solo disponible en Windows y macOS.")
        return False
    if not quiet:
        print(f"Listo. {APP_NAME} arrancará con el sistema ({path}).")
    return True


def remove_autostart(quiet=False):
    found = False
    for path in ((LAUNCH_PLIST, OLD_LAUNCH) if SYSTEM == "Darwin" else (WIN_STARTUP,)):
        if path and os.path.exists(path):
            os.remove(path)
            found = True
    if not quiet:
        print("Quitado del arranque." if found else "No estaba instalado en el arranque.")
    return found


def _migrate_autostart():
    """Si antes arrancaba el script de la Terminal al iniciar sesión, ahora arranca la app."""
    if FROZEN and SYSTEM == "Darwin" and os.path.exists(OLD_LAUNCH):
        try:
            install_autostart(quiet=True)
        except Exception:
            pass


def _setup_log():
    """En la app no hay Terminal: los errores quedan en ~/.live_timer/registro.txt."""
    if not FROZEN:
        return
    import traceback
    os.makedirs(APP_DIR, exist_ok=True)
    path = os.path.join(APP_DIR, "registro.txt")
    try:
        if os.path.exists(path) and os.path.getsize(path) > 512 * 1024:
            os.replace(path, path + ".anterior")
        log = open(path, "a", encoding="utf-8", buffering=1)
    except OSError:
        return
    sys.stdout = sys.stderr = log
    print(f"--- {APP_NAME} {VERSION} · {dt.datetime.now():%Y-%m-%d %H:%M} · "
          f"{platform.platform()}")

    def hook(t, v, tb):
        traceback.print_exception(t, v, tb)
    sys.excepthook = hook


def main():
    _setup_log()
    if "--instalar-inicio" in sys.argv:
        return install_autostart()
    if "--quitar-inicio" in sys.argv:
        return remove_autostart()
    if psutil is None and not DEMO and SYSTEM == "Windows":
        print("Falta psutil. Instala con:  pip install psutil")
        sys.exit(1)
    if SYSTEM == "Darwin" and tk.TkVersion < 8.6:
        print("Aviso: este Python usa Tk", tk.TkVersion, "(el de Apple, obsoleto).\n"
              "Si el widget sale en blanco, instala Python desde "
              "https://www.python.org/downloads/ y usa ese python3.")

    # Una sola instancia: si ya hay un timer abierto, se le pide que se cierre
    # y esta versión toma su lugar (así siempre corre el código más reciente).
    lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    for attempt in range(40):
        try:
            lock.bind(("127.0.0.1", LOCK_PORT))
            break
        except OSError:
            if attempt == 0:
                try:
                    c = socket.create_connection(("127.0.0.1", LOCK_PORT), timeout=1)
                    c.sendall(b"QUIT")
                    c.close()
                except OSError:
                    pass
            time.sleep(0.15)
    else:
        print(f"{APP_NAME} ya está abierto. Ciérralo con ctrl+clic → Salir y vuelve a intentar.")
        sys.exit(0)
    lock.listen(1)

    _migrate_autostart()
    app = GauxTimer()
    app.lock = lock
    app.app_hooks()

    def listen():
        while True:
            try:
                conn, _ = lock.accept()
                if conn.recv(16).startswith(b"QUIT"):
                    app.quit_requested = True
                conn.close()
            except OSError:
                return

    threading.Thread(target=listen, daemon=True).start()
    app.run()


if __name__ == "__main__":
    main()
