# -*- mode: python ; coding: utf-8 -*-
# Receta de PyInstaller: "Gaux Live Timer.app" (macOS) y "Gaux Live Timer.exe" (Windows).
# La usan package_mac.sh, package_windows.ps1 y build_mac.sh.
import os
import re
import sys

ROOT = SPECPATH
VERSION = re.search(r'^VERSION = "(.+)"', open(os.path.join(ROOT, "live_timer.py"),
                                                encoding="utf-8").read(), re.M).group(1)
MAC = sys.platform == "darwin"
WIN = sys.platform.startswith("win")
ICON = os.path.join(ROOT, "app", "GauxLiveTimer.icns" if MAC else "GauxLiveTimer.ico")

a = Analysis(
    [os.path.join(ROOT, "live_timer.py")],
    pathex=[ROOT],
    hiddenimports=["gaux_analizador", "sounddevice", "_sounddevice_data", "numpy"]
                  + (["psutil"] if WIN else []),
    excludes=["matplotlib", "scipy", "pandas", "PIL", "IPython", "pytest", "setuptools"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Gaux Live Timer",
    console=False,               # sin Terminal ni consola
    argv_emulation=False,
    icon=ICON,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Gaux Live Timer")

if MAC:
    app = BUNDLE(
        coll,
        name="Gaux Live Timer.app",
        icon=ICON,
        bundle_identifier="com.aleksandergaux.livetimer",
        version=VERSION,
        info_plist={
            "CFBundleName": "Gaux Live Timer",
            "CFBundleDisplayName": "Gaux Live Timer",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "LSUIElement": True,                 # sin ícono en el Dock: vive sobre tu DAW
            "LSMinimumSystemVersion": "12.0",
            "NSHighResolutionCapable": True,
            "NSHumanReadableCopyright": "© 2026 Aleksander Gaux",
            "NSMicrophoneUsageDescription":
                "Solo si usas BlackHole en vez del plugin Gaux Link: macOS lo trata como "
                "micrófono. Gaux Live Timer no graba ni envía nada.",
            "NSAppleEventsUsageDescription":
                "Gaux Live Timer mueve la ventana de tu DAW para hacerle espacio a la franja "
                "Top Live.",
        },
    )
