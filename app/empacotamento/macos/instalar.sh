#!/bin/bash
# openTARS para macOS: instala sem senha de administrador, só na pasta do usuário.
#
#   curl -fsSL https://raw.githubusercontent.com/project-opentars/OpenTARS/main/app/empacotamento/macos/instalar.sh | bash
#
# Desde 14/11/2026 o openTARS do macOS é um app pronto (Python, Qt e o motor llama.cpp com Metal dentro), assinado ad-hoc.
# Este script baixa o .dmg da última Release para o seu Mac (Apple Silicon ou Intel), confere o SHA-256 no SHA256SUMS da mesma
# Release, copia o openTARS.app para ~/Applications e liga o comando "opentars" em ~/.local/bin. Baixado pelo curl, o app não
# ganha a marca de quarentena, então o macOS não o bloqueia na primeira abertura (o .dmg baixado pelo navegador pede
# "Abrir mesmo assim" em Ajustes do Sistema > Privacidade e Segurança, uma vez).
# Quem tinha a instalação antiga por script passa para o app pronto; as conversas, as configurações e os modelos ficam.
# Rodar de novo atualiza. Remover: o mesmo comando com "| bash -s -- --remover".
set -euo pipefail

RELEASE="${OPENTARS_RELEASE:-https://github.com/project-opentars/OpenTARS/releases/latest/download}"   # o CI aponta para os arquivos que acabou de montar
APP_MAC="$HOME/Applications/openTARS.app"
BIN="$HOME/.local/bin"
ANTIGO="$HOME/Library/Application Support/openTARS"      # a instalação por script (app/ e venv/); os dados ficam lá também
REMOVER=0
while [ $# -gt 0 ]; do
    case "$1" in
        --remover) REMOVER=1 ;;
        --fonte) shift ;;                       # aceitos por compatibilidade (o app vem pronto da Release)
        --sem-ollama|--com-ollama) ;;           # o Ollama saiu em 14/11
    esac
    shift
done
case "${LANG:-}" in pt*) PT=1 ;; *) PT=0 ;; esac
dizer() { if [ "$PT" = 1 ]; then echo "[openTARS] $1"; else echo "[openTARS] $2"; fi; }
MARCA_PATH="# openTARS (comandos opentars e opentars-gui)"

limpar_antigo() {
    rm -rf "$ANTIGO/app" "$ANTIGO/venv" "$BIN/opentars-gui"
}

if [ "$REMOVER" = 1 ]; then
    pkill -f "$APP_MAC/Contents/Resources/runtime" 2>/dev/null || true
    rm -rf "$APP_MAC" "$BIN/opentars" "$HOME/Library/LaunchAgents/opentars-assistente.plist"
    limpar_antigo
    for arq in "$HOME/.zprofile" "$HOME/.zshrc" "$HOME/.bash_profile"; do      # tira as 2 linhas que o instalador pôs no PATH
        if grep -qF "$MARCA_PATH" "$arq" 2>/dev/null; then
            grep -vF -e "$MARCA_PATH" -e 'export PATH="$HOME/.local/bin:$PATH"' "$arq" > "$arq.novo" && mv "$arq.novo" "$arq" || true
        fi
    done
    dizer "Removido. Suas conversas, configurações e modelos ficaram em ~/Library/Application Support/opentars." \
          "Removed. Your chats, settings and models stay in ~/Library/Application Support/opentars."
    exit 0
fi

case "$(uname -m)" in arm64) MAQUINA=arm64 ;; *) MAQUINA=x86_64 ;; esac
DMG_NOME="openTARS-macos-$MAQUINA.dmg"
TEMP="$(mktemp -d)"
PONTO=""
trap '[ -n "$PONTO" ] && hdiutil detach "$PONTO" -quiet 2>/dev/null; rm -rf "$TEMP"' EXIT

dizer "Baixando o openTARS para o seu Mac ($MAQUINA)..." "Downloading openTARS for your Mac ($MAQUINA)..."
curl -fL# --retry 3 "$RELEASE/$DMG_NOME" -o "$TEMP/$DMG_NOME"
curl -fsSL --retry 3 "$RELEASE/SHA256SUMS" -o "$TEMP/SHA256SUMS"
ESPERADO="$(awk -v n="$DMG_NOME" '$2 == n || $2 == "*"n {print $1}' "$TEMP/SHA256SUMS")"
OBTIDO="$(shasum -a 256 "$TEMP/$DMG_NOME" | awk '{print $1}')"
if [ -z "$ESPERADO" ] || [ "$ESPERADO" != "$OBTIDO" ]; then
    echo "SHA-256 check failed: $OBTIDO" >&2
    exit 1
fi
dizer "Conferido (SHA-256). Instalando em ~/Applications..." "Verified (SHA-256). Installing into ~/Applications..."

PONTO="$TEMP/montado"
mkdir -p "$PONTO" "$HOME/Applications" "$BIN"
hdiutil attach -nobrowse -readonly -noautoopen -mountpoint "$PONTO" "$TEMP/$DMG_NOME" >/dev/null
pkill -f "$APP_MAC/Contents/Resources/runtime" 2>/dev/null || true      # o openTARS aberto (e o motor dele) sai antes da troca
pkill -f "$ANTIGO/venv" 2>/dev/null || true
rm -rf "$APP_MAC.novo"
ditto "$PONTO/openTARS.app" "$APP_MAC.novo"
hdiutil detach "$PONTO" -quiet && PONTO=""
rm -rf "$APP_MAC"
mv "$APP_MAC.novo" "$APP_MAC"
limpar_antigo
ln -sf "$APP_MAC/Contents/Resources/bin/opentars" "$BIN/opentars"

# o Terminal do macOS (zsh) não tem ~/.local/bin no PATH: uma linha marcada, nos arquivos que o zsh e o bash leem; o --remover tira
for arq in "$HOME/.zprofile" "$HOME/.zshrc" "$HOME/.bash_profile"; do
    [ "$arq" = "$HOME/.bash_profile" ] && [ ! -f "$arq" ] && continue
    grep -qF "$MARCA_PATH" "$arq" 2>/dev/null || printf '\n%s\nexport PATH="$HOME/.local/bin:$PATH"\n' "$MARCA_PATH" >> "$arq"
done

dizer "Pronto. Abra o openTARS em ~/Applications (na primeira vez ele baixa o Gargantua 2.5, com barra)." \
      "Done. Open openTARS from ~/Applications (the first time it downloads Gargantua 2.5, with a progress bar)."
dizer "O macOS vai pedir Acessibilidade e Gravação de Tela para o openTARS clicar e ver a tela: libere em Ajustes do Sistema > Privacidade e Segurança." \
      "macOS will ask for Accessibility and Screen Recording so openTARS can click and see the screen: allow it in System Settings > Privacy & Security."
dizer "Num Terminal novo: 'opentars --diagnostico' confere tudo." "In a new Terminal: 'opentars --diagnostico' checks everything."
open "$APP_MAC" >/dev/null 2>&1 || true
