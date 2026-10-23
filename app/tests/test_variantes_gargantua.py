"""Variantes do Gargantua (Lite, Code) no openTARS: o app nunca as confunde com o oficial e as usa só onde servem."""
from _util import carregar_tars

tars = carregar_tars()
import tars_primeiro_uso as pu

# 1) reconhecer a variante pelo nome OU pela etiqueta
casos = [("gargantua-code", "code"), ("gargantua-lite:latest", "lite"), ("ProjectOpenTARS/Gargantua:code", "code"),
         ("ProjectOpenTARS/Gargantua:1.2-lite", "lite"), ("ProjectOpenTARS/Gargantua:latest", ""), ("ProjectOpenTARS/Gargantua:1.2", ""),
         ("gargantua", ""), ("enzo/gargantua-teste:1.0", ""), ("qwen3:4b", ""), ("qwen2.5-coder:7b", ""), ("", ""), (None, "")]
for nome, esperado in casos:
    assert tars.variante_do_gargantua(nome) == esperado, (nome, tars.variante_do_gargantua(nome))
    assert pu.e_variante_do_gargantua(nome) == bool(esperado), nome         # a cópia do primeiro uso concorda
print("OK: variante reconhecida pelo nome e pela etiqueta (e as duas cópias da regra concordam)")

# 2) 'o Gargantua instalado' é o oficial; variante só conta se não houver outro
cat = {"gargantua-code:latest": {}, "ProjectOpenTARS/Gargantua:code": {}, "gargantua-lite:latest": {}}
assert tars.variante_do_gargantua(tars.gargantua_instalado(cat))             # só variantes: devolve uma delas, nunca None
cat["ProjectOpenTARS/Gargantua:latest"] = {}
assert tars.gargantua_instalado(cat) == "ProjectOpenTARS/Gargantua:latest"
assert pu.tem_gargantua(["gargantua-code:latest", "ProjectOpenTARS/Gargantua:code", "gargantua-lite"]) is False   # o primeiro uso baixa o oficial
assert pu.tem_gargantua(["ProjectOpenTARS/Gargantua:code", "ProjectOpenTARS/Gargantua:latest"]) is True
assert pu.nome_do_gargantua(["ProjectOpenTARS/Gargantua:code", "ProjectOpenTARS/Gargantua:latest"]) == "ProjectOpenTARS/Gargantua:latest"
assert pu.nome_do_gargantua(["ProjectOpenTARS/Gargantua:code"]) == pu.MODELO_GARGANTUA
print("OK: o Gargantua oficial nunca é trocado por uma variante (instalado, primeiro uso)")


def entrada(tag, params, caps=("completion", "tools"), categoria="geral"):
    return {"tag": tag, "familia": tag.split(":")[0], "parametros_b": params, "quantizacao": "Q4_K_M",
            "vram_estimado_gb": params * 0.6 + 0.6, "capacidades": set(caps), "capacidades_conhecidas": True,
            "categoria": categoria, "emoji": "x", "nuvem": False}


catalogo = {
    "qwen3:8b": entrada("qwen3:8b", 8.2), "qwen3:4b": entrada("qwen3:4b", 4.0),
    "qwen2.5-coder:7b": entrada("qwen2.5-coder:7b", 7.6, categoria="codigo"),
    "ProjectOpenTARS/Gargantua:latest": entrada("ProjectOpenTARS/Gargantua:latest", 4.0),
    "gargantua-code:latest": entrada("gargantua-code:latest", 4.0, categoria="codigo"),
    "gargantua-lite:latest": entrada("gargantua-lite:latest", 1.7),
}

# 3) ação/busca: o oficial na frente; Lite só depois dele; o Code (que é de código) nem entra na frente
for tarefa in ("acao", "busca", "acao_complexa"):
    fila = tars.construir_cadeia_fallback(tarefa, catalogo=catalogo)
    assert fila[0] == "ProjectOpenTARS/Gargantua:latest", (tarefa, fila)
    assert fila.index("gargantua-lite:latest") > 0
    assert fila.index("gargantua-code:latest") > fila.index("qwen3:8b") or fila.index("gargantua-code:latest") > fila.index("gargantua-lite:latest"), (tarefa, fila)
    assert fila.index("gargantua-code:latest") >= len(fila) - 2, (tarefa, fila)       # especialista em código: no fim fora de código
print("OK: nas ações o oficial vai na frente; Lite depois; Code só como último recurso")

# 4) código: o Gargantua Code vai na frente do qwen2.5-coder e do oficial
fila = tars.construir_cadeia_fallback("codigo", catalogo=catalogo)
assert fila[0] == "gargantua-code:latest" and "ProjectOpenTARS/Gargantua:latest" in fila, fila
sem_code = {k: v for k, v in catalogo.items() if "code:" not in k}
assert tars.construir_cadeia_fallback("codigo", catalogo=sem_code)[0] == "qwen2.5-coder:7b"      # sem ele, o de sempre
print("OK: em pedido de código o Gargantua Code vai na frente (e sem ele nada muda)")

# 5) só com Lite instalado (PC fraco): ele atende as ações
so_lite = {"gargantua-lite:latest": catalogo["gargantua-lite:latest"], "qwen3:0.6b": entrada("qwen3:0.6b", 0.6, categoria="simples")}
assert tars.construir_cadeia_fallback("acao", catalogo=so_lite)[0] == "gargantua-lite:latest"
print("OK: num PC fraco só com o Lite, ele atende as ações")

# 6) TARS_SEM_GARGANTUA desliga a preferência (também a do Code)
import os
os.environ["TARS_SEM_GARGANTUA"] = "1"
assert tars.construir_cadeia_fallback("codigo", catalogo=catalogo)[0] == "qwen2.5-coder:7b"
assert tars.construir_cadeia_fallback("acao", catalogo=catalogo)[0] != "ProjectOpenTARS/Gargantua:latest"
del os.environ["TARS_SEM_GARGANTUA"]

# 7) o formato (prompt curto + 19 ferramentas, sem raciocínio) vale pras variantes: foram treinadas assim
for v in ("gargantua-code:latest", "gargantua-lite:latest", "ProjectOpenTARS/Gargantua:code"):
    assert tars.eh_gargantua(v), v
print("\nTUDO OK.")
