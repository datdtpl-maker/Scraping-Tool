; Inno Setup Script cho Derm Keyword Hunter Pro
#define MyAppName "Derm Keyword Hunter Pro"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Khai Hoan Digital"
#define MyAppExeName "DermKeywordHunter_Desktop.exe"
#define SourceDir "D:\Project Anti\Derm-Keyword-Hunter"

[Setup]
AppId={{E68A1B70-5F1A-48E2-A23C-9B63467BC92A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\DermKeywordHunter
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir={#SourceDir}\Cai_Dat
OutputBaseFilename=DermKeywordHunter_Setup_v1.0
SetupIconFile={#SourceDir}\logo.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#SourceDir}\dist\DermKeywordHunter_Desktop\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SourceDir}\logo.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\logo.ico"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\logo.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
