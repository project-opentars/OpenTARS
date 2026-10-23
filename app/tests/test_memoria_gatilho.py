#!/usr/bin/env python3
"""O pedido que fala de memória ganha as ferramentas remember/forget (print do Enzo: "keep in memory i use brave" não ganhava)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import tars_memoria as m

SIM = [
    "keep in memory i use brave as my browser", "use the tool to save the memory", "save this to memory",
    "remember that I use Brave", "please memorize my folder", "forget what you know about my browser",
    "keep in mind that I use brave", "from now on open links in brave", "note that my name is Enzo",
    "guarda na memória que eu uso o brave", "salve na memoria que eu uso o brave", "lembre que eu uso o brave",
    "anota que meu navegador é o brave", "tenha em mente que eu uso o brave", "o que você sabe sobre mim?",
    "esquece o que eu disse do navegador", "de agora em diante abra tudo no brave",
]
NAO = [
    "abra a calculadora", "que horas são", "tire um print da tela", "crie uma pasta chamada teste",
    "pesquise ollama modelos locais", "mova a janela para a direita", "calcule 12 vezes 15",
]
for f in SIM:
    assert m.fala_de_memoria(f), "devia dar as ferramentas de memória: " + f
for f in NAO:
    assert not m.fala_de_memoria(f), "não devia: " + f
print(f"OK: {len(SIM)} pedidos de memória reconhecidos e {len(NAO)} comuns deixados em paz")
print("TUDO OK.")
