#!/usr/bin/env python3

import os
import sys
import difflib
import json
import time
import shlex
import shutil
import subprocess
import tempfile
import webbrowser
import threading
import re
import io
import base64
import gettext
import functools
import unicodedata
from pathlib import Path
from urllib.parse import quote_plus
from concurrent.futures import ThreadPoolExecutor

import socket
import logging
from logging.handlers import RotatingFileHandler

import requests
import psutil
from PIL import Image

import tars_i18n as i18n
from tars_i18n import t
import tars_acessibilidade as acess
import tars_escolha as escolha
import tars_murph as murph
import tars_mouse as mouse
import tars_memoria as memoria_lib
import tars_atualizacao as atualizacao
rotinas_lib = memoria_lib  # nome antigo (o kit do Gargantua ainda usa)
import tars_ambiente as ambiente
import tars_visao as visao_lib
import tars_openai as api
import tars_voz as voz_lib
import tars_anexos as anexos_lib
import tars_rotinas as agenda_lib
import tars_primeiro_uso as primeiro_uso
import tars_modos as modos
import tars_confianca as confianca_lib
import tars_plataforma as plataforma
import tars_shell as shell_lib

# Windows: num terminal ou num pipe em cp1252 não existem ✓ ✗ ⎿; trocar o caractere é melhor que o programa cair
for _saida in (sys.stdout, sys.stderr):
    try:
        _saida.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
import tars_probes as probes_lib
import tars_web as web_lib


# ------------------------------------------------------------
# Sessão gráfica. O controle de mouse/teclado (pyautogui) fala com o
# servidor X. Numa sessão Wayland ele só alcança janelas XWayland, e
# sem nenhum display ele nem importa: o import falha e, antes, isso
# derrubava o openTARS inteiro, até o chat que não precisa de mouse.
# ------------------------------------------------------------

def _tipo_sessao():
    # 4.5: TARS_SEM_INTERFACE=1 trata a máquina como sem tela (servidor, SSH, só terminal)
    if ambiente.forcado_sem_interface():
        return "nenhuma"
    if os.environ.get("WAYLAND_DISPLAY") or os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland":
        return "wayland"
    if os.environ.get("DISPLAY"):
        return "x11"
    # 5.2: os nomes de sessão que o Gargantua viu no treino (bloco THIS COMPUTER da "pele de sistema")
    return {"windows": "windows", "macos": "aqua"}.get(plataforma.sistema(), "nenhuma")


SESSAO_GRAFICA = _tipo_sessao()
# 4.5 Endurance: onde estamos (WSL? sem tela?). Sem tela, o openTARS vira um
# assistente de terminal: conversa, comandos, arquivos e as IAs.
AMBIENTE = ambiente.detectar()
if SESSAO_GRAFICA == "nenhuma":
    AMBIENTE["sem_interface"], AMBIENTE["tela"] = True, False
SEM_INTERFACE = AMBIENTE["sem_interface"]
EM_WSL = bool(AMBIENTE["wsl"])


class _PyautoguiIndisponivel:
    """Fica no lugar do pyautogui quando ele não carrega: qualquer uso
    (mover mouse, clicar, digitar) vira um erro com o motivo real, que
    a ferramenta devolve pra IA em vez de quebrar o programa."""

    def __init__(self, motivo):
        self.__dict__["_motivo"] = motivo

    def __getattr__(self, nome):
        raise RuntimeError(f"mouse/keyboard control unavailable: {self._motivo}")


# O pyautogui (via python-xlib) aborta a importação se não houver
# arquivo de autorização do X. Sem ~/.Xauthority e sem $XAUTHORITY não
# existe cookie nenhum mesmo, então apontar pra um arquivo vazio só
# evita o crash (os lançadores fazem o mesmo; isso cobre quem roda o
# tars.py direto).
def achar_autorizacao_x():
    """O arquivo de cookie do X. No GNOME com Wayland o XWayland guarda o seu em /run/user/<uid>/ (o mutter cria
    .mutter-Xwaylandauth.*); apontar pra /dev/null nesse caso impede a conexão ("Authorization required")."""
    try:
        pasta = Path(os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}")
        for padrao in (".mutter-Xwaylandauth.*", "xauth_*", ".Xwaylandauth*"):
            for arq in sorted(pasta.glob(padrao)):
                if arq.is_file():
                    return str(arq)
    except OSError:
        pass
    return None


if plataforma.sistema() == "linux" and not os.environ.get("XAUTHORITY") and not (Path.home() / ".Xauthority").exists():
    os.environ["XAUTHORITY"] = achar_autorizacao_x() or "/dev/null"

try:
    import pyautogui
    ERRO_PYAUTOGUI = None
except Exception as _e:  # sem display, display inacessível, Xlib ausente...
    # Texto técnico (vai pra IA nos resultados das ferramentas); pro
    # usuário, avisos_de_ambiente() explica no idioma dele.
    ERRO_PYAUTOGUI = (
        "no graphical session (DISPLAY is empty)"
        if SESSAO_GRAFICA == "nenhuma"
        else f"{type(_e).__name__}: {_e}"
    )
    pyautogui = _PyautoguiIndisponivel(ERRO_PYAUTOGUI)


# 3.0: no Wayland, mouse e teclado pelo ydotool (1.0+, com o ydotoold
# rodando), que alcança qualquer janela. Sem ele, fica o pyautogui (só
# janelas XWayland). TARS_YDOTOOL=0 desliga. Ver tars_wayland.py.
import tars_wayland as wayland  # noqa: E402

ENTRADA_WAYLAND = None      # "ydotool" quando o mouse/teclado vão por ele
MOTIVO_SEM_YDOTOOL = None
if SESSAO_GRAFICA == "wayland" and os.environ.get("TARS_YDOTOOL", "1") not in ("0", "off", "no", "nao"):
    MOTIVO_SEM_YDOTOOL = wayland.motivo_indisponivel()
    if MOTIVO_SEM_YDOTOOL is None:
        try:
            _tamanho_tela = pyautogui.size()  # o XWayland sabe o tamanho da área de trabalho
        except Exception:
            _tamanho_tela = (1920, 1080)
        pyautogui = wayland.PyautoguiYdotool(_tamanho_tela)
        ERRO_PYAUTOGUI = None
        ENTRADA_WAYLAND = "ydotool"


# ============================================================
# CONFIGURAÇÃO
# ============================================================

VERSAO = "5.1"
# 3.0 Miller: o classificador Murph e o modo AUTO.
# 4.0 Endurance: o Gargantua (IA oficial); Endurance Neo: aviso de versão nova, tarefas longas.
# 4.5 Endurance: o Cooper (visão da tela), WSL e Linux sem interface gráfica.
# 4.6 Endurance: a versão mais leve (19 ferramentas; só Ollama; sem voz, anexos, OCR, desfazer);
#     o que saiu volta a ser considerado na 5.0.
# 5.0 Tesseract: janela nova em Qt (PySide6), igual ao mockup; começa pelo assistente de primeiro uso.
# 5.1 Tesseract: modos Lite/Base/Pro, Probes, terminal no nível das CLIs de IA, Gargantua Lite no setup, nuvem pela
#     conta do Ollama e pesquisa web pelo SearXNG.
CODINOME = "Tesseract"
VERSAO_EXIBIDA = f"{VERSAO} {CODINOME}"
# Endurance Neo: sobe a cada pacote publicado (AAAAMMDDNN). O aviso de versão
# nova compara com a REVISAO do tars.py do GitHub (tars_atualizacao.py).
REVISAO = 2026102103

# Endereço do servidor Ollama — respeita a variável de ambiente padrão
# do próprio Ollama (OLLAMA_HOST), pra funcionar sem editar o código
# em qualquer máquina onde o Ollama não esteja no endereço padrão
# (outra porta, outro host na rede, WSL, container etc.).
def _normalizar_ollama_host(valor):
    """Interpreta OLLAMA_HOST do mesmo jeito que o próprio Ollama: o
    valor pode vir sem esquema ("0.0.0.0", "192.168.0.10:11434"), sem
    porta, ou só com a porta (":11434"). Muita gente deixa
    OLLAMA_HOST=0.0.0.0 no ambiente pra expor o Ollama na rede — usado
    cru, isso virava a URL "0.0.0.0/api/chat" e nada funcionava."""

    s = (valor or "").strip()
    if not s:
        return "http://127.0.0.1:11434"

    if "://" in s:
        esquema, resto = s.split("://", 1)
        esquema = esquema.lower()
        porta_padrao = {"http": "80", "https": "443"}.get(esquema, "11434")
    else:
        esquema, resto = "http", s
        porta_padrao = "11434"

    hostporta, _, caminho = resto.partition("/")

    m = re.fullmatch(r"\[([^\]]*)\](?::(\d+))?", hostporta)  # IPv6: [::1]:11434
    if m:
        host, porta = m.group(1), m.group(2)
    elif hostporta.count(":") == 1:
        host, porta = hostporta.split(":")
    else:
        host, porta = hostporta, None

    # Endereços "escute em todas as interfaces" servem pro servidor,
    # não pra conectar: do lado do cliente, significam esta máquina.
    if host in ("", "0.0.0.0", "::"):
        host = "127.0.0.1"
    if ":" in host:
        host = f"[{host}]"

    url = f"{esquema}://{host}:{porta or porta_padrao}"
    if caminho.strip("/"):
        url += "/" + caminho.strip("/")
    return url


OLLAMA_HOST = _normalizar_ollama_host(os.environ.get("OLLAMA_HOST"))


def _ollama_responde(url, espera=0.8):
    try:
        return requests.get(f"{url}/api/version", timeout=espera).status_code == 200
    except Exception:
        return False


# 4.5: no WSL2 o Ollama costuma estar no Windows, e o "localhost" do Linux não
# o alcança (rede NAT). Sem OLLAMA_HOST definido e sem Ollama local, tenta o IP
# do Windows (servidor DNS e gateway do WSL). O Ollama do Windows precisa
# escutar fora do 127.0.0.1 (OLLAMA_HOST=0.0.0.0 lá).
OLLAMA_NO_WINDOWS = False
if EM_WSL and not os.environ.get("OLLAMA_HOST") and not _ollama_responde(OLLAMA_HOST):
    for _candidato in ambiente.candidatos_ollama_wsl():
        if _ollama_responde(_candidato):
            OLLAMA_HOST, OLLAMA_NO_WINDOWS = _candidato, True
            break

OLLAMA_URL = f"{OLLAMA_HOST}/api/chat"
OLLAMA_TAGS_URL = f"{OLLAMA_HOST}/api/tags"
OLLAMA_SHOW_URL = f"{OLLAMA_HOST}/api/show"
OLLAMA_GENERATE_URL = f"{OLLAMA_HOST}/api/generate"
OLLAMA_PS_URL = f"{OLLAMA_HOST}/api/ps"

# Quanto tempo cada modelo fica na memória (RAM/VRAM) depois do último uso: o
# Ollama o descarrega sozinho. Curto = PC fraco liberado mais cedo; o modelo
# que ficou parado não custa nada. Tudo é carregado só quando um pedido precisa.
#   KEEP_ALIVE        modelo da conversa (varia: TARS_KEEP_ALIVE=15m)
#   KEEP_ALIVE_VISAO  Cooper e modelos que só descrevem prints (TARS_KEEP_ALIVE_VISAO)
#   KEEP_ALIVE_AJUDANTE  IA leve de bastidor
# Aceita "30s", "5m", "1h", ou "0" (descarrega logo após cada resposta).
KEEP_ALIVE = os.environ.get("TARS_KEEP_ALIVE", "5m")
KEEP_ALIVE_VISAO = os.environ.get("TARS_KEEP_ALIVE_VISAO", "2m")
KEEP_ALIVE_AJUDANTE = os.environ.get("TARS_KEEP_ALIVE_AJUDANTE", "2m")
# TARS_PRECARGA=1 volta a carregar o ajudante e o Cooper ao abrir (PC forte, quer o 1º pedido mais rápido).
PRECARGA = os.environ.get("TARS_PRECARGA", "0").lower() in ("1", "on", "yes", "sim", "true")

# Usado só como último recurso, se o catálogo dinâmico (ver mais
# abaixo) vier vazio por algum motivo (Ollama offline, sem nenhum
# modelo baixado). O TARS não depende mais de uma lista fixa de
# modelos — ele descobre o que está instalado e como cada um se
# comporta consultando o próprio Ollama.
MODELO_PADRAO = os.environ.get("TARS_MODELO_PADRAO", "qwen3:0.6b")

# Neo: o classificador por IA (qwen2.5:0.5b) saiu; quem decide o tipo do
# pedido é a helper Murph. Os ajudantes das versões antigas, se ainda
# estiverem instalados, ficam fora da escolha de conversa.
class _Ajudantes(set):
    """Modelos que não entram na escolha de conversa: os ajudantes antigos e
    o Cooper (4.5), que só olha a tela."""

    def __contains__(self, tag):
        return set.__contains__(self, tag) or visao_lib.e_cooper(tag)


MODELOS_AJUDANTES = _Ajudantes({"qwen2.5:0.5b", "gemma3:270m"})

# ------------------------------------------------------------
# Timeouts de rede (segundos) — nomeados por propósito, não por valor,
# pra ficar claro o que cada chamada está esperando e por quê.
# ------------------------------------------------------------
TIMEOUT_HTTP_CURTO = 5          # checagens rápidas: /api/tags, /api/ps
TIMEOUT_HTTP_MODELO_INFO = 6    # /api/show de um modelo
TIMEOUT_HTTP_DESCARREGAR = 30   # pedido de unload (keep_alive=0)
TIMEOUT_HTTP_AJUDANTE = 20      # consulta pontual e curta a um modelo leve
TIMEOUT_HTTP_LONGO = 600        # carregar um modelo grande / resposta de conversa completa
TIMEOUT_TERMINAL_COMANDO = 30   # comando digitado pelo usuário/IA no terminal
TIMEOUT_SUBPROCESSO_PADRAO = 15 # subprocessos internos em geral (flatpak, etc.)
TIMEOUT_GPU = 5                 # nvidia-smi
TIMEOUT_FLATPAK_LISTAGEM = 10   # flatpak list
TIMEOUT_DNS = 3                 # checar se um domínio sugerido pela IA existe de fato


# ------------------------------------------------------------
# Temperaturas — cada uso tem um propósito diferente: a classificadora
# quer sempre a mesma resposta pro mesmo texto (determinístico), a
# conversa principal quer um pouco de variação natural.
# ------------------------------------------------------------
TEMPERATURA_CONVERSA = 0.1


def temperatura_conversa():
    """5.1: no modo Pro a pessoa pode trocar a temperatura (Configurações > Ajustes avançados)."""
    escolhida = modos.avancado()["temperatura"]
    return TEMPERATURA_CONVERSA if escolhida is None else escolhida


TEMPERATURA_AJUDANTE = 0.1

# TTL (segundos) do cache de apps instalados (.desktop / flatpak).
# Evita re-escanear o sistema de arquivos e chamar subprocess a cada comando.
CACHE_APPS_TTL = 30

# ------------------------------------------------------------
# Outros limites/ajustes numéricos usados pelo código — nomeados aqui
# em vez de espalhados como números soltos no meio da lógica.
# ------------------------------------------------------------
LIMITE_CICLOS_FERRAMENTAS = 20      # máximo de idas-e-voltas com tool calls por mensagem (clicar num app leva vários)
LIMITE_HISTORICO_MENSAGENS = 30     # mensagens guardadas por sessão antes de podar
LIMITE_STDOUT_CHARS = 8000          # truncamento do stdout do terminal
LIMITE_STDERR_CHARS = 4000          # truncamento do stderr do terminal
LIMITE_CANDIDATOS_APP = 5           # nomes de executável sugeridos pela IA por pedido
LARGURA_MINIMA_CAIXA = 44           # largura mínima das caixas de status no terminal

# Confirmação de que um app abriu: em vez de dormir um tempo fixo e só
# então checar uma vez (que ou demora demais pra apps rápidos, ou é
# curto demais pra apps pesados tipo navegador), faz polling — checa
# em intervalos curtos até confirmar o processo ativo ou estourar o
# teto. Isso deixa apps leves (calculadora, editor de texto) prontos
# quase na hora, e dá mais chance real de apps pesados estarem de pé
# antes do TARS devolver sucesso — importante pra tarefa composta tipo
# "abra X e digite Y", onde o type_text roda logo em seguida.
INTERVALO_POLL_PROCESSO_SEG = 0.15
TIMEOUT_POLL_PROCESSO_SEG = 2.0

# Automação de mouse/teclado — durações bem curtas de propósito: o
# usuário quer velocidade aqui, não uma animação suave de cursor.
# pyautogui.PAUSE (configurado logo abaixo) é o que mais pesava nisso:
# por padrão ele insere 0.1s de pausa DEPOIS de toda chamada (move,
# clique, tecla...), e numa tarefa com vários passos (abrir, mover,
# clicar, digitar, apertar tecla) isso somava meio segundo só de
# pausas artificiais.
DURACAO_MOVER_MOUSE_SEG = 0.03
DURACAO_MOVER_PARA_SCROLL_SEG = 0.02
INTERVALO_DIGITACAO_SEG = 0.005
PYAUTOGUI_PAUSE_SEG = 0.01

pyautogui.PAUSE = PYAUTOGUI_PAUSE_SEG
# FAILSAFE fica ligado de propósito: jogar o mouse pro canto da tela
# ainda aborta qualquer automação em andamento, e isso não tem custo
# de velocidade nenhum.

TENTATIVAS_ENCERRAR_IAS = 4
ESPERA_ENTRE_TENTATIVAS_ENCERRAR_SEG = 1.5

# Largura máxima (em pixels) do print enviado pro modelo de visão.
# Uma tela 4K sem redimensionar gera um PNG grande o bastante pra
# pesar de verdade na codificação em base64, no envio pro Ollama e no
# processamento da imagem pelo próprio modelo (que internamente já
# reduz a resolução de qualquer jeito) — encolher ANTES de mandar
# corta esse tempo todo sem perder legibilidade prática (texto de UI
# continua lendo bem nessa largura). Configurável por variável de
# ambiente pra quem quiser mais nitidez à custa de velocidade.
LARGURA_MAXIMA_SCREENSHOT = int(os.environ.get("TARS_LARGURA_SCREENSHOT", "1280"))

# Capacidades reconhecidas pelo Ollama que o TARS realmente usa pra
# decidir comportamento — mostradas na listagem de modelos e citadas
# no prompt da IA classificadora.
_CAPACIDADES_RELEVANTES = {"tools", "vision", "thinking"}


# ============================================================
# NÚCLEO EM PARTES (3.0)
# ============================================================
#
# O núcleo tinha 7.800 linhas num arquivo só. Agora cada assunto fica em
# nucleo/<parte>.py, executado aqui, na ordem, dentro deste namespace:
# pra quem usa (tars_gui, testes, "import tars") nada muda, tars.<nome>
# continua existindo, e trocar tars.<função> num teste vale em todas as
# partes. Os tracebacks apontam o arquivo e a linha da parte.

PASTA_NUCLEO = Path(__file__).resolve().parent / "nucleo"
PARTES_NUCLEO = (
    "registro",
    "ollama",
    "hardware",
    "aplicacoes",
    "controle",
    "janelas",
    "visao",
    "elementos",
    "ferramentas",
    "selecao",
    "prompt",
    "chat",
    "nuvem",
    "anexos",
    "memoria",
    "rotinas",
    "utilidades",
    "gargantua",
    "codigo",
    "web",
    "voz",
    "terminal",
)


def _carregar_nucleo():
    for parte in PARTES_NUCLEO:
        caminho = PASTA_NUCLEO / f"{parte}.py"
        codigo = compile(caminho.read_text(encoding="utf-8"), str(caminho), "exec")
        exec(codigo, globals())


_carregar_nucleo()


if __name__ == "__main__":
    main()
