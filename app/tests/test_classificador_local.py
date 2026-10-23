"""Escolha da tarefa sem IA (Endurance Neo: o classificador antigo, o
ajudante qwen2.5:0.5b e os embeddings saíram; quem decide é a Murph com as
camadas instantâneas). Aqui:
  - as frases de treino não repetem (nem quase repetem) as de teste;
  - os casos que davam errado: "entra no gmail pra mim", "e aí, como você
    está hoje?"."""

import json
import os
import re
from pathlib import Path

os.environ["TARS_IDIOMA"] = "pt_BR"
from _util import carregar_tars  # noqa: E402
from frases_classificador import FRASES  # noqa: E402

tars = carregar_tars()
import tars_escolha as escolha  # noqa: E402
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "murph"))
from tars_exemplos import EXEMPLOS  # noqa: E402
from tars_exemplos_mais import MAIS  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
AVALIACAO = {l: [tuple(p) for p in json.loads((RAIZ / "idiomas" / f"{l}.json").read_text(encoding="utf-8"))["avaliacao"]]
             for l in sorted(p.stem for p in (RAIZ / "idiomas").glob("*.json"))}
TESTE = list(FRASES) + [p for lista in AVALIACAO.values() for p in lista]


def _tokens(frase):
    return re.findall(r"\w+", tars.normalizar(frase))


def chave(frase):
    return " ".join(_tokens(frase))


def palavras(frase):
    return set(_tokens(frase)) - tars._PALAVRAS_VAZIAS


# ------------------------------------------------------------
# 1. Treino separado do teste
# ------------------------------------------------------------
treino = {chave(f): c for c, lista in EXEMPLOS.items() for f in lista}
repetidas = [f for f, _ in TESTE if chave(f) in treino]
assert not repetidas, f"frases de teste dentro dos exemplos: {repetidas}"
quase = []
for c, lista in MAIS.items():
    for f in lista:
        for g, _ in TESTE:
            a, b = palavras(f), palavras(g)
            if a and len(a & b) / len(a | b) >= 0.75:
                quase.append((f, g))
assert not quase, f"exemplos novos quase iguais a frases de teste: {quase}"
assert sum(map(len, EXEMPLOS.values())) >= 850, "os exemplos da 2.9.1 foram somados"
print(f"OK: {sum(map(len, EXEMPLOS.values()))} exemplos, nenhum repetido das {len(TESTE)} frases de teste")

# ------------------------------------------------------------
# 5. Os casos que davam errado
# ------------------------------------------------------------
casos = [
    ("entra no gmail pra mim", "simples"),
    ("go to gmail for me", "simples"),
    ("vídeos de receita de lasanha no youtube", "busca"),
    ("spotify pausa a música", "acao"),
]
for frase, esperado in casos:
    d = tars.decidir_tarefa(frase, anterior="geral")
    assert d.categoria == esperado, (frase, d)
# "e aí..." é cumprimento, não "e (depois)...": não herda a tarefa anterior
assert not escolha.eh_continuacao(tars.normalizar("e aí, como você está hoje?"))
assert escolha.eh_continuacao(tars.normalizar("e depois fecha"))
tars.lembrar_tarefa("busca")
d = tars.decidir_tarefa("e aí, como você está hoje?")
assert d.categoria == "simples" and not any(c == "contexto" for c, _ in d.trilha), d
print("OK: 'entra no gmail pra mim' abre o site; 'e aí, como você está hoje?' é cumprimento")

print("\nTUDO OK.")
