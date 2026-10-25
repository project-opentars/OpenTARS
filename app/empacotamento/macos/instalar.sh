#!/bin/bash
# openTARS para macOS (5.2, experimental): instala sem senha de administrador, só na pasta do usuário.
#
#   curl -fsSL https://raw.githubusercontent.com/project-opentars/OpenTARS/main/app/empacotamento/macos/instalar.sh | bash
#
# O que faz: baixa o código do app (pasta app/ do repositório), instala o uv (traz o Python), cria um ambiente Python com
# as dependências, instala o Ollama se faltar (o app oficial, em ~/Applications), monta o openTARS.app em ~/Applications e
# o assina ad-hoc (grátis, sem conta da Apple; um app montado no próprio Mac não ganha a marca de quarentena), e cria os
# comandos opentars e opentars-gui em ~/.local/bin. O modelo (Gargantua 2) é baixado na primeira abertura, com barra.
# Rodar de novo atualiza. Remover: o mesmo comando com "| bash -s -- --remover".
# Suas conversas e configurações (em ~/Library/Application Support/opentars) ficam; apague a pasta se quiser.
set -euo pipefail

PASTA="$HOME/Library/Application Support/openTARS"
APP_CODIGO="$PASTA/app"
VENV="$PASTA/venv"
BIN="$HOME/.local/bin"
APP_MAC="$HOME/Applications/openTARS.app"
ZIP="https://github.com/project-opentars/OpenTARS/archive/refs/heads/main.zip"
FONTE=""            # --fonte PASTA: a pasta app/ local em vez de baixar (o CI usa)
SEM_OLLAMA=0        # --sem-ollama: não instala o Ollama (o CI usa)
REMOVER=0
while [ $# -gt 0 ]; do
    case "$1" in
        --remover) REMOVER=1 ;;
        --fonte) FONTE="$2"; shift ;;
        --sem-ollama) SEM_OLLAMA=1 ;;
    esac
    shift
done
case "${LANG:-}" in pt*) PT=1 ;; *) PT=0 ;; esac
dizer() { if [ "$PT" = 1 ]; then echo "[openTARS] $1"; else echo "[openTARS] $2"; fi; }

if [ "$REMOVER" = 1 ]; then
    rm -rf "$PASTA" "$APP_MAC" "$BIN/opentars" "$BIN/opentars-gui" "$HOME/Library/LaunchAgents/opentars-assistente.plist"
    for arq in "$HOME/.zprofile" "$HOME/.zshrc" "$HOME/.bash_profile"; do      # tira as 2 linhas que o instalador pôs no PATH
        if grep -qF "# openTARS (comandos opentars e opentars-gui)" "$arq" 2>/dev/null; then
            grep -vF -e "# openTARS (comandos opentars e opentars-gui)" -e 'export PATH="$HOME/.local/bin:$PATH"' "$arq" > "$arq.novo" && mv "$arq.novo" "$arq" || true
        fi
    done
    dizer "Removido. Suas conversas e configurações ficaram em ~/Library/Application Support/opentars; o Ollama e os modelos também." \
          "Removed. Your chats and settings stay in ~/Library/Application Support/opentars; Ollama and the models stay too."
    exit 0
fi

dizer "Instalando em $PASTA (sem senha de administrador)." "Installing into $PASTA (no administrator password)."
mkdir -p "$PASTA" "$BIN" "$HOME/Applications"

# 1. O código do app
TEMP="$(mktemp -d)"
trap 'rm -rf "$TEMP"' EXIT
if [ -n "$FONTE" ]; then
    ORIGEM="$(cd "$FONTE" && pwd)"
else
    dizer "Baixando o openTARS..." "Downloading openTARS..."
    curl -fsSL "$ZIP" -o "$TEMP/opentars.zip"
    unzip -q "$TEMP/opentars.zip" -d "$TEMP"
    ORIGEM="$TEMP/OpenTARS-main/app"
fi
[ -f "$ORIGEM/tars.py" ] || { echo "tars.py not found in $ORIGEM" >&2; exit 1; }
rm -rf "$APP_CODIGO"
cp -R "$ORIGEM" "$APP_CODIGO"
touch "$APP_CODIGO/.instalado-pelo-script"      # a hora da instalação: o app avisa do lançamento seguinte (tars_atualizacao.py)

# 2. O Python (pelo uv) e as dependências
UV="$(command -v uv || true)"
if [ -z "$UV" ]; then
    dizer "Instalando o uv (traz o Python, sem senha)..." "Installing uv (brings Python, no password)..."
    curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh
    UV="$HOME/.local/bin/uv"
fi
[ -x "$UV" ] || { echo "uv not found" >&2; exit 1; }
dizer "Preparando o Python e as dependências (alguns minutos na primeira vez)..." \
      "Setting up Python and the dependencies (a few minutes the first time)..."
[ -x "$VENV/bin/python3" ] || "$UV" venv --python 3.12 "$VENV"
"$UV" pip install --python "$VENV/bin/python3" requests psutil pyautogui pillow PySide6-Essentials numpy onnxruntime pyobjc-framework-ApplicationServices pip

# 3. O Ollama (o app oficial). Sem ele o openTARS abre, mas não tem IA local.
if [ "$SEM_OLLAMA" = 0 ]; then
    if command -v ollama >/dev/null 2>&1 || [ -d /Applications/Ollama.app ] || [ -d "$HOME/Applications/Ollama.app" ]; then
        dizer "Ollama já instalado." "Ollama already installed."
    else
        dizer "Instalando o Ollama (o app oficial, em ~/Applications)..." "Installing Ollama (the official app, in ~/Applications)..."
        curl -fsSL https://ollama.com/download/Ollama-darwin.zip -o "$TEMP/ollama.zip"
        unzip -q "$TEMP/ollama.zip" -d "$HOME/Applications"
    fi
    open -a Ollama >/dev/null 2>&1 || open "$HOME/Applications/Ollama.app" >/dev/null 2>&1 || true
fi

# 4. O openTARS.app (um lançador que abre a janela), assinado ad-hoc, e os comandos
rm -rf "$APP_MAC"
mkdir -p "$APP_MAC/Contents/MacOS" "$APP_MAC/Contents/Resources"
cp "$APP_CODIGO/empacotamento/macos/opentars.icns" "$APP_MAC/Contents/Resources/opentars.icns" 2>/dev/null || true
cat > "$APP_MAC/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>openTARS</string>
  <key>CFBundleDisplayName</key><string>openTARS</string>
  <key>CFBundleIdentifier</key><string>io.github.project-opentars.opentars</string>
  <key>CFBundleExecutable</key><string>openTARS</string>
  <key>CFBundleIconFile</key><string>opentars</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>5.2</string>
  <key>LSMinimumSystemVersion</key><string>12.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSMicrophoneUsageDescription</key><string>openTARS listens for your voice requests when you turn the voice on. The audio stays on this Mac.</string>
</dict></plist>
PLIST
cat > "$APP_MAC/Contents/MacOS/openTARS" <<LANCADOR
#!/bin/bash
cd "$APP_CODIGO" && exec "$VENV/bin/python3" -m tars_qt "\$@"
LANCADOR
chmod +x "$APP_MAC/Contents/MacOS/openTARS"
codesign --force --deep -s - "$APP_MAC" >/dev/null 2>&1 || dizer "Aviso: não consegui assinar o app (codesign)." "Warning: could not sign the app (codesign)."

printf '#!/bin/bash\nexec "%s/bin/python3" "%s/tars.py" "$@"\n' "$VENV" "$APP_CODIGO" > "$BIN/opentars"
printf '#!/bin/bash\ncd "%s" && exec "%s/bin/python3" -m tars_qt "$@"\n' "$APP_CODIGO" "$VENV" > "$BIN/opentars-gui"
chmod +x "$BIN/opentars" "$BIN/opentars-gui"

dizer "Pronto. Abra o openTARS em ~/Applications (na primeira vez ele baixa o Gargantua 2, com barra)." \
      "Done. Open openTARS from ~/Applications (the first time it downloads Gargantua 2, with a progress bar)."
dizer "O macOS vai pedir Acessibilidade e Gravação de Tela para o openTARS clicar e ver a tela: libere em Ajustes do Sistema > Privacidade e Segurança." \
      "macOS will ask for Accessibility and Screen Recording so openTARS can click and see the screen: allow it in System Settings > Privacy & Security."
# o Terminal do macOS (zsh) não tem ~/.local/bin no PATH: sem isto, "opentars" dá "command not found". Uma linha marcada,
# nos arquivos que o zsh e o bash do Mac leem ao abrir um terminal; o --remover tira.
MARCA_PATH="# openTARS (comandos opentars e opentars-gui)"
for arq in "$HOME/.zprofile" "$HOME/.zshrc" "$HOME/.bash_profile"; do
    [ "$arq" = "$HOME/.bash_profile" ] && [ ! -f "$arq" ] && continue
    grep -qF "$MARCA_PATH" "$arq" 2>/dev/null || printf '\n%s\nexport PATH="$HOME/.local/bin:$PATH"\n' "$MARCA_PATH" >> "$arq"
done
export PATH="$BIN:$PATH"
dizer "Os comandos opentars e opentars-gui ficaram em $BIN (já no PATH dos seus terminais novos: abra um Terminal novo)." \
      "The opentars and opentars-gui commands are in $BIN (already on the PATH of new terminals: open a new Terminal)."
dizer "Para conferir e medir: '$BIN/opentars --diagnostico' e '$BIN/opentars --prova'; mande os relatórios que eles salvam." \
      "To check and measure: '$BIN/opentars --diagnostico' and '$BIN/opentars --prova'; send the reports they save."
