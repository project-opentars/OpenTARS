"""Escolha da tarefa em camadas (2.9; Neo: só camadas instantâneas, sem IA).

Cada camada olha o pedido de um jeito e dá VOTOS (categoria -> peso):

  1. palavras-chave  verbo/alvo explícito ("feche", "pesquise")     peso 3
                     só o assunto ("pasta", "erro")                  peso 1,5
  2. contexto        continuação do pedido anterior ("de novo")      peso 2,5
  3. estrutura       bloco de código, erro, comando, link, pergunta  peso 1–6
  4. Murph           a helper treinada com os exemplos               peso 2,5–3,5 / 1
                     (tars_murph.py; instantânea, sem Ollama)
     -> se as camadas 1–4 já concordam, decide aqui
  5. apps            cita um app instalado ("spotify", "gimp")       peso 1
     -> senão, a mais votada (ou, sem voto, pelo tamanho do pedido)
  6. coerência       corrige resultados sem sentido ("simples" pra um
                     pedido de 20 palavras)

Antes de responder, mais duas análises que mudam COMO a IA trabalha:

  - várias etapas ("abre o claude E faz uma pergunta"): a IA pensa antes,
    ganha um lembrete de fazer tudo e um modelo maior;
  - histórico: cada modelo tem, por tarefa, os acertos e falhas das
    últimas vezes NESTE PC. Quem falha muito numa tarefa vai pro fim da
    fila dela (e volta se melhorar).

Este arquivo tem as partes que não dependem do Ollama nem do sistema
(regras de texto e a combinação dos votos), pra poder testar isoladas."""

import json
import os
import re
import threading
from collections import Counter, deque
from dataclasses import dataclass, field
from pathlib import Path

PESO_PALAVRA = 3.0
PESO_PALAVRA_FRACA = 1.5   # só o assunto ("pasta", "erro") ou ordem dentro de pergunta
# Pedido curto que COMEÇA com a ordem ("abra o vs code", "feche o terminal"):
# é ação mesmo quando o alvo soa técnico ("code", "terminal").
PESO_ORDEM_NO_INICIO = 4.5
LIMITE_PALAVRAS_ORDEM = 6
PESO_CONTEXTO = 2.5
PESO_APP = 1.0
# 2.9.1: confiante, o classificador local acerta ~97% nas frases de teste
# (as palavras-chave, ~90%). O peso cresce com a folga: logo acima do
# limite vale 2,5 (menos que um verbo explícito: "abra o terminal" é ação,
# não Linux); com o dobro da folga, 3,5 (vence uma palavra-chave sozinha,
# mas não palavra-chave + estrutura concordando).
PESO_LOCAL_CERTO = 3.5
PESO_LOCAL_CERTO_MIN = 2.5
PESO_LOCAL_DUVIDA = 1.0


def peso_local(folga, limite):
    """Peso do voto do classificador local quando ele está seguro."""
    extra = min(1.0, max(0.0, (folga - limite) / limite)) if limite > 0 else 1.0
    return PESO_LOCAL_CERTO_MIN + (PESO_LOCAL_CERTO - PESO_LOCAL_CERTO_MIN) * extra

# Decide sem o ajudante: a 1ª tarefa soma pelo menos isso E fica pelo menos
# MARGEM_DECISAO na frente da 2ª.
MINIMO_DECISAO = 2.5
MARGEM_DECISAO = 1.5
MAX_FINALISTAS = 3

# Continuação curta do pedido anterior ("agora clica no =", "de novo",
# "and then close it"). Normalizado (sem acento, minúsculo).
_RE_CONTINUACAO = re.compile(
    r"^(e |agora|depois|entao|de novo|denovo|mais uma vez|tambem|outra vez|isso|faz isso|"
    r"and |now|then|again|also|do it|do that|same |"
    r"y |ahora|despues|otra vez|tambien|"
    r"et |maintenant|puis|encore|aussi|"
    r"und |jetzt|dann|nochmal|auch)\b"
)
LIMITE_PALAVRAS_CONTINUACAO = 7
VALIDADE_CONTEXTO_SEG = 300

_RE_BLOCO_CODIGO = re.compile(r"```|^\s*(def |class |import |from \S+ import |function |const |let |#include|public static)", re.M)
_RE_ERRO_CODIGO = re.compile(r"(traceback \(most recent call last\)|syntaxerror|typeerror|nameerror|"
                             r"indentationerror|undefined is not|segmentation fault|nullpointer)", re.I)
_RE_ARQUIVO_CODIGO = re.compile(r"\b\w+\.(py|js|ts|jsx|tsx|java|cpp|c|h|rs|go|rb|php|kt|swift)\b", re.I)
_RE_COMANDO = re.compile(r"(^|\s)(sudo |apt |apt-get |dpkg |systemctl |journalctl |flatpak |snap |pip |"
                         r"chmod |chown |grep |ls -|cd /|/etc/|/usr/|/var/|\.sh\b|\.deb\b|nvidia-smi|"
                         r"e: |error: |erro: )", re.I)
_RE_URL = re.compile(r"(https?://|www\.)\S+|\b[a-z0-9-]+\.(com|com\.br|org|net|io|dev|br|gov)\b", re.I)
_RE_PERGUNTA = re.compile(r"^(o que|oque|qual|quais|quem|quando|por que|porque|como funciona|"
                          r"what|who|when|why|how does|which|que es|quien|cuando|por que|"
                          r"qu'est|qui |quand|pourquoi|was ist|wer |wann|warum)\b")

# Cumprimento ou agradecimento no começo de um pedido curto ("e aí, como
# você está hoje?"): sem isso, o "hoje" puxava pra busca.
_RE_CUMPRIMENTO = re.compile(
    r"^(oi+|ola|opa|e ai|eai|fala|salve|bom dia|boa tarde|boa noite|valeu|obrigad[oa]|brigad[oa]|"
    r"hey|hi|hello|yo|good (morning|afternoon|evening|night)|thanks|thank you|thx|"
    r"hola|buenas|buenos dias|buenas (tardes|noches)|gracias|"
    r"salut|bonjour|bonsoir|coucou|merci|"
    r"hallo|servus|moin|guten (morgen|tag|abend)|danke)\b"
)
LIMITE_PALAVRAS_CUMPRIMENTO = 8

# Perguntar como o assistente está é papo, mesmo com "hoje" ("e aí, como
# você está hoje?" ia pra busca por causa do "hoje").
_RE_PAPO = re.compile(
    r"\b(como (voce|vc|ce|tu) (esta|ta|vai|anda)|tudo (bem|bom|certo|tranquilo|joia)|"
    r"how are you|how('s| is) it going|how are things|what'?s up|"
    r"como estas|como te va|que tal|todo bien|"
    r"comment (vas-tu|allez-vous|ca va)|ca va|"
    r"wie geht'?s|wie geht es (dir|ihnen)|alles (gut|klar))\b"
)


@dataclass
class Decisao:
    categoria: str
    via: str                                   # camadas que decidiram
    votos: dict = field(default_factory=dict)  # categoria -> soma
    finalistas: list = field(default_factory=list)
    multi_etapas: bool = False                 # "faz X e depois Y"
    trilha: list = field(default_factory=list)  # (camada, o que concluiu): o raciocínio

    def resumo(self):
        votos = ", ".join(f"{c}={v:.1f}" for c, v in sorted(self.votos.items(), key=lambda x: -x[1]))
        return f"{self.categoria} via {self.via} [{votos}]"


class Votos:
    def __init__(self):
        self.soma = {}
        self.origem = {}   # categoria -> [camadas]

    def dar(self, categoria, peso, camada):
        if not categoria or peso <= 0:
            return
        self.soma[categoria] = self.soma.get(categoria, 0.0) + peso
        self.origem.setdefault(categoria, []).append(camada)

    def ranking(self):
        return sorted(self.soma.items(), key=lambda x: -x[1])

    def decisao_clara(self):
        """(categoria, via) se a 1ª ganha com folga, senão None."""
        r = self.ranking()
        if not r:
            return None
        primeira, nota = r[0]
        segunda = r[1][1] if len(r) > 1 else 0.0
        if nota >= MINIMO_DECISAO and nota - segunda >= MARGEM_DECISAO:
            return primeira, "+".join(self.origem[primeira])
        return None

    def finalistas(self, validas):
        r = [c for c, v in self.ranking() if v > 0 and c in validas][:MAX_FINALISTAS]
        return r


def eh_pergunta(texto_normalizado):
    return bool(_RE_PERGUNTA.match(texto_normalizado))


def eh_cumprimento(texto_normalizado):
    return (len(texto_normalizado.split()) <= LIMITE_PALAVRAS_CUMPRIMENTO
            and bool(_RE_CUMPRIMENTO.match(texto_normalizado)))


# Só "de novo"/"again" e nada mais: não diz tarefa nenhuma. Sem o pedido
# anterior, o classificador (que só vê a frase) não deve decidir por ela
# (3.0.4: a Murph ligava "novo" a busca, de "o que tem de novo").
_RE_SO_REPETICAO = re.compile(
    r"^(faz |faca |do it |do that |hazlo |refais-le |refais |mach das |mach es )?"
    r"(de novo|denovo|mais uma vez|outra vez|again|one more time|otra vez|una vez mas|"
    r"encore|encore une fois|nochmal|noch einmal)"
    r"( (por favor|pf|pls|please|bitte|s'il te plait))?[\s.!?]*$")


def so_repeticao(texto_normalizado):
    return bool(_RE_SO_REPETICAO.match(texto_normalizado.strip()))


# 18/10: "use the built-in tool", "faz de verdade", "usa o buscador", "try again": a frase não diz a tarefa, ela manda FAZER
# o pedido anterior. Classificar só a frase dava qualquer coisa (o Lite abriu o "app" google = Chrome e disse que tinha
# pesquisado). Com o pedido anterior, a decisão e a IA sabem do que se trata.
_RE_RETOMADA = re.compile(
    r"^(?:(?:ok|okay|ta|entao|agora|now|so|then|please|por favor|pf|mas|but|no|nao)[,]? )*"
    r"(?:(?:use|usa|usar|utiliza|utilize|uses|using)(?: (?:the|your|a|o|as|os|uma|um|sua|seu|teu|tua))?"
    r"(?: [\w-]+){0,3} (?:tool|tools|ferramenta|ferramentas|search engine|search|buscador|busca|pesquisa|navegador|browser)"
    r"|(?:(?:actually|really) )?do it(?: for real| now| properly| yourself)?"
    r"|(?:faz|faca|faz isso|faca isso|fazer)(?: isso)?(?: de verdade| direito| agora| voce mesmo)+"
    r"|(?:pesquisa|procura|busca|search|look it up|google it)(?: isso| it| that)?(?: de verdade| for real| online| na internet| on the internet| no google| on google)+"
    r"|(?:tenta|tente|try)(?: de novo| again| outra vez)+)"
    r"(?: (?:por favor|pf|please|pls))?[\s.!?]*$")


def eh_retomada(texto_normalizado):
    """A frase só manda fazer (de verdade, com a ferramenta) o pedido anterior. Inclui o "de novo"/"again" de so_repeticao."""
    t = " ".join(texto_normalizado.replace(",", " ").split())
    return 0 < len(t.split()) <= 9 and (bool(_RE_RETOMADA.match(t)) or so_repeticao(t))


# 18/10: o Gargantua 2 responde em português a pedido em inglês. Só o inglês precisa de lembrete (o desvio é sempre para o português).
_PALAVRAS_EN = frozenset("the is are was what who whom how why when where open search please use and to of for can you tell my it "
                         "in on with about latest give show find write explain does do did this that your joke name price weather news what's whats "
                         "today tomorrow much many best list files file folder close launch play take screenshot from into there here "
                         "which should would could will have has been".split())
_PALAVRAS_PT = frozenset("o os as de do da dos das que para pra um uma abre abra pesquisa pesquise faz faca quem como qual quais "
                         "com no na nos nas por meu minha isso pro voce mim qual onde quando porque pelo pela esse essa".split())


def pedido_em_ingles(texto_normalizado):
    """True quando o pedido é claramente em inglês (pelo menos 2 palavras de inglês e mais que as de português)."""
    palavras = re.findall(r"[a-z']+", texto_normalizado)
    en = sum(1 for w in palavras if w in _PALAVRAS_EN)
    pt = sum(1 for w in palavras if w in _PALAVRAS_PT)
    return en >= 2 and en > pt


def eh_continuacao(texto_normalizado):
    palavras = texto_normalizado.split()
    # "e aí, tudo bem?" começa com "e " mas é cumprimento, não "e (depois)..."
    return (0 < len(palavras) <= LIMITE_PALAVRAS_CONTINUACAO and bool(_RE_CONTINUACAO.match(texto_normalizado))
            and not eh_cumprimento(texto_normalizado))


def votos_estruturais(texto, texto_normalizado, votos):
    """Camada 3: o FORMATO do pedido diz muito, sem IA nenhuma."""
    if _RE_BLOCO_CODIGO.search(texto) or _RE_ERRO_CODIGO.search(texto):
        # Código colado ou um erro de programa: inconfundível, vence as
        # palavras soltas que aparecem dentro dele ("File", "open"...).
        votos.dar("codigo", 6.0, "estrutura")
    elif _RE_ARQUIVO_CODIGO.search(texto):
        votos.dar("codigo", 1.5, "estrutura")
    if _RE_COMANDO.search(texto):
        votos.dar("tecnico", 2.0, "estrutura")
    if _RE_URL.search(texto):
        # Link sozinho ("abre github.com") é abrir site; link + texto, busca.
        votos.dar("simples" if len(texto_normalizado.split()) <= 4 else "busca", 1.5, "estrutura")
    palavras = len(texto_normalizado.split())
    if _RE_PERGUNTA.match(texto_normalizado) and palavras >= 4:
        votos.dar("geral", 1.0, "estrutura")
    if eh_cumprimento(texto_normalizado):
        votos.dar("simples", 2.0, "estrutura")
    if palavras <= LIMITE_PALAVRAS_CUMPRIMENTO and _RE_PAPO.search(texto_normalizado):
        votos.dar("simples", 2.0, "estrutura")


def coerencia(categoria, texto_normalizado, votos):
    """Camada 7: resultado sem sentido vira o mais provável que faça sentido."""
    palavras = len(texto_normalizado.split())
    if categoria == "simples" and palavras > 12:
        alternativa = next((c for c, _ in votos.ranking() if c != "simples"), "geral")
        return alternativa, "coerencia"
    return categoria, None


# ------------------------------------------------------------
# Saúde do ajudante
# ------------------------------------------------------------

# ------------------------------------------------------------
# Várias etapas
# ------------------------------------------------------------

# Onde um pedido se divide em partes (já normalizado: sem acento, minúsculo).
_RE_CONECTORES = re.compile(
    r"\s*(?:;|,?\s+e depois\s+|,?\s+depois\s+|,?\s+e entao\s+|,?\s+em seguida\s+|,\s*e\s+|\s+e\s+|"
    r",?\s+and then\s+|,?\s+then\s+|,?\s+after that\s+|,\s*and\s+|\s+and\s+|"
    r",?\s+y luego\s+|,?\s+y despues\s+|,?\s+luego\s+|\s+y\s+|"
    r",?\s+et ensuite\s+|,?\s+puis\s+|\s+et\s+|"
    r",?\s+und dann\s+|,?\s+dann\s+|,?\s+danach\s+|\s+und\s+|,)\s*"
)


def partes_do_pedido(texto_normalizado, verbos):
    """As partes do pedido que pedem uma AÇÃO (têm um verbo de ação)."""
    partes = [p.strip() for p in _RE_CONECTORES.split(texto_normalizado) if p and p.strip()]
    return [p for p in partes if set(p.split()) & verbos]


def eh_multi_etapas(texto_normalizado, verbos):
    """'abre a calculadora e faz 12 x 8', 'fecha o spotify e depois abre o
    discord': duas ou mais partes com verbo de ação. 'pesquise preço e
    qualidade' não conta (só um verbo)."""
    return len(partes_do_pedido(texto_normalizado, verbos)) >= 2


# ------------------------------------------------------------
# Histórico de acertos por modelo e tarefa
# ------------------------------------------------------------

class Historico:
    """Últimos resultados (1 = deu certo, 0 = falhou) de cada modelo em cada
    tarefa, guardados em ~/.cache/opentars. Um modelo que falha a maioria
    das vezes numa tarefa desce na fila DAQUELA tarefa; como só as últimas
    vezes contam, ele volta a subir se passar a acertar (ex: modelo novo
    do Ollama, openTARS atualizado)."""

    MAX_REGISTROS = 20
    MIN_AMOSTRAS = 3
    TAXA_RUIM = 0.6

    def __init__(self, caminho):
        self.caminho = Path(caminho)
        self.dados = None
        self.versao = 0
        self._trava = threading.Lock()

    def _carregar(self):
        if self.dados is None:
            try:
                dados = json.loads(self.caminho.read_text(encoding="utf-8"))
                self.dados = {k: [1 if x else 0 for x in v][-self.MAX_REGISTROS:]
                              for k, v in dados.items() if isinstance(v, list)}
            except Exception:
                self.dados = {}
        return self.dados

    @staticmethod
    def _chave(modelo, tarefa):
        return f"{tarefa}|{modelo}"

    def registrar(self, modelo, tarefa, ok):
        if not modelo or not tarefa or ok is None:
            return
        with self._trava:
            dados = self._carregar()
            chave = self._chave(modelo, tarefa)
            dados[chave] = (dados.get(chave, []) + [1 if ok else 0])[-self.MAX_REGISTROS:]
            self.versao += 1
            try:
                self.caminho.parent.mkdir(parents=True, exist_ok=True)
                temporario = self.caminho.with_suffix(".tmp")
                temporario.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
                os.replace(temporario, self.caminho)
            except Exception:
                pass  # sem disco: vale só nesta sessão

    def placar(self, modelo, tarefa):
        """(acertos, total) das últimas vezes."""
        lista = self._carregar().get(self._chave(modelo, tarefa), [])
        return sum(lista), len(lista)

    def ruim(self, modelo, tarefa):
        acertos, total = self.placar(modelo, tarefa)
        return total >= self.MIN_AMOSTRAS and (total - acertos) / total >= self.TAXA_RUIM

    def reordenar(self, modelos, tarefa, fixos_no_fim=()):
        """Os que falham muito nessa tarefa vão pro fim (antes dos fixos,
        ex: modelos de programação numa tarefa que não é código)."""
        fixos = [m for m in modelos if m in fixos_no_fim]
        resto = [m for m in modelos if m not in fixos_no_fim]
        bons = [m for m in resto if not self.ruim(m, tarefa)]
        ruins = [m for m in resto if self.ruim(m, tarefa)]
        return bons + ruins + fixos
