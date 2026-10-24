# openTARS para Windows (5.2, experimental): instala sem administrador, só na pasta do usuário.
#
#   irm https://raw.githubusercontent.com/project-opentars/OpenTARS/main/app/empacotamento/windows/instalar.ps1 | iex
#
# O que faz: baixa o código do app (pasta app/ do repositório), instala o uv (um programa que traz o Python), cria um
# ambiente Python com as dependências, instala o Ollama se faltar (o instalador oficial, por usuário), cria o atalho
# no Menu Iniciar e os comandos opentars e opentars-gui. O modelo (Gargantua 2) é baixado na primeira abertura, com barra.
# Rodar de novo atualiza. Remover:
#   & ([scriptblock]::Create((irm https://raw.githubusercontent.com/project-opentars/OpenTARS/main/app/empacotamento/windows/instalar.ps1))) -Remover
# Suas conversas e configurações (em %APPDATA%\opentars) ficam; apague a pasta se quiser.
param(
    [switch]$Remover,
    [string]$Fonte = "",        # pasta app/ local em vez de baixar (o CI usa)
    [switch]$SemOllama          # não instala o Ollama (o CI usa)
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"        # a barra do Invoke-WebRequest deixa o download muito lento no 5.1

$Pasta = Join-Path $env:LOCALAPPDATA "openTARS"
$App = Join-Path $Pasta "app"
$Venv = Join-Path $Pasta "venv"
$Bin = Join-Path $Pasta "bin"
$MenuIniciar = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\openTARS.lnk"
$Inicializar = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup\opentars-assistente.lnk"
$Zip = "https://github.com/project-opentars/OpenTARS/archive/refs/heads/main.zip"
$Pt = (Get-Culture).Name -like "pt*"

function Dizer($pt, $en) { if ($Pt) { Write-Host "[openTARS] $pt" } else { Write-Host "[openTARS] $en" } }

function Tirar-Do-Path {
    $atual = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($atual) {
        $novo = ($atual -split ";" | Where-Object { $_ -and ($_ -ne $Bin) }) -join ";"
        [Environment]::SetEnvironmentVariable("Path", $novo, "User")
    }
}

if ($Remover) {
    Get-Process pythonw, python -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$Venv*" } | Stop-Process -Force
    Remove-Item -Recurse -Force $Pasta -ErrorAction SilentlyContinue
    Remove-Item -Force $MenuIniciar, $Inicializar -ErrorAction SilentlyContinue
    Tirar-Do-Path
    Dizer "Removido. Suas conversas e configurações ficaram em $env:APPDATA\opentars; o Ollama e os modelos também ficaram." `
          "Removed. Your chats and settings stay in $env:APPDATA\opentars; Ollama and the models stay too."
    return
}

Dizer "Instalando em $Pasta (sem administrador)." "Installing into $Pasta (no administrator needed)."
New-Item -ItemType Directory -Force -Path $Pasta, $Bin | Out-Null

# 1. O código do app
$temp = Join-Path $env:TEMP ("opentars-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $temp | Out-Null
try {
    if ($Fonte) {
        $origem = (Resolve-Path $Fonte).Path
    } else {
        Dizer "Baixando o openTARS..." "Downloading openTARS..."
        Invoke-WebRequest -UseBasicParsing -Uri $Zip -OutFile (Join-Path $temp "opentars.zip")
        Expand-Archive -Path (Join-Path $temp "opentars.zip") -DestinationPath $temp -Force
        $origem = Join-Path $temp "OpenTARS-main\app"
    }
    if (-not (Test-Path (Join-Path $origem "tars.py"))) { throw "tars.py not found in $origem" }
    if (Test-Path $App) { Remove-Item -Recurse -Force $App }
    Copy-Item -Recurse -Force $origem $App
} finally {
    Remove-Item -Recurse -Force $temp -ErrorAction SilentlyContinue
}

# 2. O Python (pelo uv) e as dependências
$uv = Get-Command uv -ErrorAction SilentlyContinue
if (-not $uv) {
    Dizer "Instalando o uv (traz o Python, sem administrador)..." "Installing uv (brings Python, no administrator)..."
    $env:UV_NO_MODIFY_PATH = "1"
    # num PowerShell filho, como a Astral manda: um "exit" do instalador dela não fecha esta janela
    powershell -NoProfile -ExecutionPolicy ByPass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    $uvExe = @((Join-Path $env:USERPROFILE ".local\bin\uv.exe"), (Join-Path $env:USERPROFILE ".cargo\bin\uv.exe")) |
        Where-Object { Test-Path $_ } | Select-Object -First 1
} else {
    $uvExe = $uv.Source
}
if (-not $uvExe -or -not (Test-Path $uvExe)) { throw "uv not found" }
Dizer "Preparando o Python e as dependências (alguns minutos na primeira vez)..." "Setting up Python and the dependencies (a few minutes the first time)..."
if (-not (Test-Path (Join-Path $Venv "Scripts\python.exe"))) {
    & $uvExe venv --python 3.12 $Venv
    if ($LASTEXITCODE) { throw "uv venv failed ($LASTEXITCODE)" }
}
& $uvExe pip install --python (Join-Path $Venv "Scripts\python.exe") requests psutil pyautogui pillow PySide6-Essentials
if ($LASTEXITCODE) { throw "uv pip install failed ($LASTEXITCODE)" }

# 3. O Ollama (por usuário). Sem ele o openTARS abre, mas não tem IA local.
if (-not $SemOllama) {
    $ollama = Get-Command ollama -ErrorAction SilentlyContinue
    $ollamaExe = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
    if (-not $ollama -and -not (Test-Path $ollamaExe)) {
        Dizer "Instalando o Ollama (o instalador oficial, para este usuário)..." "Installing Ollama (the official installer, for this user)..."
        $setup = Join-Path $env:TEMP "OllamaSetup.exe"
        Invoke-WebRequest -UseBasicParsing -Uri "https://ollama.com/download/OllamaSetup.exe" -OutFile $setup
        Start-Process -FilePath $setup -ArgumentList "/VERYSILENT", "/NORESTART", "/SUPPRESSMSGBOXES" -Wait
        Remove-Item -Force $setup -ErrorAction SilentlyContinue
        $bandeja = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama app.exe"
        if (Test-Path $bandeja) { Start-Process -FilePath $bandeja }
    } else {
        Dizer "Ollama já instalado." "Ollama already installed."
    }
}

# 4. Comandos (opentars, opentars-gui) e o atalho no Menu Iniciar
$python = Join-Path $Venv "Scripts\python.exe"
$pythonw = Join-Path $Venv "Scripts\pythonw.exe"
Set-Content -Encoding ASCII -Path (Join-Path $Bin "opentars.cmd") -Value "@echo off`r`n`"$python`" `"$App\tars.py`" %*"
Set-Content -Encoding ASCII -Path (Join-Path $Bin "opentars-gui.cmd") -Value "@echo off`r`ncd /d `"$App`"`r`nstart `"`" `"$pythonw`" -m tars_qt %*"
$caminho = [Environment]::GetEnvironmentVariable("Path", "User")
if (-not $caminho) { $caminho = "" }
if (($caminho -split ";") -notcontains $Bin) {
    [Environment]::SetEnvironmentVariable("Path", ($caminho.TrimEnd(";") + ";" + $Bin).TrimStart(";"), "User")
}
$atalho = (New-Object -ComObject WScript.Shell).CreateShortcut($MenuIniciar)
$atalho.TargetPath = $pythonw
$atalho.Arguments = "-m tars_qt"
$atalho.WorkingDirectory = $App
$atalho.Description = "openTARS"
$atalho.Save()

Dizer "Pronto. Abra o openTARS pelo Menu Iniciar (na primeira vez ele baixa o Gargantua 2, com barra)." `
      "Done. Open openTARS from the Start menu (the first time it downloads Gargantua 2, with a progress bar)."
Dizer "Num terminal NOVO: 'opentars --diagnostico' confere tudo e 'opentars --prova' mede a IA; mande os relatórios que eles salvam." `
      "In a NEW terminal: 'opentars --diagnostico' checks everything and 'opentars --prova' measures the AI; send the reports they save."
