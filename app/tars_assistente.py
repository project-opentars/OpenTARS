"""5.2: o assistente residente (decisões do Enzo, 20/10; tudo ligado por padrão desde 24/10). Sem Qt.

- Ligado: as ações de texto usam o Lite; depois de cada uso o modelo fica na memória só por KEEP_ALIVE_OCIOSO e o
  Ollama o descarrega sozinho (25/10, pedido do Enzo: parado, a IA sai da memória). Desligar descarrega na hora (0).
- Iniciar com o sistema: sobe o openTARS escondido (`opentars-gui --residente`), com o ícone na bandeja.
- O atalho das ações de texto é à parte (`tars_atalho.registrar_acoes`).
- aplicar_padroes(): liga tudo isso (e a sugestão pelo programa em uso) uma vez, na primeira abertura."""
import os
import sys
import threading
from pathlib import Path

import requests

import tars_i18n as i18n
import tars_plataforma as plataforma

NOME_AUTOSTART = "opentars-assistente"


def ligado():
    return bool(i18n.ler_config().get("assistente"))


KEEP_ALIVE_OCIOSO = "3m"       # quanto o modelo do assistente fica na memória depois do último uso


def manter_carregado(host, modelo, carregar, sessao=None):
    """Um pedido sem prompt carrega o modelo por KEEP_ALIVE_OCIOSO (e o Ollama descarrega sozinho) ou descarrega já (0)."""
    r = (sessao or requests).post(f"{host}/api/generate", json={"model": modelo, "keep_alive": KEEP_ALIVE_OCIOSO if carregar else 0},
                                  timeout=(5, 180))
    if r.status_code != 200:
        try:
            motivo = r.json().get("error")
        except ValueError:
            motivo = None
        raise RuntimeError(motivo or f"HTTP {r.status_code}")


def ligar(ativo, host, modelo, sessao=None):
    """Guarda a escolha. Ligar não carrega nada (a IA só entra na memória quando é usada); desligar descarrega o modelo
    na hora. Erro do Ollama sobe (a tela mostra); a escolha fica guardada."""
    i18n.salvar_config(assistente=bool(ativo))
    if not ativo:
        manter_carregado(host, modelo, False, sessao)


def comando_residente():
    if plataforma.sistema() == "windows":    # o atalho do Windows roda na pasta do app; pythonw não abre console
        python = Path(sys.executable)
        sem_console = python.with_name("pythonw.exe")
        return [str(sem_console if sem_console.exists() else python), "-m", "tars_qt", "--residente"]
    # shortcut: rodando da fonte (sem o pacote instalado) o início com o sistema não acha o opentars-gui; só vale instalado
    return [plataforma.lancador("opentars-gui") or "opentars-gui", "--residente"]


def inicia_com_sistema():
    try:
        return plataforma.arquivo_autostart(NOME_AUTOSTART).exists()
    except OSError:          # NaoSuportado fora do Linux, até a F5/F6
        return False


def iniciar_com_sistema(ativo):
    return plataforma.autostart(NOME_AUTOSTART, "openTARS", comando_residente(), bool(ativo))


def aplicar_padroes(em_segundo_plano=True):
    """Decisão do Enzo (24/10): o assistente vem todo ligado: o modelo das ações na memória, o atalho das ações de texto,
    o início com o sistema e a sugestão pelo programa em uso. Uma vez só (na primeira abertura, ou na primeira depois de
    atualizar), e só o que a pessoa ainda não escolheu: o que ela desligar depois continua desligado. Os testes e a prova
    (TARS_SEM_ATALHO=1) não mexem no sistema. O início com o sistema leva segundos no Windows (PowerShell): vai numa
    thread. Devolve o que ligou."""
    config = i18n.ler_config()
    if config.get("assistente_padroes") or os.environ.get("TARS_SEM_ATALHO") == "1":
        return []
    novos = {"assistente_padroes": True}
    if "assistente" not in config:
        novos["assistente"] = True
    if "sugestoes_programa" not in config:
        novos["sugestoes_programa"] = True
    i18n.salvar_config(**novos)
    ligou = [k for k in ("assistente", "sugestoes_programa") if k in novos]
    if "atalho_acoes_registrado" not in config:
        import tars_atalho
        try:
            if tars_atalho.registrar_acoes()[0]:
                ligou.append("atalho")
        except Exception:  # noqa: BLE001  (sem GNOME, sem gsettings: fica o botão Cadastrar na página Assistente)
            pass
    if not inicia_com_sistema():
        def inicio():
            try:
                iniciar_com_sistema(True)
            except Exception:  # noqa: BLE001  (sem permissão na pasta: fica a caixa na página Assistente)
                pass
        if em_segundo_plano:
            threading.Thread(target=inicio, daemon=True).start()
        else:
            inicio()
        ligou.append("inicio")
    return ligou
