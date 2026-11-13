"""Pedidos de vários passos: "cria a pasta backup e copia notas.txt para ela", "procura ERROR no log e salva num arquivo".

Medido em 07/11 (prova de capacidade): 0 de 6. O modelo de 270M faz um passo só e erra o resto. Aqui a frase se divide onde começa
um verbo novo, cada parte passa pelas mesmas regras de uma vez só, e o que uma parte produz chega na seguinte:
a pasta criada vira o "ela"/"it", a saída vira o "isso"/"essas linhas", e "quantos são" conta o que a parte anterior achou.
"""
import re

VERBOS = (r"(?:me\s+)?(?:cria|crie|criar|faz|faca|copia|copie|copiar|move|mova|mover|leva|leve|mostra|mostre|lista|liste|diz|diga|conta|conte|"
          r"salva|salve|grava|grave|guarda|guarde|apaga|apague|abre|abra|le|leia|roda|rode|instala|instale|coloca|coloque|poe|ponha|adiciona|"
          r"adicione|renomeia|renomeie|compacta|compacte|ve|veja|procura|procure|testa|teste|verifica|verifique|"
          r"create|make|copy|move|show|list|tell|count|save|store|write|delete|remove|open|read|run|install|put|add|rename|zip|compress|"
          r"find|search|check|test|then)\b")
_DIVISAO = re.compile(r",?\s+(?:e depois|e em seguida|e entao|e ai|depois|em seguida|and then|then|e|and)\s+(?=" + VERBOS + ")")
_LUGAR = re.compile(r"\b(para|pra|pro|em|into|in|inside|to|dentro de)\s+(ela|ele|l[aá]|it|there)(?!\w)|(?<!\w)(nela|nele|l[aá] dentro|inside it|in it|into it|there|pra l[aá]|para l[aá])(?!\w)",
                    re.IGNORECASE)
_SALVAR = re.compile(r"^(?:e\s+)?(?:salva|salve|grava|grave|guarda|guarde|save|store|write|put)\s+(?:isso|isto|essas linhas|esse resultado|o resultado|a saida|"
                     r"tudo|elas|it|them|that|those lines|the lines|the result|the output|everything)?\s*(?:em|num|numa|no|na|to|into|in)\s+"
                     r"(?:um |uma |o |a |an? |the )?(?:novo |new )?(?:arquivo |file )?(?:chamado |called |named )?(\S+?)\s*[.!?]*$")
_QUANTOS = re.compile(r"^(?:e\s+)?(?:me\s+)?(?:diz|diga|conta|conte|tell me|count)\b.{0,20}\b(?:quantos|quantas|how many)\b|^(?:e\s+)?(?:count them|conta eles|conta elas)\b")


def dividir(pedido, n):
    """As partes do pedido (com as maiúsculas de quem escreveu), ou None se é um passo só.
    Só divide onde a parte seguinte começa com um verbo. n: o pedido normalizado, do mesmo tamanho."""
    original = pedido.strip() if len(pedido.strip()) == len(n) else n
    partes, inicio = [], 0
    for achado in _DIVISAO.finditer(n):
        partes.append(original[inicio:achado.start()])
        inicio = achado.end()
    partes.append(original[inicio:])
    partes = [p.strip(" ,.") for p in partes if p.strip(" ,.")]
    return partes if len(partes) > 1 else None


def com_lugar(parte, lugar):
    """'copia notas.txt para ela' -> 'copia notas.txt para backup'."""
    if not lugar:
        return parte

    def troca(achado):
        if achado.group(1):
            return f"{achado.group(1)} {lugar}"
        palavra = achado.group(3).lower()
        if palavra.startswith(("pra", "para")):
            return f"para {lugar}"
        return f"em {lugar}" if palavra.startswith(("nel", "la", "lá")) else f"in {lugar}"
    return _LUGAR.sub(troca, parte)


def salvar_em(parte):
    achado = _SALVAR.search(parte)
    return achado.group(1) if achado else None


def pede_contagem(parte):
    return bool(_QUANTOS.search(parte))
