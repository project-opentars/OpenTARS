"""A visão da tela do openTARS (era o Cooper até a 5.1; descontinuado em 18/10/2026).

Desde o Gargantua 2 o próprio modelo enxerga: ele responde às perguntas sobre um print (onde está um botão, se algo está
marcado, o que diz um campo) no mesmo formato em que o Cooper respondia, porque o treino de visão do Gargantua 2 usou
exatamente essas perguntas. Instalar:  ollama pull ProjectOpenTARS/Gargantua-2

(Antes tars_cooper.py; os nomes foram trocados por "visão" em 18/10. `e_cooper` e `MODELO_COOPER` ficam de propósito: servem
para reconhecer um Cooper antigo que ainda esteja instalado, que só entra como reserva se não houver Gargantua 2.)

Este módulo é puro (sem rede): as perguntas no formato do treino, a leitura das respostas e a conversão de milésimos
(0-1000 da imagem) em pixels. Quem fala com o Ollama é o núcleo (nucleo/visao.py).
"""

import json
import os
import re

MODELO_VISAO = os.environ.get("TARS_MODELO_GARGANTUA", "ProjectOpenTARS/Gargantua-2")
COMANDO_INSTALAR = f"ollama pull {MODELO_VISAO}"
MODELO_COOPER = "ProjectOpenTARS/cooper:1.2"       # descontinuado: só para reconhecer um Cooper que já esteja instalado
ESCALA = 1000

TIMEOUT_VISAO = 60


def ligado(env=None):
    """TARS_VISAO=0 desliga a visão da tela (TARS_COOPER=0, o nome antigo, continua valendo)."""
    env = os.environ if env is None else env
    valor = env.get("TARS_VISAO", env.get("TARS_COOPER", "1"))
    return str(valor).lower() not in ("0", "off", "no", "nao", "não", "false")


def e_cooper(tag):
    """'ProjectOpenTARS/cooper:latest', 'cooper', 'cooper-1.0'... (o nome
    depois da última barra começa com 'cooper')."""
    nome = str(tag or "").strip().lower().split(":")[0].split("/")[-1]
    return nome.startswith("cooper")


def e_gargantua_2(tag):
    """Quem enxerga: a família Gargantua-2 (:latest, 2B; :lite, 0,8B) e o Lite 2.0 antigo (Gargantua:2.0-lite, também Qwen3.5)."""
    base, _, etiqueta = str(tag or "").strip().lower().partition(":")
    return base.split("/")[-1].startswith("gargantua-2") or (base.split("/")[-1] == "gargantua" and etiqueta == "2.0-lite")


def e_lite_sem_telas(tag):
    """O Lite 2.0 ANTIGO (Gargantua:2.0-lite, 17/10): enxerga, mas não foi treinado com telas (30% ao achar botão pelo app).
    O Gargantua-2:lite de 18/10 em diante foi treinado com elas (72%): vale como olho, atrás do 2B (85%)."""
    base, _, etiqueta = str(tag or "").strip().lower().partition(":")
    return base.split("/")[-1] == "gargantua" and etiqueta == "2.0-lite"


def olho_valido(tag):
    """Quem pode olhar a tela por conta do openTARS: a família Gargantua-2 (o 2B e o Lite novo) e, só com
    TARS_VISAO_NO_LITE=1, o Lite 2.0 antigo."""
    if not e_gargantua_2(tag):
        return False
    return not e_lite_sem_telas(tag) or str(os.environ.get("TARS_VISAO_NO_LITE", "0")).lower() in ("1", "true", "sim")


def achar_instalado(tags):
    """A tag do modelo que olha a tela: o Gargantua 2 (o :latest primeiro); sem ele, um Cooper antigo; senão None."""
    g2 = sorted(t for t in tags or [] if olho_valido(t))
    if g2:
        return next((t for t in g2 if str(t).lower().endswith(":latest")), g2[0])
    achados = [t for t in tags or [] if e_cooper(t)]
    if not achados:
        return None
    oficial = MODELO_COOPER.lower()
    for t in achados:                                           # a versão oficial exata (cooper:1.2) primeiro
        if str(t).lower() == oficial:
            return t
    for t in achados:                                           # depois qualquer etiqueta do mesmo nome (cooper:latest)
        if str(t).lower().split(":")[0] == oficial.split(":")[0]:
            return t
    return sorted(achados)[0]


# ------------------------------------------------------------
# Perguntas (os modelos de pergunta do treino; ver o README do Cooper)
# ------------------------------------------------------------

_TIPOS = (
    # (palavras que aparecem no nome pedido, tipo que o Cooper conhece)
    (("checkbox", "check box", "caixa de seleção", "caixa de selecao"), "checkbox"),
    (("radio",), "radio button"),
    (("tab", "aba"), "tab"),
    (("menu",), "menu"),
    (("link",), "link"),
    (("icon", "ícone", "icone"), "icon"),
    (("field", "campo", "input", "text box", "textbox", "caixa de texto"), "field"),
    (("list item", "item da lista"), "list item"),
    (("button", "botão", "botao"), "button"),
)


def tipo_do_alvo(nome):
    """('button', 'Save') a partir de 'the Save button' / 'botão Salvar' /
    'Save'. Sem pista de tipo, assume botão (o caso mais comum)."""
    texto = str(nome or "").strip().strip("\"'")
    baixo = texto.lower()
    for palavras, tipo in _TIPOS:
        for p in palavras:
            achado = re.search(rf"(?<![\w]){re.escape(p)}(?![\w])", baixo)
            if achado:
                limpo = (texto[:achado.start()] + " " + texto[achado.end():]).strip()
                limpo = re.sub(r"^(the|o|a|um|uma|de|do|da)\s+", "", limpo, flags=re.IGNORECASE).strip(" \"'")
                return tipo, (limpo or texto)
    return "button", texto


def pergunta_localizar(nome, janela=None):
    tipo, rotulo = tipo_do_alvo(nome)
    rotulo = rotulo.replace('"', "'")
    onde = f' in the window "{str(janela).replace(chr(34), chr(39))}"' if janela else ""
    return (f'Where is the {tipo} "{rotulo}"{onde} on the screen? Answer with its center as JSON '
            '{"x": 0-1000, "y": 0-1000} (thousandths of the image width and height). '
            'If it is not on the screen, answer {"found": false}.')


def pergunta_descrever(pedido):
    pedido = str(pedido or "").replace('"', "'")
    return ('Describe this screenshot for an assistant that must operate the computer to do: '
            f'"{pedido}". List the open windows and the buttons, fields and other clickable elements, '
            'each with its center as (x, y) in thousandths of the image width and height (0-1000).')


# ------------------------------------------------------------
# Respostas
# ------------------------------------------------------------

def _json_da_resposta(texto):
    texto = re.sub(r"```(?:json)?", "", str(texto or "")).strip()
    for achado in re.finditer(r"\{[^{}]*\}", texto):
        try:
            dados = json.loads(achado.group(0))
        except ValueError:
            continue
        if isinstance(dados, dict):
            return dados
    return None


def ler_ponto(texto):
    """('achou', x, y) com x e y em milésimos, ('ausente', None, None) se
    o Cooper disse que não está na tela, ou None se a resposta não presta."""
    dados = _json_da_resposta(texto)
    if dados is not None:
        if dados.get("found") is False and "x" not in dados:
            return ("ausente", None, None)
        try:
            x, y = float(dados["x"]), float(dados["y"])
        except (KeyError, TypeError, ValueError):
            return None
        if 0 <= x <= ESCALA and 0 <= y <= ESCALA:
            return ("achou", x, y)
        return None
    par = re.search(r"\(\s*(\d{1,4}(?:\.\d+)?)\s*,\s*(\d{1,4}(?:\.\d+)?)\s*\)", str(texto or ""))
    if par:
        x, y = float(par.group(1)), float(par.group(2))
        if x <= ESCALA and y <= ESCALA:
            return ("achou", x, y)
    return None


def para_pixels(x, y, largura, altura):
    """Milésimos -> pixels da imagem de tamanho largura x altura."""
    px = round(float(x) / ESCALA * largura)
    py = round(float(y) / ESCALA * altura)
    return max(0, min(largura - 1, px)), max(0, min(altura - 1, py))


def descricao_em_pixels(texto, largura, altura):
    """Troca os pares (x, y) de milésimos, na descrição, por pixels da
    imagem; os que fogem de 0-1000 ficam como estão."""
    def troca(m):
        x, y = float(m.group(1)), float(m.group(2))
        if x > ESCALA or y > ESCALA:
            return m.group(0)
        px, py = para_pixels(x, y, largura, altura)
        return f"({px}, {py})"

    corpo = re.sub(r"\(\s*(\d{1,4}(?:\.\d+)?)\s*,\s*(\d{1,4}(?:\.\d+)?)\s*\)", troca, str(texto or ""))
    corpo = re.sub(r'\{\s*"x"\s*:\s*(\d{1,4}(?:\.\d+)?)\s*,\s*"y"\s*:\s*(\d{1,4}(?:\.\d+)?)\s*\}', troca_json(largura, altura), corpo)
    return corpo.strip()


def troca_json(largura, altura):
    def f(m):
        x, y = float(m.group(1)), float(m.group(2))
        if x > ESCALA or y > ESCALA:
            return m.group(0)
        px, py = para_pixels(x, y, largura, altura)
        return f"({px}, {py})"
    return f
