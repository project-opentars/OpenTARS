"""openTARS 2.9.2: mouse preciso.

Lógica pura (sem X, sem pyautogui) dos cliques e arrastos, testável sozinha:

- ancora():       "top-left", "canto superior esquerdo", "oben links"... -> ponto da tela
- caminho():      os pontos de um arrasto "de gente": sai devagar do lugar
                  (apps como o Chrome/Brave só entendem que é arrasto depois
                  de uns pixels com o botão apertado), acelera e freia no fim
- recorte_em_volta(): a região em volta de um ponto
- mudanca():      quanto a tela mudou entre duas capturas (o clique pegou?)
"""

import re
import unicodedata


# ------------------------------------------------------------
# Âncoras: lugares da tela por nome, em 5 idiomas
# ------------------------------------------------------------
MARGEM_ANCORA = 48  # px da borda: soltar colado na borda liga o "encaixe" de janela do GNOME/KDE

_VERTICAL = {
    "topo": ("top", "upper", "topo", "cima", "alto", "superior", "arriba", "haut", "oben", "obere", "oberen"),
    "base": ("bottom", "lower", "baixo", "inferior", "embaixo", "abajo", "bas", "unten", "untere", "unteren"),
}
_HORIZONTAL = {
    "esquerda": ("left", "esquerda", "esquerdo", "izquierda", "izquierdo", "gauche", "links", "linke", "linken"),
    "direita": ("right", "direita", "direito", "derecha", "derecho", "droite", "rechts", "rechte", "rechten"),
}
_CENTRO = ("center", "centre", "middle", "centro", "meio", "medio", "milieu", "mitte")


def _normalizar(texto):
    texto = unicodedata.normalize("NFKD", str(texto or "").lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.findall(r"[a-z]+", texto)


def ancora(nome, largura, altura, margem=MARGEM_ANCORA):
    """(x, y) do lugar da tela chamado 'nome', ou None se não for um lugar.
    'top-left' -> perto do canto superior esquerdo; 'left' -> meio da
    borda esquerda; 'center' -> centro."""
    palavras = set(_normalizar(nome))
    if not palavras:
        return None
    vertical = next((k for k, v in _VERTICAL.items() if palavras & set(v)), None)
    horizontal = next((k for k, v in _HORIZONTAL.items() if palavras & set(v)), None)
    centro = bool(palavras & set(_CENTRO))
    if not (vertical or horizontal or centro):
        return None
    # "metade esquerda", "left half": o centro daquela metade
    metade = bool(palavras & {"half", "metade", "mitad", "moitie", "halfte", "haelfte"})
    margem = max(0, min(margem, largura // 4, altura // 4))
    if horizontal == "esquerda":
        x = largura // 4 if metade else margem
    elif horizontal == "direita":
        x = largura - largura // 4 if metade else largura - 1 - margem
    else:
        x = largura // 2
    if vertical == "topo":
        y = altura // 4 if metade else margem
    elif vertical == "base":
        y = altura - altura // 4 if metade else altura - 1 - margem
    else:
        y = altura // 2
    return x, y


# ------------------------------------------------------------
# Caminho do arrasto
# ------------------------------------------------------------
EMPURRAO_PX = 14      # o primeiro pedaço, devagar: vira "arrasto" no app
PASSOS_ARRASTO = 24


def caminho(x0, y0, x1, y1, passos=PASSOS_ARRASTO, empurrao=EMPURRAO_PX):
    """Pontos inteiros de (x0, y0) até (x1, y1), sem o de partida e
    terminando exatamente no destino. Os primeiros cobrem só 'empurrao' px
    (em 3 passos); o resto vai com aceleração e freada (ease-in-out)."""
    dx, dy = x1 - x0, y1 - y0
    distancia = (dx * dx + dy * dy) ** 0.5
    if distancia < 1:
        return [(int(x1), int(y1))]
    pontos = []
    inicio = min(1.0, empurrao / distancia)
    for i in (1, 2, 3):
        f = inicio * i / 3
        pontos.append((round(x0 + dx * f), round(y0 + dy * f)))
    resto = max(2, passos - 3)
    for i in range(1, resto + 1):
        s = i / resto
        suave = s * s * (3 - 2 * s)  # smoothstep
        f = inicio + (1 - inicio) * suave
        pontos.append((round(x0 + dx * f), round(y0 + dy * f)))
    pontos[-1] = (int(x1), int(y1))
    limpos = []
    for p in pontos:
        if not limpos or limpos[-1] != p:
            limpos.append(p)
    return limpos


def recorte_em_volta(x, y, raio, largura, altura):
    """(x0, y0, x1, y1) do quadrado de lado 2*raio em volta de (x, y),
    empurrado pra dentro da imagem (sem encolher, se couber)."""
    lado = 2 * raio
    x0 = min(max(0, x - raio), max(0, largura - lado))
    y0 = min(max(0, y - raio), max(0, altura - lado))
    return x0, y0, min(largura, x0 + lado), min(altura, y0 + lado)


SEMELHANCA_COR = 30  # soma R+G+B: até isso é "a mesma cor" (antisserrilhado à parte)


def _mesma_cor(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1]) + abs(a[2] - b[2]) <= SEMELHANCA_COR


def encaixar(imagem, x, y, raio=20):
    """Se o ponto caiu numa área lisa (errou o botão
    por pouco), vai pro centro do elemento INTEIRO mais perto (uma mancha
    de cor própria que cabe na região). Caiu em cima de algo: fica."""
    try:
        img = imagem.convert("RGB")
        if not (0 <= x < img.width and 0 <= y < img.height):
            return x, y
        x0, y0, x1, y1 = recorte_em_volta(x, y, 3, img.width, img.height)
        cor = img.getpixel((x, y))
        if not all(_mesma_cor(cor, img.getpixel((i, j))) for i in range(x0, x1) for j in range(y0, y1)):
            return x, y  # já está em cima de alguma coisa
        x0, y0, x1, y1 = recorte_em_volta(x, y, raio, img.width, img.height)
        regiao = img.crop((x0, y0, x1, y1))
        largura, altura = regiao.size
        px = regiao.load()
        visto = [[False] * largura for _ in range(altura)]
        lx, ly = x - x0, y - y0
        melhor = None
        for j in range(altura):
            for i in range(largura):
                if visto[j][i]:
                    continue
                semente = px[i, j]
                pilha, pontos = [(i, j)], []
                visto[j][i] = True
                while pilha:
                    a, b = pilha.pop()
                    pontos.append((a, b))
                    for na, nb in ((a + 1, b), (a - 1, b), (a, b + 1), (a, b - 1)):
                        if 0 <= na < largura and 0 <= nb < altura and not visto[nb][na] \
                                and _mesma_cor(px[na, nb], semente):
                            visto[nb][na] = True
                            pilha.append((na, nb))
                xs = [a for a, _ in pontos]
                ys = [b for _, b in pontos]
                bx0, bx1, by0, by1 = min(xs), max(xs), min(ys), max(ys)
                # o fundo onde o ponto caiu, pedaços de coisa maior (encostam
                # na borda) e ruído não são "o botão"
                if (bx0 <= lx <= bx1 and by0 <= ly <= by1 and (lx, ly) in set(pontos)) \
                        or bx0 == 0 or by0 == 0 or bx1 == largura - 1 or by1 == altura - 1 \
                        or len(pontos) < 12:
                    continue
                dx = max(bx0 - lx, 0, lx - bx1)
                dy = max(by0 - ly, 0, ly - by1)
                d = dx * dx + dy * dy
                if melhor is None or d < melhor[0]:
                    melhor = (d, (bx0 + bx1) / 2, (by0 + by1) / 2)
        if melhor is None:
            return x, y
        return round(x0 + melhor[1]), round(y0 + melhor[2])
    except Exception:
        return x, y


# ------------------------------------------------------------
# A tela mudou?
# ------------------------------------------------------------
LARGURA_COMPARACAO = 320
LIMIAR_PIXEL = 40        # diferença R+G+B pra contar como pixel mudado
FRACAO_MUDOU = 0.002     # 0,2% dos pixels: uma aba fechando já passa disso


def mudanca(antes, depois):
    """Fração (0–1) dos pixels que mudaram entre duas capturas do mesmo
    lugar. Compara em tamanho pequeno: rápido e ignora ruído de 1 px."""
    if antes is None or depois is None or antes.size != depois.size:
        return None
    largura = min(LARGURA_COMPARACAO, antes.width)
    altura = max(1, round(antes.height * largura / antes.width))
    a = antes.convert("RGB").resize((largura, altura))
    b = depois.convert("RGB").resize((largura, altura))
    pa, pb = a.load(), b.load()
    mudados = 0
    for j in range(altura):
        for i in range(largura):
            ca, cb = pa[i, j], pb[i, j]
            if abs(ca[0] - cb[0]) + abs(ca[1] - cb[1]) + abs(ca[2] - cb[2]) > LIMIAR_PIXEL:
                mudados += 1
    return mudados / (largura * altura)


def mudou(fracao):
    return fracao is not None and fracao >= FRACAO_MUDOU


# ------------------------------------------------------------
# 3.0 Miller: mover JANELA (não arrastar o que está escrito nela)
# ------------------------------------------------------------
# "arraste a janela do openTARS pro topo esquerdo": antes o arrasto ia
# até o TEXTO "openTARS" dentro da janela. Mover janela é com o
# gerenciador de janelas (EWMH), que sabe onde fica a borda e a barra.
_PALAVRAS_JANELA = {"janela", "window", "ventana", "fenetre", "fenster", "titlebar", "barra de titulo",
                    "title bar", "barre de titre", "titelleiste", "barra de titulo"}
_PALAVRAS_ABA = {"aba", "tab", "guia", "pestana", "onglet", "reiter", "tabs", "abas"}
_RE_MAXIMIZAR = {"maximize", "maximizar", "maximizada", "maximiser", "maximieren", "tela cheia", "full screen",
                 "fullscreen", "pantalla completa", "plein ecran", "vollbild", "inteira"}
_RE_RESTAURAR = {"restore", "restaurar", "restaure", "wiederherstellen", "normal", "unmaximize"}


def fala_de_janela(texto):
    """'janela do openTARS', 'barra de título', 'the firefox window' (mas não 'aba do YouTube')."""
    n = " ".join(_normalizar(texto))
    palavras = set(n.split())
    if palavras & _PALAVRAS_ABA:
        return False
    return bool(palavras & _PALAVRAS_JANELA) or any(p in n for p in _PALAVRAS_JANELA if " " in p)


def sem_palavras_de_janela(texto):
    """'a janela do openTARS' -> 'openTARS'."""
    fora = {"a", "o", "the", "la", "le", "die", "der", "da", "do", "de", "of", "del", "du", "des"}
    fora |= {p for p in _PALAVRAS_JANELA if " " not in p}
    fora |= {"barra", "titulo", "title", "bar", "barre", "titre", "titelleiste", "sua", "your", "minha", "my"}
    return " ".join(p for p in str(texto or "").split() if " ".join(_normalizar(p)) not in fora).strip()


def lugar_da_janela(lugar, area, tamanho=None):
    """Onde pôr a janela: (x, y, largura, altura) do retângulo EXTERNO (com a
    borda), largura/altura None = não muda o tamanho; ou 'maximizar' /
    'restaurar'; ou None se 'lugar' não é um lugar conhecido.

    area = (x, y, largura, altura) da área útil (sem painéis, _NET_WORKAREA);
    tamanho = (largura, altura) da janela por fora, pra encostar nos cantos
    da direita/de baixo e centralizar."""
    palavras = set(_normalizar(lugar))
    n = " ".join(_normalizar(lugar))
    if palavras & _RE_MAXIMIZAR or any(p in n for p in _RE_MAXIMIZAR if " " in p):
        return "maximizar"
    if palavras & _RE_RESTAURAR:
        return "restaurar"
    ax, ay, al, aa = area
    vertical = next((k for k, v in _VERTICAL.items() if palavras & set(v)), None)
    horizontal = next((k for k, v in _HORIZONTAL.items() if palavras & set(v)), None)
    centro = bool(palavras & set(_CENTRO))
    metade = bool(palavras & {"half", "metade", "mitad", "moitie", "halfte", "haelfte"})
    if not (vertical or horizontal or centro):
        return None
    if metade:
        if horizontal and not vertical:
            return (ax if horizontal == "esquerda" else ax + al // 2, ay, al // 2, aa)
        if vertical and not horizontal:
            return (ax, ay if vertical == "topo" else ay + aa // 2, al, aa // 2)
    largura, altura = tamanho or (al // 2, aa // 2)
    largura, altura = min(largura, al), min(altura, aa)
    if horizontal == "esquerda":
        x = ax
    elif horizontal == "direita":
        x = ax + al - largura
    else:
        x = ax + (al - largura) // 2
    if vertical == "topo":
        y = ay
    elif vertical == "base":
        y = ay + aa - altura
    else:
        y = ay + (aa - altura) // 2
    return (x, y, None, None)
