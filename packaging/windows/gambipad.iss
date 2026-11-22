; Inno Setup script: turns dist\GambiPad (see build_exe.py) into GambiPad-Setup.exe.
;
;   iscc /DAppVersion=0.1.0 packaging\windows\gambipad.iss
;
; Installs for the current user only, so no administrator prompt is needed.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6B0E4C0E-6C7D-4E53-9B2B-5C6A7C1F9A41}
AppName=GambiPad
AppVersion={#AppVersion}
AppPublisher=agentkyo
AppPublisherURL=https://github.com/agentkyo/gambipad
AppSupportURL=https://github.com/agentkyo/gambipad/issues
DefaultDirName={localappdata}\Programs\GambiPad
DefaultGroupName=GambiPad
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\..\dist
OutputBaseFilename=GambiPad-Setup-{#AppVersion}
SetupIconFile=..\..\dist\GambiPad\gambipad.ico
UninstallDisplayIcon={app}\GambiPad.exe
LicenseFile=..\..\LICENSE
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[CustomMessages]
english.AutoStart=Start GambiPad with Windows (in the system tray)
brazilianportuguese.AutoStart=Iniciar o GambiPad com o Windows (na bandeja)
english.DesktopIcon=Create a desktop shortcut
brazilianportuguese.DesktopIcon=Criar um atalho na área de trabalho
english.MissingViGEm=GambiPad needs the ViGEmBus driver to create the virtual controller, and it is not installed.%n%nOpen the download page now?
brazilianportuguese.MissingViGEm=O GambiPad precisa do driver ViGEmBus para criar o controle virtual, e ele não está instalado.%n%nAbrir a página de download agora?
english.MissingHidHide=HidHide is not installed. Without it games see both the real and the virtual controller, and every press arrives twice.%n%nOpen the download page now?
brazilianportuguese.MissingHidHide=O HidHide não está instalado. Sem ele os jogos enxergam o controle real e o virtual, e cada aperto chega duas vezes.%n%nAbrir a página de download agora?

[Tasks]
Name: "autostart"; Description: "{cm:AutoStart}"
Name: "desktopicon"; Description: "{cm:DesktopIcon}"; Flags: unchecked

[Files]
Source: "..\..\dist\GambiPad\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\GambiPad"; Filename: "{app}\GambiPad.exe"
Name: "{userdesktop}\GambiPad"; Filename: "{app}\GambiPad.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "GambiPad"; ValueData: """{app}\GambiPad.exe"" gui --minimized"; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\GambiPad.exe"; Description: "{cm:LaunchProgram,GambiPad}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Make the real controller visible again before the program goes away.
Filename: "{app}\GambiPad.exe"; Parameters: "unhide"; Flags: runhidden; RunOnceId: "GambiPadUnhide"

[Code]
procedure OfferDriver(const Service, MessageName, Url: String);
var
  ErrorCode: Integer;
begin
  if RegKeyExists(HKLM, 'SYSTEM\CurrentControlSet\Services\' + Service) then
    exit;
  if WizardSilent then
    exit;
  if MsgBox(CustomMessage(MessageName), mbConfirmation, MB_YESNO) = IDYES then
    ShellExec('open', Url, '', '', SW_SHOWNORMAL, ewNoWait, ErrorCode);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    OfferDriver('ViGEmBus', 'MissingViGEm', 'https://github.com/nefarius/ViGEmBus/releases/latest');
    OfferDriver('HidHide', 'MissingHidHide', 'https://github.com/nefarius/HidHide/releases/latest');
  end;
end;
