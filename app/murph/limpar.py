"""Junta as frases geradas e tira: repetidas, já existentes, e qualquer uma
AVISO (4.0 Endurance Neo): este script de desenvolvimento usa o tars_classificador.py
(Naive Bayes), que saiu do openTARS. Pra rodar, pegue esse arquivo da 4.0 Endurance.
parecida com uma frase de teste EM QUALQUER IDIOMA.

As frases de teste entram aqui nos 5 idiomas: as da avaliação já existem
traduzidas (idiomas/*.json) e as de tests/frases_classificador.py foram
traduzidas só pra este filtro (filtro_traducoes_teste.json). Assim some
também a TRADUÇÃO de uma frase de teste, não só a cópia.

Sai: parecida (pedaços de letras ou palavras) OU que divide com uma frase
de teste uma palavra rara (número de 2+ dígitos, ou palavra que quase não
aparece no resto dos dados, tipo "mona", "framework").
"""
import glob
import json
import os
import re
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from dados import teste, treino, RAIZ, TAREFAS  # noqa: E402
sys.path.insert(0, RAIZ)
import tars_classificador as cl  # noqa: E402
from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: E402
from sklearn.metrics.pairwise import cosine_similarity  # noqa: E402

av, ex = teste()
T = [f for f, _, _ in av + ex]
for item in json.load(open(os.path.join(AQUI, "filtro_traducoes_teste.json"), encoding="utf-8")):
    T += [item[k] for k in ("pt_BR", "en", "es", "fr", "de") if item.get(k)]
existentes = {cl.normalizar(f) for f, _ in treino()}


def palavras(f):
    return set(cl.tokens(cl.normalizar(f))) - cl.VAZIAS


gerado, vistos = [], set()
for arq in sorted(glob.glob(os.path.join(AQUI, "gerado", "*.json"))):
    idioma = os.path.basename(arq)[:-5]
    for cat, lista in json.load(open(arq, encoding="utf-8")).items():
        assert cat in TAREFAS, cat
        for f in lista:
            k = cl.normalizar(f)
            if k in vistos or k in existentes:
                continue
            vistos.add(k)
            gerado.append((f, cat, idioma))

# frequência de cada palavra em todos os dados de treino (pra achar as raras)
df = {}
for f in [g[0] for g in gerado] + [f for f, _ in treino()]:
    for w in palavras(f):
        df[w] = df.get(w, 0) + 1
Tp = [palavras(t) for t in T]
raras_teste = set()
for p in Tp:
    for w in p:
        if re.fullmatch(r"\d{2,}", w) or (len(w) >= 4 and df.get(w, 0) <= 2):
            raras_teste.add(w)

vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5)).fit([g[0] for g in gerado] + T)
sim = cosine_similarity(vec.transform([g[0] for g in gerado]), vec.transform(T))
limpo, fora = [], []
for i, (f, cat, idi) in enumerate(gerado):
    a = palavras(f)
    jac = max((len(a & b) / len(a | b) if a and b else 0) for b in Tp)
    rara = a & raras_teste
    if sim[i].max() >= 0.6 or jac >= 0.4 or rara:
        fora.append((f, T[sim[i].argmax()], round(float(sim[i].max()), 2), round(jac, 2), sorted(rara)))
    else:
        limpo.append((f, cat, idi))
with open(os.path.join(AQUI, "gerado_limpo.json"), "w", encoding="utf-8") as saida:
    json.dump(limpo, saida, ensure_ascii=False, indent=0)
print(f"geradas {len(gerado)} · ficaram {len(limpo)} · saíram por parecer teste {len(fora)}")
if "-v" in sys.argv:
    for x in fora:
        print("  ", x)
