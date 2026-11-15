# openTARS para Windows: instala sem administrador, só na pasta do usuário.
#
#   irm https://raw.githubusercontent.com/project-opentars/OpenTARS/main/app/empacotamento/windows/instalar.ps1 | iex
#
# Desde 14/11/2026 o openTARS do Windows é um app pronto (Python, Qt e o motor llama.cpp dentro). Este script só baixa o
# instalador da última Release (opentars-setup.exe), confere o SHA-256 no SHA256SUMS da mesma Release e o roda em silêncio.
# Quem tinha a instalação antiga por script (código e Python em %LOCALAPPDATA%\openTARS) passa para o app pronto: o
# instalador apaga o código e o Python antigos e mantém as conversas, as configurações e os modelos.
# Rodar de novo atualiza. Remover:
#   & ([scriptblock]::Create((irm https://raw.githubusercontent.com/project-opentars/OpenTARS/main/app/empacotamento/windows/instalar.ps1))) -Remover
param(
    [switch]$Remover,
    [string]$Fonte = "",        # aceito por compatibilidade (não usado: o instalador vem pronto da Release)
    [switch]$SemOllama,         # aceito por compatibilidade (o Ollama saiu em 14/11)
    [switch]$ComOllama          # aceito por compatibilidade (o Ollama saiu em 14/11)
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"        # a barra do Invoke-WebRequest deixa o download muito lento no PowerShell 5.1

$Release = if ($env:OPENTARS_RELEASE) { $env:OPENTARS_RELEASE } else { "https://github.com/project-opentars/OpenTARS/releases/latest/download" }   # o CI aponta para os arquivos que acabou de montar
$Instalado = Join-Path $env:LOCALAPPDATA "Programs\openTARS"
$Antigo = Join-Path $env:LOCALAPPDATA "openTARS"
$Pt = (Get-Culture).Name -like "pt*"

function Dizer($pt, $en) { if ($Pt) { Write-Host "[openTARS] $pt" } else { Write-Host "[openTARS] $en" } }

if ($Remover) {
    $desinstalador = Join-Path $Instalado "unins000.exe"
    if (Test-Path $desinstalador) {
        Start-Process -FilePath $desinstalador -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES" -Wait
    }
    # a instalação antiga por script, se ainda existir
    Get-Process pythonw, python -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$Antigo\venv*" } | Stop-Process -Force
    foreach ($p in "app", "venv", "bin") { Remove-Item -Recurse -Force (Join-Path $Antigo $p) -ErrorAction SilentlyContinue }
    Remove-Item -Force (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup\opentars-assistente.lnk") -ErrorAction SilentlyContinue
    Dizer "Removido. Suas conversas, configurações e modelos ficaram em $env:APPDATA\opentars e $env:LOCALAPPDATA\opentars." `
          "Removed. Your chats, settings and models stay in $env:APPDATA\opentars and $env:LOCALAPPDATA\opentars."
    return
}

$temp = Join-Path $env:TEMP ("opentars-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $temp | Out-Null
try {
    $setup = Join-Path $temp "opentars-setup.exe"
    Dizer "Baixando o openTARS (cerca de 200 MB, a barra mostra o andamento)..." "Downloading openTARS (about 200 MB, the bar shows the progress)..."
    # o curl.exe vem com o Windows 10 e 11 e mostra o andamento; o Invoke-WebRequest fica de reserva
    if (Get-Command curl.exe -ErrorAction SilentlyContinue) {
        & curl.exe -L --fail --retry 3 --progress-bar -o $setup "$Release/opentars-setup.exe"
        if ($LASTEXITCODE) { throw "download failed ($LASTEXITCODE)" }
    } else {
        Invoke-WebRequest -UseBasicParsing -Uri "$Release/opentars-setup.exe" -OutFile $setup
    }
    $arqSomas = Join-Path $temp "SHA256SUMS"
    if (Get-Command curl.exe -ErrorAction SilentlyContinue) {
        & curl.exe -fsSL --retry 3 -o $arqSomas "$Release/SHA256SUMS"
        if ($LASTEXITCODE) { throw "SHA256SUMS download failed ($LASTEXITCODE)" }
    } else {
        Invoke-WebRequest -UseBasicParsing -Uri "$Release/SHA256SUMS" -OutFile $arqSomas
    }
    $somas = Get-Content -Raw $arqSomas
    $esperado = ($somas -split "`n" | Where-Object { $_ -match "\sopentars-setup\.exe\s*$" } | ForEach-Object { ($_ -split "\s+")[0] }) | Select-Object -First 1
    $obtido = (Get-FileHash -Algorithm SHA256 $setup).Hash.ToLower()
    if (-not $esperado -or $obtido -ne $esperado.ToLower()) { throw "SHA-256 check failed: $obtido" }
    Dizer "Conferido (SHA-256). Instalando, sem pedir nada..." "Verified (SHA-256). Installing, no questions asked..."
    $p = Start-Process -FilePath $setup -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/REABRIR=1" -Wait -PassThru
    if ($p.ExitCode -ne 0) { throw "setup exit code $($p.ExitCode)" }
} finally {
    Remove-Item -Recurse -Force $temp -ErrorAction SilentlyContinue
}

Dizer "Pronto. O openTARS está no Menu Iniciar (na primeira vez ele baixa o Gargantua 2.5, com barra)." `
      "Done. openTARS is in the Start menu (the first time it downloads Gargantua 2.5, with a progress bar)."
Dizer "Num terminal NOVO: 'opentars --diagnostico' confere tudo e 'opentars --prova' mede a IA." `
      "In a NEW terminal: 'opentars --diagnostico' checks everything and 'opentars --prova' measures the AI."
