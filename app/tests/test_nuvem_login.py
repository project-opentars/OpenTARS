"""5.1: nuvem pela conta do Ollama, sem chave. conta_ollama lê POST /api/me (só o nome), iniciar_login acha o endereço
que o `ollama signin` imprime, o componente da tela abre o navegador e espera a conta aparecer, e o rodapé da
conversa avisa quando o modelo escolhido é da nuvem do Ollama. Sem Ollama de verdade, sem rede."""
import io
import json
import os
import subprocess
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
CASA = tempfile.mkdtemp(prefix="opentars-nuvem-login-")
os.environ["HOME"] = CASA
for k, n in (("TARS_ARQUIVO_SESSOES", "s.json"), ("TARS_ARQUIVO_PRIMEIRO_USO", "p.json"), ("TARS_ARQUIVO_CONFIG", "c.json"),
             ("TARS_ARQUIVO_NUVEM", "n.json")):
    os.environ[k] = os.path.join(CASA, n)

from _util import RAIZ  # noqa: E402,F401

import tars_primeiro_uso as pu  # noqa: E402


class Resposta(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def abrir_com(dados):
    def abrir(pedido, timeout=0):
        assert pedido.get_method() == "POST" and pedido.full_url.endswith("/api/me")
        if isinstance(dados, Exception):
            raise dados
        return Resposta(json.dumps(dados).encode())
    return abrir


assert pu.conta_ollama("http://x", abrir=abrir_com({"name": "Enzo", "email": "e@x.com"})) == "Enzo"
assert pu.conta_ollama("http://x", abrir=abrir_com(OSError("401"))) is None
assert pu.conta_ollama("http://x", abrir=abrir_com({"name": ""})) is None


def rodar_com(saida):
    return lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=saida, stderr="")


assert pu.iniciar_login(rodar_com("You are already signed in as user 'Enzo'\n")) == ("Enzo", None, None)
url = "https://ollama.com/connect?name=pc&key=c3NoLWVk"
assert pu.iniciar_login(rodar_com(f"You need to be signed in.\nTo sign in, navigate to:\n    {url}\n")) == (None, url, None)
assert pu.iniciar_login(rodar_com("algo estranho"))[2] == "algo estranho"
assert pu.modelos_de_nuvem(["qwen3:4b", "gpt-oss:20b-cloud", "gemma4:cloud", "cloudy:1b"]) == ["gpt-oss:20b-cloud", "gemma4:cloud"]
print("OK: conta (só o nome), o endereço de login e quais modelos são da nuvem")

try:
    from PySide6.QtTest import QTest
except ImportError:
    print("(PySide6 não instalado: parte da tela pulada)")
    sys.exit(0)

from tars_qt.primeiro_uso import criar_aplicativo  # noqa: E402
from tars_qt.login_ollama import LoginOllama  # noqa: E402

app = criar_aplicativo(["teste"])


def esperar(cond, segundos=10, o_que=""):
    fim = time.time() + segundos
    while time.time() < fim:
        app.processEvents()
        if cond():
            return
        QTest.qWait(20)
    raise AssertionError(f"tempo esgotado: {o_que}")


estado = {"conta": None, "modelos": ["qwen3:4b"]}
pu.conta_ollama = lambda host, **k: estado["conta"]
pu.modelos_instalados = lambda host: estado["modelos"]
pu.iniciar_login = lambda rodar=None: (None, url, None)
abertos = []
w = LoginOllama(lambda: "http://x", abrir_link=abertos.append)
w.show()
w.atualizar()
esperar(lambda: w.b_entrar.isVisibleTo(w), o_que="botão Entrar")
w.entrar()
esperar(lambda: abertos == [url], o_que="abrir o navegador")
assert w._relogio.isActive() and not w.b_entrar.isEnabled()
estado["conta"] = "Enzo"
w._conferir_login()
esperar(lambda: "Enzo" in w.estado.plano() and w.b_modelo.isVisibleTo(w), o_que="conta conectada")
assert not w._relogio.isActive() and w.b_sair.isVisibleTo(w)
estado["modelos"] = ["qwen3:4b", "gpt-oss:20b-cloud"]
w.atualizar()
esperar(lambda: "gpt-oss:20b-cloud" in w.estado.plano() and not w.b_modelo.isVisibleTo(w), o_que="modelo da nuvem")
print("OK: Entrar abre o navegador, espera a conta e oferece o modelo da nuvem")
print("\nTUDO OK.")
