"""5.2: o assistente residente (decisões do Enzo, 20/10). Sem Qt.

- Ligado: o Gargantua Lite fica na memória do Ollama (keep_alive -1) para as ações de texto responderem na hora; desligar
  descarrega na hora (keep_alive 0). O Gargantua 2 só carrega quando uma ação pede (texto longo) e descarrega sozinho.
- Iniciar com o sistema: só se a pessoa ligar; sobe o openTARS escondido (`opentars-gui --residente`), com o ícone na bandeja.
- O atalho das ações de texto é à parte (`tars_atalho.registrar_acoes`)."""
import shutil
import sys
from pathlib import Path

import requests

import tars_i18n as i18n
import tars_plataforma as plataforma

NOME_AUTOSTART = "opentars-assistente"


def ligado():
    return bool(i18n.ler_config().get("assistente"))


def manter_carregado(host, modelo, carregar, sessao=None):
    """Um pedido sem prompt só carrega (keep_alive -1: até mandar descarregar) ou descarrega (0) o modelo."""
    r = (sessao or requests).post(f"{host}/api/generate", json={"model": modelo, "keep_alive": -1 if carregar else 0},
                                  timeout=(5, 180))
    if r.status_code != 200:
        try:
            motivo = r.json().get("error")
        except ValueError:
            motivo = None
        raise RuntimeError(motivo or f"HTTP {r.status_code}")


def ligar(ativo, host, modelo, sessao=None):
    """Guarda a escolha e carrega/descarrega o Lite. Erro do Ollama sobe (a tela mostra); a escolha fica guardada."""
    i18n.salvar_config(assistente=bool(ativo))
    manter_carregado(host, modelo, bool(ativo), sessao)


def comando_residente():
    if plataforma.sistema() == "windows":    # o atalho do Windows roda na pasta do app; pythonw não abre console
        python = Path(sys.executable)
        sem_console = python.with_name("pythonw.exe")
        return [str(sem_console if sem_console.exists() else python), "-m", "tars_qt", "--residente"]
    # shortcut: rodando da fonte (sem o pacote instalado) o início com o sistema não acha o opentars-gui; só vale instalado
    return [shutil.which("opentars-gui") or "opentars-gui", "--residente"]


def inicia_com_sistema():
    try:
        return plataforma.arquivo_autostart(NOME_AUTOSTART).exists()
    except OSError:          # NaoSuportado fora do Linux, até a F5/F6
        return False


def iniciar_com_sistema(ativo):
    return plataforma.autostart(NOME_AUTOSTART, "openTARS", comando_residente(), bool(ativo))
