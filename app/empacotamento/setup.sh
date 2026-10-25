#!/bin/bash
# Configuração do openTARS: instala o que falta pra ele rodar (Ollama,
# ambiente Python isolado com as dependências, modelos do Ollama; nenhum
# ajudante desde a 3.0.5: a helper Murph vem no pacote; desde a 3.1, usa as
# IAs que outros programas já têm; desde a 4.0, baixa o Gargantua, a IA
# oficial; na Endurance Neo, nada de modelo de embeddings) e NUNCA reinstala
# algo que já está presente no PC.
# Roda automaticamente depois do "apt install" (chamado pelo postinst)
# e pode ser rodado de novo a qualquer momento com "opentars --setup".
#
# De propósito, NUNCA sai com erro: se o dpkg visse esse script falhar,
# deixaria o pacote marcado como "quebrado" mesmo com o openTARS
# utilizável. Cada etapa arriscada (rede, permissões) avisa e segue.

set -uo pipefail

# Ajudantes das versões antigas (não são mais baixados nem usados): se já
# estiverem instalados, só não contam como modelo de conversa.
MODELO_AJUDANTE="qwen2.5:0.5b"
MODELO_AJUDANTE_ANTIGO="gemma3:270m"
DIR_OPENTARS="/usr/share/opentars"
VENV="$DIR_OPENTARS/venv"
DEPENDENCIAS=("requests:requests" "psutil:psutil" "pyautogui:pyautogui" "PIL:pillow" "PySide6:PySide6-Essentials" "numpy:numpy" "onnxruntime:onnxruntime")

# Textos no idioma do sistema: vêm de idiomas/*.json, pelo mesmo módulo
# que o openTARS usa (tars_i18n.py). Se algo falhar, aparecem as chaves
# em vez das frases — a instalação nunca quebra por causa disso.
eval "$(python3 "$DIR_OPENTARS/tars_i18n.py" --shell setup. 2>/dev/null)" 2>/dev/null || true

# t chave [campo=valor ...]  ->  frase do idioma, com os {campos} preenchidos
t() {
    local var="T_setup_$1" texto par
    texto="${!var:-$1}"
    shift
    for par in "$@"; do
        texto="${texto//"{${par%%=*}}"/${par#*=}}"
    done
    printf '%s' "$texto"
}

msg()   { echo "[openTARS] $*"; }
aviso() { echo "[openTARS] $(t aviso): $*"; }

echo ""
echo "$(t titulo)"
echo ""

OLLAMA_URL="http://127.0.0.1:11434"
# Respeita OLLAMA_HOST (o mesmo do próprio Ollama): "0.0.0.0", "host:porta" ou URL
if [ -n "${OLLAMA_HOST:-}" ]; then
    OLLAMA_URL="$OLLAMA_HOST"
    case "$OLLAMA_URL" in *://*) ;; *) OLLAMA_URL="http://$OLLAMA_URL" ;; esac
    case "${OLLAMA_URL#*://}" in *:*) ;; *) OLLAMA_URL="$OLLAMA_URL:11434" ;; esac
    OLLAMA_URL="${OLLAMA_URL/\/\/0.0.0.0/\/\/127.0.0.1}"
fi

ollama_responde() {
    curl -fsS --max-time 3 "$OLLAMA_URL/api/version" >/dev/null 2>&1
}

# 4.5: WSL. O Ollama costuma ficar no Windows, que o WSL2 alcança pelo IP dele
# (servidor DNS e gateway do WSL), não pelo 127.0.0.1.
em_wsl() {
    grep -qi microsoft /proc/version 2>/dev/null || [ -n "${WSL_DISTRO_NAME:-}" ]
}

ollama_do_windows() {
    local ip
    for ip in $(awk '/^nameserver/ {print $2}' /etc/resolv.conf 2>/dev/null) $(ip route 2>/dev/null | awk '/^default/ {print $3}'); do
        case "$ip" in 127.*|"") continue ;; esac
        if curl -fsS --max-time 2 "http://$ip:11434/api/version" >/dev/null 2>&1; then
            echo "http://$ip:11434"
            return 0
        fi
    done
    return 1
}

if em_wsl; then
    msg "$(t wsl_detectado)"
    if [ -z "${OLLAMA_HOST:-}" ] && ! ollama_responde && windows_url="$(ollama_do_windows)"; then
        OLLAMA_URL="$windows_url"
        msg "$(t ollama_windows url="$OLLAMA_URL")"
    fi
fi
# O comando "ollama" (pull) fala com o mesmo servidor que o resto deste script
export OLLAMA_HOST="${OLLAMA_URL#*://}"

# Nomes dos modelos baixados, um por linha (via API: funciona mesmo com
# o Ollama rodando em Docker, sem o comando "ollama" no PC).
modelos_instalados() {
    curl -fsS --max-time 5 "$OLLAMA_URL/api/tags" 2>/dev/null \
        | grep -o '"name"[[:space:]]*:[[:space:]]*"[^"]*"' | cut -d'"' -f4
}

# ------------------------------------------------------------------
# 1. Ollama — só instala se ainda não existir.
#
# Um Ollama que já responde na porta padrão (instalado de outro jeito,
# em Docker, via Snap...) conta como instalado: instalar outro por cima
# criaria um segundo serviço brigando pela mesma porta.
# ------------------------------------------------------------------
if command -v ollama >/dev/null 2>&1; then
    msg "$(t ollama_ja)"
elif ollama_responde; then
    msg "$(t ollama_existente url="$OLLAMA_URL")"
else
    msg "$(t ollama_instalando)"
    # Baixa pro disco e só então executa: com "curl | sh" o status do
    # pipe é o do "sh", que "funciona" mesmo se o download falhar.
    instalador="$(mktemp)"
    if curl -fsSL https://ollama.com/install.sh -o "$instalador" && sh "$instalador"; then
        msg "$(t ollama_ok)"
    else
        aviso "$(t ollama_falhou)"
        echo "        $(t ollama_manual)"
    fi
    rm -f "$instalador"
fi

# ------------------------------------------------------------------
# 2. Ambiente Python isolado.
#
# Um venv próprio evita o conflito do pyautogui com o setuptools do
# sistema em distros recentes (Ubuntu 24.04+, Zorin 17+).
# --system-site-packages deixa o venv enxergar o tkinter, que só existe
# como pacote do sistema (python3-tk), nunca via pip.
#
# Se o venv existe mas o Python dele não roda mais (ex: atualização da
# distro trocou a versão do Python), ele é recriado do zero.
# ------------------------------------------------------------------
# Escolhe o Python base: o "python3" padrão, a menos que ele não tenha
# tkinter e outro python3.X instalado tenha (acontece quando o python3
# do PATH foi trocado e o pacote python3-tk é da versão padrão da distro).
escolher_python() {
    local candidato
    for candidato in python3 /usr/bin/python3 $(ls /usr/bin/python3.[0-9]* 2>/dev/null | grep -E 'python3\.[0-9]+$' | sort -t. -k2 -n -r); do
        command -v "$candidato" >/dev/null 2>&1 || continue
        "$candidato" -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" 2>/dev/null || continue
        "$candidato" -c "import venv, tkinter" >/dev/null 2>&1 && { echo "$candidato"; return; }
    done
    echo python3
}

venv_ok() {
    [ -x "$VENV/bin/python3" ] && "$VENV/bin/python3" -c "pass" >/dev/null 2>&1
}

# Venv criado com um Python sem tkinter enquanto existe outro com tkinter
# (ex: python3-tk instalado depois): recria pra liberar a interface gráfica.
PYTHON_BASE="$(escolher_python)"
if venv_ok && ! "$VENV/bin/python3" -c "import tkinter" >/dev/null 2>&1 \
        && "$PYTHON_BASE" -c "import tkinter" >/dev/null 2>&1; then
    msg "$(t venv_sem_tk python="$PYTHON_BASE")"
    rm -rf "$VENV"
fi

if venv_ok; then
    msg "$(t venv_ja)"
else
    [ -e "$VENV" ] && msg "$(t venv_quebrado)"
    rm -rf "$VENV"
    msg "$(t venv_criando versao="$("$PYTHON_BASE" --version 2>&1)")"
    if "$PYTHON_BASE" -m venv --system-site-packages "$VENV"; then
        "$VENV/bin/pip" install --quiet --upgrade pip setuptools wheel \
            || aviso "$(t pip_falhou)"
        msg "$(t venv_ok)"
    else
        aviso "$(t venv_falhou)"
        rm -rf "$VENV"
    fi
fi

if [ -x "$VENV/bin/python3" ]; then
    msg "$(t deps_verificando)"

    faltando=()
    for par in "${DEPENDENCIAS[@]}"; do
        modulo="${par%%:*}"
        pacote="${par##*:}"
        # find_spec só checa se o módulo existe, sem executá-lo. Um
        # "import" real do pyautogui lê $DISPLAY na hora e dá KeyError
        # sem sessão gráfica (como durante o próprio postinst).
        if ! "$VENV/bin/python3" -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('$modulo') else 1)" >/dev/null 2>&1; then
            faltando+=("$pacote")
        fi
    done

    if [ "${#faltando[@]}" -eq 0 ]; then
        msg "$(t deps_ok)"
    else
        msg "$(t deps_instalando pacotes="${faltando[*]}")"
        if ! "$VENV/bin/pip" install --quiet "${faltando[@]}"; then
            aviso "$(t deps_falhou)"
        fi
    fi

    if "$VENV/bin/python3" -c "import tkinter" >/dev/null 2>&1; then
        msg "$(t tk_ok)"
    else
        aviso "$(t tk_falta)"
        echo "        $(t tk_instale)"
        echo "        $(t tk_terminal)"
    fi

    # Clicar nos botões pelo nome (árvore de acessibilidade, AT-SPI).
    if "$VENV/bin/python3" -c "import gi; gi.require_version('Atspi', '2.0'); from gi.repository import Atspi" >/dev/null 2>&1; then
        msg "$(t acess_ok)"
    else
        aviso "$(t acess_falta)"
        echo "        $(t acess_instale)"
    fi
else
    aviso "$(t sem_venv)"
fi

# ------------------------------------------------------------------
# 3. Serviço do Ollama pronto (a helper Murph já vem no pacote).
# ------------------------------------------------------------------
servico_pronto=0

# Recém-instalado, o serviço leva um instante pra subir. Se o Ollama
# existe mas o serviço está parado (sem systemd, por exemplo), tenta
# iniciar.
if ! ollama_responde && command -v systemctl >/dev/null 2>&1 \
        && systemctl list-unit-files ollama.service >/dev/null 2>&1; then
    systemctl start ollama >/dev/null 2>&1 || true
fi

for _ in $(seq 1 10); do
    if ollama_responde; then
        servico_pronto=1
        break
    fi
    sleep 2
done

# 3.0.5: nenhum modelo ajudante é baixado. Quem decide o tipo de cada
# pedido é a helper Murph, que já vem no pacote (modelos/murph.json).
msg "$(t helper_murph versao="1.0")"
if [ "$servico_pronto" -eq 0 ]; then
    aviso "$(t ollama_nao_respondeu url="$OLLAMA_URL")"
    # 4.5: WSL (e contêiner) costuma não ter systemd: o serviço não sobe sozinho
    if em_wsl || ! command -v systemctl >/dev/null 2>&1; then
        echo "        $(t ollama_serve_manual)"
    fi
fi

# ------------------------------------------------------------------
# 3d. Gargantua (4.0): a IA oficial do openTARS, treinada pra usar as ferramentas
#     dele. Desde 18/10 é o Gargantua 2 (Qwen3.5 2B, ~1,6 GB, enxerga a tela: o Cooper,
#     modelo à parte, foi descontinuado). Baixa só se ainda não tiver.
#     Com ele instalado, o passo 4 não baixa outro modelo de conversa.
#     TARS_SEM_GARGANTUA=1 pula; TARS_MODELO_GARGANTUA=<nome> troca.
# ------------------------------------------------------------------
MODELO_GARGANTUA="${TARS_MODELO_GARGANTUA:-ProjectOpenTARS/Gargantua-2}"

# 5.1: máquina fraca (sem placa NVIDIA com 4 GB E com até 6 GB de RAM OU menos de 4 threads) recebe o Gargantua Lite
# (Qwen3.5 0,8B com visão, 0,6 GB, Gargantua-2:lite). TARS_GARGANTUA=lite|completo força. A mesma regra do primeiro uso (tars_primeiro_uso.py).
maquina_fraca() {
    case "${TARS_GARGANTUA:-}" in lite) return 0 ;; completo) return 1 ;; esac
    local vram=0 ram threads
    if command -v nvidia-smi >/dev/null 2>&1; then
        vram="$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>/dev/null | sort -n | tail -1 | cut -d. -f1)"
    fi
    [ "${vram:-0}" -ge 4000 ] 2>/dev/null && return 1
    ram="$(awk '/^MemTotal:/ {print int($2/1024)}' /proc/meminfo 2>/dev/null)"
    threads="$(nproc 2>/dev/null || echo 4)"
    [ "${ram:-99999}" -le 6200 ] || [ "${threads:-4}" -lt 4 ]
}
if [ -z "${TARS_MODELO_GARGANTUA:-}" ] && maquina_fraca; then
    MODELO_GARGANTUA="ProjectOpenTARS/Gargantua-2:lite"
fi

gargantua_instalado() {
    # Qualquer "gargantua" conta (o oficial ou um treinado no próprio PC).
    modelos_instalados | awk -F/ '{print tolower($NF)}' | grep -q '^gargantua'
}

if [ "$servico_pronto" -eq 1 ]; then
    if [ "${TARS_SEM_GARGANTUA:-0}" = "1" ]; then
        msg "$(t gargantua_pulado)"
    elif gargantua_instalado; then
        msg "$(t gargantua_ja modelo="$(modelos_instalados | grep -i 'gargantua' | head -1)")"
    else
        msg "$(t gargantua_baixando modelo="$MODELO_GARGANTUA")"
        if [ -t 1 ]; then
            # num terminal ("dpkg -i", "apt install", "opentars --setup"): baixa aqui, com a barra do Ollama
            msg "$(t pode_demorar)"
            if command -v ollama >/dev/null 2>&1; then
                ollama pull "$MODELO_GARGANTUA" || true
            else
                curl -fsS --max-time 7200 "$OLLAMA_URL/api/pull" \
                    -d "{\"model\":\"$MODELO_GARGANTUA\",\"stream\":false}" >/dev/null || true
            fi
            if gargantua_instalado; then
                msg "$(t baixado modelo="$MODELO_GARGANTUA")"
            else
                aviso "$(t nao_baixou modelo="$MODELO_GARGANTUA")"
            fi
        else
            # SEM terminal (loja de aplicativos, instalação automática, atualização pelo próprio openTARS): um pull aqui
            # segura a instalação por minutos sem mostrar nada, e a barra da loja fica parada em 0% enquanto o
            # Ollama já está em 50%. Baixa em segundo plano, solto da instalação; o assistente de primeiro uso do
            # openTARS acompanha o mesmo download (o Ollama junta os pedidos) e mostra a barra de verdade.
            msg "$(t gargantua_segundo_plano)"
            if command -v ollama >/dev/null 2>&1; then
                ( setsid nohup ollama pull "$MODELO_GARGANTUA" >/dev/null 2>&1 < /dev/null & )
            else
                ( setsid nohup curl -fsS --max-time 7200 "$OLLAMA_URL/api/pull" \
                    -d "{\"model\":\"$MODELO_GARGANTUA\",\"stream\":false}" >/dev/null 2>&1 < /dev/null & )
            fi
        fi
    fi
fi

# ------------------------------------------------------------------
# 4. Modelo de conversa: sem nenhum, o openTARS abre mas não tem quem
#    responda. Baixa UM, do tamanho certo pro PC, só se não houver
#    nenhum ainda (quem já tem modelos escolheu os seus).
#    TARS_MODELO_CONVERSA=<modelo> escolhe outro; TARS_SEM_MODELO=1 pula.
# ------------------------------------------------------------------
vram_gb() {
    local total=0
    if command -v nvidia-smi >/dev/null 2>&1; then
        total=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>/dev/null \
            | awk '{s+=$1} END {printf "%d", s/1024}')
    fi
    if [ "${total:-0}" -eq 0 ]; then
        for d in /sys/class/drm/card[0-9]*/device; do
            [ "$(cat "$d/vendor" 2>/dev/null)" = "0x1002" ] || continue
            local b; b=$(cat "$d/mem_info_vram_total" 2>/dev/null || echo 0)
            [ "$b" -ge 2147483648 ] && total=$((total + b / 1073741824))
        done
    fi
    echo "${total:-0}"
}

ram_gb() {
    awk '/MemTotal/ {printf "%d", $2/1048576}' /proc/meminfo 2>/dev/null || echo 0
}

modelo_de_conversa_sugerido() {
    local vram ram
    vram=$(vram_gb); ram=$(ram_gb)
    if [ "$vram" -ge 6 ]; then
        echo "qwen3:8b"        # ~5 GB, cabe na placa
    elif [ "$ram" -ge 12 ]; then
        echo "qwen3:4b"        # ~2.5 GB, roda bem na CPU
    else
        echo "qwen3:1.7b"      # ~1.4 GB, pra PC com pouca memória
    fi
}

contar_modelos_de_conversa() {
    modelos_instalados | grep -vx "$MODELO_AJUDANTE" | grep -vx "$MODELO_AJUDANTE_ANTIGO" \
        | grep -viE 'embed|minilm|bge-|cooper' | wc -l
}

if [ "$servico_pronto" -eq 1 ]; then
    outros=$(contar_modelos_de_conversa)
    if [ "$outros" -gt 0 ]; then
        msg "$(t ja_tem_modelos n="$outros")"
    elif [ "${TARS_SEM_MODELO:-0}" = "1" ]; then
        aviso "$(t sem_modelo_pedido)"
    else
        MODELO_CONVERSA="${TARS_MODELO_CONVERSA:-$(modelo_de_conversa_sugerido)}"
        msg "$(t baixando_conversa modelo="$MODELO_CONVERSA" vram="$(vram_gb)" ram="$(ram_gb)")"
        msg "$(t pode_demorar)"
        if command -v ollama >/dev/null 2>&1; then
            ollama pull "$MODELO_CONVERSA" || true
        else
            curl -fsS --max-time 7200 "$OLLAMA_URL/api/pull" \
                -d "{\"model\":\"$MODELO_CONVERSA\",\"stream\":false}" >/dev/null || true
        fi
        if modelos_instalados | grep -qx "$MODELO_CONVERSA"; then
            msg "$(t baixado modelo="$MODELO_CONVERSA")"
        else
            aviso "$(t nao_baixou modelo="$MODELO_CONVERSA")"
        fi
    fi
else
    aviso "$(t sem_ollama_modelo)"
fi

echo ""
echo "$(t pronto)"
echo "$(t dica_atalho)"
echo ""

exit 0
