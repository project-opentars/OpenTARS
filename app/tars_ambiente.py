"""openTARS 4.5 Endurance: onde o programa está rodando.

Parte pura (sem rede, sem tela): diz se é WSL, se há interface gráfica, e
traduz caminhos do Windows. Quem usa é o tars.py (modo sem interface, abrir
links pelo Windows, achar o Ollama do Windows a partir do WSL).

Três situações que importam:
  * área de trabalho Linux (X11 ou Wayland): tudo como sempre;
  * WSL com WSLg (o Windows 11 mostra janelas Linux): há DISPLAY, a janela
    abre, mas não existe uma "área de trabalho" Linux pra controlar;
  * sem interface (servidor, SSH, WSL sem WSLg, contêiner): só conversa no
    terminal, comandos, arquivos e a IA; nada de mouse, teclado nem tela.
"""

import os
import re
from pathlib import Path

import tars_plataforma as plataforma


def _ler(caminho):
    try:
        return Path(caminho).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def versao_wsl(env=None, ler=None):
    """1 ou 2 dentro do WSL; None fora dele."""
    env = os.environ if env is None else env
    ler = ler or _ler
    release = ler("/proc/sys/kernel/osrelease").lower()
    versao = ler("/proc/version").lower()
    dentro = bool(env.get("WSL_DISTRO_NAME") or env.get("WSL_INTEROP")) or "microsoft" in release or "microsoft" in versao
    if not dentro:
        return None
    return 2 if "wsl2" in release or "wsl2" in versao or env.get("WSL_INTEROP") else 1


def e_wsl(env=None, ler=None):
    return versao_wsl(env, ler) is not None


def tem_tela(env=None):
    env = os.environ if env is None else env
    # Windows e macOS sempre têm a área de trabalho do sistema; DISPLAY/WAYLAND_DISPLAY são coisa do Linux
    return plataforma.sistema() != "linux" or bool(env.get("DISPLAY") or env.get("WAYLAND_DISPLAY"))


def forcado_sem_interface(env=None):
    """TARS_SEM_INTERFACE=1: trata a máquina como sem tela mesmo com DISPLAY
    (servidor com X remoto, quem quer só o terminal)."""
    env = os.environ if env is None else env
    return str(env.get("TARS_SEM_INTERFACE", "")).lower() in ("1", "on", "sim", "yes", "true")


def detectar(env=None, ler=None):
    """{'wsl': 1|2|None, 'wslg': bool, 'tela': bool, 'ssh': bool, 'sem_interface': bool,
        'tipo': 'desktop'|'wslg'|'sem_tela', 'rotulo': str (em inglês)}"""
    env = os.environ if env is None else env
    wsl = versao_wsl(env, ler)
    sem = forcado_sem_interface(env) or not tem_tela(env)
    ssh = bool(env.get("SSH_CONNECTION") or env.get("SSH_TTY"))
    wslg = bool(wsl) and not sem and (bool(env.get("WAYLAND_DISPLAY")) or bool(env.get("DISPLAY")))
    tipo = "sem_tela" if sem else ("wslg" if wslg else "desktop")
    if sem:
        rotulo = f"WSL{wsl} (no graphical session)" if wsl else ("SSH (no graphical session)" if ssh else "no graphical session")
    elif wslg:
        rotulo = f"WSL{wsl} with WSLg"
    else:
        rotulo = "desktop"
    return {"wsl": wsl, "wslg": wslg, "tela": not sem, "ssh": ssh, "sem_interface": sem, "tipo": tipo, "rotulo": rotulo}


# ------------------------------------------------------------
# Caminhos do Windows vistos de dentro do WSL
# ------------------------------------------------------------

_UNIDADE = re.compile(r"^([A-Za-z]):[\\/]*(.*)$", re.DOTALL)
_REDE_WSL = re.compile(r"^[\\/]{2}(?:wsl\$|wsl\.localhost)[\\/]+[^\\/]+[\\/]*(.*)$", re.IGNORECASE | re.DOTALL)


def parece_caminho_windows(texto):
    t = (texto or "").strip()
    return bool(_UNIDADE.match(t) or _REDE_WSL.match(t))


def caminho_do_windows(texto):
    """'C:\\Users\\ana\\a b.txt' -> '/mnt/c/Users/ana/a b.txt';
    '\\\\wsl$\\Ubuntu\\home\\ana\\x' -> '/home/ana/x'. Texto que não parece
    caminho do Windows volta como veio."""
    t = (texto or "").strip()
    achado = _REDE_WSL.match(t)
    if achado:
        return "/" + achado.group(1).replace("\\", "/").strip("/")
    achado = _UNIDADE.match(t)
    if achado:
        resto = achado.group(2).replace("\\", "/").strip("/")
        base = f"/mnt/{achado.group(1).lower()}"
        return f"{base}/{resto}" if resto else base
    return t


# ------------------------------------------------------------
# Ollama do Windows, visto de dentro do WSL2
# ------------------------------------------------------------

def gateway_padrao(texto_route):
    """IP do gateway padrão a partir do conteúdo de /proc/net/route."""
    for linha in (texto_route or "").splitlines()[1:]:
        campos = linha.split()
        if len(campos) >= 3 and campos[1] == "00000000":
            try:
                n = int(campos[2], 16)
            except ValueError:
                continue
            if n:
                return ".".join(str((n >> (8 * i)) & 255) for i in range(4))
    return None


def servidor_dns(texto_resolv):
    for linha in (texto_resolv or "").splitlines():
        partes = linha.split()
        if len(partes) >= 2 and partes[0] == "nameserver" and re.fullmatch(r"\d+\.\d+\.\d+\.\d+", partes[1]):
            return partes[1]
    return None


def candidatos_ollama_wsl(porta=11434, ler=None):
    """Endereços onde o Ollama do Windows pode estar, vistos do WSL2 (além
    do 127.0.0.1 de sempre): o IP do Windows aparece como servidor DNS e
    como gateway. Sem repetição, na ordem em que vale tentar."""
    ler = ler or _ler
    achados = []
    for ip in (servidor_dns(ler("/etc/resolv.conf")), gateway_padrao(ler("/proc/net/route"))):
        if ip and ip not in achados and not ip.startswith("127."):
            achados.append(ip)
    return [f"http://{ip}:{porta}" for ip in achados]


def abridor_de_links_do_windows(existe=None):
    """Como abrir um link no navegador do Windows a partir do WSL sem
    interface: ['wslview'] (pacote wslu) ou ['explorer.exe']. None se não houver."""
    import shutil
    existe = existe or shutil.which
    for comando in (["wslview"], ["explorer.exe"]):
        if existe(comando[0]):
            return comando
    return None
