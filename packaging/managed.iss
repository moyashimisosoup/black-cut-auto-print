#ifndef BuildVersion
  #error BuildVersion must be supplied
#endif
#ifndef BuildExe
  #error BuildExe must be supplied
#endif
#ifndef LicenseFile
  #error LicenseFile must be supplied
#endif
[Setup]
AppId=APP-033-BlackCutPrint
AppName=BlackCutPrint
AppVersion={#BuildVersion}
DefaultDirName={localappdata}\Programs\BlackCutPrint
DisableDirPage=yes
UsePreviousAppDir=no
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=no
RestartApplications=no
AppMutex=Local\APP033-BlackCutPrint
OutputBaseFilename=BlackCutPrint-Setup-{#BuildVersion}
Compression=lzma2
SolidCompression=yes
UninstallDisplayIcon={app}\BlackCutPrint.exe

[Files]
Source: "{#BuildExe}"; DestDir: "{app}"; DestName: "BlackCutPrint.exe"; Flags: ignoreversion
Source: "{#LicenseFile}"; DestDir: "{app}"; DestName: "WinSparkle-LICENSE.txt"; Flags: ignoreversion

[Icons]
Name: "{userprograms}\BlackCutPrint"; Filename: "{app}\BlackCutPrint.exe"

[Run]
Filename: "{app}\BlackCutPrint.exe"; Flags: nowait

[Code]
function InitializeSetup(): Boolean;
var I: Integer;
begin
  { Wait for WinSparkle's shutdown callback. Never forcibly terminate printing. }
  for I := 1 to 120 do
  begin
    if not CheckForMutexes('Local\APP033-BlackCutPrint') then
    begin
      Result := True;
      exit;
    end;
    Sleep(500);
  end;
  Result := False;
end;
