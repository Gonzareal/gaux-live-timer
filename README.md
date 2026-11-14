# Gaux Live Timer

Cuenta el tiempo que **de verdad** produces en tu DAW: solo mientras el DAW está al frente y usas el teclado o el mouse. Metas diarias, semanales y mensuales; horas por proyecto; modo con descansos; franja **Top Live** sobre tu DAW y un analizador de audio (onda, espectro, stereo y loudness). Hecho por **Aleksander Gaux**.

Incluye **Gaux Link**, un plugin (VST3 / AU) que se pone al final del Master y le pasa el audio al analizador, sin BlackHole ni VB-Cable.

## Descargar

| | |
|---|---|
| **Mac** (Apple Silicon, macOS 12+) | [GauxLiveTimer_Mac.zip](https://github.com/Gonzareal/gaux-live-timer/raw/instalador-mac/GauxLiveTimer_Mac.zip) |
| **Windows** (10/11, 64 bits) | [GauxLiveTimer_Windows.zip](https://github.com/Gonzareal/gaux-live-timer/raw/instalador-windows/GauxLiveTimer_Windows.zip) |

Son los últimos instaladores probados (se actualizan solos con cada cambio). Cada zip trae un **ANTES DE INSTALAR** con los pasos: como no están firmados con cuentas pagas, la primera vez macOS y Windows muestran un aviso que se salta en dos clics.

## Cómo funciona

- `live_timer.py`: la app (Python + Tk). `gaux_analizador.py`: el analizador.
- `link/`: el plugin Gaux Link (C++ / JUCE). Envía el audio por UDP a `127.0.0.1:47654` (protocolo en `link/Source/LinkProtocol.h`).
- `GauxLiveTimer.spec`: empaquetado con PyInstaller.
- `package_mac.sh` / `package_windows.ps1`: arman los instaladores; `.github/workflows/instaladores.yml` los corre en GitHub en Mac y Windows reales, los instala, abre la app, valida el plugin con pluginval y publica los zip.

La guía completa de uso está en [LEEME.md](LEEME.md).

## Pruebas

`tests/` tiene más de 1400 pruebas automáticas que corren en Mac, Windows y Linux en cada cambio
(pestaña *Actions → Pruebas*). Cubren las 3 vistas × 2 orientaciones × 7 estilos en todos los
tamaños, el modo Top Live (también en pantalla completa con notch), los 15 DAWs compatibles
(nombres de proceso y títulos de ventana), el conteo y los proyectos (crear, renombrar, unir,
eliminar, exportar), los descansos y metas, todas las páginas de Ajustes, el analizador (LUFS
según EBU R128, true peak, espectro, espectrograma, onda, stereo) y Gaux Link por UDP. En Mac y
Windows además se abren apps con el nombre de cada DAW para comprobar que las reconoce.

```
pip install numpy psutil pytest pytest-timeout
python -m pytest tests          # en Linux: xvfb-run -a python -m pytest tests
```

## Licencia

Software libre bajo la **GNU AGPLv3** (Gaux Link usa JUCE bajo esa licencia). Ver `packaging/LICENCIA.txt`.
