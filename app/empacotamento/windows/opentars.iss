; Instalador do openTARS para Windows (14/11/2026: o app vem pronto, com Python e dependências dentro; a instalação não baixa
; nada). Sem administrador, sem assinatura paga. Embrulha a pasta que o montar_pacote.py monta.
; Compilar (Windows, Inno Setup 6), depois do montar_pacote.py:
;   iscc /DVersao=5.3 /DPacote=..\..\..\dist\pacote\openTARS app\empacotamento\windows\opentars.iss
; A saída vai para dist\opentars-setup.exe (na pasta app).
;
; Atualização pelo app: ele baixa este setup.exe da Release, confere o SHA-256 e roda
;   opentars-setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /REABRIR=1
; O instalador fecha o openTARS aberto (Restart Manager), troca os arquivos e o reabre no fim.
#ifndef Versao
  #define Versao "0.0"
#endif
#ifndef Pacote
  #define Pacote "..\..\..\dist\pacote\openTARS"
#endif
[Setup]
; o mesmo AppId do setup.exe de antes: quem instalou por ele recebe este por cima, e o openTARS aparece uma vez só em Aplicativos
AppId={{C6BAED4F-7BE2-421A-A5D8-3516502824C6}
AppName=openTARS
UninstallDisplayName=openTARS
AppVersion={#Versao}
AppPublisher=project-opentars
AppPublisherURL=https://project-opentars.github.io/OpenTARS/
; metadados que o Windows mostra em Propriedades > Detalhes e que o Defender/SmartScreen leem: instalador sem editora,
; sem descrição e sem versão pontua pior na reputação do que um que se identifica
; versão de quatro partes nos metadados do .exe ("5.3" vira 5.3.0.0)
VersionInfoVersion={#Versao}.0.0
VersionInfoProductVersion={#Versao}.0.0
VersionInfoCompany=project-opentars
VersionInfoDescription=openTARS Setup
VersionInfoProductName=openTARS
VersionInfoCopyright=MIT License, project-opentars
VersionInfoOriginalFileName=opentars-setup.exe
AppSupportURL=https://github.com/project-opentars/OpenTARS/issues
DefaultDirName={localappdata}\Programs\openTARS
UsePreviousAppDir=no
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
PrivilegesRequired=lowest
OutputDir=..\..\dist
OutputBaseFilename=opentars-setup
SetupIconFile=opentars.ico
UninstallDisplayIcon={app}\app\empacotamento\windows\opentars.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=force
RestartApplications=no
ChangesEnvironment=yes

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "pt"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[InstallDelete]
; a versão nova substitui a anterior inteira (arquivo que saiu de uma versão não fica sobrando)
Type: filesandordirs; Name: "{app}\app"
Type: filesandordirs; Name: "{app}\runtime"
; a instalação antiga por script (instalar.ps1 de antes de 14/11): código e Python ficavam em %LOCALAPPDATA%\openTARS.
; As conversas, as configurações e os modelos ficam em %APPDATA%\opentars e %LOCALAPPDATA%\opentars\... e não são tocados.
Type: filesandordirs; Name: "{localappdata}\openTARS\app"
Type: filesandordirs; Name: "{localappdata}\openTARS\venv"
Type: filesandordirs; Name: "{localappdata}\openTARS\bin"
Type: filesandordirs; Name: "{localappdata}\openTARS-setup"

[Files]
Source: "{#Pacote}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\openTARS"; Filename: "{app}\runtime\pythonw.exe"; Parameters: "-m tars_qt"; WorkingDir: "{app}\app"; \
  IconFilename: "{app}\app\empacotamento\windows\opentars.ico"; Comment: "openTARS"; AppUserModelID: "project-opentars.openTARS"

[Registry]
; o comando "opentars" nos terminais novos (PATH do usuário)
Root: HKCU; Subkey: "Environment"; ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}\bin"; Check: PrecisaPath

[Run]
Filename: "{app}\runtime\pythonw.exe"; Parameters: "-m tars_qt"; WorkingDir: "{app}\app"; Description: "{cm:LaunchProgram,openTARS}"; \
  Flags: nowait postinstall skipifsilent
; atualização pelo próprio app (instalação silenciosa com /REABRIR=1): reabre o openTARS no fim
Filename: "{app}\runtime\pythonw.exe"; Parameters: "-m tars_qt"; WorkingDir: "{app}\app"; Flags: nowait runasoriginaluser; Check: Reabrir

[UninstallRun]
; fecha o openTARS e o motor que rodam desta pasta (só os desta pasta: outros llama-server e Pythons da pessoa ficam)
Filename: "powershell.exe"; Parameters: "-NoProfile -Command ""Get-Process | Where-Object {{ $_.Path -like '{app}\*' } | Stop-Process -Force"""; \
  Flags: runhidden waituntilterminated; RunOnceId: "FecharOpenTARS"

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
Type: files; Name: "{userstartup}\opentars-assistente.lnk"

[Code]
function Reabrir: Boolean;
begin
  Result := ExpandConstant('{param:REABRIR|0}') = '1';
end;

function PrecisaPath: Boolean;
var
  Atual: string;
begin
  if not RegQueryStringValue(HKCU, 'Environment', 'Path', Atual) then
    Result := True
  else
    Result := Pos(';' + Uppercase(ExpandConstant('{app}\bin')) + ';', ';' + Uppercase(Atual) + ';') = 0;
end;

procedure TirarDoPath(Pasta: string);
var
  Atual, Novo, Parte: string;
  P: Integer;
begin
  if not RegQueryStringValue(HKCU, 'Environment', 'Path', Atual) then
    Exit;
  Novo := '';
  Atual := Atual + ';';
  while Length(Atual) > 0 do
  begin
    P := Pos(';', Atual);
    Parte := Copy(Atual, 1, P - 1);
    Delete(Atual, 1, P);
    if (Parte <> '') and (CompareText(Parte, Pasta) <> 0) then
    begin
      if Novo <> '' then Novo := Novo + ';';
      Novo := Novo + Parte;
    end;
  end;
  RegWriteExpandStringValue(HKCU, 'Environment', 'Path', Novo);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Codigo: Integer;
  Filtro: String;
begin
  // fecha o que roda da versão anterior (o app, o motor e o llama-server, inclusive os da instalação antiga por script),
  // senão os arquivos ficam presos e o motor velho continua servindo depois da troca
  Filtro := '$_.Path -like ''' + ExpandConstant('{app}') + '\*'' -or $_.Path -like ''' + ExpandConstant('{localappdata}') +
            '\openTARS\venv\*'' -or $_.Path -like ''' + ExpandConstant('{localappdata}') + '\opentars\motor\*''';
  Exec('powershell.exe', '-NoProfile -Command "Get-Process | Where-Object { $_.Path -and (' + Filtro + ') } | Stop-Process -Force"',
       '', SW_HIDE, ewWaitUntilTerminated, Codigo);
  Result := '';
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    TirarDoPath(ExpandConstant('{localappdata}\openTARS\bin'));     // o comando da instalação antiga por script
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    TirarDoPath(ExpandConstant('{app}\bin'));
end;
