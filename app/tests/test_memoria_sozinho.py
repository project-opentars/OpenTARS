"""5.1: "keep in memory i use brave as my browser" MANDA salvar. Se o modelo não chamar remember (só diz "anotado!", ou
escreve num arquivo pelo shell, como no print do Enzo), o openTARS salva o fato sozinho."""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("XDG_CONFIG_HOME", tempfile.mkdtemp(prefix="opentars-config-"))
from _util import carregar_tars  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import tars_memoria as m  # noqa: E402

# 1. o reconhecimento
SALVAR = {
    "keep in memory i use brave as my browser": "i use brave as my browser",
    "Remember that my name is Enzo": "my name is Enzo",
    "please remember my folder is ~/dev": "my folder is ~/dev",
    "lembre que eu uso o brave": "eu uso o brave",
    "guarde na memória que eu moro em Francisco Beltrão": "eu moro em Francisco Beltrão",
    "salve na memoria que eu uso o brave": "eu uso o brave",
    "anota que meu navegador é o brave": "meu navegador é o brave",
    "tenha em mente que eu uso o brave": "eu uso o brave",
    "recuerda que uso Brave": "uso Brave",
    "souviens-toi que j'utilise Brave": "j'utilise Brave",
    "merk dir, dass ich Brave nutze": "ich Brave nutze",
}
NAO = ["do you remember my browser?", "você lembra do meu navegador?", "lembre-me de ligar amanhã", "me lembra de beber água",
       "abra a calculadora", "remember", "what do you remember about me", "forget my browser", "use the tool to save the memory",
       "tire um print da tela", "o que você sabe sobre mim?"]
for frase, fato in SALVAR.items():
    assert m.intencao_de_lembrar(frase) == fato, (frase, m.intencao_de_lembrar(frase))
for frase in NAO:
    assert m.intencao_de_lembrar(frase) is None, frase
print(f"OK: {len(SALVAR)} pedidos de salvar reconhecidos com o fato certo e {len(NAO)} outros deixados em paz")

# 2. no laço do chat
tars = carregar_tars()
lib = tars.memoria_lib
pasta = tempfile.mkdtemp(prefix="opentars-memoria-")
tars.catalogar_modelos = lambda forcar=False: {}
tars.carregar_modelo = lambda mod, silencioso=False: True
tars.contexto_ia = lambda: 8192
tars.modo_modelo = "MANUAL"
tars.listar_janelas_x = lambda: None


def rodar(texto, turnos, multi=False):
    tars.memoria = lib.Memoria(os.path.join(pasta, f"m{rodar.n}.json"))
    rodar.n += 1
    roteiro = iter(turnos)
    chamadas = []
    original = tars.executar_ferramenta
    tars.executar_ferramenta = lambda nome, a: (chamadas.append((nome, dict(a))), original(nome, a))[1]
    tars._executar_turno_streaming = lambda *a, **k: (next(roteiro), None)
    tars.conversa = []
    try:
        resposta = tars.perguntar_modelo("gpt-oss:20b", texto, tarefa="geral", multi_etapas=multi)
    finally:
        tars.executar_ferramenta = original
    return resposta, chamadas, tars.memoria.listar()


rodar.n = 0
FINAL = {"content": "Pronto, guardei.", "tool_calls": []}

# a) o modelo só responde "anotado!" (o 1º print do Enzo)
r, ch, mem = rodar("keep in memory i use brave as my browser",
                   [{"content": "Got it, I'll remember that Brave is your browser.", "tool_calls": []}, FINAL])
assert mem == ["i use brave as my browser"] and ch == [("remember", {"fact": "i use brave as my browser"})], (mem, ch)
assert r == "Pronto, guardei."
print("OK: o modelo diz 'anotado' e não chama nada: o openTARS salva")

# b) o modelo vai de shell escrever num arquivo (o 2º print)
sh = {"content": "", "tool_calls": [{"function": {"name": "run_command", "arguments": {"command": "echo 'browser=brave' > ~/.cfg"}}}]}
r, ch, mem = rodar("keep in memory i use brave as my browser", [sh, FINAL])
assert [c[0] for c in ch] == ["remember"] and mem == ["i use brave as my browser"], (ch, mem)
print("OK: o modelo tenta o shell: o shell NÃO roda, entra o remember")

# c) o modelo chama remember sozinho: uma vez só, sem duplicar
ok = {"content": "", "tool_calls": [{"function": {"name": "remember", "arguments": {"fact": "Uso o Brave"}}}]}
r, ch, mem = rodar("lembre que eu uso o brave", [ok, FINAL])
assert [c[0] for c in ch] == ["remember"] and mem == ["Uso o Brave"], (ch, mem)
print("OK: se o modelo chama remember, o dele vale e não duplica")

# d) pedido com outra etapa: não mexe
r, ch, mem = rodar("lembre que eu uso o brave e abre ele", [{"content": "Ok.", "tool_calls": []}], multi=True)
assert ch == [] and mem == []
print("OK: pedido com outra etapa fica com o modelo")

# e) pergunta: nada
r, ch, mem = rodar("você lembra do meu navegador?", [{"content": "Não sei.", "tool_calls": []}])
assert ch == [] and mem == [] and r == "Não sei."
print("OK: pergunta não salva nada")

print("\nTUDO OK.")
