#!/bin/bash
# ============================================================
#  Gaux Live Timer - instalador para Mac (.pkg con la app y el plugin Gaux Link)
#  Uso:  bash package_mac.sh        (lo corre GitHub Actions; también sirve en tu Mac)
#  Necesita: Python 3.10+ de python.org con pyinstaller, numpy y sounddevice; cmake y Xcode.
#  Resultado: dist/GauxLiveTimer_v<versión>_Mac.zip
# ============================================================
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"
PY="${PYTHON:-python3}"

VERSION="$(sed -n 's/^VERSION = "\(.*\)"/\1/p' live_timer.py)"
NAME="GauxLiveTimer_v${VERSION}_Mac"
WORK="build-pkg"
DIST="dist/$NAME"
echo ""
echo "=== Gaux Live Timer $VERSION: instalador para Mac ==="

# 1) La app
"$PY" -m PyInstaller --noconfirm --clean --log-level WARN \
      --distpath build-app/dist --workpath build-app/work GauxLiveTimer.spec
APP="build-app/dist/Gaux Live Timer.app"

# 2) El plugin Gaux Link (universal: Apple Silicon + Intel)
cmake -S link -B build-link -DCMAKE_BUILD_TYPE=Release -DCMAKE_OSX_ARCHITECTURES="arm64;x86_64"
cmake --build build-link --config Release --target GauxLink_VST3 GauxLink_AU -j "$(sysctl -n hw.ncpu)"
OUT="build-link/GauxLink_artefacts/Release"
VST3="$OUT/VST3/Gaux Link.vst3"
AU="$OUT/AU/Gaux Link.component"
for p in "$APP" "$VST3" "$AU"; do [ -e "$p" ] || { echo "ERROR: no se generó $p"; exit 1; }; done

# 3) Firma local (ad-hoc): obligatoria para que el código arm64 cargue
for p in "$VST3" "$AU" "$APP"; do
    xattr -cr "$p" 2>/dev/null || true
    codesign --force --deep --sign - "$p"
    codesign --verify --deep "$p"
done

# 4) Un paquete por componente (cada uno a su carpeta del sistema)
rm -rf "$WORK"; mkdir -p "$WORK"
make_component () {   # id  bundle  destino  nombre.pkg  [scripts]
    local id="$1" src="$2" dest="$3" pkg="$4" scripts="${5:-}"
    local root="$WORK/root-$id"
    mkdir -p "$root$dest"
    ditto "$src" "$root$dest/$(basename "$src")"
    pkgbuild --analyze --root "$root" "$WORK/$id.plist" >/dev/null
    local i=0
    while /usr/libexec/PlistBuddy -c "Print :$i" "$WORK/$id.plist" >/dev/null 2>&1; do
        /usr/libexec/PlistBuddy -c "Set :$i:BundleIsRelocatable false" "$WORK/$id.plist" 2>/dev/null \
            || /usr/libexec/PlistBuddy -c "Add :$i:BundleIsRelocatable bool false" "$WORK/$id.plist"
        i=$((i + 1))
    done
    # (bash 3.2 de macOS: sin arreglos vacíos con set -u)
    if [ -n "$scripts" ]; then
        pkgbuild --root "$root" --component-plist "$WORK/$id.plist" --identifier "$id" --version "$VERSION" \
                 --install-location "/" --scripts "$scripts" "$WORK/$pkg"
    else
        pkgbuild --root "$root" --component-plist "$WORK/$id.plist" --identifier "$id" --version "$VERSION" \
                 --install-location "/" "$WORK/$pkg"
    fi
}
make_component com.aleksandergaux.livetimer.app "$APP"  "/Applications"                     app.pkg  packaging/mac/scripts
make_component com.aleksandergaux.link.vst3     "$VST3" "/Library/Audio/Plug-Ins/VST3"       vst3.pkg packaging/mac/scripts
make_component com.aleksandergaux.link.au       "$AU"   "/Library/Audio/Plug-Ins/Components" au.pkg   packaging/mac/scripts

sed -e "s/@VERSION@/$VERSION/g" packaging/mac/distribution.xml > "$WORK/distribution.xml"
rm -rf "$DIST"; mkdir -p "$DIST"
productbuild --distribution "$WORK/distribution.xml" --resources packaging/mac --package-path "$WORK" \
             "$DIST/Gaux Live Timer.pkg"

# 5) Textos, licencia y código fuente (la licencia AGPLv3 de Gaux Link pide incluirlo)
cp "packaging/ANTES DE INSTALAR - Mac.txt" "$DIST/"
cp packaging/LICENCIA.txt "$DIST/"
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git archive --format=zip --prefix=GauxLiveTimer/ -o "$DIST/GauxLiveTimer_codigo_fuente.zip" HEAD
fi
(cd dist && rm -f "$NAME.zip" && ditto -c -k --sequesterRsrc --keepParent "$NAME" "$NAME.zip")
echo ""
echo "=== Listo: dist/$NAME.zip ==="
