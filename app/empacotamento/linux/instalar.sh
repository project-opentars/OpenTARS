#!/bin/bash
# openTARS para outros Linux (Fedora, Arch, openSUSE e derivados; 5.2, experimental). No Ubuntu, Debian, Mint, Zorin e
# Pop!_OS o caminho continua sendo o .deb.
#
#   curl -fsSL https://raw.githubusercontent.com/project-opentars/OpenTARS/main/app/empacotamento/linux/instalar.sh | bash
#
# O que faz: instala os pacotes do sistema que o openTARS usa pelo gerenciador da distribuição (dnf, pacman, zypper ou
# apt; é a única parte que pede a senha), baixa o código do app (pasta app/ do repositório) para a pasta do usuário, cria
# um ambiente Python com o Python do sistema (que enxerga o PyGObject e o tkinter da distribuição), instala o Ollama pelo
# instalador oficial se faltar, e cria os comandos opentars e opentars-gui em ~/.local/bin e o atalho no menu. O modelo
# (Gargantua 2) é baixado na primeira abertura, com barra. Rodar de novo atualiza. Remover: "| bash -s -- --remover".
# Suas conversas e configurações (em ~/.config/opentars e ~/.local/share/opentars) ficam; apague as pastas se quiser.
set -euo pipefail

DADOS="${XDG_DATA_HOME:-$HOME/.local/share}"
PASTA="$DADOS/opentars-app"
APP="$PASTA/app"
VENV="$PASTA/venv"
BIN="$HOME/.local/bin"
ATALHO="$DADOS/applications/opentars.desktop"
ICONE="$DADOS/icons/hicolor/scalable/apps/opentars.svg"
INICIO="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"
ZIP="https://github.com/project-opentars/OpenTARS/archive/refs/heads/main.zip"
FONTE=""            # --fonte PASTA: a pasta app/ local em vez de baixar (o CI usa)
SEM_OLLAMA=0        # --sem-ollama: não instala o Ollama (o CI usa)
SEM_SISTEMA=0       # --sem-sistema: não instala pacotes do sistema (quem já instalou à mão, ou sem sudo)
REMOVER=0
while [ $# -gt 0 ]; do
    case "$1" in
        --remover) REMOVER=1 ;;
        --fonte) FONTE="$2"; shift ;;
        --sem-ollama) SEM_OLLAMA=1 ;;
        --sem-sistema) SEM_SISTEMA=1 ;;
    esac
    shift
done
case "${LANG:-}" in pt*) PT=1 ;; *) PT=0 ;; esac
dizer() { if [ "$PT" = 1 ]; then echo "[openTARS] $1"; else echo "[openTARS] $2"; fi; }
if [ "$(id -u)" = 0 ]; then SUDO=(); else SUDO=(sudo); fi

if [ "$REMOVER" = 1 ]; then
    rm -rf "$PASTA" "$BIN/opentars" "$BIN/opentars-gui" "$ATALHO" "$ICONE" \
           "$INICIO/opentars-assistente.desktop" "$INICIO/opentars-probes.desktop"
    dizer "Removido. Suas conversas e configurações ficaram em ~/.config/opentars e ~/.local/share/opentars; o Ollama e os modelos também." \
          "Removed. Your chats and settings stay in ~/.config/opentars and ~/.local/share/opentars; Ollama and the models stay too."
    exit 0
fi

# 1. Pacotes do sistema: Python com venv, tkinter, PyGObject e AT-SPI (clicar pelo nome), área de transferência,
#    notificações, lixeira (gio), PDF, áudio e as bibliotecas que a janela Qt usa
if [ "$SEM_SISTEMA" = 0 ]; then
    if command -v dnf >/dev/null 2>&1; then
        INSTALAR=(dnf install -y)
        PACOTES=(python3 python3-tkinter python3-gobject gobject-introspection at-spi2-core curl zstd pciutils xdg-utils xclip wl-clipboard
                 libnotify glib2 poppler-utils alsa-utils xcb-util-cursor xcb-util-wm xcb-util-image xcb-util-keysyms
                 xcb-util-renderutil libxkbcommon-x11 mesa-libEGL mesa-libGL fontconfig)
    elif command -v pacman >/dev/null 2>&1; then
        INSTALAR=(pacman -S --needed --noconfirm)
        PACOTES=(python python-gobject at-spi2-core tk curl zstd pciutils xdg-utils xclip wl-clipboard libnotify glib2
                 poppler alsa-utils xcb-util-cursor xcb-util-wm xcb-util-image xcb-util-keysyms xcb-util-renderutil libxkbcommon-x11
                 libglvnd fontconfig)
    elif command -v zypper >/dev/null 2>&1; then
        INSTALAR=(zypper --non-interactive install --no-recommends)
        PACOTES=(python3 python3-gobject typelib-1_0-Atspi-2_0 at-spi2-core python3-tk curl zstd pciutils xdg-utils xclip
                 wl-clipboard libnotify-tools glib2-tools poppler-tools alsa-utils libxcb-cursor0 libxcb-icccm4 libxcb-image0
                 libxcb-keysyms1 libxcb-render-util0 libxcb-shape0 libxkbcommon-x11-0
                 libgthread-2_0-0 Mesa-libEGL1 Mesa-libGL1 fontconfig)
    elif command -v apt-get >/dev/null 2>&1; then
        dizer "Debian/Ubuntu: o caminho recomendado é o .deb (README). Seguindo com o script mesmo assim." \
              "Debian/Ubuntu: the recommended way is the .deb (README). Going on with the script anyway."
        INSTALAR=(apt-get install -y)
        PACOTES=(python3 python3-venv python3-tk python3-gi gir1.2-atspi-2.0 at-spi2-core curl zstd pciutils xdg-utils xclip
                 wl-clipboard libnotify-bin libglib2.0-bin poppler-utils alsa-utils libxcb-cursor0 libxcb-icccm4 libxcb-image0
                 libxcb-keysyms1 libxcb-render-util0 libxcb-shape0 libxcb-xinerama0 libxkbcommon-x11-0
                 libegl1 libgl1 fontconfig)
        "${SUDO[@]}" apt-get update -qq || true
    else
        dizer "Não reconheci o gerenciador de pacotes (dnf, pacman, zypper, apt). Instale à mão: python3 com venv, tkinter, PyGObject e at-spi2-core, e rode de novo com --sem-sistema." \
              "Unknown package manager (dnf, pacman, zypper, apt). Install by hand: python3 with venv, tkinter, PyGObject and at-spi2-core, then run again with --sem-sistema."
        exit 1
    fi
    dizer "Instalando os pacotes do sistema (${INSTALAR[0]}; pode pedir a sua senha): ${PACOTES[*]}" \
          "Installing the system packages (${INSTALAR[0]}; may ask for your password): ${PACOTES[*]}"
    if ! "${SUDO[@]}" "${INSTALAR[@]}" "${PACOTES[@]}"; then
        # um nome que esta versão da distribuição não tem não pode derrubar o resto: tenta um a um
        FALTARAM=()
        for pacote in "${PACOTES[@]}"; do
            "${SUDO[@]}" "${INSTALAR[@]}" "$pacote" >/dev/null 2>&1 || FALTARAM+=("$pacote")
        done
        if [ ${#FALTARAM[@]} -gt 0 ]; then
            dizer "Não consegui instalar: ${FALTARAM[*]} (o openTARS abre sem eles, com menos recursos)." \
                  "Could not install: ${FALTARAM[*]} (openTARS opens without them, with fewer features)."
        fi
    fi
fi
if ! command -v python3 >/dev/null 2>&1; then
    dizer "Falta o python3. No Arch, atualize o sistema antes (sudo pacman -Syu) e rode este comando de novo." \
          "python3 is missing. On Arch, update the system first (sudo pacman -Syu) and run this command again."
    exit 1
fi

dizer "Instalando em $PASTA." "Installing into $PASTA."
mkdir -p "$PASTA" "$BIN"

# 2. O código do app (o zip é aberto pelo próprio Python: não depende do unzip)
TEMP="$(mktemp -d)"
trap 'rm -rf "$TEMP"' EXIT
if [ -n "$FONTE" ]; then
    ORIGEM="$(cd "$FONTE" && pwd)"
else
    dizer "Baixando o openTARS..." "Downloading openTARS..."
    curl -fsSL "$ZIP" -o "$TEMP/opentars.zip"
    python3 -m zipfile -e "$TEMP/opentars.zip" "$TEMP"
    ORIGEM="$TEMP/OpenTARS-main/app"
fi
[ -f "$ORIGEM/tars.py" ] || { echo "tars.py not found in $ORIGEM" >&2; exit 1; }
rm -rf "$APP"
cp -R "$ORIGEM" "$APP"
touch "$APP/.instalado-pelo-script"      # o app não oferece o .deb como atualização (tars_atualizacao.py)

# 3. O ambiente Python, com o Python do sistema (--system-site-packages: o PyGObject e o tkinter vêm da distribuição)
if ! "$VENV/bin/python3" -c "import sys" >/dev/null 2>&1; then
    rm -rf "$VENV"
    dizer "Preparando o Python ($(python3 --version 2>&1)) e as dependências (alguns minutos na primeira vez)..." \
          "Setting up Python ($(python3 --version 2>&1)) and the dependencies (a few minutes the first time)..."
    python3 -m venv --system-site-packages "$VENV" || {
        dizer "Não consegui criar o ambiente Python (falta o módulo venv da distribuição?)." \
              "Could not create the Python environment (is the distribution's venv module missing?)."
        exit 1; }
fi
"$VENV/bin/python3" -m pip install --quiet --upgrade pip
"$VENV/bin/python3" -m pip install --quiet requests psutil pyautogui pillow PySide6-Essentials

# 4. O Ollama, pelo instalador oficial (ele mesmo pede a senha). Sem ele o openTARS abre, mas não tem IA local.
if [ "$SEM_OLLAMA" = 0 ]; then
    if command -v ollama >/dev/null 2>&1; then
        dizer "Ollama já instalado." "Ollama already installed."
    else
        dizer "Instalando o Ollama (o instalador oficial; pode pedir a sua senha)..." \
              "Installing Ollama (the official installer; may ask for your password)..."
        curl -fsSL https://ollama.com/install.sh -o "$TEMP/ollama.sh" && sh "$TEMP/ollama.sh" \
            || dizer "Não consegui instalar o Ollama; veja https://ollama.com/download" "Could not install Ollama; see https://ollama.com/download"
    fi
fi

# 5. Comandos: o opentars-gui é o mesmo do .deb (instância única, modo seguro do Qt), com os caminhos daqui
printf '#!/bin/bash\nexec "%s/bin/python3" "%s/tars.py" "$@"\n' "$VENV" "$APP" > "$BIN/opentars"
"$VENV/bin/python3" - "$APP/empacotamento/bin/opentars-gui" "$BIN/opentars-gui" "$APP" "$VENV" "$BIN" <<'PY'
import sys
origem, destino, app, venv, pasta_bin = sys.argv[1:]
texto = open(origem, encoding="utf-8").read()
for velho, novo in (('DIR_OPENTARS="/usr/share/opentars"', f'DIR_OPENTARS="{app}"'),
                    ('PYTHON="$DIR_OPENTARS/venv/bin/python3"', f'PYTHON="{venv}/bin/python3"'),
                    ("exec /usr/bin/opentars --chat", f'exec "{pasta_bin}/opentars" --chat')):
    assert texto.count(velho) == 1, f"o lançador do .deb mudou: {velho}"
    texto = texto.replace(velho, novo)
open(destino, "w", encoding="utf-8").write(texto)
PY
chmod +x "$BIN/opentars" "$BIN/opentars-gui"

# 6. Atalho no menu de aplicativos, nos idiomas do app, e o ícone
"$VENV/bin/python3" "$APP/empacotamento/gerar_desktop.py" "$APP/empacotamento/desktop" "$TEMP/desktop"
mkdir -p "$(dirname "$ATALHO")" "$(dirname "$ICONE")"
sed "s|/usr/bin/opentars-gui|\"$BIN/opentars-gui\"|" "$TEMP/desktop/opentars.desktop" > "$ATALHO"
cp "$APP/empacotamento/icone/opentars.svg" "$ICONE"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q "$(dirname "$ATALHO")" || true

dizer "Pronto. Abra o openTARS pelo menu de aplicativos (na primeira vez ele baixa o Gargantua 2, com barra)." \
      "Done. Open openTARS from the application menu (the first time it downloads Gargantua 2, with a progress bar)."
case ":$PATH:" in *":$BIN:"*) ;; *) dizer "Os comandos ficaram em $BIN; para usar no terminal: export PATH=\"$BIN:\$PATH\"" \
                                           "The commands are in $BIN; to use them in a terminal: export PATH=\"$BIN:\$PATH\"" ;; esac
dizer "Para conferir e medir: 'opentars --diagnostico' e 'opentars --prova'; mande os relatórios que eles salvam." \
      "To check and measure: 'opentars --diagnostico' and 'opentars --prova'; send the reports they save."
