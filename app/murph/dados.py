"""Dados da Murph ajudante: treino = exemplos do openTARS; teste = frases
que o openTARS guarda SEPARADAS pra avaliação (nenhum classificador treina nelas)."""
import json, os, sys
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ); sys.path.insert(0, os.path.join(RAIZ, "tests")); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tars_exemplos import EXEMPLOS
from frases_classificador import FRASES

TAREFAS = ["visao", "codigo", "tecnico", "acao", "busca", "simples", "geral"]
IDIOMAS = ["pt_BR", "en", "es", "fr", "de"]

def treino():
    return [(f, cat) for cat, lista in EXEMPLOS.items() for f in lista]

def teste():
    avaliacao = []
    # 4.0: es/fr/de saíram da interface; as frases de avaliação deles ficam em tests/
    outros = json.load(open(os.path.join(RAIZ, "tests", "avaliacao_outros_idiomas.json"), encoding="utf-8"))
    for idioma in IDIOMAS:
        arquivo = os.path.join(RAIZ, "idiomas", f"{idioma}.json")
        pares = json.load(open(arquivo, encoding="utf-8"))["avaliacao"] if os.path.exists(arquivo) else outros[idioma]
        avaliacao += [(f, c, idioma) for f, c in pares]
    extra = [(f, c, "misto") for f, c in FRASES]
    return avaliacao, extra
