"""Com a janela aberta o modelo não sai da memória; escondida ela volta ao tempo normal e avisa o Ollama. Um nome com barra
continua sendo Gargantua. Ollama de mentira."""
import os
from _util import carregar_tars

os.environ.pop("TARS_KEEP_ALIVE", None)
tars = carregar_tars()
assert tars.eh_gargantua("Gargantua-lite-gen2-teste-4/11:latest")
assert tars.eh_gargantua("ProjectOpenTARS/Gargantua-2:lite") and not tars.eh_gargantua("qwen3:4b")
assert tars.variante_do_gargantua("Gargantua-lite-teste-4/11:latest") == "lite"
assert tars.pensar_do_modelo("Gargantua-lite-teste-4/11:latest", "geral", "write me a poem") is False


class Sessao:
    pedidos = []

    def post(self, url, json=None, timeout=None):
        self.pedidos.append(json)


tars._SESSION = Sessao()
tars.listar_modelos_rodando = lambda: {"meu-modelo", "de-outro-programa"}
tars.modelos_do_tars.add("meu-modelo")
normal = tars.KEEP_ALIVE
tars.manter_modelo_com_janela(True)
# o número -1, nunca o texto "-1": o Ollama 0.40.13 devolve HTTP 400 ('time: missing unit in duration') para o texto
assert tars.KEEP_ALIVE == -1 and isinstance(tars.KEEP_ALIVE, int) and [p["keep_alive"] for p in Sessao.pedidos] == [-1], Sessao.pedidos
assert Sessao.pedidos[0]["model"] == "meu-modelo" and Sessao.pedidos[0]["options"]["num_ctx"] == tars.contexto_ia()
tars.manter_modelo_com_janela(False)
assert tars.KEEP_ALIVE == normal and Sessao.pedidos[-1]["keep_alive"] == normal
print("ok")
