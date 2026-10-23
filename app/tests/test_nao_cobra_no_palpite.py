"""17/10: o app só cobra ferramenta ("você respondeu sem fazer, faça de verdade") quando faz sentido. Conversa solta que a Murph só
palpitou (via melhor_voto) e que continua uma resposta de texto NÃO vira ordem de agir: "but i need to wash the car", resposta a
uma pergunta de conversa, foi palpitada como visao e o app mandou o modelo fechar o Claude do Enzo e abrir o Brave.
Modelo de mentira: nada é executado."""
from _util import carregar_tars

tars = carregar_tars()
tars.carregar_modelo = lambda *a, **k: True
pedidos_ao_modelo = []


def modelo_falso(modelo, mensagens, tools, pensar=True):
    pedidos_ao_modelo.append([m.get("content", "") for m in mensagens if m.get("role") == "user"][-1])
    return {"content": "Walk. It is only 50 meters away.", "thinking": "", "tool_calls": []}, None


tars._executar_turno_streaming = modelo_falso


def rodar(texto, categoria, via, conversa_antes=False):
    pedidos_ao_modelo.clear()
    sessao = tars.obter_sessao("qwen3:4b")
    sessao.clear()
    if conversa_antes:
        sessao += [{"role": "user", "content": "should i walk or drive?"}, {"role": "assistant", "content": "Walk."}]
    tars._ultima_decisao["d"] = tars.escolha.Decisao(categoria, via, {}, [categoria])
    tars.perguntar_modelo("qwen3:4b", texto, tarefa=categoria)
    return list(pedidos_ao_modelo)


cobrou = lambda vistos: len(vistos) == 2 and "You answered without doing it" in vistos[1]  # noqa: E731

# 1) palpite DEPOIS de uma resposta de texto: é conversa, sem cobrança
for via in ("melhor_voto", "padrao", "melhor_voto+coerente"):
    vistos = rodar("but i need to wash the car", "visao", via, conversa_antes=True)
    assert len(vistos) == 1, (via, vistos)
print("OK: palpite logo depois de uma resposta de texto não vira cobrança de ferramenta")

# 2) o primeiro pedido da conversa continua cobrado mesmo em palpite (13 dos 84 pedidos da prova do Lab são assim)
assert cobrou(rodar("put this in the calculator: 1494 divided by 18", "acao", "melhor_voto"))
print("OK: o primeiro pedido, mesmo palpitado, continua cobrado")

# 3) tarefa decidida com certeza é cobrada até depois de conversa
for via in ("palavras+local", "apps", "estrutura+local"):
    assert cobrou(rodar("abre a calculadora", "acao", via, conversa_antes=True)), via
print("OK: pedido de ação decidido com certeza continua sendo cobrado, uma vez")

# 4) palpite depois de uma resposta que USOU ferramenta: era trabalho, continua cobrado
tars._ultima_decisao["d"] = tars.escolha.Decisao("acao", "melhor_voto", {}, ["acao"])
sessao = tars.obter_sessao("qwen3:4b")
sessao.clear()
sessao += [{"role": "user", "content": "abre a calculadora"},
           {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "open_application", "arguments": {"app": "calc"}}}]},
           {"role": "tool", "content": "ok"}, {"role": "assistant", "content": "Abri."}]
pedidos_ao_modelo.clear()
tars.perguntar_modelo("qwen3:4b", "now 2 plus 2", tarefa="acao")
assert cobrou(list(pedidos_ao_modelo)), pedidos_ao_modelo
print("OK: palpite depois de uma troca em que a IA usou ferramentas continua cobrado")
print("\nTUDO OK.")
