; Установщик AxAI (Inno Setup). Собирается в GitHub Actions, см. .github/workflows/build-windows.yml
; Путь относительно этого файла: корень репозитория = ..\..
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppName=AxAI
AppVersion={#AppVersion}
AppPublisher=AxAI
DefaultDirName={autopf}\AxAI
DefaultGroupName=AxAI
PrivilegesRequired=lowest
OutputDir=..\..\installer_out
OutputBaseFilename=AxAI-Setup
SetupIconFile=..\..\build\axai.ico
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\AxAI.exe

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Ярлыки:"

[Files]
; сама программа
Source: "..\..\dist\AxAI\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
; офлайн-модели сразу в хранилище пользователя; уже установленные файлы не затираем, при удалении программы не трогаем
Source: "..\..\build\models\*"; DestDir: "{%USERPROFILE}\AxAI_Storage\models"; Flags: recursesubdirs createallsubdirs onlyifdoesntexist uninsneveruninstall

[Icons]
Name: "{autoprograms}\AxAI"; Filename: "{app}\AxAI.exe"
Name: "{autodesktop}\AxAI"; Filename: "{app}\AxAI.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\AxAI.exe"; Description: "Запустить AxAI"; Flags: nowait postinstall skipifsilent
