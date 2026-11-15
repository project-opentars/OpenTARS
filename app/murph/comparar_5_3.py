"""Compara duas Murph (a atual e um candidato) em todas as provas, para só trocar se nenhuma piorar (PLANO_5.3 F2.7, d):
a série de rotas, a avaliação dos idiomas (175) e a conferência (tests/frases_classificador.py, 86).

    python3 murph/comparar_5_3.py modelos/murph.json /tmp/murph-candidata.json
"""
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.dirname(AQUI))
import tars_murph as mm  # noqa: E402
from dados import teste  # noqa: E402
from serie_rotas import SERIE  # noqa: E402


def notas(caminho):
    m = mm.Murph.carregar(caminho)
    av, ex = teste()
    conta = lambda pares: sum(m.classificar(f)[0] == c for f, c in pares)  # noqa: E731
    return {"serie": conta(SERIE), "avaliacao": conta([(f, c) for f, c, _ in av]), "conferencia": conta([(f, c) for f, c, _ in ex])}, \
        {"serie": len(SERIE), "avaliacao": len(av), "conferencia": len(ex)}


if __name__ == "__main__":
    a, total = notas(sys.argv[1])
    b, _ = notas(sys.argv[2])
    for k in a:
        print(f"{k:12} atual {a[k]}/{total[k]}   candidata {b[k]}/{total[k]}")
    piorou = [k for k in a if b[k] < a[k]]
    print("TROCAR" if not piorou and b != a else ("NÃO TROCAR: piorou em " + ", ".join(piorou) if piorou else "IGUAIS"))
