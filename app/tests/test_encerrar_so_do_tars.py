"""Ao fechar, o openTARS descarrega só os modelos que ele mesmo carregou, não o de outro programa que usa o mesmo Ollama.
O comando manual 'encerrar todas llms' continua descarregando tudo. Ollama de mentira: sem rede, sem GPU."""
from _util import carregar_tars

tars = carregar_tars()
print("(o openTARS está carregado; vou trocar o Ollama por um de mentira)")

rodando = {"qwen3:4b", "do-outro-programa:7b"}
descarregados = []


def listar():
    return set(rodando)


def descarregar(modelo):
    descarregados.append(modelo)
    rodando.discard(modelo)
    return True


tars.listar_modelos_rodando = listar
tars.descarregar_modelo = descarregar
tars.visao_instalada = lambda: None

# 1) fechar o app: só o que o openTARS carregou
tars.modelos_do_tars.clear()
tars.modelos_do_tars.add("qwen3:4b")
tars.modelo_atual = "qwen3:4b"
r = tars.encerrar_todas_ias(so_do_tars=True, max_tentativas=1, espera_seg=0)
assert r["sucesso"] and r["encerrados"] == ["qwen3:4b"], r
assert descarregados == ["qwen3:4b"], descarregados
assert "do-outro-programa:7b" in rodando, "o modelo do outro programa não pode sair ao fechar"
print("OK: ao fechar, o modelo do outro programa fica")

# 2) o comando manual descarrega tudo
descarregados.clear()
rodando.update({"qwen3:4b", "do-outro-programa:7b"})
tars.modelo_atual = None
r = tars.encerrar_todas_ias(max_tentativas=1, espera_seg=0)
assert set(descarregados) == {"qwen3:4b", "do-outro-programa:7b"}, descarregados
print("OK: o comando manual 'encerrar' descarrega todos")

# 3) o Cooper conta como do openTARS
rodando.update({"cooper:latest", "do-outro-programa:7b"})
descarregados.clear()
tars.modelos_do_tars.clear()
tars.modelo_atual = None
tars.visao_instalada = lambda: "cooper:latest"
tars.encerrar_todas_ias(so_do_tars=True, max_tentativas=1, espera_seg=0)
assert descarregados == ["cooper:latest"], descarregados
print("OK: o Cooper é descarregado ao fechar")
print("\nTUDO OK.")
