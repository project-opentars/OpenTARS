"""openTARS: sinal de que uma resposta de conversa pode ser invenção (anti-alucinação, 5.2).

O Ollama devolve o logprob de cada token que o modelo escreveu. Quando o Gargantua responde de cabeça a algo que não sabe
(pessoa, empresa ou livro que não existe, um número, um dado de agora), a média desses logprobs tende a cair. Medido com
`fonte/kit/prova_alucinacao.py` (modo app, temperatura 0,1, 120 primeiros tokens): AUC 0,93 nas 48 perguntas em que o limiar
foi escolhido, mas só 0,73 (2B) e 0,70 (Lite) nas 28 perguntas de validação, que ele nunca viu. Com o limiar -0,25 a validação
pega 7 de 10 respostas erradas do 2B e 17 de 21 do Lite, e marca 3 de 10 certas do 2B e 2 de 5 do Lite. É um sinal moderado,
não um detector: por isso o app só PESQUISA (pesquisa web ligada) ou AVISA, nunca bloqueia nem reescreve a resposta. Sem geração
extra: custo zero. Só biblioteca padrão, sem Qt. Reconferir com a prova do Lab depois de cada treino.
"""
import os
import re
import unicodedata

JANELA = 120          # tokens do começo da resposta que entram na média (os mesmos da prova)
LIMIAR = -0.25        # média abaixo disso = pouca confiança
MIN_TOKENS = 8        # resposta curta demais não diz nada ("oi!")
MIN_CARACTERES = 25

_NAO_E_FATO = re.compile(  # pedido criativo ou de texto, em qualquer posição (antes só valia no começo da frase)
    r"\b(escreva|escreve|poema|poesia|conto|historia|cancao|musica|letra|verso|rima|piada|crie|cria|invente|inventa|"
    r"faca|faz|gere|gera|sugira|traduza|traduz|resuma|resume|reescreva|corrija|"
    r"write|poem|poetry|story|joke|song|lyrics|translate|summari[sz]e|rewrite|fix|improve|draft|make up|tell me)\b", re.I)
_PERGUNTA = re.compile(  # a forma de pergunta de fato: termina com "?" ou começa com palavra interrogativa
    r"\?\s*$|^(quem|qual|quais|quando|quanto|quanta|quantos|quantas|onde|por que|porque|o que|que|como|existe|"
    r"who|what|when|where|which|how|is|are|does|did)\b")


def ligado():
    """TARS_CONFIANCA=0 desliga (por exemplo, para medir o modelo sem o app mexer na resposta)."""
    return os.environ.get("TARS_CONFIANCA", "1") != "0"


def _sem_acento(texto):
    t = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in t if not unicodedata.combining(c)).lower().strip()


def media(logprobs):
    """Média dos logprobs dos primeiros JANELA tokens (None se não vieram: Ollama antigo ou modelo de API)."""
    valores = [x for x in (logprobs or [])[:JANELA] if isinstance(x, (int, float))]
    return sum(valores) / len(valores) if len(valores) >= MIN_TOKENS else None


def pouca_confianca(logprobs, limiar=None):
    m = media(logprobs)
    return m is not None and m < (LIMIAR if limiar is None else limiar)


def vale_conferir(tarefa, pedido, resposta):
    """Só pergunta de fato respondida em texto: nada de ação no computador, código ou visão, nem pedido de texto criativo
    (escrever, traduzir, resumir), nem resposta com bloco de código."""
    if tarefa in ("acao", "visao", "codigo", "tecnico"):
        return False
    if len((resposta or "").strip()) < MIN_CARACTERES or "```" in (resposta or ""):
        return False
    pedido = _sem_acento(pedido)
    return len(pedido.split()) >= 3 and _PERGUNTA.search(pedido) is not None and not _NAO_E_FATO.search(pedido)


def logprobs_do_pedaco(pedaco):
    """Os logprobs de um pedaço do streaming do Ollama ([{'token','logprob',...}])."""
    return [x["logprob"] for x in (pedaco or []) if isinstance(x, dict) and isinstance(x.get("logprob"), (int, float))]
