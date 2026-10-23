"""4.1: tarefas longas. Antes todo pedido parava em 20 idas-e-voltas.
Agora:
- pedido com plano começa com mais (20 + 6 por etapa além da segunda, até 50);
- enquanto a IA faz progresso de verdade (ações que deram certo), ganha
  mais 20 de fôlego, até o teto (TARS_LIMITE_ETAPAS, 120);
- andar em círculos só olhando a tela continua parando em 20;
- os resultados de ferramenta antigos do mesmo pedido são encurtados."""

import json

from _util import carregar_tars

tars = carregar_tars()

assert tars.limite_de_ciclos([]) == 20 and tars.limite_de_ciclos(["a", "b"]) == 20
assert tars.limite_de_ciclos(["a", "b", "c", "d"]) == 32 and tars.limite_de_ciclos(list("abcdefghij")) == 50
assert tars._merece_folego(20, 15, 0) and not tars._merece_folego(20, 3, 3) and not tars._merece_folego(120, 99, 0)
print("OK: limite inicial cresce com o plano; fôlego só com ação nova e abaixo do teto")

tars.catalogar_modelos = lambda forcar=False: {}
tars.carregar_modelo = lambda mod, silencioso=False: True
tars.ollama_online = lambda: True
tars.modo_modelo = "MANUAL"
tars.modelo_manual = "qwen3:8b"
tars.salvar_sessoes = lambda: None
tars._contexto_do_pedido = lambda *a, **k: None
feitos = []
tars._DISPATCH_FERRAMENTAS["open_application"] = lambda a: feitos.append(a["app"]) or {
    "sucesso": True, "mensagem": "SUCCESS: opened " + a["app"] + " " + "x" * 2000}
tars._DISPATCH_FERRAMENTAS["list_windows"] = lambda a: {"sucesso": True, "mensagem": "1 window", "janelas": []}
assert "list_windows" in tars._FERRAMENTAS_SO_OLHAM

ACOES = 45
maior_conversa = [0]


def turno_trabalhador(modelo, msgs, tools, pensar=True, **kw):
    maior_conversa[0] = max(maior_conversa[0], sum(len(m.get("content") or "") for m in msgs))
    if len(feitos) < ACOES:
        return {"content": "", "tool_calls": [{"function": {"name": "open_application",
                                                            "arguments": {"app": f"app{len(feitos)}"}}}]}, None
    return {"content": f"Pronto: abri os {ACOES} apps.", "tool_calls": []}, None


tars._executar_turno_streaming = turno_trabalhador
resposta = tars.perguntar_modelo("qwen3:8b", "abra os 45 apps da lista", tarefa="acao")
assert resposta == f"Pronto: abri os {ACOES} apps." and len(feitos) == ACOES, (resposta, len(feitos))
folegos = [m for m in tars.conversa if "Long task in progress" in (m.get("content") or "")]
assert len(folegos) == 2, len(folegos)
resultados = [m["content"] for m in tars.conversa if m.get("role") == "tool"]
assert all(len(r) < 700 for r in resultados[:-tars.RESULTADOS_INTEIROS]), [len(r) for r in resultados]
inteiros = resultados[-tars.RESULTADOS_INTEIROS:]
assert len(inteiros[-1]) > 2000, "o resultado mais novo fica inteiro"
assert sum(len(r) for r in inteiros) <= int(tars.contexto_ia() * 3 * 0.4) + len(inteiros[-1]), "os 'inteiros' cabem no orçamento do contexto"
print(f"OK: 45 ações seguidas terminam (2 fôlegos extras); resultados antigos encurtados "
      f"(maior conversa: {maior_conversa[0] // 1000} mil caracteres)")

# Em círculos, só olhando: para no limite de sempre
tars.limpar_sessao()
olhadas = []


def turno_que_so_olha(modelo, msgs, tools, pensar=True, **kw):
    olhadas.append(1)
    return {"content": "", "tool_calls": [{"function": {"name": "list_windows",
                                                        "arguments": {"filtro": str(len(olhadas))}}}]}, None


tars._executar_turno_streaming = turno_que_so_olha
resposta = tars.perguntar_modelo("qwen3:8b", "faz alguma coisa", tarefa="acao")
assert len(olhadas) == 20 and "20" in resposta, (len(olhadas), resposta)
print("OK: sem progresso (só olhando), para nas 20 etapas de sempre")

# Teto
tars.limpar_sessao()
feitos.clear()
ACOES = 10_000
tars._executar_turno_streaming = turno_trabalhador
resposta = tars.perguntar_modelo("qwen3:8b", "abra tudo", tarefa="acao")
assert len(feitos) == tars.LIMITE_CICLOS_MAX == 120 and "120" in resposta, (len(feitos), resposta)
print("OK: mesmo fazendo progresso, para no teto de 120 etapas")

print("\nTUDO OK.")
