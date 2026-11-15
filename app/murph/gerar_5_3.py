"""Frases novas para a Murph (14/11/2026, o método do Pi): um professor (o Gargantua 2.5 pelo Ollama de desenvolvimento; o beam:cloud ficou sem cota) escreve
pedidos por classe e idioma; o filtro tira as repetidas, as que já estão no treino e as parecidas com qualquer frase de prova
(avaliação dos idiomas, tests/frases_classificador.py e a série de rotas). Sai em gerado/5.3.json; o treino_5_3 junta.

    python3 murph/gerar_5_3.py            (gera e filtra)
    python3 murph/gerar_5_3.py --filtrar  (só refaz o filtro do que já foi gerado)
"""
import json
import os
import re
import sys
import unicodedata
import urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from dados import teste, treino  # noqa: E402
from serie_rotas import SERIE  # noqa: E402

PROFESSOR = os.environ.get("MURPH_PROFESSOR", "ProjectOpenTARS/Gargantua-2.5:latest")   # 14/11: o beam:cloud ficou sem cota (402)
OLLAMA = "http://127.0.0.1:11434/api/chat"
CLASSES = {
    "visao": "the user wants the assistant to LOOK AT THE SCREEN: describe what is on screen, read a popup or error shown, or click/drag something visible (a button, icon, tab)",
    "codigo": "the user wants PROGRAMMING help: write, fix, explain or convert code, scripts, regex, SQL, APIs",
    "tecnico": "the user has a COMPUTER/SYSTEM problem or terminal question: Linux, Windows or macOS settings, drivers, packages, wifi, disks, services, commands",
    "acao": "the user wants the assistant to DO something on the computer now: open/close an app, files and folders, volume, brightness, dark mode, lock, shutdown, move or delete files",
    "busca": "the user needs CURRENT information from the internet: news, prices, weather, sports results, release dates, store hours, or explicitly asks to search the web or YouTube",
    "simples": "SMALL TALK with the assistant itself: greetings, thanks, goodbyes, how are you, who are you, what is your name, what can you do, compliments, the user's mood",
    "geral": "GENERAL knowledge or writing that does not change over time: explain a concept, history, science, write a poem, story, email or message, jokes, advice, ideas, summaries",
}
IDIOMAS = {"pt_BR": ("Brazilian Portuguese", 60), "en": ("English", 60), "es": ("Spanish", 20), "fr": ("French", 20), "de": ("German", 20)}
SAIDA = os.path.join(AQUI, "gerado", "5.3.json")
BRUTO = os.path.join(AQUI, "gerado", "5.3-bruto.json")


def pedir(classe, idioma, n):
    nome, _ = IDIOMAS[idioma]
    prompt = (f"Write {n} different messages a real person types to an AI assistant on their desktop computer, where {CLASSES[classe]}. "
              f"Language: {nome}. Vary length (2 to 20 words), tone, slang, missing accents and small typos, like real chat. "
              "Do not number them. One message per line. No quotes, no explanations.")
    corpo = {"model": PROFESSOR, "stream": False, "messages": [{"role": "user", "content": prompt}], "options": {"temperature": 1.0}}
    pedido = urllib.request.Request(OLLAMA, json.dumps(corpo).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(pedido, timeout=300) as r:
        texto = json.loads(r.read())["message"]["content"]
    linhas = [re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", l).strip().strip('"').strip() for l in texto.splitlines()]
    return [l for l in linhas if 2 <= len(l.split()) <= 30]


def normal(f):
    f = unicodedata.normalize("NFKD", f.lower())
    return re.sub(r"[^\w\s]", " ", "".join(c for c in f if not unicodedata.combining(c))).split()


def parecida(a, b):
    a, b = set(a), set(b)
    return bool(a and b) and len(a & b) / len(a | b) >= 0.6


def filtrar(bruto):
    av, ex = teste()
    provas = [normal(f) for f, *_ in av + ex] + [normal(f) for f, _ in SERIE]
    for item in json.load(open(os.path.join(AQUI, "filtro_traducoes_teste.json"), encoding="utf-8")):
        provas += [normal(item[k]) for k in ("pt_BR", "en", "es", "fr", "de") if item.get(k)]
    vistos = {" ".join(normal(f)) for f, _ in treino()}
    saida, fora = [], 0
    for f, classe, idioma in bruto:
        n = normal(f)
        chave = " ".join(n)
        if not chave or chave in vistos or any(parecida(n, p) for p in provas):
            fora += 1
            continue
        vistos.add(chave)
        saida.append([f, classe, idioma])
    print(f"{len(saida)} frases novas ({fora} fora: repetidas ou parecidas com prova)")
    return saida


def main():
    if "--filtrar" not in sys.argv:
        bruto = []
        for classe in CLASSES:
            for idioma, (_, n) in IDIOMAS.items():
                try:
                    achadas = pedir(classe, idioma, n)
                except Exception as e:  # noqa: BLE001
                    print("falhou", classe, idioma, e, flush=True)
                    continue
                bruto += [[f, classe, idioma] for f in achadas]
                print(classe, idioma, len(achadas), flush=True)
        json.dump(bruto, open(BRUTO, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    bruto = json.load(open(BRUTO, encoding="utf-8"))
    json.dump(filtrar(bruto), open(SAIDA, "w", encoding="utf-8"), ensure_ascii=False, indent=0)


if __name__ == "__main__":
    main()
