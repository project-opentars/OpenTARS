"""Teste CEGO: 280 pedidos "bagunçados" (erros de digitação, gíria, sem
AVISO (4.0 Endurance Neo): este script de desenvolvimento usa o tars_classificador.py
(Naive Bayes), que saiu do openTARS. Pra rodar, pegue esse arquivo da 4.0 Endurance.
acento, bem curtos ou compridos) escritos por um agente que não viu nada
do openTARS: nem o treino, nem o teste, nem a Murph. Rodado UMA vez, com
o modelo já congelado.

    python3 murph/teste_cego.py

Antes de medir, tira do teste qualquer pedido parecido com o TREINO da
Murph (senão a nota dela sairia inflada); a mesma lista vale pros dois.
"""
import json
import os
import subprocess
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from dados import treino, RAIZ  # noqa: E402

ARQUIVO = os.path.join(AQUI, "teste_cego.json")


def frases_validas():
    sys.path.insert(0, RAIZ)
    import tars_classificador as cl
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    todas = [tuple(x) for x in json.load(open(ARQUIVO, encoding="utf-8"))]
    ger = [f for f, _, _ in json.load(open(os.path.join(AQUI, "gerado_limpo.json"), encoding="utf-8"))]
    base = [f for f, _ in treino()] + ger

    def palavras(f):
        return set(cl.tokens(cl.normalizar(f))) - cl.VAZIAS
    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5)).fit(base + [f for f, _, _ in todas])
    sim = cosine_similarity(vec.transform([f for f, _, _ in todas]), vec.transform(base))
    bp = [palavras(b) for b in base]
    boas = []
    for i, (f, c, idi) in enumerate(todas):
        a = palavras(f)
        jac = max((len(a & b) / len(a | b) if a and b else 0) for b in bp)
        if sim[i].max() < 0.6 and jac < 0.4:
            boas.append((f, c, idi))
    return todas, boas


def modo_auto(ajudante_perfeito, frases):
    os.environ.setdefault("XDG_CONFIG_HOME", tempfile.mkdtemp())
    sys.path.insert(0, os.path.join(RAIZ, "tests"))
    sys.path.insert(0, RAIZ)
    import _util  # noqa: F401
    import tars
    gabarito = {f: c for f, c, _ in frases}
    chamadas = []
    tars.ollama_online = lambda: False
    tars.modelo_embedding = lambda *a, **k: None
    if ajudante_perfeito:
        tars.listar_modelos_instalados = lambda forcar=False: {tars.MODELO_AJUDANTE}
        tars.saude_ajudante.confiavel = lambda *a, **k: True

        def ajudante(texto, finalistas=None, anterior=None, pistas=None):
            chamadas.append(texto)
            return gabarito[texto] if not finalistas or gabarito[texto] in finalistas else finalistas[0]
    else:
        tars.listar_modelos_instalados = lambda forcar=False: set()

        def ajudante(texto, finalistas=None, anterior=None, pistas=None):
            return None
    tars._classificar_com_ia = ajudante
    certas = [tars.decidir_tarefa(f).categoria == c for f, c, _ in frases]
    return certas, len(chamadas)


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--auto":
        frases = json.loads(sys.stdin.read())
        certas, n = modo_auto(sys.argv[2] == "perfeito", frases)
        print(json.dumps({"certas": certas, "chamadas": n}))
        sys.exit(0)

    todas, frases = frases_validas()
    print(f"{len(todas)} pedidos; {len(todas) - len(frases)} saíram por parecer com o treino; valem {len(frases)}\n")
    sys.path.insert(0, RAIZ)
    import tars_classificador as nbm
    import tars_murph as mm
    murph = mm.Murph.carregar(mm.CAMINHO_PADRAO)
    nb = nbm.Modelo(nbm.amostras_padrao())
    n = len(frases)

    def placar(nome, a, b):
        ga = sum(x and not y for x, y in zip(a, b))
        gb = sum(y and not x for x, y in zip(a, b))
        print(f"  NB atual {sum(a)}/{n} = {100 * sum(a) / n:.1f}%  ·  Murph {sum(b)}/{n} = {100 * sum(b) / n:.1f}%"
              f"   (só a Murph acertou: {gb} · só o NB acertou: {ga})")

    print("1. Classificador sozinho")
    a = [nb.classificar(f)[0] == c for f, c, _ in frases]
    b = [murph.classificar(f)[0] == c for f, c, _ in frases]
    placar("sozinho", a, b)
    seguras = [(f, c) for f, c, _ in frases if mm.classificar(f)["certo"]]
    ok = sum(murph.classificar(f)[0] == c for f, c in seguras)
    print(f"  Murph segura em {len(seguras)}/{n}; acertou {ok} dessas ({100 * ok / max(1, len(seguras)):.1f}%)")

    for titulo, modo in (("2. Modo AUTO sem Ollama", "sem"), ("3. Modo AUTO com ajudante perfeito", "perfeito")):
        print(f"\n{titulo}")
        res = {}
        for ligada in ("off", "on"):
            env = dict(os.environ, TARS_MURPH="off" if ligada == "off" else "")
            saida = subprocess.run([sys.executable, __file__, "--auto", modo], env=env, check=True,
                                   input=json.dumps(frases), capture_output=True, text=True).stdout
            res[ligada] = json.loads(saida.strip().splitlines()[-1])
        placar(titulo, res["off"]["certas"], res["on"]["certas"])
        if modo == "perfeito":
            print(f"  chamadas ao ajudante: NB {res['off']['chamadas']} · Murph {res['on']['chamadas']}")

    print("\nPor idioma (sozinhos): ", end="")
    for idi in ("pt_BR", "en", "es", "fr", "de"):
        sub = [(f, c) for f, c, i in frases if i == idi]
        print(f"{idi} NB {sum(nb.classificar(f)[0] == c for f, c in sub)}/{len(sub)} "
              f"Murph {sum(murph.classificar(f)[0] == c for f, c in sub)}/{len(sub)}", end=" · ")
    print("\n\nErros da Murph sozinha:")
    for f, c, i in frases:
        r, p = murph.classificar(f)
        if r != c:
            print(f"  [{i}] {f} | esperado {c} | murph {r} ({p:.2f}) | NB {nb.classificar(f)[0]}")
