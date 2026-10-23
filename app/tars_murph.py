"""Murph (3.0.4): a ajudante que decide a TAREFA de cada pedido.

Regressão logística (softmax) sobre pedaços de palavra (2 a 5 letras),
palavras e pares de palavras, com peso TF-IDF. Diferente do Naive Bayes
atual, os pesos são aprendidos DISCRIMINANDO as tarefas (o que separa
"desliga o bluetooth" de "o bluetooth não funciona"), e as palavras curtas
("isso", "that", "aí") contam: elas são pista de visão.

Treinada com os exemplos do openTARS mais ~2.300 frases novas escritas
por um modelo grande nos 5 idiomas (a receita do TinyStories: o modelo
grande escreve, o pequeno aprende). Frases parecidas com as de avaliação
ficaram de fora do treino.

Rodar só precisa de Python puro (~0,2 ms por pedido). O treino usa
scikit-learn e fica em murph/treinar_murph.py (não vai no pacote).

Entrou no lugar do Naive Bayes (tars_classificador, removido na Endurance Neo) como camada 4 da
escolha da tarefa; sem o modelos/murph.json, o openTARS volta pro NB.
"""

import json
import math
import os
import re
import threading
import unicodedata

VERSAO_FORMATO = 1
VERSAO = "1.0"          # helper Murph 1.0 (3.0.5): mostrado na janela e no terminal
N_GRAMAS = (2, 3, 4, 5)
_RE_PALAVRA = re.compile(r"\w+", re.UNICODE)


def normalizar(texto):
    s = unicodedata.normalize("NFKD", texto or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", s.lower().replace("ß", "ss")).strip()


def contagens(texto):
    """{característica: contagem} (antes do TF-IDF)."""
    t = normalizar(texto)
    palavras = _RE_PALAVRA.findall(t)
    feats = {}
    for w in palavras:
        feats["w:" + w] = feats.get("w:" + w, 0) + 1
        marcada = f" {w} "
        for n in N_GRAMAS:
            for i in range(max(0, len(marcada) - n + 1)):
                k = "c:" + marcada[i:i + n]
                feats[k] = feats.get(k, 0) + 1
    for a, b in zip(palavras, palavras[1:]):
        k = f"b:{a}_{b}"
        feats[k] = feats.get(k, 0) + 1
    n = len(palavras)
    feats["#n" + ("1" if n <= 1 else "2" if n <= 3 else "6" if n <= 6 else "+")] = 1
    return feats


def cobertura(texto, idf):
    """Quanto do texto (pedaços de palavra e palavras) o modelo já viu no
    treino, de 0 a 1. "asdfgh" ou uma língua que ela não conhece: baixo."""
    c = contagens(texto)
    total = sum(n for k, n in c.items() if not k.startswith("#"))
    if not total:
        return 0.0
    return sum(n for k, n in c.items() if not k.startswith("#") and k in idf) / total


def vetor(texto, idf):
    """Características com TF sublinear x IDF, normalizadas (L2).
    Só entra o que o modelo conhece (idf)."""
    v = {}
    for k, c in contagens(texto).items():
        peso = idf.get(k)
        if peso is not None:
            v[k] = (1.0 + math.log(c)) * peso
    norma = math.sqrt(sum(x * x for x in v.values())) or 1.0
    return {k: x / norma for k, x in v.items()}


class Murph:
    def __init__(self, dados):
        self.tarefas = dados["tarefas"]
        self.idf = dados["idf"]
        self.vies = dados["vies"]
        # pesos: {característica: [peso por tarefa]}
        self.pesos = dados["pesos"]
        self.limite = float(dados.get("limite", 0.1))
        self.cobertura_minima = float(dados.get("cobertura_minima", 0.0))
        self.versao = str(dados.get("versao") or VERSAO)

    @classmethod
    def carregar(cls, caminho):
        with open(caminho, encoding="utf-8") as f:
            dados = json.load(f)
        if dados.get("formato") != VERSAO_FORMATO:
            raise ValueError("formato de modelo desconhecido")
        return cls(dados)

    def probabilidades(self, texto):
        """[(probabilidade, tarefa)] da mais provável pra menos."""
        notas = list(self.vies)
        for k, x in vetor(texto, self.idf).items():
            linha = self.pesos.get(k)
            if linha:
                for i, w in enumerate(linha):
                    notas[i] += x * w
        topo = max(notas)
        exps = [math.exp(n - topo) for n in notas]
        soma = sum(exps)
        return sorted(((e / soma, t) for e, t in zip(exps, self.tarefas)), reverse=True)

    def classificar(self, texto):
        """(tarefa, confiança 0..1)."""
        p = self.probabilidades(texto)
        return p[0][1], p[0][0]


# ------------------------------------------------------------
# Uso no openTARS (mesmo formato do antigo tars_classificador.classificar)
# ------------------------------------------------------------

CAMINHO_PADRAO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "modelos", "murph.json")
_estado = {"modelo": None, "falhou": False}
_trava = threading.Lock()


def preparar(caminho=None):
    """A Murph carregada (~0,3 s na primeira vez) ou None se o arquivo não
    existe / está estragado (aí quem chama usa o Naive Bayes)."""
    if _estado["modelo"] is not None or _estado["falhou"]:
        return _estado["modelo"]
    if os.environ.get("TARS_MURPH", "").lower() in ("0", "off", "no", "nao", "não"):
        return None  # TARS_MURPH=off: usa o Naive Bayes (pra comparar)
    with _trava:
        if _estado["modelo"] is None and not _estado["falhou"]:
            try:
                _estado["modelo"] = Murph.carregar(caminho or os.environ.get("TARS_MURPH_ARQUIVO") or CAMINHO_PADRAO)
            except Exception:  # arquivo faltando ou estragado: volta pro Naive Bayes
                _estado["falhou"] = True
    return _estado["modelo"]


def disponivel():
    return preparar() is not None


def versao():
    """"1.0" (a versão gravada no modelo, ou a deste arquivo)."""
    m = preparar()
    return getattr(m, "versao", None) or VERSAO


def classificar(texto):
    """{"notas": [(nota, tarefa)...], "margem": folga da 1ª, "certo",
    "limite"} — igual ao antigo tars_classificador, pra entrar no mesmo lugar.
    A nota é a probabilidade menos a da 1ª (a 1ª fica com 0)."""
    m = preparar()
    if m is None or not normalizar(texto):
        return None
    p = m.probabilidades(texto)
    topo = p[0][0]
    folga = topo - p[1][0] if len(p) > 1 else 1.0
    limite = m.limite
    # Segura = folga grande E o pedido parece com o que ela aprendeu. Texto
    # estranho (letras aleatórias, outra língua) fica "em dúvida" mesmo com
    # folga: aí as camadas seguintes (apps, contexto) decidem.
    visto = cobertura(texto, m.idf)
    return {"notas": [(prob - topo, t) for prob, t in p], "margem": folga,
            "certo": folga >= limite and visto >= m.cobertura_minima, "limite": limite,
            "probabilidade": topo, "cobertura": visto}


def esquecer():
    """Só pros testes."""
    _estado["modelo"] = None
    _estado["falhou"] = False
