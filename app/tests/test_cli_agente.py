"""5.1: o terminal no nível das CLIs de agente. -p (texto e JSON, stdin, código de saída, sem sobrescrever a conversa
salva), modo plano, "sempre nesta sessão" (nunca para apagar em massa), ferramentas de código só no terminal e nunca
para o Gargantua, edição com diff e /undo, AGENTS.md e /init, /compact, /mode e /resume. Sem Ollama de verdade."""
import contextlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path

pasta = Path(tempfile.mkdtemp(prefix="opentars-cli-"))
os.environ["TARS_ARQUIVO_SESSOES"] = str(pasta / "sessoes.json")
os.environ["HOME"] = str(pasta / "casa")
(pasta / "casa").mkdir()

from _util import carregar_tars  # noqa: E402

tars = carregar_tars()
tars.ollama_online = lambda: False
tars.avisos_de_ambiente = lambda: []

# ---------------------------------------------------------------- -p
sessao_salva = json.dumps({"versao": 2, "conversa": [{"role": "user", "content": "conversa da pessoa"}]})
Path(os.environ["TARS_ARQUIVO_SESSOES"]).write_text(sessao_salva)
recebidos = []


def processar_falso(texto, anexos=None):
    recebidos.append(texto)
    tars.emitir("ferramenta", nome="execute_terminal", resumo="ls")
    tars.emitir("ferramenta_fim", nome="execute_terminal", sucesso=True, segundos=0.1)
    print("passo que não pode sujar o stdout")
    tars.salvar_sessoes()
    return "três arquivos"


tars.processar_mensagem = processar_falso


def rodar_print(pedido, formato="text", entrada="", modelo=None):
    saida, erros = io.StringIO(), io.StringIO()
    stdin_antigo = sys.stdin
    sys.stdin = io.StringIO(entrada)
    try:
        with contextlib.redirect_stdout(saida), contextlib.redirect_stderr(erros):
            codigo = tars.modo_print(pedido, formato, modelo)
    finally:
        sys.stdin = stdin_antigo
    return codigo, saida.getvalue(), erros.getvalue()


codigo, saida, erros = rodar_print("quantos arquivos?", entrada="a.txt\nb.txt\n")
assert codigo == 0 and saida == "três arquivos\n", (codigo, saida)
assert "passo que não pode sujar" in erros and "passo" not in saida
assert "<stdin>\na.txt\nb.txt" in recebidos[-1], recebidos[-1]
assert Path(os.environ["TARS_ARQUIVO_SESSOES"]).read_text() == sessao_salva, "o -p não pode sobrescrever a conversa salva"
codigo, saida, _ = rodar_print("liste", "json", modelo="qwen3:4b")
dados = json.loads(saida)
assert codigo == 0 and dados["ok"] and dados["resposta"] == "três arquivos" and tars.modelo_manual == "qwen3:4b"
assert dados["ferramentas"] == [{"nome": "execute_terminal", "resumo": "ls", "sucesso": True}], dados
tars.processar_mensagem = lambda texto, anexos=None: None
assert rodar_print("algo")[0] == 1, "sem resposta: código 1"
assert rodar_print("")[0] == 2, "sem pedido nem stdin: código 2"
print("OK: -p em texto e JSON, stdin como dado, passos no stderr, código de saída e conversa salva intacta")

# ---------------------------------------------------------------- modo plano
chamou = []
tars._DISPATCH_FERRAMENTAS["open_application"] = lambda a: chamou.append("abriu") or {"sucesso": True, "mensagem": "ok"}
tars._DISPATCH_FERRAMENTAS["list_windows"] = lambda a: chamou.append("olhou") or {"sucesso": True, "mensagem": "janelas"}
tars._tratar_comando_do_chat("/modo plano")
assert tars.MODO_PERMISSAO == "plano"
r = tars.executar_ferramenta("open_application", {"app": "firefox"})
assert r["sucesso"] and "NOT run" in r["mensagem"] and chamou == [] and tars.PASSOS_DO_PLANO == ["open_application firefox"]
assert tars.executar_ferramenta("list_windows", {})["mensagem"] == "janelas" and chamou == ["olhou"], "só olhar continua"
with contextlib.redirect_stdout(io.StringIO()) as plano:
    tars._mostrar_plano()
assert "open_application firefox" in plano.getvalue() and not tars.PASSOS_DO_PLANO
tars._tratar_comando_do_chat("/mode auto")
assert tars.MODO_PERMISSAO == "automatico"
tars._tratar_comando_do_chat("/modo perguntar")
print("OK: no modo plano nada que muda roda (o que só olha roda) e o plano aparece no fim")

# ---------------------------------------------------------------- "sempre nesta sessão"
respostas = []
tars.input = lambda prompt="": respostas.pop(0)
tars.confirmar_comando_hook = None
respostas[:] = ["sempre"]
assert tars._confirmar_comando_perigoso("git push origin main") and not respostas
assert tars._confirmar_comando_perigoso("git push origin main"), "liberado nesta sessão: não pergunta de novo"
respostas[:] = ["sempre", "n"]
assert not tars._confirmar_comando_perigoso("rm -rf ~/pasta"), "'sempre' não vale para apagar em massa"
assert not tars._confirmar_comando_perigoso("rm -rf ~/pasta") and not respostas, "e pergunta de novo"
print("OK: 'sempre nesta sessão' vale para envio/instalação; apagar em massa pergunta toda vez")

# ---------------------------------------------------------------- ferramentas de código
nomes = lambda lista: {f["function"]["name"] for f in lista}  # noqa: E731
tars.CLI_ATIVO = False
assert "edit_file" not in nomes(tars.ferramentas_do_pedido("codigo", "corrige o bug no app.py")), "fora do terminal, não"
tars.CLI_ATIVO = True
assert {"read_file", "search_files", "edit_file", "write_file"} <= nomes(tars.ferramentas_do_pedido(None, "corrige o bug no app.py"))
assert "edit_file" not in nomes(tars.ferramentas_do_pedido(None, "abre a calculadora")), "pedido que não é de código"
assert "edit_file" not in nomes(tars.ferramentas_do_modelo("ProjectOpenTARS/Gargantua:code", "codigo", "corrige o app.py"))
assert len(tars.ferramentas_do_modelo("ProjectOpenTARS/Gargantua:latest", "codigo", "corrige o app.py")) == 19

projeto = pasta / "projeto"
projeto.mkdir()
os.chdir(projeto)
(projeto / "app.py").write_text("def soma(a, b):\n    return a - b\n\nprint(soma(1, 2))\n")
r = tars.executar_ferramenta("read_file", {"path": "app.py"})
assert "    2      return a - b" in r["mensagem"], r["mensagem"]
assert "app.py:2" in tars.executar_ferramenta("search_files", {"pattern": "return a"})["mensagem"]
tars.iniciar_rodada()
respostas[:] = ["s"]
r = tars.executar_ferramenta("edit_file", {"path": "app.py", "old_text": "return a - b", "new_text": "return a + b"})
assert r["sucesso"] and "return a + b" in (projeto / "app.py").read_text() and not respostas, r
respostas[:] = ["n"]
r = tars.executar_ferramenta("write_file", {"path": "novo.py", "content": "x = 1\n"})
assert not r["sucesso"] and not (projeto / "novo.py").exists(), "negado: nada é escrito"
assert not tars.executar_ferramenta("edit_file", {"path": "app.py", "old_text": "a", "new_text": "b"})["sucesso"], \
    "trecho repetido é recusado"
tars.iniciar_rodada()
tars.MODO_PERMISSAO = "automatico"
r = tars.executar_ferramenta("write_file", {"path": "novo.py", "content": "x = 1\n"})
assert r["sucesso"] and (projeto / "novo.py").read_text() == "x = 1\n", "modo automático: dentro do projeto não pergunta"
fora = pasta / "casa" / "fora.txt"
respostas[:] = ["n"]
assert not tars.executar_ferramenta("write_file", {"path": str(fora), "content": "x"})["sucesso"] and not fora.exists(), \
    "fora da pasta do projeto pergunta mesmo no automático"
tars.MODO_PERMISSAO = "perguntar"
assert tars.desfazer_ultima_rodada() == [str(projeto / "novo.py")] and not (projeto / "novo.py").exists()
with contextlib.redirect_stdout(io.StringIO()):
    tars._tratar_comando_do_chat("/undo")
assert "return a - b" in (projeto / "app.py").read_text(), "/undo volta a edição do pedido anterior"
assert tars.desfazer_ultima_rodada() == []
print("OK: ferramentas de código só no terminal e nunca para o Gargantua; diff com confirmação; /undo volta")

# ---------------------------------------------------------------- AGENTS.md e /init
(projeto / "README.md").write_text("# Calculadora\n")
(projeto / "test_app.py").write_text("def test(): pass\n")
with contextlib.redirect_stdout(io.StringIO()):
    tars._tratar_comando_do_chat("/init")
texto = (projeto / "AGENTS.md").read_text()
assert texto.startswith("# Calculadora") and "python3 -m pytest" in texto and "Python" in texto, texto
assert tars.criar_agents_md() is None, "não sobrescreve"
(projeto / "sub").mkdir()
assert tars.carregar_contexto_projeto(projeto / "sub") == projeto / "AGENTS.md", "acha o da pasta de cima"
assert "PROJECT INSTRUCTIONS" in tars._memoria_para_prompt()
tars.CLI_ATIVO = False
assert "PROJECT INSTRUCTIONS" not in tars._memoria_para_prompt(), "só na conversa do terminal"
tars.CLI_ATIVO = True
print("OK: /init cria o AGENTS.md (sem sobrescrever) e ele entra no prompt só no terminal")

# ---------------------------------------------------------------- /compact e /context
tars.conversa[:] = [{"role": "system", "content": "s"}]
for i in range(6):
    tars.conversa += [{"role": "user", "content": f"pedido {i}"}, {"role": "assistant", "content": f"resposta {i}"}]
antes, depois = tars.compactar_conversa(resumir=lambda txt: "resumo: " + txt.count("pedido") * "x")
usuarios = [m["content"] for m in tars.conversa if m["role"] == "user"]
assert usuarios[0].startswith("[Summary of the earlier conversation]\nresumo: xxx") and usuarios[1:] == ["pedido 3", "pedido 4", "pedido 5"]
assert depois < antes and tars.conversa[0]["role"] == "system"
assert tars.compactar_conversa() is None, "conversa curta: nada a compactar"
print("OK: /compact troca o começo por um resumo e guarda os 3 últimos pedidos inteiros")

# ---------------------------------------------------------------- /resume
import tars_historico  # noqa: E402

h = tars_historico.Historico(str(pasta / "historico.json"))
tars.SESSAO_CLI["historico"] = h
h.salvar("antiga", [{"role": "user", "content": "como faço backup"}, {"role": "assistant", "content": "assim"}])
respostas[:] = ["1"]
with contextlib.redirect_stdout(io.StringIO()):
    assert tars._escolher_conversa()
assert tars.SESSAO_CLI["id"] == "antiga" and tars.conversa[1]["content"] == "como faço backup"
print("OK: /resume lista as conversas salvas (as da janela) e carrega a escolhida")
print("\nTUDO OK.")
