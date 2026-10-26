"""5.2 (25/10): gerar imagem com o Bonsai Image 4B (opcional). O pedido em pt e en, a conferência de placa e disco, a
instalação (clone no commit fixo e o setup deles, de mentira aqui), o descarregar do Ollama antes, e o chat: sem o Bonsai
explica como instalar; com ele, mostra a imagem; sem memória na placa, diz o porquê. A geração de verdade só no PC do Enzo."""
import io
import json
import os
import tempfile
from pathlib import Path

from _util import carregar_tars

os.environ["TARS_PASTA_IMAGEM"] = tempfile.mkdtemp(prefix="opentars-imagem-")
tars = carregar_tars()
import tars_imagem as ti  # noqa: E402

for frase, esperado in (("desenhe uma raposa vermelha na neve", "uma raposa vermelha na neve"),
                        ("gera uma imagem de um farol ao entardecer", "um farol ao entardecer"),
                        ("cria um desenho de um gato astronauta", "um gato astronauta"),
                        ("draw a fox in the snow", "a fox in the snow"),
                        ("please generate an image of a lighthouse at dusk.", "a lighthouse at dusk"),
                        ("abra o firefox", None), ("o que é uma imagem vetorial?", None), ("desenhe", None)):
    assert ti.pedido_de_imagem(frase) == esperado, (frase, ti.pedido_de_imagem(frase))
print("OK: o pedido de imagem é reconhecido em pt e en, e o resto não")

assert ti.pode_instalar(vram_mb=2048, livre_gb=100) == (False, "placa") or ti.plataforma.sistema() == "macos"
assert ti.pode_instalar(vram_mb=6144, livre_gb=3)[1] in ("disco", "falta:git", "falta:curl", "apple_silicon")
print("OK: placa pequena ou pouco disco: não instala, e diz o motivo")

comandos = []


def rodar(comando, cwd, ao_linha, env=None):
    comandos.append(comando)
    ao_linha("linha do setup")
    if comando[:2] == ["git", "clone"]:
        (ti.demo() / ".git").mkdir(parents=True)
    if "setup" in " ".join(comando):
        ti.python_do_venv().parent.mkdir(parents=True)
        ti.python_do_venv().write_text("")
        (ti.demo() / "models" / "bonsai-image-4B-ternary-gemlite").mkdir(parents=True)
    return True


linhas = []
assert not ti.instalado()
assert ti.instalar(linhas.append, rodar=rodar) == (True, "") and ti.instalado()
assert comandos[0][:2] == ["git", "clone"] and comandos[1][-1] == ti.COMMIT and "linha do setup" in linhas
print("OK: instalar clona, fixa o commit, roda o setup deles e só então conta como instalado")


class _R(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


pedidos = []


def abrir(pedido, timeout=0):
    url = pedido if isinstance(pedido, str) else pedido.full_url
    pedidos.append((url, None if isinstance(pedido, str) else json.loads(pedido.data)))
    return _R(json.dumps({"models": [{"name": "ProjectOpenTARS/Gargantua-2:latest"}]}).encode())


assert ti.descarregar_ollama("http://x", abrir=abrir) == ["ProjectOpenTARS/Gargantua-2:latest"]
assert pedidos[-1] == ("http://x/api/generate", {"model": "ProjectOpenTARS/Gargantua-2:latest", "keep_alive": 0})
print("OK: antes de gerar, os modelos do Ollama saem da placa")

tars.emitir = lambda tipo, **d: None
ti.instalado = lambda: False
assert tars._gerar_imagem_pelo_chat("abra o firefox") is None
assert "Bonsai Image 4B" in tars._gerar_imagem_pelo_chat("desenhe um gato")
ti.instalado = lambda: True
saida = Path(tempfile.mkdtemp()) / "gato.png"
saida.write_bytes(b"png")
ti.gerar = lambda o_que, host=None: saida
resposta = tars._gerar_imagem_pelo_chat("desenhe um gato na praia")
assert f"![um gato na praia]({saida})" in resposta and tars.conversa[-1]["content"] == resposta
ti.gerar = lambda o_que, host=None: (_ for _ in ()).throw(RuntimeError("sem_memoria:1200"))
assert "1200" in tars._gerar_imagem_pelo_chat("desenhe um gato")
print("OK: no chat, sem o Bonsai explica como instalar; com ele, mostra a imagem; sem memória na placa, diz o porquê")
print("test_imagem: TUDO OK.")

# o cartão em Mais modelos: instalar pede o segundo clique; depois de instalado, mostra Remover
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402
from tars_qt import configuracoes as cfgmod  # noqa: E402
app = QApplication.instance() or QApplication([])


class _Cfg:
    def depois(self, f):
        f()

    def em_segundo_plano(self, trabalho, pronto):
        pronto(trabalho())


ti.instalado = lambda: False
ti.pode_instalar = lambda: (True, "")
chamou = []
ti.instalar = lambda ao_linha: (chamou.append(1), ao_linha("Downloading model"), (True, ""))[2]
cartao = cfgmod._CartaoBonsai(_Cfg())
cartao.atualizar()          # a conferência da máquina roda quando a página abre (ao_abrir)
assert cartao.b_instalar.isVisibleTo(cartao) and not cartao.b_remover.isVisibleTo(cartao)
cartao.b_instalar.click()
assert not chamou, "o primeiro clique só arma a confirmação"
ti.instalado = lambda: bool(chamou)
cartao.b_instalar.click()
assert chamou and cartao.b_remover.isVisibleTo(cartao) and not cartao.b_instalar.isVisibleTo(cartao)
ti.pode_instalar = lambda: (False, "placa")
ti.instalado = lambda: False
cartao.atualizar()
assert not cartao.b_instalar.isEnabled() and cartao.info.plano() == cfgmod.t("cfg.bonsai.nao_da.placa")
print("OK: o cartão do Bonsai instala só com a confirmação, mostra Remover depois e explica quando a máquina não serve")
