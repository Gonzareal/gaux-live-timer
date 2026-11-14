"""Formatos de tiempo, mezcla de ajustes y lectura/escritura de archivos."""
import json
import math
import os

import pytest

import live_timer as L


@pytest.mark.parametrize("s,out", [
    (0, "00:00:00"), (1, "00:00:01"), (59, "00:00:59"), (60, "00:01:00"), (61.9, "00:01:01"),
    (3599, "00:59:59"), (3600, "01:00:00"), (36000, "10:00:00"), (86399, "23:59:59"),
    (360000, "100:00:00"), (-0.5, "00:00:00"),
])
def test_fmt_clock(s, out):
    assert L.fmt_clock(s) == out


@pytest.mark.parametrize("s,out", [
    (0, "0m"), (59, "0m"), (60, "1m"), (3599, "59m"), (3600, "1h 00m"), (3660, "1h 01m"),
    (36000, "10h 00m"), (12236.08, "3h 23m"), (360000, "100h 00m"),
])
def test_fmt_short(s, out):
    assert L.fmt_short(s) == out


@pytest.mark.parametrize("s,out", [
    (0, "0m"), (60, "1m"), (1800, "30m"), (3600, "1h"), (5400, "1h 30m"), (4 * 3600, "4h"),
    (20 * 3600, "20h"), (80 * 3600, "80h"), (3661, "1h 1m"),
])
def test_fmt_goal(s, out):
    assert L.fmt_goal(s) == out


@pytest.mark.parametrize("s,out", [
    (0, "0m"), (1, "1m"), (59, "1m"), (60, "1m"), (61, "2m"), (3599, "1h 00m"),
    (-30, "0m"), (3601, "1h 01m"),
])
def test_fmt_ceil(s, out):
    assert L.fmt_ceil(s) == out


@pytest.mark.parametrize("s,out", [
    (0, "0:00"), (5, "0:05"), (65, "1:05"), (299.9, "4:59"), (300, "5:00"), (-4, "0:00"),
    (3600, "60:00"),
])
def test_fmt_mmss(s, out):
    assert L.fmt_mmss(s) == out


@pytest.mark.parametrize("over,key,val", [
    ({}, "tema", "noche"),
    ({"tema": "gaux"}, "tema", "gaux"),
    ({"metas": {"diaria": {"segundos": 7200}}}, ("metas", "diaria", "segundos"), 7200),
    ({"metas": {"diaria": {"segundos": 7200}}}, ("metas", "diaria", "activa"), True),
    ({"metas": {"diaria": {"segundos": 7200}}}, ("metas", "semanal", "segundos"), 72000),
    ({"autonomo": {"break_min": 10}}, ("autonomo", "trabajo_min"), 50),
    ({"analizador": {"modulos": {"spec": False}}}, ("analizador", "modulos", "wave"), True),
    ({"extra_viejo": 1}, "extra_viejo", 1),
])
def test_deep_merge(over, key, val):
    out = L.deep_merge(L.DEFAULT_CONF, over)
    keys = key if isinstance(key, tuple) else (key,)
    for k in keys:
        out = out[k]
    assert out == val


def test_deep_merge_no_toca_el_original():
    before = json.dumps(L.DEFAULT_CONF, sort_keys=True)
    out = L.deep_merge(L.DEFAULT_CONF, {"metas": {"diaria": {"segundos": 1}}})
    out["metas"]["semanal"]["segundos"] = 5
    assert json.dumps(L.DEFAULT_CONF, sort_keys=True) == before


@pytest.mark.parametrize("content", [
    "", "{", "null", "[]", "123", "\"texto\"", "{\"dias\": 5}", "\x00\x01\x02",
    "{\"a\": NaN}", "{" * 5000,
])
def test_load_json_dañado_no_revienta(tmp_path, content):
    p = tmp_path / "x.json"
    p.write_bytes(content.encode("utf-8", "ignore"))
    out = L.load_json(str(p))
    assert isinstance(out, dict)


def test_load_json_inexistente(tmp_path):
    assert L.load_json(str(tmp_path / "nada.json")) == {}


@pytest.mark.parametrize("data", [
    {}, {"a": 1}, {"ñ": "canción ✦ 🎧"}, {"n": list(range(1000))},
    {"proyectos": {"Westing Time With U": {"segundos": 1.5}}},
])
def test_save_y_load_json(tmp_path, monkeypatch, data):
    monkeypatch.setattr(L, "APP_DIR", str(tmp_path))
    p = str(tmp_path / "d.json")
    L.save_json(p, data)
    assert L.load_json(p) == data
    assert not os.path.exists(p + ".tmp")


def test_save_json_respalda_datos_dañados(tmp_path, monkeypatch):
    """Si datos.json se daña, no se pierde: queda una copia para recuperar las horas."""
    monkeypatch.setattr(L, "APP_DIR", str(tmp_path))
    p = tmp_path / "datos.json"
    p.write_text("{\"dias\": {\"2026-11-01\": 3600}, ")       # cortado a la mitad
    assert L.load_json(str(p)) == {}
    backups = [f for f in os.listdir(tmp_path) if f.startswith("datos.json.dañado")]
    assert backups, "el archivo dañado debe guardarse aparte antes de sobrescribirlo"


@pytest.mark.parametrize("a,b,t,out", [
    ("#000000", "#ffffff", 0, "#000000"), ("#000000", "#ffffff", 1, "#ffffff"),
    ("#000000", "#ffffff", .5, "#808080"), ("#FF0000", "#0000FF", .5, "#800080"),
])
def test_mix(a, b, t, out):
    assert L.mix(a, b, t).lower() == out


@pytest.mark.parametrize("tema", list(L.TEMAS))
def test_temas_completos(tema):
    T = L.TEMAS[tema]
    for k in ("nombre", "bg", "bg2", "borde", "acento", "acento2", "texto", "dim", "pista",
              "alpha"):
        assert k in T, k
    for k in ("bg", "bg2", "borde", "acento", "acento2", "texto", "dim", "pista"):
        assert len(L.hex2rgb(T[k])) == 3
    assert 0.3 <= T["alpha"] <= 1


@pytest.mark.parametrize("color", L.PERSONAL_COLORS + ["#000000", "#FFFFFF", "#123456"])
@pytest.mark.parametrize("forma", ["redondeada", "angular"])
def test_tema_personal(color, forma):
    T = L.build_personal_theme({"color": color, "forma": forma, "nombre": "Gaux"})
    assert T["personal"]
    for k in ("bg", "bg2", "borde", "acento", "acento2", "texto", "dim", "pista"):
        assert T[k].startswith("#") and len(T[k]) == 7


@pytest.mark.parametrize("bad", [None, "", "rojo", "#12", "#GGGGGG", 123, "#1234567"])
def test_tema_personal_color_invalido(bad):
    T = L.build_personal_theme({"color": bad})
    for k in ("bg", "borde", "acento"):
        assert T[k].startswith("#") and len(T[k]) == 7


def test_break_y_meta_no_negativos():
    for s in (-1e9, -1, 0, math.inf):
        try:
            L.fmt_mmss(s if s != math.inf else 1e12)
        except Exception as e:      # pragma: no cover
            pytest.fail(repr(e))
