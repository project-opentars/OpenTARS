"""Treina a Murph ajudante e exporta pra murph.json.

    python3 murph/treinar_murph.py            # treina com tudo e salva
    python3 murph/treinar_murph.py --cv       # só validação cruzada (escolha do C)
"""
import json
import math
import os
import sys

import numpy as np
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from dados import treino, TAREFAS  # noqa: E402
sys.path.insert(0, os.path.dirname(AQUI))
import tars_murph as mm  # noqa: E402


def amostras():
    ger = [(f, c) for f, c, _ in json.load(open(os.path.join(AQUI, "gerado_limpo.json"), encoding="utf-8"))]
    return treino() + ger


def treinar(dados, C):
    textos = [f for f, _ in dados]
    y = np.array([TAREFAS.index(c) for _, c in dados])
    cont = [mm.contagens(t) for t in textos]
    n = len(cont)
    df = {}
    for f in cont:
        for k in f:
            df[k] = df.get(k, 0) + 1
    idf = {k: math.log((1 + n) / (1 + d)) + 1.0 for k, d in df.items()}
    vetores = [mm.vetor(t, idf) for t in textos]
    dv = DictVectorizer()
    X = dv.fit_transform(vetores)
    clf = LogisticRegression(C=C, max_iter=5000)
    clf.fit(X, y)
    nomes = dv.get_feature_names_out()
    W = clf.coef_.T  # (n_feats, n_tarefas)
    pesos = {}
    for k, linha in zip(nomes, W):
        if np.abs(linha).max() >= 1e-3:
            pesos[k] = [round(float(x), 4) for x in linha]
    idf = {k: round(v, 4) for k, v in idf.items() if k in pesos}
    return mm.Murph({"tarefas": TAREFAS, "idf": idf, "vies": [float(b) for b in clf.intercept_], "pesos": pesos})


def fora_da_dobra(dados, C, dobras=5):
    """(folga p1-p2, acertou, cobertura) de cada frase, prevista por um
    modelo que não a viu."""
    y = np.array([c for _, c in dados])
    res = []
    for tr, te in StratifiedKFold(dobras, shuffle=True, random_state=0).split(dados, y):
        m = treinar([dados[i] for i in tr], C)
        for i in te:
            p = m.probabilidades(dados[i][0])
            res.append((p[0][0] - p[1][0], p[0][1] == dados[i][1], mm.cobertura(dados[i][0], m.idf)))
    return res


def calibrar(res, alvo=0.98):
    """Menor folga com que a Murph ainda acerta >= alvo. Confiante, ela decide
    SOZINHA (pula embeddings e ajudante): por isso a régua é alta (98%)."""
    res = sorted(res, reverse=True)
    escolhida, acertos = 1.0, 0
    for n, (folga, ok) in enumerate(res, 1):
        acertos += ok
        if acertos / n >= alvo:
            escolhida = folga
    return max(0.05, escolhida), sum(ok for _, ok in res) / len(res)


def cv(dados, C, dobras=5):
    y = np.array([c for _, c in dados])
    acc = []
    for tr, te in StratifiedKFold(dobras, shuffle=True, random_state=0).split(dados, y):
        m = treinar([dados[i] for i in tr], C)
        acc.append(np.mean([m.classificar(dados[i][0])[0] == dados[i][1] for i in te]))
    return np.mean(acc), np.std(acc)


if __name__ == "__main__":
    dados = amostras()
    if "--cv" in sys.argv:
        for C in (5, 10, 20, 50):
            m, s = cv(dados, C)
            print(f"C={C:<3} CV {100 * m:.1f}% ± {100 * s:.1f}", flush=True)
    else:
        C = float(os.environ.get("MURPH_C", 20))
        res = fora_da_dobra(dados, C)
        limite, precisao = calibrar([(f, ok) for f, ok, _ in res])
        # 98% das frases que ela nunca viu têm pelo menos esta cobertura;
        # abaixo disso o pedido não se parece com nada do treino.
        cobertura_minima = float(np.percentile([cob for _, _, cob in res], 2))
        print(f"validação cruzada: {100 * precisao:.1f}%, folga 'confiante' >= {limite:.3f}, "
              f"cobertura mínima {cobertura_minima:.2f}")
        m = treinar(dados, C)
        saida = mm.CAMINHO_PADRAO
        with open(saida, "w", encoding="utf-8") as f:
            json.dump({"formato": mm.VERSAO_FORMATO, "versao": mm.VERSAO, "tarefas": m.tarefas, "idf": m.idf, "vies": m.vies,
                       "pesos": m.pesos,
                       "limite": round(limite, 4), "cobertura_minima": round(cobertura_minima, 4), "precisao_cv": round(precisao, 4), "frases": len(dados)}, f, ensure_ascii=False, separators=(",", ":"))
        print(f"{len(dados)} frases, {len(m.pesos)} características, {os.path.getsize(saida) / 1e6:.1f} MB -> {saida}")
