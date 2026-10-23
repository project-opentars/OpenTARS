"""Modelo de nuvem (gemma4:cloud, gpt-oss:120b-cloud...) nunca é escolhido sozinho: o que a pessoa escreve e os prints
sairiam do computador. Só vale se ela o escolher pelo nome.

Antes, um modelo ':cloud' entrava no catálogo como qualquer outro: numa tarefa de visão ficava em 1º lugar da fila do AUTO,
e nas demais era o último recurso."""
from _util import carregar_tars

tars = carregar_tars()

# 1) o que é nuvem
assert tars.eh_modelo_de_nuvem("gemma4:cloud") and tars.eh_modelo_de_nuvem("gpt-oss:120b-cloud")
assert tars.eh_modelo_de_nuvem("kimi-k2.6:CLOUD")
assert tars.eh_modelo_de_nuvem("qualquer:coisa", {"remote_host": "https://ollama.com:443"})
assert tars.eh_modelo_de_nuvem("x", {"remote_model": "gpt-oss:120b"})
assert not tars.eh_modelo_de_nuvem("qwen3:8b") and not tars.eh_modelo_de_nuvem("ProjectOpenTARS/Gargantua:latest")
assert not tars.eh_modelo_de_nuvem("cloudy:7b") and not tars.eh_modelo_de_nuvem("") and not tars.eh_modelo_de_nuvem(None)
print("OK: reconhece modelo de nuvem pela etiqueta e pelos campos do /api/show, sem confundir 'cloudy:7b'")


def entrada(tag, params, nuvem=False, caps=("completion", "tools"), categoria="geral"):
    return {"tag": tag, "familia": tag.split(":")[0], "parametros_b": params, "quantizacao": "Q4_K_M",
            "vram_estimado_gb": None if params is None else params * 0.6 + 0.6, "capacidades": set(caps),
            "capacidades_conhecidas": True, "categoria": categoria, "emoji": "x", "nuvem": nuvem}


catalogo = {
    "qwen3:8b": entrada("qwen3:8b", 8.2), "qwen3:4b": entrada("qwen3:4b", 4.0), "qwen3:0.6b": entrada("qwen3:0.6b", 0.6, categoria="simples"),
    "ProjectOpenTARS/Gargantua:latest": entrada("ProjectOpenTARS/Gargantua:latest", 4.0),
    # o pior caso: de visão (ia pro 1º lugar), sem tamanho conhecido, com ferramentas
    "gemma4:cloud": entrada("gemma4:cloud", None, nuvem=True, caps=("completion", "tools", "thinking", "vision"), categoria="visao"),
    "gpt-oss:120b-cloud": entrada("gpt-oss:120b-cloud", None, nuvem=True, caps=("completion", "tools", "thinking")),
}

# 2) nenhuma fila automática tem nuvem, em nenhuma tarefa
for tarefa in ("acao", "acao_complexa", "busca", "visao", "codigo", "tecnico", "geral", "simples"):
    fila = tars.construir_cadeia_fallback(tarefa, catalogo=catalogo)
    assert fila and not [m for m in fila if "cloud" in m], (tarefa, fila)
print("OK: nenhuma fila do AUTO (ação, busca, visão, código, técnico, geral, simples) tem modelo de nuvem")

# 3) mesmo sem nenhum modelo local, a fila fica vazia em vez de mandar pra nuvem
so_nuvem = {k: v for k, v in catalogo.items() if v["nuvem"]}
assert tars.construir_cadeia_fallback("acao", catalogo=so_nuvem) == []
print("OK: só com modelos de nuvem instalados o AUTO não escolhe nenhum (nada sai do computador)")

# 4) o ajudante (resolve nome de app) e o '/modelo o maior' também não escolhem nuvem
assert "cloud" not in tars.modelo_ajudante(catalogo)
tars.catalogar_modelos = lambda forcar=False: catalogo
for alvo in ("o maior", "o menor", "o de visão"):
    escolhido = tars.interpretar_comando_modelo(f"/modelo {alvo}")
    assert "cloud" not in str(tars.modelo_manual), (alvo, tars.modelo_manual)
print("OK: o ajudante e '/modelo o maior/menor/de visão' também deixam a nuvem de fora")

# 5) escolhendo pelo nome, funciona (a pessoa sabe o que está fazendo)
tars.interpretar_comando_modelo("/modelo gemma4:cloud")
assert tars.modo_modelo == "MANUAL" and tars.modelo_manual == "gemma4:cloud", (tars.modo_modelo, tars.modelo_manual)
assert tars.escolher_modelo("oi") == "gemma4:cloud"
print("OK: escolhido pelo nome, o modelo de nuvem funciona")

print("\nTUDO OK.")
