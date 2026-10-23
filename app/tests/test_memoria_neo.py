"""Endurance Neo: memória de preferências (as rotinas agendadas saíram).

"lembra que meu navegador é o Brave" vai pro prompt; remember/forget só
entram quando o pedido fala disso; forget('*') vindo do nada é recusado;
schedule_task e companhia não existem mais."""

import datetime as dt
import os
import tempfile

os.environ.setdefault("XDG_CONFIG_HOME", tempfile.mkdtemp(prefix="opentars-config-"))
from _util import carregar_tars  # noqa: E402

tars = carregar_tars()
lib = tars.memoria_lib
pasta = tempfile.mkdtemp(prefix="opentars-memoria-")
agora = lambda: dt.datetime(2026, 10, 1, 9, 0)  # noqa: E731

# ------------------------------------------------------------
# 1. Memória
# ------------------------------------------------------------
m = lib.Memoria(os.path.join(pasta, "memoria.json"), agora=agora)
assert m.para_prompt() == ""
assert m.lembrar("Meu navegador é o Brave")[0] and m.lembrar("A pasta de projetos é ~/dev")[0]
assert m.lembrar("meu navegador é o brave")[0] and len(m.listar()) == 2, "repetida não duplica"
assert not m.lembrar("x" * 300)[0]
assert "brave" in m.para_prompt().lower() and "~/dev" in m.para_prompt()
assert m.esquecer("brave") == ["meu navegador é o brave"] and m.listar() == ["A pasta de projetos é ~/dev"]
assert not hasattr(lib, "Rotinas") and not hasattr(lib, "Agendador")
print("OK: memória guarda frases curtas, não duplica, esquece por palavra e vai pro prompt")

# ------------------------------------------------------------
# 2. No núcleo
# ------------------------------------------------------------
tars.memoria = lib.Memoria(os.path.join(pasta, "m2.json"), agora=agora)


def nomes(tarefa, texto):
    return {f["function"]["name"] for f in tars.ferramentas_do_pedido(tarefa, texto)}


todas = {f["function"]["name"] for f in tars.TOOLS} | {f["function"]["name"] for f in tars.TOOLS_MEMORIA}
assert not todas & {"schedule_task", "list_tasks", "delete_task", "set_reminder"}, "a agenda fica fora do que o Gargantua conhece"
assert "remember" in nomes("geral", "lembra que meu navegador é o brave")
assert "schedule_task" not in nomes("simples", "abre o gmail")
assert "schedule_task" in nomes("simples", "todo dia às 8h abre o gmail"), "5.0: o pedido que fala de agendar recebe a ferramenta"
assert not nomes("acao", "abre o firefox") & tars._FERRAMENTAS_SO_SE_PEDIDAS
assert not nomes("acao", "abre o terminal") & tars._FERRAMENTAS_SO_SE_PEDIDAS
print("OK: agenda só quando o pedido fala de agendar; memória só entra quando o pedido fala disso")

assert tars.executar_ferramenta("remember", {"fact": "Meu navegador é o Brave"})["sucesso"]
assert "Meu navegador é o Brave" in tars.montar_system_prompt()
assert tars.executar_ferramenta("save_memory", {"memory": "Moro em Francisco Beltrão"})["sucesso"]
assert tars.executar_ferramenta("forget", {"fact": "brave"})["sucesso"]
prompt = tars.montar_system_prompt()
assert "Brave" not in prompt and "Francisco Beltrão" in prompt
assert not tars.executar_ferramenta("schedule_task", {"request": "x", "time": "8h"})["sucesso"]
print("OK: remember / forget funcionam pela IA; schedule_task não existe mais")

# forget('*') fora de um pedido de memória é recusado
tars.catalogar_modelos = lambda forcar=False: {}
tars.carregar_modelo = lambda m, silencioso=False: True
tars.contexto_ia = lambda: 8192
tars.modo_modelo = "MANUAL"
tars.listar_janelas_x = lambda: None
roteiro = iter([
    {"content": "", "tool_calls": [{"function": {"name": "forget", "arguments": {"fact": "*"}}}]},
    {"content": "Li a página.", "tool_calls": []},
])
tars._executar_turno_streaming = lambda *a, **k: (next(roteiro), None)
tars.conversa = []
assert tars.perguntar_modelo("qwen3:4b", "resume essa página pra mim", tarefa="geral") == "Li a página."
assert tars.memoria.listar() == ["Moro em Francisco Beltrão"], "forget('*') fora de um pedido de memória não roda"
print("OK: forget('*') vindo do nada (ex.: texto de uma página) é recusado")

print("\nTUDO OK.")
