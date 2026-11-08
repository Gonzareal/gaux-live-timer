# ============================================================
#  Gaux Live Timer - instalador para Windows (app + plugin Gaux Link)
#  Uso: powershell -ExecutionPolicy Bypass -File package_windows.ps1   (lo corre GitHub Actions)
#  Necesita: Python 3.10+ con pyinstaller, numpy, sounddevice y psutil; Visual Studio 2022 (C++);
#            Inno Setup 6.
#  Resultado: dist\GauxLiveTimer_v<versión>_Windows.zip
# ============================================================
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$root = (Get-Location).Path
$py = if ($env:PYTHON) { $env:PYTHON } else { 'python' }

$m = Select-String -Path live_timer.py -Pattern '^VERSION = "(.+)"'
$version = $m.Matches[0].Groups[1].Value
$name = "GauxLiveTimer_v${version}_Windows"
$dist = Join-Path $root "dist\$name"
Write-Host "`n=== Gaux Live Timer ${version}: instalador para Windows ===`n"

$iscc = (Get-Command iscc -ErrorAction SilentlyContinue).Source
foreach ($p in @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe", "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe")) {
    if (-not $iscc -and (Test-Path $p)) { $iscc = $p }
}
if (-not $iscc) { throw 'No encuentro Inno Setup 6 (https://jrsoftware.org/isdl.php)' }

# --- 1) la app ---
& $py -m PyInstaller --noconfirm --clean --log-level WARN --distpath build-app\dist --workpath build-app\work GauxLiveTimer.spec
if ($LASTEXITCODE) { throw 'Fallo PyInstaller' }
$appDir = Join-Path $root 'build-app\dist\Gaux Live Timer'
if (-not (Test-Path -LiteralPath "$appDir\Gaux Live Timer.exe")) { throw 'No se genero Gaux Live Timer.exe' }

# --- 2) el plugin ---
cmake -S link -B build-link -A x64 -DCMAKE_BUILD_TYPE=Release
if ($LASTEXITCODE) { throw 'Fallo la configuracion del plugin' }
cmake --build build-link --config Release --parallel --target GauxLink_VST3
if ($LASTEXITCODE) { throw 'Fallo la compilacion del plugin' }
$linkDir = Join-Path $root 'build-link\GauxLink_artefacts\Release'
if (-not (Test-Path -LiteralPath "$linkDir\VST3\Gaux Link.vst3")) { throw 'No se genero Gaux Link.vst3' }

# --- 3) instalador ---
if (Test-Path -LiteralPath $dist) { Remove-Item -LiteralPath $dist -Recurse -Force }
New-Item -ItemType Directory -Path $dist | Out-Null
& $iscc /Q "/DAppVersion=$version" "/DAppDir=$appDir" "/DLinkDir=$linkDir" "/DOutDir=$dist" 'packaging\windows\GauxLiveTimer.iss'
if ($LASTEXITCODE) { throw 'Fallo Inno Setup' }

# --- 4) textos, licencia y código fuente ---
Copy-Item -LiteralPath 'packaging\ANTES DE INSTALAR - Windows.txt' -Destination $dist
Copy-Item -LiteralPath 'packaging\LICENCIA.txt' -Destination $dist
if ((Get-Command git -ErrorAction SilentlyContinue) -and (Test-Path .git)) {
    & git archive --format=zip --prefix=GauxLiveTimer/ -o (Join-Path $dist 'GauxLiveTimer_codigo_fuente.zip') HEAD
}
$zip = Join-Path $root "dist\$name.zip"
if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip }
Compress-Archive -Path $dist -DestinationPath $zip
Write-Host "`n=== Listo: $zip ===`n"
