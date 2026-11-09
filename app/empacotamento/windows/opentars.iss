; Instalador .exe do openTARS para Windows: só embrulha o instalar.ps1 (que continua sendo a fonte de verdade), para o winget
; ter um instalador de verdade e para o openTARS aparecer em "Aplicativos instalados". Sem administrador, sem assinatura paga.
; Compilar (Windows, Inno Setup 6):  iscc /DVersao=5.3 windows\opentars.iss   (a saída vai para dist\opentars-setup.exe)
#ifndef Versao
  #define Versao "0.0"
#endif
[Setup]
AppId={{C6BAED4F-7BE2-421A-A5D8-3516502824C6}
AppName=openTARS
AppVersion={#Versao}
AppPublisher=project-opentars
AppPublisherURL=https://project-opentars.github.io/OpenTARS/
AppSupportURL=https://github.com/project-opentars/OpenTARS/issues
DefaultDirName={localappdata}\openTARS-setup
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\..\dist
OutputBaseFilename=opentars-setup
SetupIconFile=opentars.ico
UninstallDisplayIcon={localappdata}\openTARS\app\empacotamento\windows\opentars.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "instalar.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\*"; DestDir: "{app}\app"; Excludes: "tests,gargantua,docs,dist,__pycache__,*.pyc,.git"; Flags: ignoreversion recursesubdirs createallsubdirs

[Run]
; o instalar.ps1 faz o resto (Python pelo uv, dependências, atalhos, PATH); com /SemOllama o CI pula o download do Ollama
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\instalar.ps1"" -Fonte ""{app}\app""{code:SemOllama}"; \
  StatusMsg: "Instalando o openTARS (alguns minutos na primeira vez)..."; Flags: runhidden waituntilterminated

[UninstallRun]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\instalar.ps1"" -Remover"; Flags: runhidden waituntilterminated; RunOnceId: "RemoverOpenTARS"

[Code]
function SemOllama(Param: String): String;
begin
  if WizardSilent and (ExpandConstant('{param:SemOllama|0}') = '1') then Result := ' -SemOllama' else Result := '';
end;
