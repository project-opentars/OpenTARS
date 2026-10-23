"""Anti-alucinação (5.2): a confiança do modelo (logprobs do Ollama) decide se o app confere ou avisa.
  1. a conta: média dos primeiros tokens, limiar, resposta curta ou sem logprobs não conta;
  2. quais respostas valem conferir (fato em texto sim; ação, código, pedido criativo e bloco de código não);
  3. o laço do chat com um Ollama de mentira: pouca confiança + pesquisa ligada = pesquisa e responde pela busca;
     pouca confiança + sem pesquisa = a resposta fica e o app avisa; confiança alta = nada muda; TARS_CONFIANCA=0 desliga."""
import io
import json
import os
import contextlib
from _util import carregar_tars

tars = carregar_tars()
cl = tars.confianca_lib

# 1) a conta
assert cl.media([-0.1] * 20) == -0.1 and cl.media([]) is None and cl.media(None) is None
assert cl.media([-1.0] * 5) is None, "poucos tokens não dizem nada"
assert abs(cl.media([-0.1] * 10 + [-9.0] * 500) - (-0.1)) < 1e-9 or cl.media([-0.1] * 120 + [-9.0] * 500) == -0.1, "só a janela conta"
assert cl.pouca_confianca([-0.6] * 20) and not cl.pouca_confianca([-0.05] * 20) and not cl.pouca_confianca([-0.6] * 3)
assert cl.pouca_confianca([-0.3] * 20, limiar=-0.2) and not cl.pouca_confianca([-0.3] * 20, limiar=-0.5)
assert cl.logprobs_do_pedaco([{"token": "a", "logprob": -0.5}, {"token": "b"}, "x"]) == [-0.5]
print("OK: média, limiar, janela e pouco token")

# 2) o que vale conferir
longa = "A empresa foi fundada por João Carlos em 2010 e atua com software."
assert cl.vale_conferir("geral", "quem fundou a empresa Zorvintech Brasil?", longa)
assert cl.vale_conferir("simples", "qual a capital da Austrália", longa)
assert not cl.vale_conferir("acao", "abre o firefox por favor", longa)
assert not cl.vale_conferir("codigo", "como faço um loop em python", longa)
assert not cl.vale_conferir("geral", "oi", longa) and not cl.vale_conferir("geral", "quem fundou a empresa X", "Não sei.")
assert not cl.vale_conferir("geral", "escreva um poema sobre o mar", longa)
assert not cl.vale_conferir("geral", "traduz isso para o inglês por favor", longa)
assert not cl.vale_conferir("geral", "como fazer um loop", longa + "\n```python\nfor i in x: pass\n```")
print("OK: só pergunta de fato respondida em texto")

# 3) o laço do chat, com os turnos do modelo roteirizados
tars.catalogar_modelos = lambda forcar=False: {}
tars.carregar_modelo = lambda mod, silencioso=False: True
tars.contexto_ia = lambda: 8192
tars.modo_modelo = "MANUAL"
tars.listar_janelas_x = lambda: None
PERGUNTA = "quem fundou a empresa Zorvintech Brasil e quando?"
INVENTADO = "A empresa Zorvintech Brasil foi fundada por João Carlos em 2010."
BUSCA = {"content": "", "tool_calls": [{"function": {"name": "search_web", "arguments": {"query": "Zorvintech Brasil fundador"}}}],
         "logprobs": []}
CONFERIDO = {"content": "Não encontrei nada confiável sobre a Zorvintech Brasil nos resultados.", "tool_calls": [], "logprobs": [-0.05] * 30}


def rodar(texto, turnos, pesquisa, tarefa="geral"):
    roteiro = iter(turnos)
    vistas = []
    tars._pesquisa_ligada = lambda: pesquisa
    tars.executar_ferramenta = lambda nome, a: {"sucesso": True, "mensagem": "SUCCESS: searched. Results: nothing found."}
    def turno(modelo, mensagens, tools, pensar=True):
        vistas.append([m.get("content") for m in mensagens if m.get("role") == "user"][-1])
        return next(roteiro), None
    tars._executar_turno_streaming = turno
    tars.conversa = []
    saida = io.StringIO()
    with contextlib.redirect_stdout(saida):
        resposta = tars.perguntar_modelo("ProjectOpenTARS/Gargantua-2:latest", texto, tarefa=tarefa)
    return resposta, saida.getvalue(), vistas


# a) pouca confiança + pesquisa ligada: o app manda conferir pela busca, e a resposta final é a da busca
r, saida, vistas = rodar(PERGUNTA, [{"content": INVENTADO, "tool_calls": [], "logprobs": [-0.9] * 30}, BUSCA, CONFERIDO], True)
assert r == CONFERIDO["content"], r
assert tars.t("msg.verificando_fato") in saida and tars.t("msg.pouca_confianca") not in saida
assert any("Call search_web" in v for v in vistas), vistas
print("OK: pouca confiança com a pesquisa ligada: confere pela busca e responde com ela")

# b) pouca confiança sem pesquisa: a resposta fica e o app avisa embaixo
r, saida, vistas = rodar(PERGUNTA, [{"content": INVENTADO, "tool_calls": [], "logprobs": [-0.9] * 30}], False)
assert r == INVENTADO and tars.t("msg.pouca_confianca") in saida and len(vistas) == 1
print("OK: pouca confiança sem pesquisa: a resposta fica e o app avisa")

# c) confiança alta: nada muda
r, saida, vistas = rodar(PERGUNTA, [{"content": "Canberra é a capital da Austrália, e fica no território da capital.", "tool_calls": [],
                                      "logprobs": [-0.02] * 30}], True)
assert tars.t("msg.pouca_confianca") not in saida and tars.t("msg.verificando_fato") not in saida and len(vistas) == 1
print("OK: confiança alta: a resposta sai como veio")

# d) sem logprobs (Ollama antigo, modelo de API) ou desligado por TARS_CONFIANCA=0: nada muda
r, saida, _ = rodar(PERGUNTA, [{"content": INVENTADO, "tool_calls": []}], True)
assert tars.t("msg.verificando_fato") not in saida and r == INVENTADO
os.environ["TARS_CONFIANCA"] = "0"
try:
    r, saida, _ = rodar(PERGUNTA, [{"content": INVENTADO, "tool_calls": [], "logprobs": [-0.9] * 30}], True)
    assert r == INVENTADO and tars.t("msg.verificando_fato") not in saida and tars.t("msg.pouca_confianca") not in saida
finally:
    del os.environ["TARS_CONFIANCA"]
print("OK: sem logprobs ou com TARS_CONFIANCA=0 o app não mexe")

# e) pedido de ação não é conferido, mesmo com confiança baixa (o app tem as outras travas para ação)
TURNO_ACAO = {"content": "Pronto, abri o navegador e entrei no GitHub, tudo certo.", "tool_calls": [], "logprobs": [-0.9] * 30}
r, saida, _ = rodar("abre o navegador e entra no github", [TURNO_ACAO] * 4, True, tarefa="acao")
assert tars.t("msg.verificando_fato") not in saida and tars.t("msg.pouca_confianca") not in saida
print("\ntest_confianca: TUDO OK.")
