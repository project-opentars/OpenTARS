"""5.3 (F8): a aparência do terminal novo (nucleo/visual.py): resposta formatada em pedaços, régua com o modo, barra de estado
com pasta e ramo, boas-vindas com o motor de verdade. Sem Ollama e sem modelo: só desenho."""
import contextlib
import io
import os
import re
import sys
import tempfile
from pathlib import Path

pasta = Path(tempfile.mkdtemp(prefix="opentars-visual-"))
os.environ["TARS_ARQUIVO_SESSOES"] = str(pasta / "sessoes.json")
os.environ["HOME"] = str(pasta / "casa")
(pasta / "casa").mkdir()

from _util import carregar_tars  # noqa: E402

tars = carregar_tars()
tars.ollama_online = lambda: False
tars.avisos_de_ambiente = lambda: []
sem_cor = lambda s: re.sub(r"\033\[[0-9;]*m", "", s)  # noqa: E731

# 1. a resposta chega aos pedaços, no meio das palavras: o que sai é igual a formatar de uma vez
md = tars._MarkdownTerminal()
texto = ("# Plano\n\nVou fazer **três** coisas:\n- abrir `main.py`\n  - e ler\n* rodar os testes\n\n```python\nprint(1)\n```\n"
         "> uma citação\nFim sem quebra")
de_uma_vez = md.alimentar(texto) + md.terminar()
md.reiniciar()
em_pedacos = "".join(md.alimentar(texto[i:i + 3]) for i in range(0, len(texto), 3)) + md.terminar()
assert de_uma_vez == em_pedacos, "formatar aos pedaços tem de dar o mesmo que de uma vez"
limpo = sem_cor(de_uma_vez).splitlines()
assert limpo[0] == "Plano" and "**" not in de_uma_vez.replace(tars.Cor.NEGRITO, "") and "`" not in sem_cor(de_uma_vez).split("```")[0]
assert "• abrir main.py" in limpo and "  • e ler" in limpo and "• rodar os testes" in limpo, limpo
assert "╭─ python" in limpo and "│ print(1)" in limpo and "╰─" in limpo, limpo
assert limpo[-1] == "Fim sem quebra" and "│ uma citação" in limpo
assert tars.Cor.NEGRITO + "três" in de_uma_vez and tars.Cor.CIANO + "main.py" in de_uma_vez
print("OK: resposta formatada: títulos, **negrito**, `código`, listas com •, bloco de código e citação; aos pedaços é igual")

# 2. um bloco de código aberto e nunca fechado não vaza para a próxima resposta
md.reiniciar()
md.alimentar("```\nsem fim\n")
md.terminar()
assert "│" not in sem_cor(md.alimentar("texto normal\n")), "o bloco aberto não pode continuar na resposta seguinte"
print("OK: bloco de código sem fim não vaza")

# 3. o evento de resposta: formatado só com o giro ligado (terminal de verdade); sem ele o texto sai puro
def imprimir(ligado):
    saida = io.StringIO()
    tars._girando.ligado = ligado
    try:
        with contextlib.redirect_stdout(saida):
            tars._TERMINAL["resposta"]({"texto": "Olá **mundo**\nlinha dois", "inicio": True, "apos_pensamento": False})
            tars._TERMINAL["fim_stream"]({})
    finally:
        tars._girando.ligado = False
    return saida.getvalue()


assert "**mundo**" in imprimir(False) and tars.Cor.NEGRITO not in imprimir(False), "fora de um terminal o texto sai como veio"
bonito = imprimir(True)
assert tars.Cor.NEGRITO + "mundo" in bonito and "**" not in bonito and sem_cor(bonito).count("linha dois") == 1, bonito
print("OK: no pipe e na janela o texto sai puro; no terminal de verdade, formatado")

# 4. régua, tempo, motor, pasta
assert sem_cor(tars._regua("automatico")).rstrip().endswith(("auto ──", "automático ──")), sem_cor(tars._regua("automatico"))
assert tars._tempo_curto(7) == "7s" and tars._tempo_curto(65) == "1m 05s" and tars._tempo_curto(600) == "10m 00s"
import tars_motor_local  # noqa: E402
tars.OLLAMA_HOST = tars_motor_local.URL
assert tars._nome_do_motor() == "llama.cpp"
tars.OLLAMA_HOST = "http://127.0.0.1:11434"
assert tars._nome_do_motor() == "Ollama"
os.chdir(pasta / "casa")
assert tars._pasta_curta() == "~" and tars._ramo_git() == ""
os.makedirs(pasta / "casa" / "projeto" / "src")
os.chdir(pasta / "casa" / "projeto" / "src")
assert tars._pasta_curta() == "~/projeto/src".replace("/", os.sep)
print("OK: régua com o modo, tempo em minutos, motor (llama.cpp ou Ollama), pasta com ~ e ramo vazio fora do git")

# 5. boas-vindas e barra de estado: nomeiam o motor e a pasta
tars.OLLAMA_HOST = tars_motor_local.URL
saida = io.StringIO()
with contextlib.redirect_stdout(saida):
    tars._boas_vindas(0)
    tars._linha_de_status()
tela = sem_cor(saida.getvalue())
assert "llama.cpp" in tela and ("reinicie o openTARS" in tela or "restart openTARS" in tela), tela
assert "projeto" in tela and "ollama:" not in tela, tela
print("OK: as boas-vindas dizem o motor de verdade (e como ligar), e o status traz a pasta")

# 5.3 (F8, só aparência): o pedido dentro da caixa do Claude Code, com a barra do opencode embaixo
barra = sem_cor(tars._barra_de_estado(100))
assert barra.startswith(" openTARS ") and "projeto" in barra and len(barra) <= 100, barra
saida = io.StringIO()
import builtins  # noqa: E402
antes, builtins.input = builtins.input, lambda prompt="": "lista os arquivos"
try:
    with contextlib.redirect_stdout(saida):
        assert tars._pedir_na_caixa("", "") == "lista os arquivos"
finally:
    builtins.input = antes
tela = sem_cor(saida.getvalue())
assert "╭" in tela and "╰" in tela and "openTARS" in tela and "\033[2A" in saida.getvalue(), repr(tela[:200])
assert re.search(r"│ ❯ lista os arquivos +│", tela), "depois do Enter a linha ganha a borda da direita"
print("OK: caixa de entrada com a barra de estado; depois do Enter a linha fecha com a borda")
print("TUDO OK.")
