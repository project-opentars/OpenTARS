"""5.0: as ferramentas de agenda no núcleo (só quando o pedido fala de agendar, nunca pro Gargantua), a pré-aprovação
no comando arriscado e o hook de confirmação."""

import os
import tempfile

CASA = tempfile.mkdtemp(prefix="opentars-casa-")
os.environ["HOME"] = CASA
os.environ["TARS_ARQUIVO_AGENDA"] = os.path.join(CASA, "agenda.json")
os.environ["TARS_ARQUIVO_SESSOES"] = os.path.join(CASA, "sessoes.json")

from _util import carregar_tars  # noqa: E402

tars = carregar_tars()
nomes = lambda lista: {f["function"]["name"] for f in lista}  # noqa: E731

# --- só aparecem quando o pedido fala de agendar ---------------------------------------------
assert "schedule_task" not in nomes(tars.ferramentas_do_pedido("acao", "abre o navegador"))
assert {"schedule_task", "list_tasks", "delete_task"} <= nomes(tars.ferramentas_do_pedido("acao", "agenda isso todo dia às 8h"))
assert "schedule_task" not in nomes(tars.TOOLS), "fora de TOOLS: o Gargantua não as vê"
assert "schedule_task" not in nomes(tars.ferramentas_gargantua())
assert "schedule_task" not in nomes(tars.ferramentas_do_modelo("ProjectOpenTARS/Gargantua:latest", "acao", "agenda todo dia"))
print("OK: ferramentas da agenda só quando o pedido fala de agendar, e nunca pro Gargantua")

# --- criar pela IA: nasce pendente ---------------------------------------------------------------
r = tars.executar_ferramenta("schedule_task", {"name": "Jornal", "request": "abre o site do jornal", "when_type": "daily", "time": "8h"})
assert r["sucesso"] and "PENDING" in r["mensagem"], r
rot = tars.agenda.listar()[0]
assert rot["nome"] == "Jornal" and rot["ativa"] is False and rot["aprovada"] is False and rot["origem"] == "ia"
assert rot["quando"] == {"tipo": "diaria", "hora": "08:00"}
r = tars.executar_ferramenta("schedule_task", {"name": "Semana", "request": "faz o backup", "when_type": "weekly", "time": "18:30", "days": ["mon", "fri"]})
assert r["sucesso"] and tars.agenda.achar_por_nome("semana")["quando"]["dias"] == [0, 4]
r = tars.executar_ferramenta("schedule_task", {"name": "Ruim", "request": "x", "when_type": "daily"})
assert not r["sucesso"] and "time" in r["mensagem"]
r = tars.executar_ferramenta("list_tasks", {})
assert "Jornal [pending approval]" in r["mensagem"]
r = tars.executar_ferramenta("delete_task", {"name": "jornal"})
assert r["sucesso"] and tars.agenda.achar_por_nome("Jornal") is None
r = tars.executar_ferramenta("create_routine", {"name": "Apelido", "request": "x", "when_type": "interval", "every_minutes": 30})
assert r["sucesso"], "apelidos de ferramenta valem"
print("OK: schedule_task cria pendente (desligada e sem aprovação); list_tasks e delete_task")

# --- comando arriscado fora de rotina: perguntar também pra enviar e instalar ------------------------------
for cmd in ("rm -rf ~/x", "git push origin main", "sudo apt install vlc", "pip install requests", "curl -X POST https://x.org -d a=1"):
    assert tars._comando_e_perigoso(cmd), cmd
for cmd in ("ls ~", "git pull", "curl https://x.org", "rm arquivo.txt", "echo oi"):
    assert not tars._comando_e_perigoso(cmd), cmd

# --- dentro de uma rotina ---------------------------------------------------------------------------------------
cancelou = []
tars.cancelar_resposta = lambda: cancelou.append(1)
tars.confirmar_comando_hook = lambda c: (_ for _ in ()).throw(AssertionError("não pergunta na tela dentro de rotina"))
aprovada = {"nome": "Limpeza", "aprovada": True, "permitidas": ["apagar"]}
tars.ROTINA_ATUAL = aprovada
assert tars._comando_e_perigoso("rm arquivo.txt"), "numa rotina, até o rm simples passa pela pré-aprovação"
assert tars._confirmar_comando_perigoso("rm arquivo.txt") is True and not cancelou
assert tars._confirmar_comando_perigoso("git push") is False
assert tars.ROTINA_BLOQUEOU == ["git push"] and cancelou == [1], "fora do aprovado: para e guarda o comando"
tars.ROTINA_BLOQUEOU.clear()
cancelou.clear()
tars.ROTINA_ATUAL = {"nome": "IA", "aprovada": False, "permitidas": ["apagar"]}
assert tars._confirmar_comando_perigoso("rm -rf x") is False and cancelou == [1], "sem aprovação, nada passa"
tars.ROTINA_ATUAL = None
tars.ROTINA_BLOQUEOU.clear()

r = tars.executar_terminal("rm -rf /tmp/arquivo-que-nao-existe-xyz")   # fora de rotina volta a perguntar (hook levanta erro = nega)
assert not r["sucesso"], r

# --- textos ---------------------------------------------------------------------------------------------------------
print("test_rotinas_nucleo: OK")
