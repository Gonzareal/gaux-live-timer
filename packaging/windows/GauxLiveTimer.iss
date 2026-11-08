; Gaux Live Timer - instalador para Windows (Inno Setup 6)
; Lo compila package_windows.ps1:
;   ISCC /DAppVersion=x.y /DAppDir=<carpeta de PyInstaller> /DLinkDir=<...\Release> /DOutDir=<...> GauxLiveTimer.iss

#ifndef AppVersion
  #define AppVersion "0.0"
#endif
#ifndef AppDir
  #define AppDir "..\..\build-app\dist\Gaux Live Timer"
#endif
#ifndef LinkDir
  #define LinkDir "..\..\build-link\GauxLink_artefacts\Release"
#endif
#ifndef OutDir
  #define OutDir "..\..\dist"
#endif

[Setup]
AppId={{56250BFD-6A48-4B25-ABC7-B5398E4BA6C3}
AppName=Gaux Live Timer
AppVersion={#AppVersion}
AppVerName=Gaux Live Timer {#AppVersion}
AppPublisher=Aleksander Gaux
DefaultDirName={autopf}\Gaux\Gaux Live Timer
DisableDirPage=yes
DisableProgramGroupPage=yes
DefaultGroupName=Gaux Live Timer
UninstallDisplayName=Gaux Live Timer
UninstallDisplayIcon={app}\Gaux Live Timer.exe
SetupIconFile=..\..\app\GauxLiveTimer.ico
OutputDir={#OutDir}
OutputBaseFilename=GauxLiveTimer_{#AppVersion}_Windows_Setup
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
PrivilegesRequired=admin
WizardStyle=modern
InfoBeforeFile=..\ANTES DE INSTALAR - Windows.txt
CloseApplications=yes

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Types]
Name: "full"; Description: "Completa (app + plugin Gaux Link)"
Name: "app"; Description: "Solo la app"
Name: "custom"; Description: "Personalizada"; Flags: iscustom

[Components]
Name: "app"; Description: "Gaux Live Timer (timer, metas, proyectos y analizador)"; Types: full app custom; Flags: fixed
Name: "link"; Description: "Gaux Link VST3: envía el audio de tu DAW al analizador (sin VB-Cable)"; Types: full

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el Escritorio"; Flags: unchecked

[InstallDelete]
; restos de una versión anterior
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{commoncf64}\VST3\Gaux Link.vst3"

[Files]
Source: "{#AppDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Components: app
Source: "{#LinkDir}\VST3\Gaux Link.vst3\*"; DestDir: "{commoncf64}\VST3\Gaux Link.vst3"; Flags: ignoreversion recursesubdirs createallsubdirs; Components: link
Source: "..\LICENCIA.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Gaux Live Timer"; Filename: "{app}\Gaux Live Timer.exe"
Name: "{autodesktop}\Gaux Live Timer"; Filename: "{app}\Gaux Live Timer.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Gaux Live Timer.exe"; Description: "Abrir Gaux Live Timer"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM ""Gaux Live Timer.exe"""; Flags: runhidden; RunOnceId: "CerrarTimer"

[UninstallDelete]
Type: filesandordirs; Name: "{commoncf64}\VST3\Gaux Link.vst3"
Type: files; Name: "{userstartup}\GauxLiveTimer.vbs"

[Messages]
es.FinishedLabel=Gaux Live Timer quedó instalado.%n%nPara el analizador: abre tu DAW, vuelve a escanear los plugins y pon Gaux Link al final del Master.
