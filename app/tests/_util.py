"""Utilitário compartilhado pelos testes: carrega tars.py isolado, sem
precisar dos pacotes de sistema (pyautogui, psutil) instalados — eles
são só usados pra controlar mouse/teclado e ler CPU/RAM, nada disso é
necessário pra testar a lógica (seleção de modelo, detecção de tarefa,
resolução de app/site, etc).

Uso, em qualquer test_*.py desta pasta:

    from _util import carregar_tars
    tars = carregar_tars()
"""

import importlib.util
import os
import sys
import tempfile
import types

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CAMINHO_TARS = os.path.join(RAIZ, "tars.py")

# Os módulos irmãos (tars_i18n, tars_acessibilidade...) são importados pelo
# tars.py; os testes rodam de dentro de tests/.
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

# Testes previsíveis: textos em português (a menos que o teste peça outro
# idioma) e nada gravado na configuração real do usuário.
os.environ.setdefault("TARS_IDIOMA", "pt_BR")
os.environ.setdefault("TARS_SEM_AVISO_VERSAO", "1")  # testes não vão à internet ver se há versão nova
os.environ.setdefault("TARS_ARQUIVO_CONFIG", os.path.join(tempfile.mkdtemp(prefix="opentars-teste-"), "config.json"))
os.environ.setdefault("TARS_SEM_ATALHO", "1")
# 5.1: a escolha do Gargantua Lite depende da máquina; os testes fixam o completo (o do Lite pede o dele)
os.environ.setdefault("TARS_GARGANTUA", "completo")
# 18/10: o registro das ferramentas também: sem isto, os testes escreviam "open_application app82..." no ~/.tars_log de verdade
os.environ.setdefault("TARS_DIR_LOG", tempfile.mkdtemp(prefix="opentars-log-"))
# Histórico de modelos, embeddings em cache...: nada no ~/.cache de verdade.
os.environ.setdefault("XDG_CACHE_HOME", tempfile.mkdtemp(prefix="opentars-cache-"))
# 16/10: nenhum teste fala com o Ollama de verdade (dois já carregavam e descarregavam modelos do Enzo). Por padrão o
# endereço é uma porta sem ninguém; quem precisa sobe o fake_ollama e põe o próprio OLLAMA_HOST antes de carregar o tars.
# TARS_TESTE_OLLAMA_REAL=1 libera (para medir com modelo de verdade, de propósito).
if os.environ.get("TARS_TESTE_OLLAMA_REAL") != "1" and (not os.environ.get("OLLAMA_HOST")
                                                     or os.environ["OLLAMA_HOST"].rstrip("/").endswith(":11434")):
    os.environ["OLLAMA_HOST"] = "http://127.0.0.1:9"


def carregar_tars():
    if "pyautogui" not in sys.modules:
        sys.modules["pyautogui"] = types.ModuleType("pyautogui")

    if "psutil" not in sys.modules:
        stub = types.ModuleType("psutil")
        stub.process_iter = lambda *a, **k: []
        sys.modules["psutil"] = stub

    spec = importlib.util.spec_from_file_location("tars", CAMINHO_TARS)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["tars"] = modulo  # como num "import tars" de verdade (sys.modules[__name__] funciona)
    spec.loader.exec_module(modulo)
    # 4.5: os testes simulam uma área de trabalho (um teste do modo sem interface liga SEM_INTERFACE de volta)
    if not os.environ.get("TARS_TESTE_SEM_INTERFACE"):
        modulo.SEM_INTERFACE = False
        modulo.AMBIENTE.update(sem_interface=False, tela=True)
    return modulo
