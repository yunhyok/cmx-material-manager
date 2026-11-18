#define Product "CMX Material Manager"
#define Binary Product + ".exe"
#define Source "..\dist\" + Product

[Setup]
AppId={{A04F2E34-9AE4-4942-934C-7A0DBED020C4}
AppName={#Product}
AppVersion={#AppVersion}
AppPublisher=yunhyok
VersionInfoVersion={#AppVersion}.0
DefaultDirName={autopf}\{#Product}
DefaultGroupName={#Product}
DisableProgramGroupPage=yes
DisableDirPage=no
PrivilegesRequired=admin
MinVersion=10.0.17763
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=CMX-Material-Manager-{#AppVersion}-windows-x64-setup
SetupIconFile=..\src\material_manager\assets\app.ico
UninstallDisplayIcon={app}\{#Binary}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#Source}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#Product}"; Filename: "{app}\{#Binary}"
Name: "{commondesktop}\{#Product}"; Filename: "{app}\{#Binary}"; Tasks: desktopicon
