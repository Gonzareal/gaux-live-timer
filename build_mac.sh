#!/bin/bash
# Arma el instalador de Mac en TU Mac (alternativa a GitHub Actions).
# Uso:   cd <carpeta del proyecto> && bash build_mac.sh
# Necesita Python 3.10+ de python.org, y para el plugin: cmake (brew install cmake) y Xcode.
set -e
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
"$PY" - <<'PYEOF'
import sys, tkinter
v = sys.version_info
if v < (3, 10):
    sys.exit(f"Necesitas Python 3.10 o más nuevo (tienes {v.major}.{v.minor}). Instálalo desde python.org")
if tkinter.TkVersion < 8.6:
    sys.exit("Este Python trae una versión vieja de Tk. Instala Python desde python.org.")
PYEOF
command -v cmake >/dev/null || { echo "Falta cmake:  brew install cmake"; exit 1; }
VENV="$HOME/Library/Caches/GauxLiveTimer-armado"
echo "→ Preparando las herramientas (la primera vez tarda unos minutos)…"
"$PY" -m venv "$VENV"
"$VENV/bin/python" -m pip install --quiet --upgrade pip
"$VENV/bin/python" -m pip install --quiet "pyinstaller>=6.11" numpy sounddevice
PYTHON="$VENV/bin/python" bash package_mac.sh
open dist
