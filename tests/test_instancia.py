"""Una sola instancia: abrir el timer otra vez (o reabrirlo tras actualizar) siempre funciona."""
import socket
import threading
import time

import pytest

import live_timer as L


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _serve(lock, got):
    """Como el timer abierto: acepta, lee el QUIT y cierra primero (deja TIME_WAIT)."""
    def run():
        while True:
            try:
                conn, _ = lock.accept()
            except OSError:
                return
            if conn.recv(16).startswith(b"QUIT"):
                got.append(True)
                conn.close()
                lock.close()
                return
            conn.close()
    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t


@pytest.fixture
def port(monkeypatch):
    p = _free_port()
    monkeypatch.setattr(L, "LOCK_PORT", p)
    return p


def test_primera_vez_toma_el_puerto(port):
    lock = L.acquire_lock(tries=3)
    assert lock is not None
    lock.close()


def test_otra_vez_reemplaza_y_no_choca_con_time_wait(port):
    """Abrir el timer con otro abierto: se le pide salir y el nuevo abre enseguida, aunque el
    cierre deje el puerto en TIME_WAIT (antes en Mac fallaba ~30 s: al actualizar no reabría)."""
    old = L.acquire_lock(tries=3)
    got = []
    _serve(old, got)
    # conexiones de "¿estás abierto?" que el viejo cierra primero (TIME_WAIT del lado del puerto)
    for _ in range(3):
        c = socket.create_connection(("127.0.0.1", port))
        c.close()
    time.sleep(0.2)
    t0 = time.monotonic()
    new = L.acquire_lock()
    assert got, "el timer viejo recibió el QUIT"
    assert new is not None, "el timer nuevo no pudo abrir"
    assert time.monotonic() - t0 < 5
    new.close()


@pytest.mark.parametrize("n", [2, 5])
def test_abrir_y_cerrar_seguido(port, n):
    """Reabrir varias veces seguidas (como al instalar una actualización)."""
    for _ in range(n):
        lock = L.acquire_lock()
        assert lock is not None
        got = []
        _serve(lock, got)
        c = socket.create_connection(("127.0.0.1", port))
        c.sendall(b"QUIT")
        c.close()
        deadline = time.monotonic() + 3
        while not got and time.monotonic() < deadline:
            time.sleep(0.05)
        assert got


def test_nunca_dos_escuchando(port):
    """Aunque se reuse la dirección, el sistema no deja dos timers escuchando a la vez."""
    a = L.acquire_lock(tries=2)
    try:
        b = socket.socket()
        if L.SYSTEM != "Windows":
            b.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        with pytest.raises(OSError):
            b.bind(("127.0.0.1", port))
            b.listen(1)
        b.close()
    finally:
        a.close()
