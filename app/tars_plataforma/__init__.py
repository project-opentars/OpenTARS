"""openTARS 5.2: a única porta de entrada para o que muda de sistema (Linux, Windows, macOS).

Este arquivo traz a interface e o que não depende do sistema (as pastas); o resto vai para o backend de cada sistema
(`linux.py`, `windows.py`, `macos.py`), escolhido na hora da chamada. No Linux é o código que o app já usava; no Windows e no
macOS só existe o que dá para fazer sem testar na máquina, e o que falta levanta `NaoSuportado` dizendo a fase do
`PLANO_5.2.md` em que entra, para nada falhar em silêncio. Só biblioteca padrão, sem Qt.

O que continua preso ao Linux fora daqui, de propósito, até a fase do sistema: a descoberta de programas pelos `.desktop`
(`nucleo/aplicacoes.py`), as janelas do X (`nucleo/janelas.py`), a acessibilidade AT-SPI (`tars_acessibilidade.py`), o
ydotool do Wayland (`tars_wayland.py`), o atalho global do GNOME (`tars_atalho.py`) e o soquete de instância única em
`XDG_RUNTIME_DIR` (`tars_instancia.py`).

Interface (devolvem o resultado ou levantam `NaoSuportado`/`OSError`):
    sistema()                               "linux" | "windows" | "macos"
    pastas()                                {"casa", "config", "dados", "cache"} (Path)
    abrir(alvo)                             abre arquivo, pasta ou endereço no programa padrão
    lixeira(caminho)                        manda para a lixeira (nunca apaga de vez)
    notificar(titulo, texto)                notificação do sistema (não espera)
    ler_area_de_transferencia()             texto copiado
    escrever_area_de_transferencia(texto)
    arquivo_autostart(nome)                 onde fica o início automático com a sessão
    autostart(nome, titulo, comando, ligado) liga ou desliga o início automático; devolve se ficou ligado
    tecla_comando()                         "ctrl", ou "command" no macOS (colar, copiar, salvar)
    ler_selecao()                           o texto marcado agora em qualquer programa ("" se nada)
    teclas_de_colar()                       as teclas de colar na janela ativa (Ctrl+Shift+V num terminal do Linux)
    nome_do_sistema()                       "Windows 11 23H2", "macOS 15.2 Sequoia" (o Linux lê o /etc/os-release no prompt)
    janelas(), janela_ativa(), focar_janela(id), fechar_janela(id), mover_janela(id, x, y, largura, altura, maximizar),
    area_util()                             fora do Linux (no Linux o núcleo fala com o X direto: nucleo/janelas.py)
    programas()                             [{nome, outros_nomes, comando, id}] fora do Linux (no Linux: os .desktop)
    recursos()                              {função: existe neste sistema?} (para o diagnóstico)
    lancador(nome)                          o comando instalado (opentars, opentars-gui), no PATH ou em ~/.local/bin
    comando_instalar(*pacotes)              "sudo dnf install ..." com os nomes desta distribuição (só no Linux)
    dica_instalar(texto)                    troca "sudo apt install x" num texto pelo comando desta distribuição
    descrever()                             sistema, versão, arquitetura, núcleos, RAM e Python (para os relatórios)
"""
import os
import platform
import re
import shutil
import sys
from pathlib import Path

NOME = "opentars"


class NaoSuportado(OSError):
    """Esta função ainda não existe neste sistema; a mensagem diz em que fase da 5.2 ela entra."""


def sistema():
    if sys.platform.startswith("win"):
        return "windows"
    return "macos" if sys.platform == "darwin" else "linux"


def _backend():
    so = sistema()
    if so == "windows":
        from . import windows as backend
    elif so == "macos":
        from . import macos as backend
    else:
        from . import linux as backend
    return backend


def pastas():
    casa = Path.home()
    so = sistema()
    if so == "windows":
        roaming = Path(os.environ.get("APPDATA") or casa / "AppData" / "Roaming")
        local = Path(os.environ.get("LOCALAPPDATA") or casa / "AppData" / "Local")
        return {"casa": casa, "config": roaming / NOME, "dados": local / NOME, "cache": local / NOME / "cache"}
    if so == "macos":
        base = casa / "Library"
        return {"casa": casa, "config": base / "Application Support" / NOME, "dados": base / "Application Support" / NOME,
                "cache": base / "Caches" / NOME}
    xdg = lambda var, padrao: Path(os.environ.get(var) or casa / padrao)  # noqa: E731
    return {"casa": casa, "config": xdg("XDG_CONFIG_HOME", ".config") / NOME, "dados": xdg("XDG_DATA_HOME", ".local/share") / NOME,
            "cache": xdg("XDG_CACHE_HOME", ".cache") / NOME}


def abrir(alvo):
    return _backend().abrir(alvo)


def lancador(nome):
    """O comando instalado (opentars, opentars-gui): no PATH ou em ~/.local/bin, onde os instaladores por usuário o põem
    (o Arch e o macOS aberto pelo Finder não têm ~/.local/bin no PATH). None se não houver."""
    local = Path.home() / ".local" / "bin" / nome
    return shutil.which(nome) or (str(local) if local.is_file() and os.access(local, os.X_OK) else None)


def comando_instalar(*pacotes):
    """Os pacotes vêm com o nome do Debian; volta o comando com os nomes desta distribuição. Fora do Linux, None."""
    return _backend().comando_instalar(*pacotes) if sistema() == "linux" else None


_RE_APT = re.compile(r"sudo apt(?:-get)? install((?: [a-z0-9][\w.+:-]*)+)")


def dica_instalar(texto):
    """Troca "sudo apt install x y" num aviso pelo comando desta distribuição (dnf, pacman, zypper), com os nomes de lá."""
    if sistema() != "linux" or (_backend().gerenciador() or "apt") == "apt":
        return texto
    return _RE_APT.sub(lambda m: comando_instalar(*m.group(1).split()), texto)


def lixeira(caminho):
    return _backend().lixeira(caminho)


def notificar(titulo, texto):
    return _backend().notificar(titulo, texto)


def ler_area_de_transferencia():
    return _backend().ler_area_de_transferencia()


def escrever_area_de_transferencia(texto):
    return _backend().escrever_area_de_transferencia(texto)


def ler_selecao():
    return _backend().ler_selecao()


def teclas_de_colar():
    return _backend().teclas_de_colar()


def arquivo_autostart(nome):
    return _backend().arquivo_autostart(nome)


def autostart(nome, titulo, comando, ligado=True):
    return _backend().autostart(nome, titulo, comando, ligado)


def nome_do_sistema():
    """O nome que vai no bloco THIS COMPUTER fora do Linux, no formato dos dados da 5.2."""
    so = sistema()
    if so == "macos":
        versao = platform.mac_ver()[0]
        nomes = {"26": "Tahoe", "15": "Sequoia", "14": "Sonoma", "13": "Ventura", "12": "Monterey", "11": "Big Sur"}
        return " ".join(x for x in ("macOS", versao, nomes.get(versao.split(".")[0], "")) if x)
    if so == "windows":
        return " ".join(x for x in ("Windows", platform.release(), _versao_windows()) if x)
    return "Linux"


def _versao_windows():
    """23H2, 24H2...: só o registro sabe (o platform dá o número do build)."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion") as chave:
            return winreg.QueryValueEx(chave, "DisplayVersion")[0]
    except (ImportError, OSError):
        return ""


def janelas():
    return _backend().janelas()


def janela_ativa():
    return _backend().janela_ativa()


def focar_janela(id_janela):
    return _backend().focar_janela(id_janela)


def fechar_janela(id_janela):
    return _backend().fechar_janela(id_janela)


def mover_janela(id_janela, x=None, y=None, largura=None, altura=None, maximizar=None):
    return _backend().mover_janela(id_janela, x, y, largura, altura, maximizar)


def area_util():
    return _backend().area_util()


def programas():
    return _backend().programas()


def tecla_comando():
    return "command" if sistema() == "macos" else "ctrl"


FUNCOES = ("abrir", "lixeira", "notificar", "ler_area_de_transferencia", "escrever_area_de_transferencia", "autostart",
           "ler_selecao", "teclas_de_colar")
FUNCOES_FORA_DO_LINUX = ("janelas", "programas")      # no Linux o núcleo usa o X e os .desktop


def recursos():
    backend = _backend()
    funcoes = FUNCOES + (FUNCOES_FORA_DO_LINUX if sistema() != "linux" else ())
    return {funcao: funcao in vars(backend) for funcao in funcoes}


def descrever():
    so = sistema()
    versao = (platform.mac_ver()[0] if so == "macos" else " ".join(x for x in platform.win32_ver()[:2] if x) if so == "windows"
              else platform.release())
    try:
        import psutil
        ram = round(psutil.virtual_memory().total / 1024 ** 3, 1)
    except (ImportError, OSError, AttributeError):   # AttributeError: psutil de mentira nos testes
        ram = None
    return {"sistema": so, "versao": versao, "plataforma": platform.platform(), "arquitetura": platform.machine(),
            "processador": platform.processor() or None, "nucleos": os.cpu_count(), "ram_gb": ram,
            "python": platform.python_version()}
