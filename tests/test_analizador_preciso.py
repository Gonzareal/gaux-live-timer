"""Analizador a fondo: precisión de LUFS en todo el espectro, tiempos de respuesta de los
medidores, true peak con cualquier fase, espectro y espectrograma en muchas frecuencias y
Gaux Link bombardeado con paquetes al azar."""
import math
import random
import struct
import time

import numpy as np
import pytest

import gaux_analizador as G
from test_analizador import (SRS, gxhi, gxlk, link, loud_of, noise, panel, pixel,  # noqa: F401
                             play, prepare, rebuild, reset_link, sender, sine, wait)

FREQS = [31.5, 63, 125, 250, 500, 1000, 2000, 4000, 8000, 12500, 16000]


def k_gain_db(f, sr):
    """Ganancia de la curva K (BS.1770) a la frecuencia f, con la fórmula del propio filtro."""
    return 10 * math.log10(float(G.k_weight_power(np.array([f]), sr)[0]))


@pytest.mark.parametrize("sr", SRS)
@pytest.mark.parametrize("f", FREQS)
def test_lufs_sigue_la_curva_k(sr, f):
    if f > sr * 0.45:
        pytest.skip("por encima de Nyquist")
    db = -20
    got = loud_of(sine(f, db, 4, sr), sr).integrated()
    # seno en 2 canales: LUFS = nivel de pico - 3.01 + 3.01 (dos canales) + ganancia K
    expect = db + k_gain_db(f, sr) - k_gain_db(997, sr)
    assert got == pytest.approx(expect, abs=0.35), (got, expect)


@pytest.mark.parametrize("sr", [44100, 48000])
@pytest.mark.parametrize("gain", [0, -5, -10, -15, -20, -25, -30, -35])
def test_lufs_lineal_con_la_ganancia(sr, gain):
    """Bajar 5 dB la señal baja exactamente 5 LU (ruido, como la música real)."""
    ref = loud_of(noise(-12, 6, sr, seed=3), sr).integrated()
    got = loud_of(noise(-12 + gain, 6, sr, seed=3), sr).integrated()
    assert got - ref == pytest.approx(gain, abs=0.1)


@pytest.mark.parametrize("sr", SRS)
def test_momentary_responde_en_400ms(sr):
    Lo = G.Loudness(sr)
    x = np.concatenate([np.zeros((sr * 2, 2), np.float32), sine(997, -20, 1.0, sr)])
    seen = []
    for i in range(0, len(x) - Lo.n + 1, Lo.n):
        Lo.push(x[i:i + Lo.n])
        seen.append((i + Lo.n) / sr)
        if Lo.momentary() > -20.3:
            break
    assert 2.35 <= seen[-1] <= 2.55, seen[-1]


@pytest.mark.parametrize("sr", [44100, 48000])
def test_short_term_responde_en_3s(sr):
    Lo = G.Loudness(sr)
    x = np.concatenate([np.zeros((sr * 3, 2), np.float32), sine(997, -20, 4.0, sr)])
    t_hit = None
    for i in range(0, len(x) - Lo.n + 1, Lo.n):
        Lo.push(x[i:i + Lo.n])
        if Lo.short_term() > -20.05:
            t_hit = (i + Lo.n) / sr
            break
    assert t_hit is not None and 5.9 <= t_hit <= 6.15, t_hit


@pytest.mark.parametrize("phase", [i * math.pi / 12 for i in range(12)])
@pytest.mark.parametrize("frac", [0.25, 0.4, 0.45])
def test_true_peak_cualquier_fase(phase, frac):
    """Picos entre muestras: el true peak nunca se queda más de 0.6 dB corto (4x oversampling)."""
    sr = 48000
    x = sine(sr * frac, -1, 0.5, sr, phase=phase)
    Lo = G.Loudness(sr)
    Lo.push(x[:Lo.n])            # el arranque brusco desde silencio sí tiene un pico real:
    Lo.tp_max = -math.inf        # se mide la señal ya estable
    for i in range(Lo.n, len(x) - Lo.n + 1, Lo.n):
        Lo.push(x[i:i + Lo.n])
    assert -1.5 <= Lo.tp_max <= -0.95, Lo.tp_max


@pytest.mark.parametrize("db", [-1, -6, -12, -24])
def test_true_peak_de_un_click(db):
    sr = 48000
    x = np.zeros((sr, 2), np.float32)
    x[sr // 2] = 10 ** (db / 20)
    Lo = loud_of(x, sr)
    assert Lo.tp_max == pytest.approx(db, abs=0.6)


ESPECTRO = [40, 55, 80, 110, 160, 220, 330, 440, 660, 880, 1300, 1800, 2600, 3500, 5000,
            7000, 9500, 14000, 17000]


@pytest.mark.parametrize("f", ESPECTRO)
def test_espectro_cada_frecuencia(panel, f):
    rebuild(panel, 1400, 172, ["spec"])
    prepare(panel)
    play(panel, sine(f, -6, 1.0, 48000))
    i = int(np.argmin(panel.spec_yv))
    assert panel.fpts[i] == pytest.approx(f, rel=0.1)


@pytest.mark.parametrize("db,orden", [(-6, 0), (-18, 1), (-36, 2)])
def test_espectro_mas_fuerte_mas_alto(panel, db, orden):
    rebuild(panel, 1400, 172, ["spec"])
    prepare(panel)
    play(panel, sine(1000, db, 1.0, 48000))
    test_espectro_mas_fuerte_mas_alto.tops = getattr(test_espectro_mas_fuerte_mas_alto,
                                                     "tops", {})
    test_espectro_mas_fuerte_mas_alto.tops[orden] = float(np.min(panel.spec_yv))
    tops = test_espectro_mas_fuerte_mas_alto.tops
    if orden > 0 and orden - 1 in tops:
        assert tops[orden] > tops[orden - 1], "más suave = más abajo"


@pytest.mark.parametrize("f", [60, 200, 500, 2000, 5000, 12000])
def test_espectrograma_cada_frecuencia(panel, f):
    rebuild(panel, 1200, 300, ["spec"])
    prepare(panel)
    bg = tuple(int(c) for c in panel.sg_lut[0])
    play(panel, sine(f, -3, 1.0, 48000))
    sg = panel.sgram
    col = (sg.wp - 2) % sg.w
    row = int(np.argmin(np.abs(np.log10(panel.frows) - math.log10(f))))
    assert pixel(sg, col, row) != bg


@pytest.mark.parametrize("f1,f2", [(100, 5000), (300, 3000), (80, 12000)])
def test_espectrograma_dos_tonos(panel, f1, f2):
    """Un acorde de dos tonos: se ven las dos líneas, separadas."""
    rebuild(panel, 1200, 300, ["spec"])
    prepare(panel)
    bg = tuple(int(c) for c in panel.sg_lut[0])
    play(panel, sine(f1, -9, 1.0, 48000) + sine(f2, -9, 1.0, 48000))
    sg = panel.sgram
    col = (sg.wp - 2) % sg.w
    rows = [int(np.argmin(np.abs(np.log10(panel.frows) - math.log10(f)))) for f in (f1, f2)]
    for r in rows:
        assert pixel(sg, col, r) != bg
    mid = int(np.argmin(np.abs(np.log10(panel.frows) - (math.log10(f1) + math.log10(f2)) / 2)))
    assert sum(pixel(sg, col, mid)) < max(sum(pixel(sg, col, r)) for r in rows)


def _fuzz_packets(seed, n=12):
    rnd = random.Random(seed)
    good = gxlk(5, 0, 48000, sine(997, -6, 64 / 48000, 48000))
    hi = gxhi(5, 48000, "Ableton Live", "Master")
    out = []
    for _ in range(n):
        kind = rnd.random()
        if kind < 0.3:
            out.append(bytes(rnd.getrandbits(8) for _ in range(rnd.randint(0, 1500))))
        elif kind < 0.6:
            b = bytearray(good)
            for _ in range(rnd.randint(1, 12)):
                b[rnd.randrange(len(b))] = rnd.getrandbits(8)
            out.append(bytes(b))
        elif kind < 0.75:
            out.append(good[:rnd.randint(0, len(good))])
        elif kind < 0.9:
            b = bytearray(hi)
            b[rnd.randrange(4, len(b))] = rnd.getrandbits(8)
            out.append(bytes(b))
        else:
            hdr = b"GXLK" + bytes([1, rnd.choice([0, 1, 2, 3, 8, 255]), 0, 0])
            hdr += struct.pack("<IIII", rnd.getrandbits(32), rnd.getrandbits(32),
                               rnd.choice([0, 1, 8000, 48000, 384000, 2 ** 31]),
                               rnd.choice([0, 1, 64, 480, 4096, 2 ** 31]))
            out.append(hdr + bytes(rnd.getrandbits(8) for _ in range(rnd.randint(0, 900))))
    return out


@pytest.mark.parametrize("seed", range(60))
def test_link_resiste_paquetes_al_azar(link, sender, seed):
    reset_link(link)
    e = G.AudioEngine()
    e.sr = 48000
    G.LinkStream(e, link)
    n0 = link.packets
    for pkt in _fuzz_packets(seed):
        sender.sendto(pkt, ("127.0.0.1", G.LINK_PORT))
    time.sleep(0.15)                       # que el receptor termine de leer la ráfaga
    reset_link(link)
    e = G.AudioEngine()
    e.sr = 48000
    G.LinkStream(e, link)
    x = sine(440, -6, 256 / 48000, 48000)
    sender.sendto(gxlk(77, 0, 48000, x), ("127.0.0.1", G.LINK_PORT))
    assert wait(lambda: e.w >= 256), "Gaux Link dejó de recibir después del bombardeo"
    assert np.allclose(e.last(256), x, atol=1e-6)
    assert link.thread.is_alive()
    assert np.isfinite(e.last(256)).all()


@pytest.mark.parametrize("n", [1, 10, 200])
def test_link_muchos_paquetes_seguidos(link, sender, n):
    """Ráfagas: lo que llega se guarda en orden y sin huecos."""
    reset_link(link)
    e = G.AudioEngine()
    e.sr = 48000
    G.LinkStream(e, link)
    frames = 128
    x = sine(997, -6, frames * n / 48000, 48000)
    for i in range(n):
        sender.sendto(gxlk(88, i, 48000, x[i * frames:(i + 1) * frames]),
                      ("127.0.0.1", G.LINK_PORT))
    assert wait(lambda: e.w >= frames * n, 4.0)
    assert np.allclose(e.last(frames * n), x, atol=1e-6)


def test_link_nan_e_infinitos_no_rompen_los_medidores(link, sender):
    reset_link(link)
    e = G.AudioEngine()
    e.sr = 48000
    G.LinkStream(e, link)
    bad = np.full((256, 2), np.nan, np.float32)
    bad[::3] = np.inf
    sender.sendto(gxlk(91, 0, 48000, bad), ("127.0.0.1", G.LINK_PORT))
    assert wait(lambda: e.w >= 256)
    Lo = G.Loudness(48000)
    blk = e.last(e.w)
    for i in range(0, len(blk) - Lo.n + 1, Lo.n):
        Lo.push(blk[i:i + Lo.n])
    for v in (Lo.momentary(), Lo.short_term(), Lo.integrated(), Lo.tp_max):
        assert not math.isnan(v)


@pytest.mark.parametrize("n", [1, 5, 30])
def test_link_sobrevive_a_plugins_que_se_cierran(link, sender, n):
    """Un plugin saluda y se cierra enseguida (quitarlo de la pista, cerrar el set): la respuesta
    rebota y en Windows eso mataba la recepción. Gaux Link debe seguir recibiendo."""
    import socket
    for i in range(n):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.sendto(gxhi(300 + i, 48000, "Ableton Live", "Pista"), ("127.0.0.1", G.LINK_PORT))
        s.close()                                    # se va antes de recibir el GXAK
    time.sleep(0.3)
    reset_link(link)
    e = G.AudioEngine()
    e.sr = 48000
    G.LinkStream(e, link)
    x = sine(440, -6, 256 / 48000, 48000)
    sender.sendto(gxlk(78, 0, 48000, x), ("127.0.0.1", G.LINK_PORT))
    assert wait(lambda: e.w >= 256), "Gaux Link dejó de recibir después de los plugins cerrados"
    assert link.thread.is_alive()
