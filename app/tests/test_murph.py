"""3.0.4: Murph, a ajudante local que decide a tarefa de cada pedido.

  - o modelo (modelos/murph.json) carrega e é rápido;
  - nas frases que ela nunca viu (idiomas/*.json "avaliacao" +
    tests/frases_classificador.py), acerta bem sozinha e no modo AUTO;
  - o treino dela não tem frase igual ou quase igual às de teste;
  - "de novo" sozinho não vira tarefa (sem contexto, é conversa);
  - TARS_MURPH=off ou sem o arquivo: as palavras-chave e os apps decidem
    (Endurance Neo: o Naive Bayes antigo saiu)."""

import json
import os
import sys
import tempfile
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, RAIZ)
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.join(RAIZ, "murph"))
os.environ.setdefault("XDG_CONFIG_HOME", tempfile.mkdtemp(prefix="opentars-config-"))
import _util  # noqa: E402,F401

import re  # noqa: E402
import unicodedata  # noqa: E402

import tars_murph as mm  # noqa: E402
from frases_classificador import FRASES  # noqa: E402
from tars_exemplos import EXEMPLOS  # noqa: E402

TESTE = list(FRASES)
for idioma in ("pt_BR", "en"):
    with open(os.path.join(RAIZ, "idiomas", f"{idioma}.json"), encoding="utf-8") as f:
        TESTE += [tuple(par) for par in json.load(f)["avaliacao"]]
# 4.0: a interface só tem pt e en, mas a Murph continua sendo medida nas
# frases de avaliação de es/fr/de de antes (guardadas aqui).
with open(os.path.join(AQUI, "avaliacao_outros_idiomas.json"), encoding="utf-8") as f:
    for pares in json.load(f).values():
        TESTE += [tuple(par) for par in pares]

# ------------------------------------------------------------
# 1. Carrega, 7 tarefas, rápido
# ------------------------------------------------------------
m = mm.Murph.carregar(mm.CAMINHO_PADRAO)
assert sorted(m.tarefas) == sorted(EXEMPLOS), m.tarefas
assert 0 < m.limite < 1
inicio = time.time()
for frase, _ in TESTE:
    m.classificar(frase)
ms = 1000 * (time.time() - inicio) / len(TESTE)
assert ms < 5, f"{ms:.2f} ms por pedido"
print(f"OK: murph.json carrega ({len(m.pesos)} características), {ms:.2f} ms por pedido")

# ------------------------------------------------------------
# 2. Treino separado do teste
# ------------------------------------------------------------
with open(os.path.join(RAIZ, "murph", "gerado_limpo.json"), encoding="utf-8") as f:
    GERADO = [(frase, cat) for frase, cat, _ in json.load(f)]


def _norm(frase):
    frase = unicodedata.normalize("NFKD", frase.lower().strip())
    return "".join(c for c in frase if not unicodedata.combining(c))


VAZIAS = {"a", "o", "e", "de", "do", "da", "um", "uma", "the", "a", "an", "to", "of", "my", "me", "meu", "minha",
          "pra", "para", "por", "favor", "please", "in", "no", "na", "em", "is", "it", "and"}


def palavras(frase):
    return set(re.findall(r"\w+", _norm(frase))) - VAZIAS


teste_norm = {_norm(f) for f, _ in TESTE}
assert not [f for f, _ in GERADO if _norm(f) in teste_norm], "frase de teste no treino da Murph"
conjuntos_teste = [palavras(f) for f, _ in TESTE]
quase = []
for frase, _ in GERADO:
    a = palavras(frase)
    for b in conjuntos_teste:
        if a and b and len(a & b) / len(a | b) >= 0.6:
            quase.append(frase)
            break
assert not quase, f"treino da Murph quase igual a frases de teste: {quase[:5]}"
print(f"OK: as {len(GERADO)} frases novas de treino não repetem nem quase repetem as {len(TESTE)} de teste")

# ------------------------------------------------------------
# 3. Sozinha, acerta bem
# ------------------------------------------------------------
acertos_murph = sum(m.classificar(f)[0] == c for f, c in TESTE)
assert acertos_murph / len(TESTE) >= 0.93, f"murph: {acertos_murph}/{len(TESTE)}"
print(f"OK: sozinha, a Murph acerta {acertos_murph}/{len(TESTE)}")

# Confiante, quase não erra
seguras = [(f, c) for f, c in TESTE if mm.classificar(f)["certo"]]
certas = sum(m.classificar(f)[0] == c for f, c in seguras)
assert len(seguras) >= len(TESTE) * 0.6 and certas / len(seguras) >= 0.97, (certas, len(seguras))
print(f"OK: segura em {len(seguras)}/{len(TESTE)}, acertou {certas} dessas")

# ------------------------------------------------------------
# 4. No modo AUTO (sem Ollama)
# ------------------------------------------------------------
import tars  # noqa: E402

tars.ollama_online = lambda: False
tars.listar_modelos_instalados = lambda forcar=False: set()
assert tars.murph.disponivel()
auto = sum(tars.decidir_tarefa(f).categoria == c for f, c in TESTE)
assert auto / len(TESTE) >= 0.95, f"AUTO com a Murph: {auto}/{len(TESTE)}"
d = tars.decidir_tarefa("desliga o bluetooth")
assert any(camada == "murph" for camada, _ in d.trilha), d.trilha
print(f"OK: modo AUTO com a Murph acerta {auto}/{len(TESTE)} sem Ollama (e aparece no --explicar)")

# ------------------------------------------------------------
# 5. "de novo": o sentido vem do pedido anterior
# ------------------------------------------------------------
tars._ultima_tarefa["ts"] = 0
assert tars.decidir_tarefa("de novo").categoria == "simples"
assert tars.decidir_tarefa("faz de novo").categoria == "simples"
assert tars.decidir_tarefa("de novo", anterior="acao").categoria == "acao"
assert tars.decidir_tarefa("again", anterior="visao").categoria == "visao"
assert tars.decidir_tarefa("pesquise capivaras gigantes no google").categoria == "busca"
print("OK: 'de novo' sozinho é conversa; depois de uma ação, repete a ação")

# ------------------------------------------------------------
# 6. Sem a Murph: palavras-chave e apps decidem
# ------------------------------------------------------------
mm.esquecer()
os.environ["TARS_MURPH"] = "off"
assert mm.preparar() is None and mm.classificar("abre o firefox") is None
r, quem = tars.classificar_local("abre o firefox")
assert r is None and quem == "murph", (quem, r)
assert tars.decidir_tarefa("pesquise capivaras gigantes no google").categoria == "busca"
assert tars.decidir_tarefa("oi, tudo bem?").categoria in ("simples", "geral")
del os.environ["TARS_MURPH"]
mm.esquecer()
assert mm.preparar("/nao/existe/murph.json") is None
mm.esquecer()
assert mm.preparar() is not None
print("OK: com TARS_MURPH=off ou sem o arquivo, as outras camadas decidem (sem Naive Bayes)")

# ------------------------------------------------------------
# 8. 3.0.5: helper Murph 1.0 no terminal; o qwen não é mais baixado
# ------------------------------------------------------------
import subprocess  # noqa: E402

assert mm.versao() == "1.0" and m.versao == "1.0"
saida = subprocess.run([sys.executable, os.path.join(RAIZ, "tars.py"), "--version"], capture_output=True, text=True,
                       env=dict(os.environ, TARS_MURPH="")).stdout
assert "helper Murph 1.0" in saida, saida
with open(os.path.join(RAIZ, "empacotamento", "setup.sh"), encoding="utf-8") as f:
    setup = f.read()
assert 'pull "$MODELO_AJUDANTE"' not in setup and "TARS_BAIXAR_AJUDANTE" not in setup
assert "helper_murph" in setup
print("OK: 'helper Murph 1.0' no --version; o setup não baixa mais o qwen2.5:0.5b")

print("\nTUDO OK.")
