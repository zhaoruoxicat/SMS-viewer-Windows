#ifndef AppVersion
  #define AppVersion "1.0.3"
#endif

[Setup]
AppId={{4D82DB77-245D-48A6-BE7C-46C9F0AF7892}
AppName=短信会话
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\SmsForwardClient
DefaultGroupName=短信会话
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist
OutputBaseFilename=sms-forward-client-{#AppVersion}-windows-x64-setup
SetupIconFile=..\build\windows\sms-client.ico
UninstallDisplayIcon={app}\SmsForwardClient.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "..\dist\SmsForwardClient\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\短信会话"; Filename: "{app}\SmsForwardClient.exe"
Name: "{autodesktop}\短信会话"; Filename: "{app}\SmsForwardClient.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\SmsForwardClient.exe"; Description: "Launch SMS Forward Client"; Flags: nowait postinstall skipifsilent
