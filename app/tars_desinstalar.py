"""5.2: `opentars --desinstalar`, igual nos três sistemas.

Pergunta antes de apagar as conversas e configurações e, à parte, os modelos oficiais do openTARS no Ollama (nunca sem
perguntar; os outros modelos do Ollama não são tocados). O programa em si sai pelo caminho de cada instalação: quem
instalou pelo script (Windows, macOS, Fedora/Arch/openSUSE) roda o --remover do próprio instalador; o .deb sai pelo apt,
e o comando é só mostrado, porque o sudo é da pessoa. Os relatórios do --diagnostico e do --prova na pasta pessoal ficam.
"""
import os
import shutil
import subprocess
from pathlib import Path

import tars_atualizacao
import tars_gerenciar_modelos
import tars_plataforma as plataforma

APP = Path(__file__).resolve().parent
REMOVEDOR = {
    "windows": ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                str(APP / "empacotamento" / "windows" / "instalar.ps1"), "-Remover"],
    "macos": ["bash", str(APP / "empacotamento" / "macos" / "instalar.sh"), "--remover"],
    "linux": ["bash", str(APP / "empacotamento" / "linux" / "instalar.sh"), "--remover"],
}


def pastas_de_dados():
    """As pastas e os arquivos com as conversas, as configurações, a memória e os registros (os de antes da 5.2 também)."""
    casa = Path.home()
    p = plataforma.pastas()
    antigos = [casa / ".tars_sessoes.json", casa / ".tars_pensa_sem_pedir.json",
               Path(os.environ.get("TARS_DIR_LOG") or casa / ".tars_log")]
    return [x for x in dict.fromkeys([p["config"], p["dados"], p["cache"], *antigos]) if x.exists()]


def _sim(pergunta, entrada):
    try:
        return entrada(f"{pergunta} [s/N] ").strip().lower() in ("s", "sim", "y", "yes")
    except EOFError:          # sem terminal para responder: não apaga nada
        return False


def executar(host, t, entrada=input, rodar=subprocess.run, soltar=subprocess.Popen):
    dados = pastas_de_dados()
    if dados and _sim(t("desinst.dados", pastas=", ".join(str(x) for x in dados)), entrada):
        for x in dados:
            shutil.rmtree(x, ignore_errors=True) if x.is_dir() else x.unlink(missing_ok=True)
        print(t("desinst.dados_ok"))
    try:
        oficiais = [m["nome"] for m in tars_gerenciar_modelos.listar(host) if m["nome"].lower().startswith("projectopentars/")]
    except Exception:  # noqa: BLE001  (Ollama parado: os modelos ficam, como sempre ficariam)
        oficiais = []
    if oficiais and _sim(t("desinst.modelos", nomes=", ".join(oficiais)), entrada):
        for nome in oficiais:
            ok, erro = tars_gerenciar_modelos.apagar(nome, host)
            print(f"  {nome}: {'ok' if ok else erro}")
    if not tars_atualizacao.pelo_script():
        print(t("desinst.deb"))
        return 0
    so = plataforma.sistema()
    if so == "windows":       # o removedor fecha o Python do openTARS e apaga a pasta: roda solto, depois que este sair
        soltar(REMOVEDOR[so], creationflags=subprocess.CREATE_NEW_CONSOLE)
        print(t("desinst.windows"))
        return 0
    return rodar(REMOVEDOR[so]).returncode
