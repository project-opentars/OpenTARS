"""3.0: planejar e conferir.

- pedido com várias etapas: a IA recebe o PLANO (lista numerada) e a
  janela/terminal mostram o plano;
- se ela encerra antes de fazer todas as etapas, é mandada terminar (uma vez);
- "Pronto!" logo depois de um clique que não mudou nada na tela é cobrado;
- cliques "certos" que não mudam nada contam pra desistir (andar em círculos)."""

import os

os.environ["TARS_IDIOMA"] = "pt_BR"
from _util import carregar_tars  # noqa: E402

tars = carregar_tars()


def m(tag, p, caps, v, fam="qwen3"):
    return {"tag": tag, "familia": fam, "parametros_b": p, "vram_estimado_gb": v, "capacidades": set(caps),
            "capacidades_conhecidas": True, "categoria": tars._categorizar_modelo(tag, set(caps), p, fam)}


catalogo = {x["tag"]: x for x in [m("qwen3:4b", 4.0, {"tools", "thinking"}, 3.0),
                                  m("qwen3:8b", 8.2, {"tools", "thinking"}, 5.5)]}
tars.catalogar_modelos = lambda forcar=False: catalogo
tars.detectar_gpu = lambda forcar=False: {"vram_total_gb": 8.0, "vram_livre_gb": 7.5}
tars.listar_modelos_instalados = lambda forcar=False: set(catalogo)
tars.carregar_modelo = lambda mod, silencioso=False: True
tars.contexto_ia = lambda: 8192
tars.modo_modelo = "AUTO"
tars.listar_janelas_x = lambda: None

eventos = []
tars.definir_ouvinte_saida(lambda tipo, dados: eventos.append((tipo, dados)))

tars._DISPATCH_FERRAMENTAS["open_application"] = lambda a: {"sucesso": True, "mensagem": "SUCCESS: opened."}
tars._DISPATCH_FERRAMENTAS["click_element"] = lambda a: {"sucesso": True, "mensagem": "SUCCESS: clicked."}

# ------------------------------------------------------------
# 1. Plano e cobrança das etapas que faltam
# ------------------------------------------------------------
recebidas = []
roteiro = iter([
    {"content": "", "tool_calls": [{"function": {"name": "open_application", "arguments": {"app": "calculadora"}}}]},
    {"content": "Pronto, abri a calculadora!", "tool_calls": []},
    {"content": "", "tool_calls": [{"function": {"name": "click_element", "arguments": {"name": "12"}}}]},
    {"content": "Abri a calculadora e fiz 12 x 8 = 96.", "tool_calls": []},
    {"content": "Abri a calculadora e fiz 12 x 8 = 96.", "tool_calls": []},  # depois da conferência de conclusão
])


def turno(modelo, msgs, tools, **kw):
    recebidas.append([x.get("content") or "" for x in msgs if x["role"] == "user"])
    return next(roteiro), None


tars._executar_turno_streaming = turno
tars.conversa = []
resposta = tars.perguntar_modelo("qwen3:4b", "abre a calculadora e faz 12 vezes 8", tarefa="acao", multi_etapas=True)
assert resposta == "Abri a calculadora e fiz 12 x 8 = 96.", resposta
contexto = next(u for u in recebidas[0] if u.startswith("[Context"))
assert "Plan: 1. abre a calculadora 2. faz 12 vezes 8" in contexto, contexto
assert any("Plan check" in u and "only 1 action" in u for u in recebidas[2]), recebidas[2]
assert any("Completion check" in u and "click_element" in u and "open_application" in u for u in recebidas[-1]), recebidas[-1]
plano = [d for tipo, d in eventos if tipo == "plano"]
assert plano and plano[-1]["etapas"] == ["abre a calculadora", "faz 12 vezes 8"], plano
print("OK: pedido de 2 etapas -> a IA recebe o plano, a tela mostra o plano, e parar na 1ª é cobrado")

# pedido de uma etapa só: nada de plano
eventos.clear()
roteiro = iter([
    {"content": "", "tool_calls": [{"function": {"name": "open_application", "arguments": {"app": "firefox"}}}]},
    {"content": "Abri o Firefox.", "tool_calls": []},
])
recebidas.clear()
assert tars.perguntar_modelo("qwen3:4b", "abre o firefox", tarefa="acao") == "Abri o Firefox."
depois = recebidas[-1][recebidas[-1].index("abre o firefox"):]
assert not any(tipo == "plano" for tipo, _ in eventos) and not any("Plan" in u for u in depois), depois
print("OK: pedido simples não ganha plano nem cobrança")

# ------------------------------------------------------------
# 2. "Pronto!" depois de um clique que não mudou a tela
# ------------------------------------------------------------
tars._DISPATCH_FERRAMENTAS["click_mouse"] = lambda a: {
    "sucesso": True, "sem_efeito": bool(a.get("x") == 5), "mensagem": "Clicked."}
roteiro = iter([
    {"content": "", "tool_calls": [{"function": {"name": "click_mouse", "arguments": {"x": 5, "y": 5}}}]},
    {"content": "Pronto, cliquei no X!", "tool_calls": []},
    {"content": "", "tool_calls": [{"function": {"name": "click_mouse",
                                                  "arguments": {"x": 9, "y": 9, "target": "X"}}}]},
    {"content": "Fechei a aba.", "tool_calls": []},
])
recebidas.clear()
assert tars.perguntar_modelo("qwen3:4b", "fecha a aba clicando no x", tarefa="acao") == "Fechei a aba."
assert any("changed NOTHING on screen" in u for u in recebidas[2]), recebidas[2]
print("OK: 'Pronto, cliquei!' depois de um clique sem efeito é cobrado; a IA mira de novo e acerta")

# ------------------------------------------------------------
# 3. Clicar no nada em círculos: desiste (outro modelo assume)
# ------------------------------------------------------------
atendeu = []
n = {"i": 0}


def turno_circulos(modelo, msgs, tools, **kw):
    atendeu.append(modelo)
    if not tools:
        return {"content": "Não consegui: o clique não pega.", "tool_calls": []}, None
    if modelo == "qwen3:4b":
        n["i"] += 1
        return {"content": "", "tool_calls": [{"function": {"name": "click_mouse",
                                                             "arguments": {"x": 5, "y": 5 + n["i"]}}}]}, None
    if not any(x["role"] == "tool" and "SUCCESS: opened" in x["content"] for x in msgs[-3:]):
        return {"content": "", "tool_calls": [{"function": {"name": "open_application",
                                                             "arguments": {"app": "x"}}}]}, None
    return {"content": "Resolvido por outro caminho.", "tool_calls": []}, None


tars._DISPATCH_FERRAMENTAS["click_mouse"] = lambda a: {"sucesso": True, "sem_efeito": True, "mensagem": "Clicked."}
tars._executar_turno_streaming = turno_circulos
tars.conversa = []
resposta = tars.perguntar_modelo("qwen3:4b", "clica no botão", tarefa="acao")
assert atendeu.count("qwen3:4b") == tars.LIMITE_FALHAS_SEGUIDAS and atendeu[-1] == "qwen3:8b", atendeu
assert resposta == "Resolvido por outro caminho.", resposta
print(f"OK: {tars.LIMITE_FALHAS_SEGUIDAS} cliques sem efeito seguidos contam como andar em círculos: outro modelo assume")

print("\nTUDO OK.")
