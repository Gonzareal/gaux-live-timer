"""Top Live en Mac: si falta el permiso de Accesibilidad, el timer lo dice claro, abre la lista
exacta de Ajustes del Sistema y pide a macOS que agregue el timer a esa lista."""
import pytest

import live_timer as L


@pytest.fixture
def mac(monkeypatch):
    calls = {"prompt": 0, "open": []}

    def trusted(prompt=False):
        if prompt:
            calls["prompt"] += 1
        return False
    monkeypatch.setattr(L, "SYSTEM", "Darwin")
    monkeypatch.setattr(L, "mac_ax_trusted", trusted)
    monkeypatch.setattr(L.subprocess, "Popen", lambda args, *a, **k: calls["open"].append(args))
    return calls


def _labels(w):
    out = []
    for c in w.winfo_children():
        try:
            out.append((c.cget("text"), c))
        except Exception:
            pass
        out += _labels(c)
    return out


def test_sin_permiso_muestra_la_guia(fresh, mac):
    app = fresh
    app.enter_top_mode()
    w = app._perm_win
    assert w.winfo_exists()
    texts = [t for t, _ in _labels(w)]
    assert "Abrir Accesibilidad" in texts and "Probar de nuevo" in texts
    assert any("Accesibilidad" in t and "interruptor" in t for t in texts)
    assert mac["prompt"] == 1, "macOS agrega el timer a la lista de Accesibilidad"
    assert not app.conf.get("top_mode")
    w.destroy()


def test_abrir_accesibilidad_va_directo_a_la_lista(fresh, mac):
    app = fresh
    app.enter_top_mode()
    app._perm_win.update()                     # en Windows el clic solo llega a ventanas ya visibles
    btn = dict(_labels(app._perm_win))["Abrir Accesibilidad"]
    btn.event_generate("<Button-1>")
    assert ["open", L.AX_SETTINGS_URL] in mac["open"]
    assert "Privacy_Accessibility" in L.AX_SETTINGS_URL
    app._perm_win.destroy()


def test_probar_de_nuevo_reintenta(fresh, mac, monkeypatch):
    app = fresh
    app.enter_top_mode()
    seen = []
    monkeypatch.setattr(app, "toggle_top_mode", lambda: seen.append(1))
    app._perm_win.update()
    dict(_labels(app._perm_win))["Probar de nuevo"].event_generate("<Button-1>")
    app.root.after(300, lambda: None)
    import time
    t = time.time()
    while not seen and time.time() - t < 2:
        app.root.update()
    assert seen


def test_una_sola_guia_aunque_se_insista(fresh, mac):
    app = fresh
    app.enter_top_mode()
    first = app._perm_win
    app.enter_top_mode()
    assert app._perm_win is first
    first.destroy()


def test_mover_el_daw_sin_permiso_avisa_con_la_guia(fresh, mac, monkeypatch):
    monkeypatch.setattr(L, "LIVE_PID", [1234])
    monkeypatch.setattr(L, "_AXWIN_OK", True, raising=False)
    with pytest.raises(L.LiveWindowError) as e:
        L._ax_try(lambda pid: [])
    assert str(e.value) == L.PERMISO_MAC


def test_bienvenida_con_boton_de_permiso(fresh, mac):
    app = fresh
    app.show_welcome(True)
    wins = [w for w in app.root.winfo_children() if w.winfo_class() == "Toplevel"]
    texts = [t for w in wins for t, _ in _labels(w)]
    assert "Dar permiso" in texts
    assert not any("System Events" in t for t in texts)
    for w in wins:
        w.destroy()


def test_el_texto_no_pide_system_events():
    assert "System Events" not in L.PERMISO_MAC
    assert "Accesibilidad" in L.PERMISO_MAC
