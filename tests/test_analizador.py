"""Analizador: loudness (EBU R128), true peak, Gaux Link (UDP), búfer de audio, espectro,
espectrograma, onda, vectorscopio y el panel en todos los estilos y tamaños."""
import itertools
import math
import socket
import struct
import time

import numpy as np
import pytest

import gaux_analizador as G
import live_timer as L
from conftest import TK_ERRORS, drain

SRS = [44100, 48000, 88200, 96000]


def sine(f, db, secs, sr, phase=0.0, ch=2):
    t = np.arange(int(round(secs * sr))) / sr
    x = (10 ** (db / 20)) * np.sin(2 * np.pi * f * t + phase)
    return np.repeat(x[:, None], ch, axis=1).astype(np.float32)


def noise(db, secs, sr, seed=1):
    rng = np.random.default_rng(seed)
    x = rng.standard_normal((int(secs * sr), 2)) * (10 ** (db / 20))
    return x.astype(np.float32)


def loud_of(x, sr):
    Lo = G.Loudness(sr)
    for i in range(0, len(x) - Lo.n + 1, Lo.n):
        Lo.push(x[i:i + Lo.n])
    return Lo


# ---------------------------------------------------------------- loudness
@pytest.mark.parametrize("sr", SRS)
@pytest.mark.parametrize("db", [-3, -6, -12, -18, -23, -30, -40])
def test_lufs_seno_1k(sr, db):
    """Seno de 997 Hz en ambos canales: LUFS integrado = nivel de pico en dBFS (±0.1)."""
    Lo = loud_of(sine(997, db, 6, sr), sr)
    assert Lo.integrated() == pytest.approx(db, abs=0.15)
    assert Lo.short_term() == pytest.approx(db, abs=0.15)
    assert Lo.momentary() == pytest.approx(db, abs=0.15)


@pytest.mark.parametrize("sr", SRS)
def test_lufs_silencio(sr):
    Lo = loud_of(np.zeros((sr * 4, 2), np.float32), sr)
    assert Lo.integrated() == -math.inf and Lo.momentary() == -math.inf


@pytest.mark.parametrize("db", [-75, -90])
def test_lufs_puerta_absoluta(db):
    sr = 48000
    Lo = loud_of(sine(997, db, 4, sr), sr)
    assert Lo.integrated() == -math.inf


def test_lufs_puerta_relativa_ignora_silencios():
    sr = 48000
    x = np.concatenate([sine(997, -20, 5, sr), np.zeros((sr * 20, 2), np.float32),
                        sine(997, -20, 5, sr)])
    assert loud_of(x, sr).integrated() == pytest.approx(-20, abs=0.2)


def test_lufs_un_solo_canal():
    sr = 48000
    x = sine(997, -20, 6, sr)
    x[:, 1] = 0
    assert loud_of(x, sr).integrated() == pytest.approx(-23.01, abs=0.2)


@pytest.mark.parametrize("f,expect", [(100, -21.8), (1000, -20.0), (10000, -16.6)])
def test_lufs_ponderacion_k(f, expect):
    """Curva K de la norma BS.1770: -1.8 dB en 100 Hz (pasa-altos RLB), 0 en 1 kHz, +3.4 en 10 kHz."""
    sr = 48000
    got = loud_of(sine(f, -20, 6, sr), sr).integrated()
    assert got == pytest.approx(expect, abs=0.6)


@pytest.mark.parametrize("sr", SRS)
@pytest.mark.parametrize("db", [-0.1, -1, -6, -20])
def test_true_peak_seno(sr, db):
    Lo = loud_of(sine(997, db, 2, sr), sr)
    assert Lo.tp_max == pytest.approx(db, abs=0.2)


def test_true_peak_entre_muestras():
    """Seno a fs/4 con fase 45°: las muestras marcan -3 dB pero el pico real es 0 dBTP."""
    sr = 48000
    x = sine(sr / 4, 0, 1, sr, phase=math.pi / 4)
    assert float(np.abs(x).max()) == pytest.approx(10 ** (-3.01 / 20), abs=0.01)
    Lo = loud_of(x, sr)
    assert Lo.tp_max > -0.5


def test_reset_loudness():
    sr = 48000
    Lo = loud_of(sine(997, -10, 3, sr), sr)
    Lo.reset()
    assert Lo.integrated() == -math.inf and Lo.tp_max == -math.inf


def test_historial_short_term():
    sr = 48000
    Lo = loud_of(sine(997, -14, 4, sr), sr)
    Lo.hist.append(Lo.short_term())
    assert Lo.hist[-1] == pytest.approx(-14, abs=0.2)


@pytest.mark.parametrize("x,out", [(1.0, 0.0), (0.5, -6.02), (0.1, -20.0), (0.0, -math.inf)])
def test_db(x, out):
    if out == -math.inf:
        assert G.db(x) < -200
    else:
        assert G.db(x) == pytest.approx(out, abs=0.02)


# ---------------------------------------------------------------- búfer de audio
@pytest.mark.parametrize("block", [32, 64, 128, 256, 512, 1024, 2048, 4096, 333])
def test_bufer_circular(block):
    e = G.AudioEngine()
    total = G.AudioEngine.SIZE + 5000          # obliga a dar la vuelta
    x = np.arange(total * 2, dtype=np.float32).reshape(total, 2) / 1e6
    for i in range(0, total, block):
        c = x[i:i + block]
        e._cb(c, len(c), None, None)
    out, start = e.read(total - 3000, total)
    assert start == total - 3000
    assert np.allclose(out, x[total - 3000:total])
    assert np.allclose(e.last(10), x[-10:])


def test_bufer_mono_a_stereo():
    e = G.AudioEngine()
    e.ch = 1
    x = np.linspace(-1, 1, 1000, dtype=np.float32)[:, None]
    e._cb(x, 1000, None, None)
    out = e.last(1000)
    assert np.allclose(out[:, 0], x[:, 0]) and np.allclose(out[:, 1], x[:, 0])


def test_bufer_lectura_vieja_se_recorta():
    e = G.AudioEngine()
    x = np.zeros((G.AudioEngine.SIZE * 2, 2), np.float32)
    e._cb(x, len(x), None, None)
    out, start = e.read(0, 100)
    assert len(out) == 0 or start > 0


def test_bufer_vacio():
    e = G.AudioEngine()
    out, _ = e.read(0, 100)
    assert out.shape == (0, 2)


def test_detecta_senal_y_silencio():
    e = G.AudioEngine()
    e._cb(np.zeros((512, 2), np.float32), 512, None, None)
    assert e.sig_t == 0.0
    e._cb(np.full((512, 2), 0.5, np.float32), 512, None, None)
    assert e.sig_t > 0 and e.peak == pytest.approx(0.5)


# ---------------------------------------------------------------- Gaux Link (UDP)
def gxlk(inst, seq, sr, data):
    frames, ch = data.shape
    hdr = b"GXLK" + bytes([1, ch, 0, 0]) + struct.pack("<IIII", inst, seq, sr, frames)
    return hdr + np.ascontiguousarray(data, np.float32).tobytes()


def gxhi(inst, sr, host, track):
    return b"GXHI" + bytes([1, 0, 0, 0]) + struct.pack("<II", inst, sr) + \
        f"{host}\n{track}".encode()


@pytest.fixture(scope="module")
def link():
    lk = G.LinkReceiver.get()
    if not lk.ok:
        pytest.skip("puerto de Gaux Link ocupado")
    return lk


@pytest.fixture
def sender():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(1.0)
    yield s
    s.close()


def wait(cond, t=1.5):
    end = time.monotonic() + t
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.005)
    return cond()


def reset_link(lk):
    lk.active = None
    lk.audio_t = 0.0
    lk.sink = None
    lk.info.clear()


@pytest.mark.parametrize("host,track", [("Ableton Live", "Master"), ("FL Studio", "Insert 1"),
                                        ("Logic Pro", ""), ("REAPER", "Mix Bus ñ"),
                                        ("Bitwig Studio", "🎧")])
def test_link_saludo_y_respuesta(link, sender, host, track):
    reset_link(link)
    sender.sendto(gxhi(7, 48000, host, track), ("127.0.0.1", G.LINK_PORT))
    ack, _ = sender.recvfrom(64)
    assert ack[:4] == b"GXAK"
    assert wait(lambda: 7 in link.info)
    assert link.info[7][0] == host and link.info[7][1] == track


@pytest.mark.parametrize("sr", SRS)
@pytest.mark.parametrize("frames", [32, 64, 128, 256, 441, 480])   # el plugin manda ≤ 480
def test_link_audio_llega_al_motor(link, sender, sr, frames):
    reset_link(link)
    e = G.AudioEngine()
    e.sr = sr
    G.LinkStream(e, link)
    x = sine(997, -6, frames * 8 / sr, sr)
    for i in range(8):
        sender.sendto(gxlk(11, i, sr, x[i * frames:(i + 1) * frames]), ("127.0.0.1", G.LINK_PORT))
    assert wait(lambda: e.w >= frames * 8)
    assert np.allclose(e.last(frames * 8), x, atol=1e-6)
    assert link.recent() and link.sr == sr


def test_link_cambio_de_frecuencia(link, sender):
    reset_link(link)
    e = G.AudioEngine()
    e.sr = 48000
    G.LinkStream(e, link)
    sender.sendto(gxlk(12, 0, 44100, sine(997, -6, 0.01, 44100)), ("127.0.0.1", G.LINK_PORT))
    assert wait(lambda: e.sr_changed)
    assert e.w == 0


@pytest.mark.parametrize("pkt", [
    b"", b"GXLK", b"GXLK" + b"\x00" * 10, b"XXXX" + b"\x00" * 40,
    b"GXLK" + bytes([1, 0, 0, 0]) + struct.pack("<IIII", 1, 0, 48000, 10) + b"\x00" * 80,
    b"GXLK" + bytes([1, 3, 0, 0]) + struct.pack("<IIII", 1, 0, 48000, 10) + b"\x00" * 120,
    b"GXLK" + bytes([1, 2, 0, 0]) + struct.pack("<IIII", 1, 0, 48000, 100) + b"\x00" * 80,
    b"GXLK" + bytes([1, 2, 0, 0]) + struct.pack("<IIII", 1, 0, 48000, 0),
    b"GXHI" + b"\xff" * 30,
    b"GXHI" + struct.pack("<II", 1, 48000) + b"\xff\xfe\xfd",
])
def test_link_paquetes_rotos_no_lo_tumban(link, sender, pkt):
    reset_link(link)
    e = G.AudioEngine()
    e.sr = 48000
    G.LinkStream(e, link)
    if pkt:
        sender.sendto(pkt, ("127.0.0.1", G.LINK_PORT))
    good = sine(997, -6, 256 / 48000, 48000)
    sender.sendto(gxlk(21, 0, 48000, good), ("127.0.0.1", G.LINK_PORT))
    assert wait(lambda: e.w >= 256), "el receptor sigue vivo después del paquete roto"


def test_link_dos_pistas_usa_la_primera(link, sender):
    reset_link(link)
    e = G.AudioEngine()
    e.sr = 48000
    G.LinkStream(e, link)
    a = np.full((128, 2), 0.25, np.float32)
    b = np.full((128, 2), -0.5, np.float32)
    sender.sendto(gxlk(31, 0, 48000, a), ("127.0.0.1", G.LINK_PORT))
    assert wait(lambda: e.w >= 128)
    sender.sendto(gxlk(32, 0, 48000, b), ("127.0.0.1", G.LINK_PORT))
    sender.sendto(gxlk(31, 1, 48000, a), ("127.0.0.1", G.LINK_PORT))
    assert wait(lambda: e.w >= 256)
    time.sleep(0.05)
    assert link.active == 31 and float(e.last(256).min()) == pytest.approx(0.25)


def test_link_mono(link, sender):
    reset_link(link)
    e = G.AudioEngine()
    e.sr = 48000
    G.LinkStream(e, link)
    m = np.linspace(-1, 1, 256, dtype=np.float32)[:, None]
    sender.sendto(gxlk(41, 0, 48000, m), ("127.0.0.1", G.LINK_PORT))
    assert wait(lambda: e.w >= 256)


def test_link_automatico_prefiere_el_plugin(link, sender):
    reset_link(link)
    sender.sendto(gxlk(51, 0, 48000, sine(997, -6, 0.01, 48000)), ("127.0.0.1", G.LINK_PORT))
    assert wait(lambda: link.recent())
    e = G.AudioEngine()
    e.start("auto")
    assert e.mode == "link" and e.label == G.LINK_NAME and e.error is None
    e.stop()


def test_sin_plugin_ni_dispositivo_avisa(link):
    reset_link(link)
    e = G.AudioEngine()
    e.start("auto")
    assert e.stream is None and e.error == "sin_dispositivo"


# ---------------------------------------------------------------- panel
class DummyStream:
    active = True

    def stop(self):
        pass

    def close(self):
        pass


@pytest.fixture
def panel(fresh):
    app = fresh
    app.conf["analizador"]["activo"] = True
    assert app.ensure_analyzer()
    p = app.analyzer
    p.running = False
    p.set_visible(True)
    yield p
    p.set_visible(False)
    p.engine.stream = None
    drain(app)


def prepare(p, sr=48000):
    e = p.engine
    e.sr = sr
    e.stream = DummyStream()
    e.mode = "link"
    p.loud = G.Loudness(sr)
    p.read_pos = p.lufs_pos = e.w
    p.wave_pos = None
    p.cur_fps = 60


def play(p, x, fps=60, frames=None):
    """Mete audio en bloques de 1/fps s y dibuja un cuadro por bloque."""
    e = p.engine
    n = int(e.sr / fps)
    count = 0
    for i in range(0, len(x) - n + 1, n):
        e._cb(x[i:i + n], n, None, None)
        e.loud_t = time.monotonic()
        p.dt = 1 / fps
        while e.w - p.lufs_pos >= p.loud.n:
            chunk, s = e.read(p.lufs_pos, p.lufs_pos + p.loud.n)
            p.lufs_pos = s + len(chunk)
            p.loud.push(chunk)
        p.render()
        count += 1
        if frames and count >= frames:
            break
    p.app.root.update_idletasks()


def rebuild(p, w, h, mods=None, tema="noche"):
    a = p.app.conf["analizador"]
    a["w"], a["h"] = w, h
    if mods is not None:
        a["modulos"] = {k: k in mods for k, _ in G.MODULES}
    p.app.conf["tema"] = tema
    p.app.apply_conf()
    p.build()


MODS = [k for k, _ in G.MODULES]
COMBOS = [c for r in range(1, 5) for c in itertools.combinations(MODS, r)]


@pytest.mark.parametrize("mods", COMBOS, ids=["+".join(c) for c in COMBOS])
@pytest.mark.parametrize("size", [(900, 172), (1600, 132), (460, 66), (700, 40), (1200, 24)])
@pytest.mark.parametrize("audio", ["con_audio", "sin_audio"])
def test_panel_modulos_y_tamanos(panel, mods, size, audio):
    panel.engine.stream = None
    panel.engine.error = None if audio == "con_audio" else "sin_dispositivo"
    rebuild(panel, *size, mods)
    if audio == "sin_audio":                              # el aviso cabe en cualquier tamaño
        cv = panel.cv
        b = cv.bbox(panel.msg_it)
        assert cv.itemcget(panel.msg_it, "text")
        assert b[0] >= 0 and b[1] >= 0 and b[2] <= panel.W and b[3] <= panel.H, b
        bb = cv.bbox(panel.msg_bg)
        assert bb[1] >= -1 and bb[3] <= panel.H + 1
        return
    prepare(panel)
    play(panel, noise(-12, 0.4, 48000))
    cv = panel.cv
    for k, (x0, y0, w, h) in panel.rects.items():
        assert w > 0 and h > 0
        assert panel.PAD + x0 + w <= panel.W + 1, (k, panel.rects)
    panel.frame_n = 0
    panel._render_lufs(np.zeros((0, 2), np.float32))      # textos con su valor real
    boxes = []
    for i in cv.find_all():
        if cv.type(i) == "text" and cv.itemcget(i, "state") != "hidden" and \
                cv.itemcget(i, "text").strip():
            b = cv.bbox(i)
            assert b[0] >= -1 and b[2] <= panel.W + 1 and b[1] >= -1 and b[3] <= panel.H + 1, \
                cv.itemcget(i, "text")
            boxes.append((cv.itemcget(i, "text"), b))
    msg = cv.itemcget(panel.msg_it, "text")
    boxes = [(t, b) for t, b in boxes if t != msg]        # el aviso va encima, con fondo
    for n, (t, b) in enumerate(boxes):                    # ningún texto pisa a otro
        for u, c in boxes[n + 1:]:
            ix = min(b[2], c[2]) - max(b[0], c[0])
            iy = min(b[3], c[3]) - max(b[1], c[1])
            assert not (ix > 2 and iy > 2), (t, u)
    assert not TK_ERRORS


@pytest.mark.parametrize("tema", list(L.TEMAS))
@pytest.mark.parametrize("color", ["tema", "rgb"])
def test_panel_estilos(panel, tema, color):
    panel.app.conf["analizador"]["color_onda"] = color
    rebuild(panel, 900, 172, MODS, tema)
    prepare(panel)
    play(panel, sine(440, -6, 0.5, 48000))
    play(panel, noise(-20, 0.3, 48000))


def pixel(srf, x, y):
    v = srf.photo.get(int(x), int(y))
    return tuple(int(c) for c in (v if isinstance(v, tuple) else str(v).split()))


@pytest.mark.parametrize("f", [60, 250, 1000, 4000, 12000])
def test_espectro_pico_en_su_frecuencia(panel, f):
    rebuild(panel, 1200, 172, ["spec"])
    prepare(panel)
    play(panel, sine(f, -6, 1.0, 48000))
    X, Y, w, sh = panel.spec_geom
    yv = panel.spec_yv
    i = int(np.argmin(yv))                       # punto más alto de la curva
    peak_f = panel.fpts[i]
    assert peak_f == pytest.approx(f, rel=0.08)
    assert yv[i] < Y + sh * 0.35, "el pico debe verse alto"


def test_espectro_silencio_baja(panel):
    rebuild(panel, 1200, 172, ["spec"])
    prepare(panel)
    play(panel, sine(1000, -6, 0.5, 48000))
    high = float(np.min(panel.spec_yv))
    panel.quiet = True
    play(panel, np.zeros((48000, 2), np.float32))
    assert float(np.min(panel.spec_yv)) > high + 20


@pytest.mark.parametrize("f", [100, 1000, 8000])
def test_espectrograma_pinta_la_frecuencia(panel, f):
    rebuild(panel, 1200, 300, ["spec"])
    prepare(panel)
    assert panel.sgram is not None
    bg = tuple(int(c) for c in panel.sg_lut[0])
    play(panel, sine(f, -3, 1.0, 48000))
    sg = panel.sgram
    col = (sg.wp - 2) % sg.w
    row = int(np.argmin(np.abs(np.log10(panel.frows) - math.log10(f))))
    assert pixel(sg, col, row) != bg, "la frecuencia debe verse en el espectrograma"
    far = int(np.argmin(np.abs(np.log10(panel.frows) - math.log10(20 if f > 500 else 15000))))
    assert sum(pixel(sg, col, row)) > sum(pixel(sg, col, far))


def test_espectrograma_avanza_60_columnas_por_segundo(panel):
    rebuild(panel, 1200, 300, ["spec"])
    prepare(panel)
    wp0 = panel.sgram.wp
    play(panel, noise(-20, 1.0, 48000))
    moved = (panel.sgram.wp - wp0) % panel.sgram.w
    assert moved == pytest.approx(60, abs=3)


@pytest.mark.parametrize("h", [24, 40, 80, 100, 103])
def test_espectrograma_se_oculta_en_franjas_bajas(panel, h):
    rebuild(panel, 1200, h, ["spec"])
    assert panel.sgram is None


@pytest.mark.parametrize("fps", [30, 60, 120])
def test_onda_avanza_a_velocidad_constante(panel, fps):
    rebuild(panel, 1200, 172, ["wave"])
    prepare(panel)
    panel.cur_fps = fps
    wp0 = panel.wave.wp
    play(panel, noise(-12, 1.5, 48000), fps=fps)
    moved = (panel.wave.wp - wp0) % panel.wave.w
    assert 120 * 1.2 <= moved <= 120 * 1.6 + 10


def test_onda_dibuja_la_amplitud(panel):
    rebuild(panel, 1200, 172, ["wave"])
    prepare(panel)
    play(panel, sine(200, -1, 1.0, 48000))
    w = panel.wave
    col = (w.wp - 1) % w.w
    H = panel.wave_H
    bg = tuple(int(c) for c in panel.bgc)
    y_hi = int(H / 2 - 0.8 * (H / 2 - 2))           # 80 % de la altura de la onda
    assert pixel(w, col, y_hi) != bg, "un seno a -1 dBFS llena casi todo el alto"
    assert pixel(w, col, 0) == bg, "pero no se sale"
    play(panel, np.zeros((48000 * 3, 2), np.float32))
    col = (w.wp - 1) % w.w
    assert pixel(w, col, y_hi) == bg, "en silencio la onda queda plana"


@pytest.mark.parametrize("kind,expect", [("mono", 1.0), ("invertido", -1.0), ("ruido", 0.0)])
def test_correlacion_stereo(panel, kind, expect):
    rebuild(panel, 900, 172, ["stereo"])
    prepare(panel)
    sr = 48000
    if kind == "mono":
        x = sine(300, -6, 1.5, sr)
    elif kind == "invertido":
        x = sine(300, -6, 1.5, sr)
        x[:, 1] *= -1
    else:
        x = noise(-12, 1.5, sr, seed=3)
    play(panel, x)
    assert panel.corr_s == pytest.approx(expect, abs=0.15)


@pytest.mark.parametrize("db", [-6, -14, -23])
def test_medidores_lufs_muestran_el_valor(panel, db):
    rebuild(panel, 900, 172, ["lufs"])
    prepare(panel)
    play(panel, sine(997, db, 4.0, 48000))
    panel.frame_n = 0
    panel._render_lufs(np.zeros((0, 2), np.float32))
    txt = panel.cv.itemcget(panel.lu["st"], "text")
    assert float(txt) == pytest.approx(db, abs=0.3)
    assert float(panel.cv.itemcget(panel.lu["i"], "text").split()[0]) == pytest.approx(db, abs=0.3)


def test_medidor_true_peak_en_rojo(panel):
    rebuild(panel, 900, 172, ["lufs"])
    prepare(panel)
    play(panel, sine(997, -0.2, 1.0, 48000))
    panel.frame_n = 0
    panel._render_lufs(np.zeros((0, 2), np.float32))
    assert panel.cv.itemcget(panel.lu["tp"], "fill").lower() == panel.alert.lower()


def test_doble_clic_reinicia_loudness(panel):
    rebuild(panel, 900, 172, ["lufs"])
    prepare(panel)
    play(panel, sine(997, -10, 2.0, 48000))
    panel.reset_loudness()
    assert panel.loud.integrated() == -math.inf


@pytest.mark.parametrize("sig", ["silencio", "clip", "dc", "nan_free_extremo"])
def test_senales_extremas_no_rompen(panel, sig):
    rebuild(panel, 900, 172, MODS)
    prepare(panel)
    sr = 48000
    if sig == "silencio":
        x = np.zeros((sr, 2), np.float32)
    elif sig == "clip":
        x = np.sign(sine(100, 0, 1, sr)) * 1.5
    elif sig == "dc":
        x = np.full((sr, 2), 0.8, np.float32)
    else:
        x = (np.random.default_rng(0).random((sr, 2)) * 2 - 1).astype(np.float32) * 4
    play(panel, x.astype(np.float32))
    panel.frame_n = 0
    panel._render_lufs(np.zeros((0, 2), np.float32))


@pytest.mark.parametrize("sr", [44100, 48000, 96000])
def test_panel_otras_frecuencias_de_muestreo(panel, sr):
    rebuild(panel, 900, 172, MODS)
    prepare(panel, sr)
    play(panel, sine(1000, -6, 1.0, sr))
    i = int(np.argmin(panel.spec_yv))
    assert panel.fpts[i] == pytest.approx(1000, rel=0.08)


def test_panel_en_reposo_baja_los_fps(panel):
    rebuild(panel, 900, 172, MODS)
    prepare(panel)
    panel.engine.loud_t = time.monotonic() - 20
    panel.quiet = True
    for _ in range(200):
        panel.render()
    assert panel.settled()


@pytest.mark.parametrize("perf", ["maximo", "equilibrado", "ahorro"])
def test_rendimiento(panel, perf):
    panel.app.conf["analizador"]["rendimiento"] = perf
    rebuild(panel, 900, 172, MODS)
    prepare(panel)
    panel.running = True
    play(panel, noise(-12, 0.2, 48000))
    panel.frame_loop()
    assert panel.cur_fps >= G.MIN_FPS
    panel.running = False


def test_activar_y_desactivar_desde_el_timer(fresh):
    app = fresh
    app.toggle_analyzer()
    assert app.conf["analizador"]["activo"] and app.analyzer
    app.toggle_analyzer()
    assert not app.conf["analizador"]["activo"] and not app.analyzer.visible


def test_menu_del_panel(panel, monkeypatch):
    import tkinter as tk
    monkeypatch.setattr(tk.Menu, "tk_popup", lambda *a, **k: None)
    ev = type("E", (), {"x_root": 10, "y_root": 10, "x": 5, "y": 5})()
    panel.show_menu(ev)
    for k in ("tema", "rgb"):
        panel.set_wave_color(k)
    for k, _ in G.MODULES:
        panel.set_module(k, False)
        panel.set_module(k, True)
    assert all(panel.app.conf["analizador"]["modulos"].values())


def test_no_se_puede_apagar_el_ultimo_modulo(panel):
    for k, _ in G.MODULES[:-1]:
        panel.set_module(k, False)
    panel.set_module(G.MODULES[-1][0], False)
    assert any(panel.app.conf["analizador"]["modulos"].values())
    for k, _ in G.MODULES:
        panel.set_module(k, True)


def test_diagnostico(panel):
    panel.open_diag()
    d = [w for w in panel.app.root.winfo_children() if isinstance(w, G.Diagnostico)]
    assert d
    d[0]._tick()
    d[0].destroy()


@pytest.mark.parametrize("dx,dy", [(200, 0), (-300, 50), (0, -9999), (5000, 5000)])
def test_mover_el_panel(panel, dx, dy):
    rebuild(panel, 900, 172, MODS)
    panel.win.update_idletasks()
    x0, y0 = panel.win.winfo_x(), panel.win.winfo_y()
    ev = type("E", (), {"x_root": x0 + 300, "y_root": y0 + 80, "x": 300, "y": 80})()
    panel.on_press(ev)
    ev2 = type("E", (), {"x_root": x0 + 300 + dx, "y_root": y0 + 80 + dy, "x": 0, "y": 0})()
    panel.on_drag(ev2)
    panel.on_release(ev2)
    a = panel.app.conf["analizador"]
    sw, sh = panel.win.winfo_screenwidth(), panel.win.winfo_screenheight()
    assert -1 <= a["x"] <= sw - panel.W + 1 and -1 <= a["y"] <= sh - panel.H + 1


@pytest.mark.parametrize("dw,dh", [(300, 100), (-700, -150), (4000, 4000)])
def test_redimensionar_el_panel(panel, dw, dh):
    rebuild(panel, 900, 172, MODS)
    panel.win.update_idletasks()
    x0, y0 = panel.win.winfo_x(), panel.win.winfo_y()
    ev = type("E", (), {"x_root": x0 + panel.W - 3, "y_root": y0 + panel.H - 3,
                        "x": panel.W - 3, "y": panel.H - 3})()
    panel.on_press(ev)
    ev2 = type("E", (), {"x_root": ev.x_root + dw, "y_root": ev.y_root + dh, "x": 0, "y": 0})()
    panel.on_drag(ev2)
    panel.on_release(ev2)
    a = panel.app.conf["analizador"]
    assert a["w"] >= 200 and a["h"] >= 24
    prepare(panel)
    play(panel, noise(-12, 0.2, 48000))
