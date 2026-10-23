"""5.1 (item 7 do plano): quando o modelo falha no meio do pedido, a troca automática vai para um modelo do mesmo
tamanho ou maior, nunca para um bem menor (no print do Enzo, o Gargantua falhou e quem respondeu foi o qwen3:0.6b). Sem
modelo à altura, o erro aparece em vez de uma resposta ruim. Ollama de mentira."""
from _util import carregar_tars

tars = carregar_tars()


def m(tag, p):
    return {"tag": tag, "parametros_b": p, "categoria": "geral", "vram_estimado_gb": p, "capacidades": {"tools"},
            "capacidades_conhecidas": True, "nuvem": False}


def rodar(catalogo, fila):
    tars.catalogar_modelos = lambda forcar=False: catalogo
    tars.construir_cadeia_fallback = lambda tarefa, catalogo=None: list(fila)
    tars.carregar_modelo = lambda *a, **k: True
    chamados = []

    def turno(modelo, mensagens, tools, **kw):
        chamados.append(modelo)
        if modelo == "ProjectOpenTARS/Gargantua:latest":
            return None, "Erro ao comunicar com Ollama: out of memory"
        return {"content": f"feito por {modelo}", "tool_calls": []}, None

    tars._executar_turno_streaming = turno
    tars.modo_modelo = "AUTO"
    tars.conversa[:] = [{"role": "system", "content": "s"}]
    return tars.perguntar_modelo("ProjectOpenTARS/Gargantua:latest", "oi, tudo bem?", tarefa="geral"), chamados


gargantua, pequeno, grande = m("ProjectOpenTARS/Gargantua:latest", 4.0), m("qwen3:0.6b", 0.75), m("qwen3:8b", 8.2)
catalogo = {x["tag"]: x for x in (gargantua, pequeno, grande)}
resposta, chamados = rodar(catalogo, ["ProjectOpenTARS/Gargantua:latest", "qwen3:0.6b", "qwen3:8b"])
assert chamados == ["ProjectOpenTARS/Gargantua:latest", "qwen3:8b"] and "qwen3:8b" in resposta, (chamados, resposta)
print("OK: depois da falha, pula o qwen3:0.6b e vai para o qwen3:8b")

catalogo = {x["tag"]: x for x in (gargantua, pequeno)}
resposta, chamados = rodar(catalogo, ["ProjectOpenTARS/Gargantua:latest", "qwen3:0.6b"])
assert chamados == ["ProjectOpenTARS/Gargantua:latest"] and "out of memory" in resposta, (chamados, resposta)
print("OK: sem modelo à altura, mostra o erro em vez de passar o pedido para o 0.6b")
print("\nTUDO OK.")
