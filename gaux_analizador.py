"""
Gaux Live Timer — analizador de audio (solo visualización).

Módulos: Waveform RGB · Spectrum + Spectrogram · Stereometer · Loudness (LUFS).
Recibe el audio de Live por un dispositivo de entrada:
  macOS  -> BlackHole 2ch (vía un Dispositivo de salida múltiple)
  Windows-> VB-Cable ("CABLE Output") o "Mezcla estéreo"

Requiere: numpy, sounddevice
"""
import math
import platform
import subprocess
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from collections import deque

import socket
import struct

import numpy as np
try:
    import sounddevice as sd          # entrada de audio (BlackHole / VB-Cable)
except Exception:                     # sin PortAudio: igual funciona con Gaux Link
    sd = None

SYSTEM = platform.system()
FROZEN = bool(getattr(sys, "frozen", False))
HOST_APP = "Gaux Live Timer" if FROZEN else ("Terminal" if SYSTEM == "Darwin" else "Python")


def mic_permission():
    """Permiso de micrófono de la app que abrió el timer (Terminal), en macOS.
    'ok', 'denegado', 'pendiente' o None si no se puede saber / no aplica.
    BlackHole cuenta como micrófono: sin este permiso macOS entrega silencio."""
    if SYSTEM != "Darwin":
        return None
    try:
        import ctypes
        ctypes.cdll.LoadLibrary("/System/Library/Frameworks/AVFoundation.framework/AVFoundation")
        objc = ctypes.cdll.LoadLibrary("/usr/lib/libobjc.A.dylib")
        objc.objc_getClass.restype = ctypes.c_void_p
        objc.objc_getClass.argtypes = [ctypes.c_char_p]
        objc.sel_registerName.restype = ctypes.c_void_p
        objc.sel_registerName.argtypes = [ctypes.c_char_p]
        objc.objc_autoreleasePoolPush.restype = ctypes.c_void_p
        objc.objc_autoreleasePoolPop.argtypes = [ctypes.c_void_p]
        msg = ctypes.cast(objc.objc_msgSend, ctypes.c_void_p).value
        send_str = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                    ctypes.c_char_p)(msg)
        send_obj = ctypes.CFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p,
                                    ctypes.c_void_p)(msg)
        pool = objc.objc_autoreleasePoolPush()
        try:
            dev = objc.objc_getClass(b"AVCaptureDevice")
            nss = objc.objc_getClass(b"NSString")
            if not dev or not nss:
                return None
            soun = send_str(nss, objc.sel_registerName(b"stringWithUTF8String:"), b"soun")
            st = send_obj(dev, objc.sel_registerName(b"authorizationStatusForMediaType:"), soun)
        finally:
            objc.objc_autoreleasePoolPop(pool)
        return {0: "pendiente", 1: "denegado", 2: "denegado", 3: "ok"}.get(int(st))
    except Exception:
        return None


def open_mic_settings():
    if SYSTEM == "Darwin":
        subprocess.Popen(["open", "x-apple.systempreferences:com.apple.preference.security"
                                  "?Privacy_Microphone"])
    elif SYSTEM == "Windows":
        subprocess.Popen(["cmd", "/c", "start", "ms-settings:privacy-microphone"])


def open_audio_setup():
    if SYSTEM == "Darwin":
        subprocess.Popen(["open", "-a", "Audio MIDI Setup"])
    elif SYSTEM == "Windows":
        subprocess.Popen(["control", "mmsys.cpl,,1"])     # Sonido → Grabación

AUTO_HINTS = ["blackhole", "loopback", "cable output", "vb-audio", "stereo mix",
              "mezcla estéreo", "mezcla estereo", "soundflower", "voicemeeter"]
WAVE_RGB = ("#ff2b2b", "#2bff6a", "#2f7bff")           # graves, medios, agudos
WAVE_THEME_DEFAULT = ("#ff4f8b", "#a855f7", "#38e1ff")
SG_DEFAULT = [(.3, "#2e0a5c"), (.55, "#9d1fb0"), (.75, "#f0457a"),
              (.9, "#fb923c"), (1, "#fde68a")]
FPS = 60
_WIN = {}


def hann(n):
    w = _WIN.get(n)
    if w is None:
        w = _WIN[n] = np.hanning(n).astype(np.float32)
    return w


PERF = {   # fps del panel, y cada cuántos cuadros se actualizan espectro y stereo
    "maximo": (120, 1),        # todo a 120
    "equilibrado": (120, 2),   # onda y medidores a 120, espectro y stereo a 60
    "ahorro": (60, 1),         # todo a 60 (el mínimo)
}
MIN_FPS = 60                   # nunca se dibuja por debajo de esto
MODULES = [("wave", "Waveform"), ("spec", "Spectrum"),
           ("stereo", "Stereo"), ("lufs", "Loudness")]


# --------------------------------------------------------------------------
# utilidades
# --------------------------------------------------------------------------
def rgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.float32)


def hexmix(a, b, t):
    ra, rb = rgb(a), rgb(b)
    c = ra + (rb - ra) * max(0.0, min(1.0, t))
    return "#%02x%02x%02x" % tuple(int(round(v)) for v in c)


def lut_from_stops(stops, n=256):
    xs = np.array([s[0] for s in stops])
    cols = np.array([rgb(s[1]) for s in stops])
    t = np.linspace(0, 1, n)
    return np.stack([np.interp(t, xs, cols[:, i]) for i in range(3)], 1).astype(np.uint8)


def db(x):
    return 20 * math.log10(x) if x > 1e-9 else -math.inf


def rrect(cv, x1, y1, x2, y2, r, **kw):
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
           x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return cv.create_polygon(pts, smooth=True, splinesteps=24, **kw)


def ppm(arr):
    """Array (h, w, 3) uint8 -> bytes PPM que Tk sabe pintar directo."""
    h, w = arr.shape[:2]
    return b"P6 %d %d 255\n" % (w, h) + np.ascontiguousarray(arr).tobytes()


class Surface:
    """Lienzo hijo con su propia imagen (recorta solo lo que le toca)."""

    def __init__(self, parent_cv, x, y, w, h, bg, panel):
        self.w, self.h = max(1, int(w)), max(1, int(h))
        self.cv = tk.Canvas(parent_cv, width=self.w, height=self.h, highlightthickness=0,
                            bd=0, bg=bg)
        self.item = parent_cv.create_window(int(x), int(y), window=self.cv, anchor="nw")
        panel.win_items.append(self.item)
        self.photo = tk.PhotoImage(width=self.w, height=self.h)
        panel.bind_child(self.cv)

    def fill(self, color_rgb):
        a = np.empty((self.h, self.w, 3), np.uint8)
        a[:] = color_rgb
        self.photo.put(ppm(a), to=(0, 0))

    def put(self, arr, x=0, y=0):
        self.photo.put(ppm(arr), to=(int(x), int(y)))


class RingSurface(Surface):
    """Desplazamiento horizontal sin redibujar: se escriben solo las columnas nuevas
    y se mueven dos copias de la imagen."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.wp = 0
        self.a = self.cv.create_image(0, 0, image=self.photo, anchor="nw")
        self.b = self.cv.create_image(0, 0, image=self.photo, anchor="nw")
        self._place()

    def _place(self):
        self.cv.coords(self.a, self.w - self.wp, 0)
        self.cv.coords(self.b, -self.wp, 0)

    def push(self, cols):
        n = cols.shape[1]
        if n <= 0:
            return
        if n >= self.w:
            cols, n = cols[:, -self.w:], self.w
        first = min(n, self.w - self.wp)
        self.put(cols[:, :first], self.wp, 0)
        if first < n:
            self.put(cols[:, first:], 0, 0)
        self.wp = (self.wp + n) % self.w
        self._place()


LINK_NAME = "Gaux Link"
LINK_PORT = 47654


class LinkReceiver:
    """Recibe el audio que manda el plugin Gaux Link (UDP en 127.0.0.1). Si hay varias
    pistas con el plugin, usa la primera que empezó a enviar."""
    _inst = None

    @classmethod
    def get(cls):
        if cls._inst is None:
            cls._inst = cls()
        return cls._inst

    def __init__(self):
        self.sink = None              # función (datos, cuadros) que recibe el audio activo
        self.active = None            # instancia en uso
        self.audio_t = 0.0            # último audio de la instancia en uso
        self.sr = 48000
        self.info = {}                # instancia -> (DAW, pista, frecuencia, último hola)
        self.packets = 0
        self.ok = False
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 20)
            self.sock.bind(("127.0.0.1", LINK_PORT))
            self.ok = True
            threading.Thread(target=self._run, daemon=True).start()
        except OSError:
            self.sock = None

    def recent(self, secs=1.5):
        return self.active is not None and time.monotonic() - self.audio_t < secs

    def describe(self):
        if not self.recent(3.0):
            return None
        host, track, sr, _ = self.info.get(self.active, ("DAW", "", self.sr, 0))
        return host, track, sr

    def _run(self):
        while True:
            try:
                pkt, addr = self.sock.recvfrom(65536)
            except OSError:
                return
            if len(pkt) < 16:
                continue
            kind = pkt[:4]
            now = time.monotonic()
            if kind == b"GXLK" and len(pkt) >= 24:
                ch = pkt[5]
                inst, seq, sr, frames = struct.unpack_from("<IIII", pkt, 8)
                if not (1 <= ch <= 2) or frames <= 0 or len(pkt) < 24 + frames * ch * 4:
                    continue
                if self.active is None or (inst != self.active and now - self.audio_t > 1.5):
                    self.active = inst          # la primera pista que envía (o la que quedó)
                if inst != self.active:
                    continue
                self.audio_t = now
                self.sr = sr or 48000
                self.packets += 1
                sink = self.sink
                if sink is not None:
                    data = np.frombuffer(pkt, np.float32, frames * ch, 24).reshape(frames, ch)
                    try:
                        sink(data, frames, sr)
                    except Exception:
                        pass
            elif kind == b"GXHI":
                inst, sr = struct.unpack_from("<II", pkt, 8)
                txt = pkt[16:].decode("utf-8", "ignore").split("\n")
                host = txt[0] if txt and txt[0] else "DAW"
                track = txt[1] if len(txt) > 1 else ""
                self.info[inst] = (host, track, sr, now)
                act = self.active if self.recent(1.5) else inst
                try:
                    self.sock.sendto(b"GXAK" + struct.pack("<I", act or 0), addr)
                except OSError:
                    pass
                for k in [k for k, v in self.info.items() if now - v[3] > 10]:
                    self.info.pop(k, None)


class LinkStream:
    """Se comporta como un InputStream de sounddevice, pero el audio viene de Gaux Link."""

    def __init__(self, engine, link):
        self.engine, self.link = engine, link
        link.sink = self._feed

    def _feed(self, data, frames, sr):
        e = self.engine
        if sr != e.sr:
            e.sr_changed = True          # el DAW cambió la frecuencia: se reabre
            return
        e._cb(data, frames, None, None)

    @property
    def active(self):
        return self.link.recent(2.5)

    def stop(self):
        if self.link.sink == self._feed:
            self.link.sink = None

    def close(self):
        self.stop()


def list_inputs():
    out = []
    if sd is None:
        return out
    try:
        for i, d in enumerate(sd.query_devices()):
            if d["max_input_channels"] > 0:
                out.append((i, d["name"]))
    except Exception:
        pass
    return out


def resolve_device(pref):
    devs = list_inputs()
    if pref and pref != "auto":
        for i, n in devs:
            if n == pref:
                return i, n
    for i, n in devs:
        if any(h in n.lower() for h in AUTO_HINTS):
            return i, n
    return None, None


# --------------------------------------------------------------------------
# captura de audio
# --------------------------------------------------------------------------
class AudioEngine:
    SIZE = 1 << 17
    BLOCK = 1024             # ~21 ms: la mitad de despertares que 512, sin retraso visible

    def __init__(self):
        self.buf = np.zeros((self.SIZE, 2), np.float32)
        self.w = 0
        self.lock = threading.Lock()
        self.stream = None
        self.sr = 48000
        self.ch = 2
        self.error = None
        self.label = ""
        self.max_block = self.BLOCK
        self.loud_t = 0.0
        self.cb_t = 0.0          # último bloque recibido (la entrada está viva)
        self.sig_t = 0.0         # último bloque con algo distinto de silencio digital
        self.t_start = 0.0
        self.cb_n = 0
        self.peak = 0.0          # pico del último medio segundo (para el diagnóstico)
        self.mode = None         # "link" (plugin Gaux Link) o "device" (BlackHole / VB-Cable)
        self.sr_changed = False

    def start(self, pref, refresh=False):
        self.stop()
        if refresh and sd is not None:
            # PortAudio guarda la lista de dispositivos al iniciar: se recarga para ver
            # entradas nuevas (BlackHole reinstalado, interfaz conectada, macOS actualizado).
            try:
                sd._terminate()
                sd._initialize()
            except Exception:
                pass
        self.t_start = time.monotonic()
        self.sig_t = 0.0
        self.cb_t = 0.0
        self.mode = None
        self.sr_changed = False
        link = LinkReceiver.get()
        if pref == LINK_NAME or (pref in (None, "auto") and link.recent()):
            # el plugin Gaux Link manda el audio directo: sin BlackHole ni permisos
            self.sr, self.ch = int(link.sr), 2
            self.stream = LinkStream(self, link)
            self.mode, self.error, self.label = "link", None, LINK_NAME
            return
        if sd is None:
            self.error = "sin_dispositivo"
            return
        idx, name = resolve_device(pref)
        if idx is None:
            self.error = "sin_dispositivo"
            return
        try:
            self.mode = "device"
            info = sd.query_devices(idx)
            self.sr = int(info["default_samplerate"]) or 48000
            self.ch = 2 if info["max_input_channels"] >= 2 else 1
            self.stream = sd.InputStream(device=idx, channels=self.ch, samplerate=self.sr,
                                         blocksize=self.BLOCK, dtype="float32",
                                         latency="low", callback=self._cb)
            self.stream.start()
            self.error, self.label = None, name
        except Exception as e:      # permiso de micrófono, dispositivo ocupado…
            self.stream, self.error = None, str(e)

    def _cb(self, indata, frames, t, status):
        now = time.monotonic()
        self.cb_t = now
        self.cb_n += 1
        self.max_block = max(self.max_block, frames)
        m = float(np.abs(indata).max())
        if m > 0.0:
            self.sig_t = now
        if m > 1e-4:
            self.loud_t = now                         # último instante con sonido
        self.peak = max(self.peak * 0.97, m)
        data = indata if self.ch == 2 else np.repeat(indata[:, :1], 2, axis=1)
        n, N = len(data), self.SIZE
        with self.lock:
            p = self.w % N
            if p + n <= N:
                self.buf[p:p + n] = data
            else:
                k = N - p
                self.buf[p:] = data[:k]
                self.buf[:n - k] = data[k:]
            self.w += n

    def read(self, start, end):
        """Muestras absolutas [start, end). Devuelve (array, start_real)."""
        with self.lock:
            w = self.w
            end = min(end, w)
            start = max(start, w - self.SIZE + 1024, 0)
            n = end - start
            if n <= 0:
                return np.zeros((0, 2), np.float32), end
            p = start % self.SIZE
            if p + n <= self.SIZE:
                out = self.buf[p:p + n].copy()
            else:
                k = self.SIZE - p
                out = np.concatenate([self.buf[p:], self.buf[:n - k]])
        return out, start

    def last(self, n):
        return self.read(self.w - n, self.w)[0]

    def stop(self):
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
        self.stream = None


# --------------------------------------------------------------------------
# loudness ITU-R BS.1770 / EBU R128
# --------------------------------------------------------------------------
def k_weight_power(freqs, fs):
    """|H(f)|^2 del filtro K (shelf + pasa-altos) para la frecuencia de muestreo."""
    def biquad_resp(b, a, w):
        z1, z2 = np.exp(-1j * w), np.exp(-2j * w)
        return (b[0] + b[1] * z1 + b[2] * z2) / (1 + a[1] * z1 + a[2] * z2)

    f0, G, Q = 1681.974450955533, 3.999843853973347, 0.7071752369554196
    K = math.tan(math.pi * f0 / fs)
    Vh = 10 ** (G / 20)
    Vb = Vh ** 0.4996667741545416
    a0 = 1 + K / Q + K * K
    b1 = [(Vh + Vb * K / Q + K * K) / a0, 2 * (K * K - Vh) / a0,
          (Vh - Vb * K / Q + K * K) / a0]
    a1 = [1, 2 * (K * K - 1) / a0, (1 - K / Q + K * K) / a0]
    f0, Q = 38.13547087602444, 0.5003270373238773
    K = math.tan(math.pi * f0 / fs)
    a0 = 1 + K / Q + K * K
    b2 = [1, -2, 1]
    a2 = [1, 2 * (K * K - 1) / a0, (1 - K / Q + K * K) / a0]
    w = 2 * np.pi * freqs / fs
    return np.abs(biquad_resp(b1, a1, w) * biquad_resp(b2, a2, w)) ** 2


def lufs(e):
    return -0.691 + 10 * math.log10(e) if e > 1e-12 else -math.inf


class Loudness:
    def __init__(self, sr):
        self.sr = sr
        self.n = sr // 10                       # bloques de 100 ms
        self.hk2 = k_weight_power(np.fft.rfftfreq(self.n, 1 / sr), sr)
        self.reset()

    def reset(self):
        self.sub = deque(maxlen=30)
        self.blocks = []
        self.tp_max = -math.inf
        self.tail = np.zeros((32, 2), np.float32)
        self.hist = deque(maxlen=120)           # short-term, 1 por segundo
        self._integ, self._integ_n = -math.inf, -1

    def push(self, chunk):
        n = len(chunk)
        X = np.fft.rfft(chunk, axis=0)
        P = (np.abs(X) ** 2) * self.hk2[:, None]
        P[1:-1 if n % 2 == 0 else None] *= 2
        e = float(P.sum() / (n * n))            # suma de canales (L+R, peso 1)
        self.sub.append(e)
        if len(self.sub) >= 4:
            self.blocks.append(sum(list(self.sub)[-4:]) / 4)
        # true peak: sobremuestreo x4 por FFT con solape para evitar bordes
        if float(np.abs(chunk).max()) < 1e-3:          # casi silencio: no puede subir el TP
            self.tail = chunk[-32:].copy()
            return
        seg = np.concatenate([self.tail, chunk])
        self.tail = chunk[-32:].copy()
        S = np.fft.rfft(seg, axis=0)
        m = len(seg)
        up = np.zeros((2 * m + 1, 2), complex)
        up[:len(S)] = S
        y = np.fft.irfft(up, n=4 * m, axis=0) * 4
        tp = max(float(np.abs(y[128:-128]).max()), float(np.abs(chunk).max()))
        self.tp_max = max(self.tp_max, db(tp))

    def momentary(self):
        return lufs(sum(list(self.sub)[-4:]) / 4) if len(self.sub) >= 4 else -math.inf

    def short_term(self):
        return lufs(sum(self.sub) / len(self.sub)) if self.sub else -math.inf

    def integrated(self):
        if len(self.blocks) == self._integ_n:
            return self._integ
        b = np.array(self.blocks)
        b = b[b > 10 ** ((-70 + 0.691) / 10)]                  # puerta absoluta
        if len(b):
            rel = lufs(b.mean()) - 10                           # puerta relativa
            b = b[b > 10 ** ((rel + 0.691) / 10)]
        self._integ = lufs(b.mean()) if len(b) else -math.inf
        self._integ_n = len(self.blocks)
        return self._integ


# --------------------------------------------------------------------------
# panel
# --------------------------------------------------------------------------
class AnalyzerPanel:
    PAD = 8
    GAP = 6

    def __init__(self, app):
        self.app = app
        self.engine = AudioEngine()
        self.loud = None
        self.visible = False
        self.running = False
        self._drag = None
        self._resize = None
        self._last_build = 0.0
        self.frame_n = 0
        self.dt = 1 / 60
        self._hist_t = 0.0
        self.read_pos = self.lufs_pos = 0
        self.pending = np.zeros(0, np.float32)

        self.win = tk.Toplevel(app.root)
        self.win.withdraw()
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        if app.clear:
            try:
                if app.clear == "systemTransparent":
                    self.win.attributes("-transparent", True)
                else:
                    self.win.attributes("-transparentcolor", app.clear)
            except tk.TclError:
                pass
        self.cv = tk.Canvas(self.win, highlightthickness=0, bd=0)
        self.cv.pack()
        cv = self.cv
        cv.bind("<ButtonPress-1>", self.on_press)
        cv.bind("<B1-Motion>", self.on_drag)
        cv.bind("<ButtonRelease-1>", self.on_release)
        cv.bind("<Motion>", self.on_motion)
        cv.bind("<Double-Button-1>", lambda e: self.reset_loudness())
        for seq in ("<Button-2>", "<Button-3>", "<Control-Button-1>"):
            cv.bind(seq, self.show_menu)
        self.build()

    # ---- configuración -----------------------------------------------------
    @property
    def alert(self):
        return self.T.get("alerta", "#f43f5e")

    @property
    def conf(self):
        return self.app.conf["analizador"]

    def start_audio(self, refresh=False):
        e = self.engine
        e.start(self.conf.get("dispositivo", "auto"), refresh=refresh)
        self._restart_t = time.monotonic()
        if e.stream is None:
            self.loud = None
        elif self.loud is None or self.loud.sr != e.sr:
            self.loud = Loudness(e.sr)
        self.read_pos = self.lufs_pos = e.w
        self.wave_pos = None
        self.pending = np.zeros(0, np.float32)
        self.perm = None
        self._update_msg()
        if not self.running:
            self.running = True
            self.win.after(100, self.loud_loop)
            self.win.after(16, self.frame_loop)

    def reconnect(self):
        """Reabre la entrada de audio y recarga la lista de dispositivos."""
        self.start_audio(refresh=True)

    def stop_audio(self):
        self.engine.stop()
        self.running = False

    def _watchdog(self, now):
        """La entrada se cayó (macOS dormido, BlackHole reiniciado, cambio de dispositivo):
        se reconecta sola. Sin dispositivo: se reintenta cada pocos segundos."""
        e = self.engine
        since = now - getattr(self, "_restart_t", 0.0)
        fails = getattr(self, "_fails", 0)
        link = LinkReceiver.get()
        pref = self.conf.get("dispositivo", "auto")
        # Gaux Link apareció (o cambió la frecuencia del DAW): se usa al instante
        if since > 1.0 and (e.sr_changed
                            or (link.recent() and e.mode != "link"
                                and pref in ("auto", LINK_NAME))):
            self._fails = 0
            self.start_audio()
            return
        wait = min(30.0, 4.0 * (1.5 ** fails))      # reintentos cada vez más espaciados
        if e.stream is not None and now - e.cb_t < 1.0:
            self._fails = 0
        if e.stream is not None:
            stalled = now - max(e.cb_t, e.t_start) > 2.5
            dead = False
            try:
                dead = not e.stream.active
            except Exception:
                dead = True
            if (stalled or dead) and since > wait:
                self._fails = fails + 1
                self.start_audio(refresh=True)
                return
        elif self.visible and since > wait:
            self._fails = fails + 1
            self.start_audio(refresh=True)
            return
        # sin señal desde que se abrió: revisar el permiso de micrófono (cada 5 s)
        if e.mode == "device" and e.sig_t == 0.0 and now - e.t_start > 2.5:
            if now - getattr(self, "_perm_t", 0.0) > 5:
                self._perm_t = now
                p = mic_permission()
                if p != self.perm:
                    self.perm = p
                    self._update_msg()
        elif self.perm == "denegado" and e.sig_t:
            self.perm = "ok"
            self._update_msg()
        self._update_hint(now)

    def set_visible(self, show):
        if show == self.visible:
            return
        self.visible = show
        if show:
            self.win.deiconify()
            if not getattr(self.app, "_stacked", False):
                self.win.attributes("-topmost", True)
            if hasattr(self.app, "restack_soon"):
                self.app.restack_soon(60)      # bajo los plugins del DAW, sobre su ventana
        else:
            self._drag = self._resize = None
            self.win.withdraw()

    def destroy(self):
        self.stop_audio()
        self.win.destroy()

    def reset_loudness(self):
        if self.loud:
            self.loud.reset()

    # ---- construcción ----------------------------------------------------------
    def build(self):
        T, cv, c = self.app.T, self.cv, self.conf
        cv.delete("all")
        self._icache, self._ccache = {}, {}
        self.spec_yv = None
        self.st_clean = False
        self.T = T
        W, H = int(c.get("w", 900)), int(c.get("h", 172))
        self.W, self.H = W, H
        base = self.app.clear or T["bg"]
        cv.config(width=W, height=H, bg=base)
        self.win.config(bg=base)
        x = c.get("x")
        y = c.get("y")
        if x is None or y is None:
            x, y = 40, self.win.winfo_screenheight() - H - 90
        if not self.docked() and hasattr(self.app, "clamp_rect"):
            # tras cambiar la resolución, una posición guardada puede quedar fuera de pantalla
            x, y = self.app.clamp_rect(int(x), int(y), W, H)
        self.win.geometry(f"{W}x{H}+{int(x)}+{int(y)}")
        self.win.after(30, self.app.raise_timer)

        self.brand = bool(T.get("marca"))
        if getattr(self.app, "angular", self.brand):   # forma angular (Gaux o Personal)
            k = 14
            cv.create_polygon(1, 1, W - 1 - k, 1, W - 1, 1 + k, W - 1, H - 1, 1 + k, H - 1,
                              1, H - 1 - k, fill=T["bg"], outline=T["borde"], width=1.2)
        else:
            rrect(cv, 1, 1, W - 1, H - 1, 14, fill=T["bg"], outline=T["borde"], width=1.2)

        P, G = self.PAD, self.GAP
        cw, ch = W - 2 * P, H - 2 * P
        self.cw, self.ch = cw, ch
        self.bgc = rgb(hexmix(T["bg"], T["bg2"], 0.35)).astype(np.uint8)
        self.bgc_hex = "#%02x%02x%02x" % tuple(int(v) for v in self.bgc)
        for w_ in getattr(self, "children", []):
            w_.destroy()
        self.children = []
        self.win_items = []
        self.sans = self.app.f_sans
        self.clockf = self.app.f_clock_family
        self.dim = T["dim"]

        mods = [k for k, _ in MODULES if c["modulos"].get(k, True)]
        fixed = {"stereo": int(min(ch, max(118, cw * 0.15))), "lufs": 214}
        flex = [k for k in mods if k not in fixed]
        free = cw - sum(fixed[k] for k in mods if k in fixed) - G * (len(mods) - 1)
        share = {"wave": 0.42, "spec": 0.58}
        tot = sum(share[k] for k in flex) or 1
        self.rects = {}
        xx = 0
        for k in mods:
            w = fixed[k] if k in fixed else max(80, int(free * share[k] / tot))
            w = min(w, cw - xx)
            self.rects[k] = (xx, 0, w, ch)
            xx += w + G
        for k, (x0, y0, w, h) in self.rects.items():
            cv.create_rectangle(P + x0, P + y0, P + x0 + w, P + y0 + h,
                                fill=self.bgc_hex, outline="")

        self.hdr = 18 if ch >= 100 else 4          # paneles bajos: sin títulos de módulo
        lab = (self.app.f_title[0], 11, "bold") if self.brand else (self.sans, 8, "bold")
        for k, name in MODULES:
            if k in self.rects and self.hdr > 10:
                x0 = self.rects[k][0]
                cv.create_text(P + x0 + 7, P + 9, text=name.upper(), anchor="w",
                               font=lab, fill=hexmix(T["dim"], T["bg"], .25))
        if "wave" in self.rects:
            self._build_wave()
        if "spec" in self.rects:
            self._build_spec()
        if "stereo" in self.rects:
            self._build_stereo()
        if "lufs" in self.rects:
            self._build_lufs()

        self.msg_bg = rrect(cv, 0, 0, 1, 1, 10, fill=T["bg"], outline=T["borde"],
                            state="hidden")
        self.msg_it = cv.create_text(W / 2, H / 2, text="", justify="center",
                                     width=W - 80, font=(self.sans, 11), fill=T["texto"])
        self.grip = None if self.docked() else cv.create_line(W - 6, H - 14, W - 14, H - 6, W - 6, H - 6, W - 6, H - 14,
                                   fill=hexmix(T["dim"], T["bg"], .5), width=1)
        # aviso "esperando audio" dentro de la onda (o del espectro si no hay onda)
        self.hint_it = None
        self.hint_on = None
        host = self.wave if "wave" in self.rects else (self.sgram if "spec" in self.rects
                                                       and self.sgram else None)
        if host is not None:
            self.hint_cv = host.cv
            name = self.engine.label or "la entrada"
            big = host.h >= 60 and host.w >= 300
            txt = (f"Esperando audio de {name}…\nDale play. Si Live suena y esto sigue quieto: "
                   "ctrl+clic → Diagnóstico de audio" if big else
                   f"Sin audio de {name} · ctrl+clic → Diagnóstico")
            self.hint_it = host.cv.create_text(host.w / 2, host.h / 2, text=txt,
                                               justify="center", width=host.w - 16,
                                               font=(self.sans, 10 if big else 8),
                                               fill=hexmix(T["dim"], T["texto"], .25),
                                               state="hidden")
            self.hint_on = False
            self._update_hint(time.monotonic())
        self._update_msg()

    def surface(self, cls, k, top, height, left=0, width=None):
        x0, y0, w, h = self.rects[k]
        width = w if width is None else width
        srf = cls(self.cv, self.PAD + x0 + left, self.PAD + y0 + top, width, height,
                  self.bgc_hex, self)
        self.children.append(srf.cv)
        return srf

    # -- waveform: búfer circular, 120 px/s constantes
    def _build_wave(self):
        x0, y0, w, h = self.rects["wave"]
        H = h - self.hdr
        self.wave = self.surface(RingSurface, "wave", self.hdr, H)
        base = np.empty((H, w, 3), np.uint8)
        base[:] = self.bgc
        self.wave_mid = rgb(hexmix(self.T["bg"], self.T["dim"], .25)).astype(np.uint8)
        base[H // 2] = self.wave_mid
        self.wave.put(base)
        self.wave_rows = np.abs(np.arange(H)[:, None] + 0.5 - H / 2)
        self.wave_H = H
        self.wave_acc = 0.0
        self.wave_pos = None

    # -- spectrum (vector) + spectrogram (búfer circular)
    def _build_spec(self):
        T, cv, P = self.T, self.cv, self.PAD
        x0, y0, w, h = self.rects["spec"]
        top = self.hdr
        # franjas bajas: todo el alto para la curva (el espectrograma ahí no se lee)
        self.sg_on = (h - top) >= 104
        sh = int((h - top) * 0.55) if self.sg_on else h - top
        gh = h - top - sh - 4
        X, Y = P + x0, P + y0 + top
        self.spec_geom = (X, Y, w, sh)
        npts = max(64, min(int(w), 520))       # ~1 punto cada 2 px: nítido y liviano
        self.fpts = np.logspace(math.log10(20), math.log10(20000), npts)
        self.xpts = X + np.linspace(0, w - 1, npts)
        self.spec_s = np.full(npts, -120.0)
        self.db_lo, self.db_hi = -84.0, 0.0
        self.sm_cache = None
        l20, l20k = math.log10(20), math.log10(20000)

        def fx(f):
            return X + (math.log10(f) - l20) / (l20k - l20) * (w - 1)

        # rejilla tipo SPAN: líneas en cada 10/100/1k, más marcadas en 100, 1k y 10k
        minor = hexmix(self.bgc_hex, T["dim"], .09)
        major = hexmix(self.bgc_hex, T["dim"], .2)
        for dec in (10, 100, 1000, 10000):
            for k in range(1, 10):
                f = dec * k
                if 20 <= f <= 20000:
                    cv.create_line(fx(f), Y, fx(f), Y + sh,
                                   fill=major if k == 1 else minor)
        cv.create_line(fx(20000), Y, fx(20000), Y + sh, fill=minor)
        # eje Y: dB a la derecha, cada 6 dB si hay espacio
        step = next((st for st in (6, 12, 24) if sh * st / (self.db_hi - self.db_lo) >= 15), 24)
        fs_ = 8 if w >= 600 and sh >= 160 else 7
        lblc = hexmix(T["dim"], T["bg"], .2)
        for d in range(-step, int(self.db_lo), -step):
            yi = Y + (self.db_hi - d) / (self.db_hi - self.db_lo) * (sh - 1)
            cv.create_line(X, yi, X + w, yi, fill=major if d % 12 == 0 else minor)
            if yi < Y + sh - 14:
                cv.create_text(X + w - 4, yi, text=str(d), anchor="e", font=(self.sans, fs_),
                               fill=lblc, tags=("freqlbl",))
        # eje X: etiquetas por prioridad, sin encimarse
        fnt = tkfont.Font(family=self.sans, size=fs_)
        prio = [(100, "100"), (1000, "1K"), (10000, "10K"), (20, "20"), (200, "200"),
                (2000, "2K"), (20000, "20K"), (40, "40"), (400, "400"), (4000, "4K"),
                (30, "30"), (60, "60"), (80, "80"), (300, "300"), (600, "600"),
                (800, "800"), (3000, "3K"), (6000, "6K"), (8000, "8K"), (50, "50"),
                (500, "500"), (5000, "5K")]
        taken = []
        ylab = Y + sh - 7
        for f, t in prio:
            tw = fnt.measure(t)
            xi = fx(f)
            if f == 20:
                x1 = X + 3
            elif f == 20000:
                x1 = X + w - 3 - tw
            else:
                x1 = xi - tw / 2
            x2 = x1 + tw
            gap = 6 if sh >= 70 else 12                # franjas bajas: menos etiquetas
            if any(x1 < b + gap and x2 > a - gap for a, b in taken):
                continue
            taken.append((x1, x2))
            cv.create_text(x1, ylab, text=t, anchor="w", font=(self.sans, fs_), fill=lblc,
                           tags=("freqlbl",))
        self.spec_poly = cv.create_polygon(X, Y + sh, X + w, Y + sh, X, Y + sh,
                                           fill=hexmix(T["acento"], self.bgc_hex, .55),
                                           outline="")
        self.spec_line = cv.create_line(X, Y + sh, X + w, Y + sh, width=1.5,
                                        fill=hexmix(T["acento2"], "#ffffff", .35))
        cv.tag_raise("freqlbl")
        self.sg_acc = 0.0
        if not self.sg_on:
            self.sgram = None
            return
        self.sgram = self.surface(RingSurface, "spec", top + sh + 4, gh)
        self.frows = np.logspace(math.log10(20000), math.log10(20), gh)
        self.sg_lut = lut_from_stops([(0, hexmix(T["bg"], T["bg2"], .35))]
                                     + T.get("espectrograma", SG_DEFAULT))
        self.sgram.fill(self.sg_lut[0])
        self.sg_acc = 0.0

    # -- stereometer
    def _build_stereo(self):
        T = self.T
        x0, y0, w, h = self.rects["stereo"]
        foot = 28 if h >= 100 else 14              # barra de correlación (y sus números)
        s = max(24, min(w - 8, h - self.hdr - foot))
        self.st_s = s
        ox, oy = (w - s) // 2, self.hdr + (h - self.hdr - foot - s) // 2
        self.stereo = self.surface(Surface, "stereo", oy, s, left=ox, width=s)
        self.stereo.cv.create_image(0, 0, image=self.stereo.photo, anchor="nw")
        self.st_acc = np.zeros((s, s), np.float32)
        self.st_lut = lut_from_stops([(0, hexmix(T["bg"], T["bg2"], .35)),
                                      (.35, T["acento"]), (.75, T["acento2"]),
                                      (1, "#ffffff")])
        g = np.empty((s, s, 3), np.uint8)
        g[:] = self.bgc
        gc = rgb(hexmix(hexmix(T["bg"], T["bg2"], .35), T["dim"], .16)).astype(np.uint8)
        idx = np.arange(s)
        g[idx, idx] = gc
        g[idx, s - 1 - idx] = gc
        g[:, s // 2] = gc
        self.st_grid = g
        self.stereo.put(g)
        cx = self.PAD + x0 + w / 2
        by = self.PAD + y0 + h - (20 if foot > 14 else 7)
        L = self.PAD + x0 + 12
        R = self.PAD + x0 + w - 12
        self.corr_geom = (L, R, by)
        self.cv.create_line(L, by, R, by, fill=T["pista"], width=4, capstyle="round")
        self.cv.create_line(cx, by - 4, cx, by + 4, fill=hexmix(T["dim"], T["bg"], .4))
        self.corr_dot = self.cv.create_oval(cx - 4, by - 4, cx + 4, by + 4,
                                            fill=T["acento2"], outline="")
        for t, xx, a in ((("-1", L, "w"), ("+1", R, "e")) if foot > 14 else ()):
            self.cv.create_text(xx, by + 11, text=t, anchor=a, font=(self.sans, 7),
                                fill=hexmix(T["dim"], T["bg"], .3))
        self.corr_txt = self.cv.create_text(cx, by + 11, text="", font=(self.sans, 7),
                                            state="normal" if foot > 14 else "hidden",
                                            fill=T["dim"])
        self.corr_s = 1.0

    # -- loudness
    def _build_lufs(self):
        T, cv, P = self.T, self.cv, self.PAD
        x0, y0, w, h = self.rects["lufs"]
        X, Y = P + x0, P + y0
        self.lu = {}
        # reparto según el alto disponible: número grande, leyenda y filas M / I / TP
        top, bottom = Y + self.hdr, Y + h - 4
        avail = bottom - top

        def ls(font):
            return tkfont.Font(family=font[0], size=font[1],
                               weight=font[2] if len(font) > 2 else "normal").metrics("linespace")

        choice = None
        for rsz in (11, 10, 9, 8):                # menos de 8 pt ya no se lee: pasa a una fila
            for bsz in (40, 36, 32, 28, 26, 24, 22, 20, 18, 16, 14):
                if bsz > 26 and avail < 200:          # el tamaño grande solo en paneles altos
                    continue
                for cap in (True, False):
                    need = ls((self.clockf, bsz, "bold")) + (ls((self.sans, 8)) if cap else 0) \
                        + 3 * (ls((self.sans, rsz)) + 1)
                    if need <= avail:
                        choice = (rsz, bsz, cap, need)
                        break
                if choice:
                    break
            if choice:
                break
        self.lu_inline = choice is None
        if self.lu_inline:                       # panel muy bajo: número grande + una fila
            return self._build_lufs_inline(X, Y, w, h, top, bottom, ls)
        rsz, bsz, cap, need = choice
        big = (self.clockf, bsz, "bold")
        rowf, rowfb = (self.sans, rsz), (self.sans, rsz, "bold")
        lb, lc, lr = ls(big), ls((self.sans, 8)), ls(rowf) + 1
        if rsz > 9 and avail - need < 40:             # filas grandes solo si sobra espacio
            pass
        hist_room = (avail - need) >= 30 and h >= 140
        gap = 0 if hist_room else min(5, (avail - need) / 5)

        y = top + gap
        self.lu["st"] = cv.create_text(X + 10, y + lb / 2, anchor="w", text="—", font=big,
                                       fill=T["texto"])
        y += lb
        if cap:
            cv.create_text(X + 11, y + lc / 2 - 1, anchor="w", text="LUFS short-term",
                           font=(self.sans, 8), fill=T["dim"])
            y += lc
        else:                                      # sin leyenda: unidad junto al número
            self.lu["st_unit"] = cv.create_text(X + 10, y - 3, anchor="sw", text="",
                                                font=(self.sans, 7), fill=T["dim"])
        y += gap
        name_w = tkfont.Font(family=rowfb[0], size=rowfb[1], weight="bold").measure("TP") + 8
        for k, name in (("m", "M"), ("i", "I"), ("tp", "TP")):
            cy = y + lr / 2
            cv.create_text(X + 10, cy, anchor="w", text=name, font=rowfb, fill=T["dim"])
            self.lu[k] = cv.create_text(X + 10 + name_w, cy, anchor="w", text="—", font=rowf,
                                        fill=T["texto"])
            y += lr + gap
        rows_end = y
        # medidores verticales: L, R (pico dBFS) y M (LUFS)
        self.meters = {}
        top, bot = Y + max(4, self.hdr - 2), Y + h - 14
        self.m_geom = (top, bot)
        for i, (k, name) in enumerate((("L", "L"), ("R", "R"), ("M", "M"))):
            mx = X + w - 52 + i * 16
            cv.create_rectangle(mx, top, mx + 8, bot, fill=T["pista"], outline="")
            fill = cv.create_rectangle(mx, bot, mx + 8, bot, fill=T["acento"], outline="")
            hold = cv.create_line(mx, bot, mx + 8, bot, fill="#ffffff")
            cv.create_text(mx + 4, bot + 7, text=name, font=(self.sans, 7), fill=T["dim"])
            self.meters[k] = dict(x=mx, fill=fill, hold=hold, v=-90.0, h=-90.0, ht=0.0)
        # historial short-term (60 s)
        self.hist_geom = None
        if hist_room:
            hx0, hx1 = X + 10, X + w - 64
            hy0, hy1 = rows_end + 10, Y + h - 8
            if hy1 - hy0 >= 20:
                self.hist_geom = (hx0, hx1, hy0, hy1)
                ref = hy0 + (hy1 - hy0) * (14 / 40)
                cv.create_line(hx0, ref, hx1, ref, fill=hexmix(T["dim"], T["bg"], .55),
                               dash=(2, 3))
                cv.create_text(hx1, ref - 5, text="-14", anchor="e", font=(self.sans, 7),
                               fill=hexmix(T["dim"], T["bg"], .35))
                self.hist_line = cv.create_line(hx0, hy1, hx0, hy1, fill=T["acento2"],
                                                width=1.5, smooth=True)

    def _build_lufs_inline(self, X, Y, w, h, top, bottom, ls):
        T, cv = self.T, self.cv
        avail = bottom - top
        rowf = (self.sans, 8)
        bsz = next((b for b in (24, 22, 20, 18, 16, 14, 12)
                    if ls((self.clockf, b, "bold")) + ls(rowf) <= avail), 12)
        big = (self.clockf, bsz, "bold")
        lb = ls(big)
        y = top + max(0, (avail - lb - ls(rowf)) / 2)
        self.lu["st"] = cv.create_text(X + 8, y + lb / 2, anchor="w", text="—", font=big,
                                       fill=T["texto"])
        self.lu["st_unit"] = cv.create_text(X + 8, y + lb - 2, anchor="sw", text="",
                                            font=(self.sans, 7), fill=T["dim"])
        ry = y + lb + ls(rowf) / 2
        x = X + 8
        fb = (self.sans, 8, "bold")
        for k, name in (("m", "M"), ("i", "I"), ("tp", "TP")):
            t = cv.create_text(x, ry, anchor="w", text=name, font=fb, fill=T["dim"])
            x = cv.bbox(t)[2] + 3
            self.lu[k] = cv.create_text(x, ry, anchor="w", text="—", font=rowf, fill=T["texto"])
            x += 34
        self.hist_geom = None
        self._build_meters(X, Y, w, h)

    def _build_meters(self, X, Y, w, h):
        T, cv = self.T, self.cv
        self.meters = {}
        top, bot = Y + max(4, self.hdr - 2), Y + h - 14
        self.m_geom = (top, bot)
        for i, (k, name) in enumerate((("L", "L"), ("R", "R"), ("M", "M"))):
            mx = X + w - 52 + i * 16
            cv.create_rectangle(mx, top, mx + 8, bot, fill=T["pista"], outline="")
            fill = cv.create_rectangle(mx, bot, mx + 8, bot, fill=T["acento"], outline="")
            hold = cv.create_line(mx, bot, mx + 8, bot, fill="#ffffff")
            cv.create_text(mx + 4, bot + 7, text=name, font=(self.sans, 7), fill=T["dim"])
            self.meters[k] = dict(x=mx, fill=fill, hold=hold, v=-90.0, h=-90.0, ht=0.0)

    # ---- mensajes ----------------------------------------------------------------
    def _update_hint(self, now):
        """Aviso discreto dentro de la onda mientras no ha llegado nada de audio."""
        it = getattr(self, "hint_it", None)
        if it is None:
            return
        e = self.engine
        show = (e.stream is not None and e.sig_t == 0.0 and now - e.t_start > 3
                and self.perm != "denegado")
        if show == getattr(self, "hint_on", False):
            return
        self.hint_on = show
        try:
            self.hint_cv.itemconfig(it, state="normal" if show else "hidden")
        except tk.TclError:
            pass

    def _update_msg(self):
        e = self.engine
        if e.stream is not None and self.perm == "denegado":
            app = HOST_APP
            txt = (f"macOS está bloqueando el audio (permiso de micrófono).\n"
                   f"Ajustes del Sistema → Privacidad y seguridad → Micrófono → activa {app}.\n"
                   "Luego ctrl+clic aquí → Reconectar audio.")
        elif e.stream is not None:
            txt = ""
        elif e.error == "sin_dispositivo":
            txt = ("Sin audio todavía.\nPon el plugin Gaux Link al final del Master de tu DAW "
                   "(recomendado), o instala BlackHole (Mac) / VB-Cable (Windows).")
        elif e.error:
            txt = f"No se pudo abrir la entrada de audio (se reintenta solo):\n{e.error[:120]}"
        else:
            txt = ""
        if not hasattr(self, "msg_it"):
            return
        self.cv.itemconfig(self.msg_it, text=txt)
        for it in self.win_items:            # las superficies tapan el aviso: ocultarlas
            self.cv.itemconfig(it, state="hidden" if txt else "normal")
        if txt:
            x1, y1, x2, y2 = self.cv.bbox(self.msg_it)
            self.cv.delete(self.msg_bg)
            self.msg_bg = rrect(self.cv, x1 - 16, y1 - 10, x2 + 16, y2 + 10, 10,
                                fill=self.T["bg"], outline=self.T["borde"])
            self.cv.tag_raise(self.msg_it)
        else:
            self.cv.itemconfig(self.msg_bg, state="hidden")

    # ---- bucles ------------------------------------------------------------------
    def loud_loop(self):
        if not self.running:
            return
        e, L = self.engine, self.loud
        now = time.monotonic()
        try:
            self._watchdog(now)
        except Exception:
            pass
        e, L = self.engine, self.loud
        if e.stream is not None and L is not None:
            if e.w - self.lufs_pos > e.sr * 2:      # nos quedamos atrás: saltar
                self.lufs_pos = e.w - L.n
            while e.w - self.lufs_pos >= L.n:
                chunk, s = e.read(self.lufs_pos, self.lufs_pos + L.n)
                self.lufs_pos = s + len(chunk)
                if len(chunk) == L.n:
                    L.push(chunk)
            if now - self._hist_t >= 1.0:
                self._hist_t = now
                L.hist.append(L.short_term())
        self.win.after(100 if self.visible else 400, self.loud_loop)

    def settled(self):
        """Todo quieto: silencio y medidores, espectro y stereo ya en reposo."""
        if time.monotonic() - self.engine.loud_t < 1.5:
            return False
        if "spec" in self.rects and not getattr(self, "spec_rest", False):
            return False
        if "stereo" in self.rects and not getattr(self, "st_clean", False):
            return False
        for m in getattr(self, "meters", {}).values():
            if m["v"] > -89 or m["h"] > -89:
                return False
        return True

    IDLE_FPS = 15            # en silencio total nada se mueve: no hace falta más

    def frame_loop(self):
        if not self.running:
            return
        now = time.perf_counter()
        if not self.visible or self.engine.stream is None:
            # oculto (otra app al frente) o sin entrada: no se dibuja nada
            self._last_frame = self._next = now
            self.win.after(200, self.frame_loop)
            return
        self.dt = min(0.1, now - getattr(self, "_last_frame", now - 1 / FPS)) or 1 / FPS
        self._last_frame = now
        try:
            self.render()
        except Exception:
            pass
        # fps elegido por el usuario mientras suena; en silencio, al mínimo útil
        fps, self.div = PERF.get(self.conf.get("rendimiento", "equilibrado"), PERF["equilibrado"])
        if time.monotonic() - self.engine.loud_t > 1.5:
            fps, self.div = MIN_FPS, 1
            if self.settled():
                fps = self.IDLE_FPS
        self.cur_fps = fps
        if self.dt > 0:                                  # fps medidos (para el menú)
            self.fps_meas = 0.95 * getattr(self, "fps_meas", fps) + 0.05 / self.dt
        self._next = getattr(self, "_next", now) + 1 / fps
        t = time.perf_counter()
        if self._next < t:
            self._next = t
        self.win.after(max(1, int((self._next - t) * 1000)), self.frame_loop)

    # ---- render -------------------------------------------------------------------
    def render(self):
        e = self.engine
        self.frame_n += 1
        self.quiet = time.monotonic() - e.loud_t > 0.3
        new, _ = e.read(max(self.read_pos, e.w - e.sr // 2), e.w)
        self.read_pos = e.w
        if "wave" in self.rects:
            self._render_wave(new)
        slow_turn = self.frame_n % getattr(self, "div", 1) == 0
        if slow_turn:
            saved_dt = self.dt
            self.dt = saved_dt * getattr(self, "div", 1)      # el tiempo real entre turnos
            if "spec" in self.rects:
                self._render_spec()
            if "stereo" in self.rects:
                self._render_stereo()
            self.dt = saved_dt
        if "lufs" in self.rects:
            self._render_lufs(new)

    WAVE_PX_S = 120          # velocidad constante: 1 px por cuadro a 120 fps, 2 a 60

    def _render_wave(self, new):
        e, sr = self.engine, self.engine.sr
        spc = max(64, int(sr / self.WAVE_PX_S))
        lat = max(2048, 3 * e.max_block)        # margen para bloques de audio irregulares
        target = e.w - lat
        if self.wave_pos is None or target - self.wave_pos > sr * 0.4 \
                or self.wave_pos > e.w:
            self.wave_pos = target - 4 * spc      # resincronizar
        # paso fijo de 2 px por cuadro; solo se corrige si el búfer se desfasa
        backlog = (target - self.wave_pos) // spc
        step = max(1, round(self.WAVE_PX_S / getattr(self, "cur_fps", FPS)))
        if backlog > 3 * step + 6:
            n = step + 1
        elif backlog < step:
            n = max(0, backlog)
        else:
            n = step
        if n <= 0:
            return
        seg, _ = e.read(self.wave_pos, self.wave_pos + n * spc)
        self.wave_pos += n * spc
        if len(seg) < n * spc:
            return
        seg = seg.mean(axis=1).reshape(n, spc)
        peak = np.clip(np.abs(seg).max(axis=1), 0, 1)
        if peak.max() < 1e-4:                           # silencio: columnas planas en caché
            if getattr(self, "wave_silent", None) is None or self.wave_silent.shape[0] != self.wave_H:
                col = np.empty((self.wave_H, 1, 3), np.uint8)
                col[:] = self.bgc
                col[self.wave_H // 2] = self.wave_mid
                self.wave_silent = col
            self.wave.push(np.repeat(self.wave_silent, n, axis=1))
            return
        X = np.abs(np.fft.rfft(seg * hann(spc), axis=1)) ** 2
        f = np.fft.rfftfreq(spc, 1 / sr)
        bands = np.stack([X[:, f < 250].sum(1), X[:, (f >= 250) & (f < 4000)].sum(1),
                          X[:, f >= 4000].sum(1) * 2.5], 1)
        bands = np.sqrt(bands)
        bands /= bands.max(axis=1, keepdims=True) + 1e-12
        cols = WAVE_RGB if self.conf.get("color_onda") == "rgb" \
            else self.T.get("onda", WAVE_THEME_DEFAULT)
        lo, mi, hi = (rgb(c) for c in cols)
        col = (bands[:, :1] * lo + bands[:, 1:2] * mi + bands[:, 2:3] * hi)
        col = col / (bands.sum(1, keepdims=True) + 1e-9)
        col = np.clip(col * (0.75 + 0.5 * peak[:, None]) + 20, 0, 255).astype(np.uint8)
        H = self.wave_H
        half = np.maximum(peak[None, :] * (H / 2 - 2), 0.5)
        mask = self.wave_rows <= half
        out = np.where(mask[..., None], col[None, :, :], self.bgc).astype(np.uint8)
        mid = out[H // 2]
        mid[~mask[H // 2]] = self.wave_mid
        self.wave.push(out)

    FFT_N = 8192

    def _fft_power(self):
        n = self.FFT_N
        x = self.engine.last(n)
        if len(x) < n:
            return None
        m = x.mean(axis=1) * hann(n)
        return (np.abs(np.fft.rfft(m)) * (2 / (n * 0.5))) ** 2

    def _smoother(self, sr):
        """Bordes fraccionarios de 1/12 de octava alrededor de cada punto (como SPAN)."""
        if self.sm_cache and self.sm_cache[0] == sr:
            return self.sm_cache[1:]
        df = sr / self.FFT_N
        c = self.fpts / df
        half = np.maximum(c * (2 ** (1 / 24) - 2 ** (-1 / 24)) / 2, 0.75)   # mínimo ~1.5 bins
        e_lo, e_hi = c - half + 0.5, c + half + 0.5      # en el eje de la suma acumulada
        self.sm_cache = (sr, e_lo, e_hi, df)
        return e_lo, e_hi, df

    def _render_spec(self):
        if self.quiet and getattr(self, "spec_rest", False):
            self._sg_silence()
            return
        Pw = self._fft_power()
        if Pw is None:
            return
        X, Y, w, sh = self.spec_geom
        e_lo, e_hi, df = self._smoother(self.engine.sr)
        cs = np.concatenate([[0.0], np.cumsum(Pw)])
        edges = np.arange(len(cs))
        P = (np.interp(e_hi, edges, cs) - np.interp(e_lo, edges, cs)) / (e_hi - e_lo)
        cur = 10 * np.log10(P + 1e-14) + 4.5 * np.log2(self.fpts / 1000)
        # subida rápida, caída suave (en el tiempo)
        up = 1 - math.exp(-self.dt / 0.012)
        down = 1 - math.exp(-self.dt / 0.25)
        self.spec_s += (cur - self.spec_s) * np.where(cur > self.spec_s, up, down)
        yv = Y + np.clip((self.db_hi - self.spec_s) / (self.db_hi - self.db_lo), 0, 1) * (sh - 1)
        last = getattr(self, "spec_yv", None)
        moved = last is None or len(last) != len(yv) or float(np.abs(yv - last).max()) > 0.4
        if moved:                                       # solo redibujar si la curva cambió
            self.spec_yv = yv
            pts = np.empty(2 * len(yv))
            pts[0::2], pts[1::2] = self.xpts, yv
            line = pts.tolist()
            self.cv.coords(self.spec_line, *line)
            self.cv.coords(self.spec_poly, X, Y + sh, *line, X + w - 1, Y + sh)
        self.spec_rest = self.quiet and not moved
        if self.sgram is None:
            return
        # espectrograma: ~60 columnas por segundo
        self.sg_acc += 60 * self.dt
        n = int(self.sg_acc)
        if n <= 0:
            return
        self.sg_acc -= n
        colv = np.interp(np.log10(self.frows), np.log10(self.fpts), cur)
        idx = np.clip((colv + 96) / 90 * 255, 0, 255).astype(np.uint8)
        col = self.sg_lut[idx][:, None, :]
        self.sgram.push(np.repeat(col, min(n, 4), axis=1))

    def _sg_silence(self):
        if self.sgram is None:
            return
        self.sg_acc += 60 * self.dt
        n = int(self.sg_acc)
        if n <= 0:
            return
        self.sg_acc -= n
        col = np.empty((self.sgram.h, 1, 3), np.uint8)
        col[:] = self.sg_lut[0]
        self.sgram.push(np.repeat(col, min(n, 4), axis=1))

    def _render_stereo(self):
        if self.quiet and float(self.st_acc.max()) < 0.004:
            if not getattr(self, "st_clean", False):
                self.st_acc[:] = 0
                self.stereo.put(self.st_grid)
                self.st_clean = True
            return
        self.st_clean = False
        s = self.st_s
        x = self.engine.last(2048)
        if len(x) < 64:
            return
        L, R = x[:, 0], x[:, 1]
        side = (L - R) * 0.7071
        mid = (L + R) * 0.7071
        rms = math.sqrt(float((L * L + R * R).mean()) + 1e-12)
        norm = max(rms * 3.2, 1e-3)
        px = np.clip((s / 2 + side / norm * s * 0.46).astype(int), 0, s - 1)
        py = np.clip((s / 2 - mid / norm * s * 0.46).astype(int), 0, s - 1)
        acc = self.st_acc
        k = self.dt * 30
        acc *= 0.72 ** k
        if rms > 1e-5:
            acc += np.bincount(py * s + px, minlength=s * s).reshape(s, s).astype(np.float32) \
                * (0.18 * k)
        img = self.st_lut[(np.clip(acc, 0, 1) * 255).astype(np.uint8)]
        img = np.maximum(img, self.st_grid)
        self.stereo.put(img)
        # correlación
        den = math.sqrt(float((L * L).sum() * (R * R).sum())) + 1e-12
        r = float((L * R).sum()) / den if rms > 1e-5 else 1.0
        self.corr_s += (r - self.corr_s) * (1 - 0.85 ** (self.dt * 30))
        Lx, Rx, by = self.corr_geom
        cx = Lx + (self.corr_s + 1) / 2 * (Rx - Lx)
        col = self.alert if self.corr_s < 0 else (self.T["acento2"] if self.corr_s > 0.3
                                                 else "#fbbf24")
        self._co(self.corr_dot, cx - 4, by - 4, cx + 4, by + 4)
        self._ic(self.corr_dot, fill=col)
        if self.frame_n % 12 == 0:
            self.cv.itemconfig(self.corr_txt, text=f"{self.corr_s:+.2f}")

    def _ic(self, item, **kw):
        c = self.__dict__.setdefault("_icache", {})
        if c.get(item) != kw:
            self.cv.itemconfig(item, **kw)
            c[item] = kw

    def _co(self, item, *xy):
        c = self.__dict__.setdefault("_ccache", {})
        xy = tuple(round(v, 1) for v in xy)
        if c.get(item) != xy:
            self.cv.coords(item, *xy)
            c[item] = xy

    def _render_lufs(self, new):
        T, cv = self.T, self.cv
        top, bot = self.m_geom
        dt = self.dt

        def ypos(v, lo, hi):
            return bot - (bot - top) * max(0.0, min(1.0, (v - lo) / (hi - lo)))

        pk = np.abs(new).max(axis=0) if len(new) else np.zeros(2)
        vals = {"L": (db(float(pk[0])), -60, 0), "R": (db(float(pk[1])), -60, 0),
                "M": (self.loud.momentary() if self.loud else -math.inf, -40, 0)}
        for k, (v, lo, hi) in vals.items():
            m = self.meters[k]
            v = max(v, -90.0)
            m["v"] = v if v > m["v"] else m["v"] - (24 if k != "M" else 12) * dt
            if m["v"] >= m["h"]:
                m["h"], m["ht"] = m["v"], 1.5
            else:
                m["ht"] -= dt
                if m["ht"] <= 0:
                    m["h"] -= 12 * dt
            y = ypos(m["v"], lo, hi)
            self._co(m["fill"], m["x"], y, m["x"] + 8, bot)
            hot = (m["v"] > -1) if k != "M" else (m["v"] > -9)
            warm = (m["v"] > -6) if k != "M" else (m["v"] > -14)
            self._ic(m["fill"], fill=self.alert if hot else "#fbbf24" if warm
                     else T["acento"])
            yh = ypos(m["h"], lo, hi)
            self._co(m["hold"], m["x"], yh, m["x"] + 8, yh)
        if self.frame_n % 6 or not self.loud:
            return
        L = self.loud

        def fmt(v):
            return "—" if v == -math.inf or v < -70 else f"{v:.1f}"
        st = L.short_term()
        self._ic(self.lu["st"], text=fmt(st))
        if "st_unit" in self.lu:
            bb = cv.bbox(self.lu["st"])
            if bb:
                cv.coords(self.lu["st_unit"], bb[2] + 4, bb[3] - 4)
                cv.itemconfig(self.lu["st_unit"], text="LUFS S")
        u_l, u_t = ("", "") if self.lu_inline else ("  LUFS", "  dBTP")
        self._ic(self.lu["m"], text=f"{fmt(L.momentary())}{u_l}")
        self._ic(self.lu["i"], text=f"{fmt(L.integrated())}{u_l}")
        tp = L.tp_max
        cv.itemconfig(self.lu["tp"], text=f"{fmt(tp)}{u_t}",
                      fill=self.alert if tp > -1 else T["texto"])
        if self.hist_geom and L.hist and self.frame_n % 30 == 0:
            hx0, hx1, hy0, hy1 = self.hist_geom
            vals = list(L.hist)[-60:]
            n = len(vals)
            pts = []
            for i, v in enumerate(vals):
                xx = hx1 - (n - 1 - i) * (hx1 - hx0) / 59
                v = -40 if v == -math.inf else max(-40, min(0, v))
                pts += [xx, hy0 + (hy1 - hy0) * (-v / 40)]
            if len(pts) >= 4:
                cv.coords(self.hist_line, *pts)

    # ---- interacción ----------------------------------------------------------
    def bind_child(self, w):
        """Los lienzos hijos reenvían el mouse al panel (arrastrar, menú, doble clic)."""
        def fwd(fn):
            def h(e):
                e.x += w.winfo_x()
                e.y += w.winfo_y()
                return fn(e)
            return h
        w.bind("<ButtonPress-1>", fwd(self.on_press))
        w.bind("<B1-Motion>", fwd(self.on_drag))
        w.bind("<ButtonRelease-1>", fwd(self.on_release))
        w.bind("<Double-Button-1>", lambda e: self.reset_loudness())
        for seq in ("<Button-2>", "<Button-3>", "<Control-Button-1>"):
            w.bind(seq, self.show_menu)

    def in_grip(self, e):
        return e.x >= self.W - 18 and e.y >= self.H - 18

    def on_motion(self, e):
        self.cv.config(cursor="bottom_right_corner"
                       if self.in_grip(e) and not self.docked() else "")

    def docked(self):
        return bool(self.app.conf.get("top_mode"))

    def on_press(self, e):
        self.win.after(20, self.app.raise_timer)
        if self.docked():                    # acoplado arriba de Live: fijo
            self._drag = self._resize = None
            return
        if self.in_grip(e):
            self._resize = (e.x_root, e.y_root, self.W, self.H)
        else:
            self._drag = (e.x_root - self.win.winfo_x(), e.y_root - self.win.winfo_y())

    def on_drag(self, e):
        if self._resize:
            x0, y0, w0, h0 = self._resize
            w = max(460, w0 + e.x_root - x0)
            h = max(120, min(420, h0 + e.y_root - y0))
            self.win.geometry(f"{w}x{h}")
            now = time.monotonic()
            if now - self._last_build > 0.12:
                self._last_build = now
                self.conf["w"], self.conf["h"] = w, h
                self.build()
        elif self._drag:
            self.win.geometry(f"+{e.x_root - self._drag[0]}+{e.y_root - self._drag[1]}")

    def on_release(self, e):
        c = self.conf
        self.win.after(20, self.app.raise_timer)
        if self.docked():
            return
        if self._resize:
            c["w"], c["h"] = self.win.winfo_width(), self.win.winfo_height()
            self.build()
        c["x"], c["y"] = self.win.winfo_x(), self.win.winfo_y()
        self._drag = self._resize = None
        self.app.save_conf()
        if hasattr(self.app, "restack_soon"):
            self.app.restack_soon(150)

    def show_menu(self, ev):
        m = tk.Menu(self.win, tearoff=0)
        e = self.engine
        m.add_command(label=(f"Entrada: {e.label} · {e.sr / 1000:g} kHz" if e.stream is not None
                             else "Entrada: sin audio"), state="disabled")
        m.add_command(label="Diagnóstico de audio…", command=self.open_diag)
        m.add_command(label="Reconectar audio", command=self.reconnect)
        m.add_separator()
        mods = self.conf["modulos"]
        for k, name in MODULES:
            var = tk.BooleanVar(value=mods.get(k, True))
            m.add_checkbutton(label=name, variable=var,
                              command=lambda k=k, v=var: self.set_module(k, v.get()))
        m.add_separator()
        cvar = tk.StringVar(value=self.conf.get("color_onda", "tema"))
        sub = tk.Menu(m, tearoff=0)
        for k, name in (("tema", "Tema (colores del estilo)"), ("rgb", "RGB estándar")):
            sub.add_radiobutton(label=name, value=k, variable=cvar,
                                command=lambda k=k: self.set_wave_color(k))
        m.add_cascade(label="Color de la onda", menu=sub)
        m.add_separator()
        m.add_command(label="Reiniciar loudness (I / TP)", command=self.reset_loudness)
        m.add_command(label="Ocultar analizador", command=self.app.toggle_analyzer)
        m.tk_popup(ev.x_root, ev.y_root)

    # ---- diagnóstico ------------------------------------------------------------
    def open_diag(self):
        d = getattr(self, "diag", None)
        if d is not None and d.winfo_exists():
            d.lift()
            return
        self.diag = Diagnostico(self)


    def set_wave_color(self, k):
        self.conf["color_onda"] = k
        self.app.save_conf()

    def set_module(self, k, on):
        mods = self.conf["modulos"]
        mods[k] = on
        if not any(mods.values()):
            mods[k] = True
        self.app.save_conf()
        self.build()


# --------------------------------------------------------------------------
# ventana de diagnóstico: qué entrada se usa y si de verdad llega audio
# --------------------------------------------------------------------------
class Diagnostico(tk.Toplevel):
    def __init__(self, panel):
        app = panel.app
        super().__init__(app.root)
        self.panel = panel
        T = app.T
        self.T = T
        self.title("Gaux Live Timer · Diagnóstico de audio")
        self.configure(bg=T["bg"])
        self.attributes("-topmost", True)
        self.resizable(False, False)
        sans = app.f_sans
        tk.Label(self, text="Diagnóstico de audio", font=(app.f_title[0], app.f_title[1] + 2,
                                                          "bold"),
                 fg=T["acento2"], bg=T["bg"]).pack(anchor="w", padx=18, pady=(14, 6))
        self.rows = {}
        box = tk.Frame(self, bg=T["bg"])
        box.pack(fill="x", padx=18)
        for k, name in (("link", "Gaux Link"), ("entrada", "Entrada"), ("estado", "Estado"),
                        ("permiso", "Permiso"), ("nivel", "Nivel")):
            r = tk.Frame(box, bg=T["bg"])
            r.pack(fill="x", pady=2)
            tk.Label(r, text=name, width=9, anchor="w", font=(sans, 11, "bold"),
                     fg=T["dim"], bg=T["bg"]).pack(side="left")
            v = tk.Label(r, text="", anchor="w", justify="left", font=(sans, 11),
                         fg=T["texto"], bg=T["bg"], wraplength=420)
            v.pack(side="left", fill="x")
            self.rows[k] = v
        self.bar = tk.Canvas(self, width=440, height=10, bg=T["pista"], highlightthickness=0)
        self.bar.pack(padx=18, pady=(4, 8), anchor="w")
        self.fill = self.bar.create_rectangle(0, 0, 0, 10, fill=T["acento"], outline="")
        self.tip = tk.Label(self, text="", justify="left", anchor="w", font=(sans, 11),
                            fg=T["texto"], bg=T["bg"], wraplength=440)
        self.tip.pack(padx=18, pady=(0, 8), anchor="w")
        btns = tk.Frame(self, bg=T["bg"])
        btns.pack(fill="x", padx=18, pady=(2, 14))
        acts = [("Reconectar", panel.reconnect)]
        if SYSTEM == "Darwin":
            acts += [("Permiso de micrófono", open_mic_settings),
                     ("Configuración de Audio MIDI", open_audio_setup)]
        elif SYSTEM == "Windows":
            acts += [("Dispositivos de grabación", open_audio_setup)]
        for i, (t, cmd) in enumerate(acts):
            b = tk.Label(btns, text=t, font=(sans, 11, "bold"), padx=10, pady=4, cursor="hand2",
                         bg=T["acento"] if i == 0 else T["bg2"],
                         fg="#ffffff" if i == 0 else T["texto"])
            b.bind("<Button-1>", lambda e, c=cmd: c())
            b.pack(side="left", padx=(0, 8))
        self.perm = mic_permission()
        self._perm_t = time.monotonic()
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"+{(sw - self.winfo_reqwidth()) // 2}+{(sh - self.winfo_reqheight()) // 3}")
        self._tick()

    def _tick(self):
        if not self.winfo_exists():
            return
        p, e, T = self.panel, self.panel.engine, self.T
        now = time.monotonic()
        if now - self._perm_t > 3:
            self._perm_t = now
            self.perm = mic_permission()
        r = self.rows
        d = LinkReceiver.get().describe()
        if d:
            host, track, sr = d
            r["link"].config(text=f"conectado · {host}" + (f" · pista {track}" if track else "")
                             + f" · {sr / 1000:g} kHz", fg=T["texto"])
        elif not LinkReceiver.get().ok:
            r["link"].config(text="no disponible (otro programa usa el puerto 47654)", fg=p.alert)
        else:
            r["link"].config(text="no detectado: pon el plugin Gaux Link en el Master",
                             fg=T["dim"])
        if e.stream is not None:
            r["entrada"].config(text=f"{e.label} · {e.sr / 1000:g} kHz · {e.ch} canales")
            alive = now - e.cb_t < 1.0
            r["estado"].config(text="recibiendo bloques de audio" if alive
                               else "la entrada no responde (se reconecta sola)",
                               fg=T["texto"] if alive else p.alert)
        else:
            r["entrada"].config(text="ninguna")
            r["estado"].config(text={"sin_dispositivo": "no hay BlackHole / VB-Cable instalado"}
                               .get(e.error, e.error or "detenida"), fg=p.alert)
        perm = "link" if e.mode == "link" else self.perm
        r["permiso"].config(text={"link": "no hace falta (Gaux Link)",
                                  "ok": "micrófono permitido", "denegado":
                                  f"micrófono BLOQUEADO para {HOST_APP}",
                                  "pendiente": "macOS aún no lo pregunta",
                                  None: "no aplica"}[perm],
                            fg=p.alert if perm == "denegado" else T["texto"])
        lvl = db(e.peak) if e.stream is not None else -math.inf
        if e.sig_t == 0.0:
            txt = "silencio digital (no llega nada)"
        elif lvl < -90:
            txt = "silencio (Live en pausa)"
        else:
            txt = f"{lvl:.1f} dBFS"
        r["nivel"].config(text=txt)
        frac = 0.0 if lvl == -math.inf else max(0.0, min(1.0, (lvl + 60) / 60))
        self.bar.coords(self.fill, 0, 0, 440 * frac, 10)
        if e.stream is None:
            tip = ("Pon el plugin Gaux Link al final del Master de tu DAW (se instala junto con la "
                   "app). También sirve BlackHole 2ch (Mac) o VB-Cable (Windows). El timer lo "
                   "detecta solo en unos segundos.")
        elif e.mode == "link" and e.sig_t == 0.0:
            tip = "Gaux Link está conectado. Dale play en tu DAW y aquí verás el nivel."
        elif e.mode == "link":
            tip = "Todo bien: el audio llega directo desde Gaux Link (sin BlackHole)."
        elif self.perm == "denegado":
            tip = (f"Activa {HOST_APP} en Privacidad y seguridad → Micrófono (BlackHole cuenta "
                   "como micrófono). Después pulsa Reconectar. Si no aparece en la lista, cierra "
                   f"{HOST_APP} y vuelve a abrirlo.")
        elif e.sig_t == 0.0:
            tip = ("La entrada está abierta pero llega silencio total. Dale play en Live. Si suena "
                   "y aquí no se mueve:\n1. Live → Ajustes → Audio → Dispositivo de salida = el "
                   "Dispositivo de salida múltiple.\n2. En Configuración de Audio MIDI, el "
                   "dispositivo múltiple debe tener marcados tu salida y BlackHole 2ch (tras "
                   "actualizar macOS a veces se desmarca).\n3. Pulsa Reconectar.")
        else:
            tip = "Todo bien: el audio de Live está llegando al analizador."
        self.tip.config(text=tip)
        self.after(200, self._tick)


def _self_test():
    """python3 gaux_analizador.py --test  → prueba la entrada sin abrir el timer."""
    print("Entradas de audio:")
    for i, n in list_inputs():
        print(f"  [{i}] {n}")
    print("Permiso de micrófono:", mic_permission())
    idx, name = resolve_device(sys.argv[2] if len(sys.argv) > 2 else "auto")
    if idx is None:
        print("No hay BlackHole / VB-Cable / Loopback. Instálalo (ver LEEME.md).")
        return
    print(f"Usando: {name}. Dale play en Live; escucho 5 segundos…")
    e = AudioEngine()
    e.start(name)
    if e.stream is None:
        print("No se pudo abrir:", e.error)
        return
    for _ in range(10):
        time.sleep(0.5)
        print(f"  bloques={e.cb_n:5d}  pico={db(e.peak):7.1f} dBFS"
              + ("   (silencio digital)" if e.sig_t == 0 else ""))
    e.stop()
    if e.cb_n == 0:
        print("RESULTADO: la entrada no entrega audio. Reinicia el Mac o reinstala BlackHole.")
    elif e.sig_t == 0:
        print("RESULTADO: llega silencio total. Revisa el permiso de micrófono de la Terminal y "
              "que la salida de Live sea el Dispositivo de salida múltiple con BlackHole marcado.")
    else:
        print("RESULTADO: OK, el audio llega.")


if __name__ == "__main__" and "--test" in sys.argv:
    _self_test()
