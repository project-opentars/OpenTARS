"""Murph x classificador atual, em frases que NENHUM dos dois viu no treino
AVISO (4.0 Endurance Neo): este script de desenvolvimento usa o tars_classificador.py
(Naive Bayes), que saiu do openTARS. Pra rodar, pegue esse arquivo da 4.0 Endurance.
(idiomas/*.json "avaliacao" + tests/frases_classificador.py).

    python3 murph/comparar.py

Mede, sem Ollama:
  1. cada classificador sozinho (NB atual, NB com os dados novos, Murph);
  2. o modo AUTO inteiro (palavras-chave + estrutura + classificador);
  3. o AUTO com um ajudante PERFEITO (acerta sempre que é chamado): o
     máximo que o sistema conseguiria com o qwen2.5:0.5b, e quantas vezes
     ele precisaria ser chamado (cada chamada: 150–500 ms).
"""
import json
import os
import subprocess
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from dados import teste, RAIZ  # noqa: E402


def sozinhos():
    sys.path.insert(0, RAIZ)
    import tars_classificador as nbm
    import tars_murph as mm
    murph = mm.Murph.carregar(mm.CAMINHO_PADRAO)
    ger = [(f, c) for f, c, _ in json.load(open(os.path.join(AQUI, "gerado_limpo.json"), encoding="utf-8"))]
    nb_atual = nbm.Modelo(nbm.amostras_padrao())
    nb_mais = nbm.Modelo(nbm.amostras_padrao(ger))
    av, ex = teste()
    for nome, fn in (("NB atual", lambda f: nb_atual.classificar(f)[0]),
                     ("NB + dados novos", lambda f: nb_mais.classificar(f)[0]),
                     ("Murph", lambda f: murph.classificar(f)[0])):
        ok = sum(fn(f) == c for f, c, _ in av + ex)
        print(f"  {nome:<18} {ok}/{len(av + ex)} = {100 * ok / len(av + ex):.1f}%")
    print("\n  Erros da Murph sozinha:")
    for f, c, i in av + ex:
        r, p = murph.classificar(f)
        if r != c:
            print(f"    [{i}] {f} | esperado {c} | murph {r} ({p:.2f})")


def modo_auto(ajudante_perfeito):
    """Roda num processo separado (TARS_MURPH vale no carregamento)."""
    os.environ.setdefault("XDG_CONFIG_HOME", tempfile.mkdtemp())
    sys.path.insert(0, os.path.join(RAIZ, "tests"))
    sys.path.insert(0, RAIZ)
    import _util  # noqa: F401
    import tars
    av, ex = teste()
    gabarito = {f: c for f, c, _ in av + ex}
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
            chamadas.append(texto)
            return None
    tars._classificar_com_ia = ajudante
    ok = sum(tars.decidir_tarefa(f).categoria == c for f, c, _ in av + ex)
    quem = "Murph" if tars.murph.disponivel() else "NB atual"
    extra = f" · chamaria o ajudante {len(chamadas)}x" if ajudante_perfeito else ""
    print(f"  {quem:<9} {ok}/{len(av + ex)} = {100 * ok / len(av + ex):.1f}%{extra}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--auto":
        modo_auto(sys.argv[2] == "perfeito")
        sys.exit(0)
    print("1. Classificador sozinho")
    sozinhos()
    for titulo, arg in (("2. Modo AUTO sem Ollama", "sem"), ("3. Modo AUTO com ajudante perfeito", "perfeito")):
        print(f"\n{titulo}")
        for murph_ligada in ("off", "on"):
            env = dict(os.environ, TARS_MURPH="off" if murph_ligada == "off" else "")
            subprocess.run([sys.executable, __file__, "--auto", arg], env=env, check=True)
