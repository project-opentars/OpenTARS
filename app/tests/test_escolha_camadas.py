"""2.9: escolha da tarefa em camadas (tars_escolha.py + decidir_tarefa)."""

import os
import time

os.environ["TARS_IDIOMA"] = "pt_BR"
from _util import carregar_tars  # noqa: E402

tars = carregar_tars()
tars.listar_modelos_instalados = lambda forcar=False: {"qwen3:8b"}
tars.desktop_entries = lambda forcar=False: [{"nome": "Spotify"}, {"nome": "GIMP"}, {"nome": "Files"}]
tars._cache_desktop["ts"] = time.time()


def decidir(texto):
    return tars.decidir_tarefa(texto)


# 1. Palavra-chave sem nada contra: decide na hora
d = decidir("feche o firefox agora mesmo")
# (a Murph, que é instantânea, costuma concordar: "palavras+local")
assert d.categoria == "acao" and d.via in ("palavras", "palavras+local"), d
print("OK: palavra-chave clara decide sozinha")

# 2. Contexto: "de novo" logo depois de uma ação
tars.lembrar_tarefa("acao")
d = decidir("de novo")
assert d.categoria == "acao" and "contexto" in d.via, d
tars._ultima_tarefa["ts"] = time.time() - 3600
d = decidir("de novo")
assert d.categoria == "simples", d
print("OK: continuação curta ('de novo') herda a tarefa anterior (por 5 minutos)")

# 3. Estrutura: traceback é código, mesmo sem palavra-chave
d = decidir('Traceback (most recent call last):\n  File "a.py", line 3\nNameError: x')
assert d.categoria == "codigo" and "estrutura" in d.via, d
d = decidir("E: Unable to locate package foo quando rodo sudo apt install foo")
assert d.categoria == "tecnico", d
print("OK: traceback -> código; 'E: ... sudo apt' -> técnico (pelo formato)")

# Daqui pra baixo, a Murph fica de fora pra não mudar as contas (ela é
# testada em test_murph.py). Endurance Neo: sem embeddings e sem ajudante.
tars._votos_modelo_local = lambda texto, votos, so_duvida=False: None

# 4. App instalado citado soma voto de ação
d = decidir("spotify pausa essa música aí")
assert d.categoria == "acao" and d.votos.get("acao", 0) > 0, d
print("OK: citar um app instalado (Spotify) puxa pra ação")

# 5. Sem acordo claro: a mais votada; sem voto nenhum, pelo tamanho do pedido
assert decidir("hmm talvez quem sabe aquilo lá").categoria == "simples"
assert decidir("o que você acha de viajar pra praia ou pra montanha nas férias").categoria == "geral"
print("OK: sem acordo, segue pelos votos e pelo tamanho do pedido")

# 6. Nenhuma camada chama IA (Endurance Neo)
for nome in ("_classificar_com_ia", "_votos_embedding", "saude_ajudante", "embeddings", "classificador_local"):
    assert not hasattr(tars, nome), nome
print("OK: a escolha da tarefa não usa mais IA nenhuma (sem ajudante, sem embeddings)")
print("\nTUDO OK.")
