"""Calendario simulado: el timer cree que hoy es la fecha que la prueba diga."""
import datetime as _dt
import types

import live_timer as L

_REAL = L.dt
_NOW = [None]


class FakeDate(_dt.date):
    @classmethod
    def today(cls):
        n = _NOW[0]
        return cls(n.year, n.month, n.day) if n else _dt.date.today()


class FakeDateTime(_dt.datetime):
    @classmethod
    def now(cls, tz=None):
        n = _NOW[0]
        return cls(n.year, n.month, n.day, n.hour, n.minute, n.second) if n \
            else _dt.datetime.now(tz)


def set_now(when):
    """when: datetime real (o None para volver al reloj del sistema)."""
    _NOW[0] = when
    L.dt = types.SimpleNamespace(date=FakeDate, datetime=FakeDateTime,
                                 timedelta=_dt.timedelta) if when else _REAL


def advance(secs):
    if _NOW[0] is not None:
        set_now(_NOW[0] + _dt.timedelta(seconds=secs))


def restore():
    set_now(None)
