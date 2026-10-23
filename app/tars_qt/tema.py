"""Tema do openTARS 5.0: as cores, as fontes e as peças do mockup aprovado.

Fundo #151E3D, barra lateral #0F1730, cartões #1A2446 com borda #2E3C6B,
texto #E8ECF4, apoio #A0B0D8, verde #5FD97A nas ações e nos estados certos,
lavanda #A0B0D8 nos pedidos de confirmação. Texto em IBM Plex Sans, rótulos
técnicos em IBM Plex Mono (as duas vão junto, licença OFL em fontes/OFL.txt).
Cantos arredondados (botões 10 px, cartões 12 a 14 px), alvos de pelo menos 44 px.
"""

import html
from pathlib import Path

from PySide6.QtCore import QByteArray, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import QLabel, QWidget

CORES = {
    "fundo": "#151E3D",
    "lateral": "#0F1730",
    "cartao": "#1A2446",
    "borda": "#2E3C6B",
    "borda2": "#34437A",
    "borda3": "#4A5A8F",
    "linha": "#243158",
    "texto": "#E8ECF4",
    "texto2": "#C5CFEA",
    "apoio": "#A0B0D8",
    "mudo": "#8A9AC8",
    "verde": "#5FD97A",
    "escuro": "#0B1020",
    "destaque": "#222F5A",
}

# Glifos que a IBM Plex NÃO tem. Quando o Qt precisa de um glifo que falta, pergunta ao fontconfig do sistema por uma
# fonte substituta; em algumas máquinas essa chamada (FcCharSetHasChar) dá segfault. Por isso a interface só usa
# caracteres que a Plex tem: estes são trocados por equivalentes que ela tem.
_TROCAS = str.maketrans({"▸": "›", "▶": "›", "►": "›", "▾": "↓", "▼": "↓", "✗": "×", "✘": "×", "✕": "×", "✔": "✓", "●": "•", "⏰": "↻"})


_FONTES_CRUAS = []


def _plex_tem(c):
    if not _FONTES_CRUAS:
        from PySide6.QtGui import QRawFont
        _FONTES_CRUAS.extend(QRawFont(str(f), 15) for f in sorted(_PASTA_FONTES.glob("*.ttf")))
    return any(f.supportsCharacter(ord(c)) for f in _FONTES_CRUAS)


def seguro(texto, externo=False):
    """O texto com os glifos que faltam na IBM Plex trocados por outros que ela tem. externo=True (texto que vem de
    fora: título de feed, nome de arquivo, frase do modelo): o que ainda faltar vira "?" (no PC do Enzo, a estrela preta ou chinês
    num QLabel derrubam a janela até no modo seguro)."""
    texto = str(texto).translate(_TROCAS)
    if not externo or texto.isascii():
        return texto
    return "".join(c if c.isascii() or c in "\n\t" or _plex_tem(c) else "?" for c in texto)


FONTE_TEXTO = "IBM Plex Sans"
FONTE_MONO = "IBM Plex Mono"

_PASTA_FONTES = Path(__file__).resolve().parent / "fontes"


def preparar_fontconfig(sistema="/etc/fonts/fonts.conf", casa=None):
    """Usa as fontes e as regras do sistema, mas com um cache de fontes só do openTARS (~/.cache/opentars/fontconfig).
    Motivo (16/10): um cache corrompido em ~/.cache/fontconfig faz o Qt cair (segfault em FcCharSetHasChar) no primeiro
    caractere que a fonte da janela não tem, até no modo seguro; o fc-cache -f conserta, mas o openTARS não deve depender
    de outro programa ter deixado o cache certo. Chamar antes de criar o QApplication. Não faz nada se a pessoa já
    escolheu um FONTCONFIG_FILE, com TARS_FONTCONFIG_SISTEMA=1, ou sem o fonts.conf do sistema. Devolve o arquivo ou None."""
    import os
    import re
    if os.environ.get("FONTCONFIG_FILE") or os.environ.get("TARS_FONTCONFIG_SISTEMA") == "1":
        return None
    try:
        texto = Path(sistema).read_text(encoding="utf-8")
    except OSError:
        return None
    pasta = Path(casa or os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "opentars"
    base = Path(sistema).parent
    # as inclusões relativas passam a ser absolutas (o arquivo novo mora em outra pasta) e os caches do sistema saem
    texto = re.sub(r"<cachedir[^>]*>.*?</cachedir>", "", texto, flags=re.S)
    texto = re.sub(r'(<include[^>]*>)\s*(?!/|~)([^<]+?)\s*(</include>)', lambda m: f"{m.group(1)}{base / m.group(2)}{m.group(3)}", texto)
    if "</fontconfig>" not in texto:
        return None
    texto = texto.replace("</fontconfig>", f"<cachedir>{pasta / 'fontconfig'}</cachedir>\n</fontconfig>", 1)
    try:
        pasta.mkdir(parents=True, exist_ok=True)
        arquivo = pasta / "fonts.conf"
        if not arquivo.exists() or arquivo.read_text(encoding="utf-8") != texto:
            arquivo.write_text(texto, encoding="utf-8")
    except OSError:
        return None
    os.environ["FONTCONFIG_FILE"] = str(arquivo)
    return arquivo


def carregar_fontes():
    """Registra as fontes que vão junto. Devolve quantas carregaram (0 = cai na fonte do sistema)."""
    carregadas = 0
    for arquivo in sorted(_PASTA_FONTES.glob("*.ttf")):
        if QFontDatabase.addApplicationFont(str(arquivo)) >= 0:
            carregadas += 1
    return carregadas


# ------------------------------------------------------------
# Marca (os mesmos SVG do mockup)
# ------------------------------------------------------------

def monolito_svg(contorno=True):
    """O monolito: quatro blocos e a barra verde, no quadrado arredondado azul."""
    borda = f' stroke="{CORES["borda2"]}" stroke-width="2"' if contorno else ""
    blocos = "".join(
        f'<rect x="{x}" y="20" width="12" height="60" rx="4" fill="{CORES["texto"]}"/>' for x in (20, 36, 52, 68)
    )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
        f'<rect width="100" height="100" rx="24" fill="{CORES["cartao"]}"{borda}/>{blocos}'
        f'<rect x="33" y="36" width="34" height="9" rx="4.5" fill="{CORES["verde"]}"/></svg>'
    )


def selo_svg():
    """O selo Tesseract: túnel de três quadrados, núcleo verde. Só em tamanho pequeno."""
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
        f'<rect x="14" y="14" width="72" height="72" rx="14" fill="none" stroke="{CORES["texto"]}" stroke-width="9"/>'
        f'<rect x="34" y="34" width="32" height="32" rx="8" fill="none" stroke="{CORES["apoio"]}" stroke-width="8"/>'
        f'<rect x="43" y="43" width="14" height="14" rx="3" fill="{CORES["verde"]}"/></svg>'
    )


def svg_widget(svg, tamanho):
    w = QSvgWidget()
    w.load(QByteArray(svg.encode()))
    w.setFixedSize(tamanho, tamanho)
    return w


def icone_do_app():
    renderizador = QSvgRenderer(QByteArray(monolito_svg(contorno=False).encode()))
    icone = QIcon()
    for lado in (16, 32, 48, 64, 128, 256):
        pixmap = QPixmap(lado, lado)
        pixmap.fill(Qt.transparent)
        pintor = QPainter(pixmap)
        renderizador.render(pintor)
        pintor.end()
        icone.addPixmap(pixmap)
    return icone


# ------------------------------------------------------------
# Folha de estilo
# ------------------------------------------------------------

def folha_de_estilo():
    c = CORES
    return f"""
* {{ font-family: "{FONTE_TEXTO}"; color: {c['texto']}; }}
QWidget#raiz, QWidget#principal {{ background: {c['fundo']}; }}
QFrame#lateral {{ background: {c['lateral']}; border: 0; border-right: 1px solid {c['linha']}; }}
QLabel {{ background: transparent; border: 0; }}
QLabel[papel="h1"] {{ font-size: 34px; font-weight: 600; }}
QLabel[papel="texto"] {{ font-size: 16px; color: {c['texto2']}; }}
QLabel[papel="kicker"] {{ font-family: "{FONTE_MONO}"; font-size: 12px; color: {c['apoio']}; }}
QLabel[papel="marca"] {{ font-size: 28px; font-weight: 600; }}
QLabel[papel="slogan"] {{ font-size: 14px; color: {c['apoio']}; }}
QLabel[papel="passo"] {{ font-size: 15px; color: {c['texto2']}; }}
QLabel[papel="passo-ativo"] {{ font-size: 15px; font-weight: 600; }}
QLabel[papel="passo-futuro"] {{ font-size: 15px; color: {c['apoio']}; }}
QLabel[papel="selo"] {{ font-family: "{FONTE_MONO}"; font-size: 11px; color: {c['mudo']}; }}
QLabel[papel="mono"] {{ font-family: "{FONTE_MONO}"; font-size: 12px; color: {c['apoio']}; }}
QLabel[papel="mono-claro"] {{ font-family: "{FONTE_MONO}"; font-size: 13px; color: {c['texto2']}; }}
QLabel[papel="linha"] {{ font-size: 15px; color: {c['texto2']}; }}
QLabel[papel="nota"] {{ font-size: 13px; color: {c['apoio']}; }}
QLabel[papel="alerta"] {{ font-size: 14px; color: {c['texto']}; }}
QLabel[papel="titulo-cartao"] {{ font-size: 17px; font-weight: 600; }}
QLabel[papel="desc-cartao"] {{ font-size: 14px; color: {c['texto2']}; }}
QLabel[papel="campo"] {{ font-size: 12px; color: {c['apoio']}; }}
QLabel[papel="erro"] {{ font-size: 14px; color: {c['texto']}; }}

QPushButton {{ font-size: 14px; font-weight: 500; }}
QPushButton[papel="primario"] {{
    background: {c['verde']}; color: {c['escuro']}; border: 0; border-radius: 10px;
    min-height: 48px; padding: 0 28px; font-size: 15px; font-weight: 600;
}}
QPushButton[papel="primario"]:hover {{ background: #74E28E; }}
QPushButton[papel="primario"]:disabled {{ background: {c['borda']}; color: {c['apoio']}; }}
QPushButton[papel="contorno"] {{
    background: transparent; color: {c['texto']}; border: 1px solid {c['borda3']}; border-radius: 10px;
    min-height: 42px; padding: 0 19px;
}}
QPushButton[papel="contorno"]:hover {{ background: {c['destaque']}; }}
QPushButton[papel="contorno"]:disabled {{ color: {c['mudo']}; border-color: {c['borda2']}; }}
QPushButton[papel="chip"] {{
    background: transparent; color: {c['texto2']}; border: 1px solid {c['borda2']}; border-radius: 8px;
    min-height: 40px; padding: 0 14px; font-size: 13px; font-weight: 400;
}}
QPushButton[papel="chip"]:hover {{ background: {c['destaque']}; }}
QPushButton[papel="chip"]:checked {{
    background: {c['fundo']}; color: {c['texto']}; border: 2px solid {c['verde']}; font-weight: 600;
}}
QFrame#cartao {{
    background: transparent; border: 1px solid {c['borda2']}; border-radius: 14px;
}}
QFrame#cartao:hover {{ background: {c['destaque']}; }}
QFrame#cartao:focus {{ border: 1px solid {c['apoio']}; }}
QFrame#cartao[marcado="true"] {{ background: {c['cartao']}; border: 2px solid {c['verde']}; }}

QFrame[papel="painel"] {{ background: {c['cartao']}; border: 1px solid {c['borda']}; border-radius: 14px; }}
QFrame[papel="aviso"] {{ background: {c['destaque']}; border: 1.5px solid {c['apoio']}; border-radius: 12px; }}

QProgressBar {{ background: {c['lateral']}; border: 0; border-radius: 6px; min-height: 12px; max-height: 12px; }}
QProgressBar::chunk {{ background: {c['verde']}; border-radius: 6px; }}

QLineEdit, QSpinBox {{
    min-height: 40px; padding: 0 12px; border-radius: 8px; border: 1px solid {c['borda2']};
    background: {c['fundo']}; font-family: "{FONTE_MONO}"; font-size: 13px; selection-background-color: {c['borda3']};
}}
QLineEdit:focus, QSpinBox:focus {{ border: 1px solid {c['verde']}; }}
QSpinBox::up-button, QSpinBox::down-button {{ width: 0; border: 0; }}
QLineEdit:disabled {{ color: {c['mudo']}; }}
QPlainTextEdit {{
    padding: 6px 10px; border-radius: 8px; border: 1px solid {c['borda2']}; background: {c['fundo']};
    color: {c['texto']}; font-size: 14px; selection-background-color: {c['borda3']};
}}
QPlainTextEdit:focus {{ border: 1px solid {c['verde']}; }}
""" + folha_principal()


def folha_principal():
    """As regras da janela principal (conversa, barra lateral, compositor, configurações)."""
    c = CORES
    return f"""
QFrame#lateral2 {{ background: {c['lateral']}; border: 0; border-right: 1px solid {c['linha']}; }}
QFrame#cabecalho {{ background: transparent; border: 0; border-bottom: 1px solid {c['linha']}; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: 0; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {c['borda']}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {c['borda3']}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QLabel[papel="titulo-conversa"] {{ font-size: 16px; font-weight: 600; }}
QLabel[papel="grupo"] {{ font-size: 11px; font-weight: 500; color: {c['mudo']}; padding: 0 8px; }}
QLabel[papel="rodape"] {{ font-family: "{FONTE_MONO}"; font-size: 11px; color: {c['mudo']}; }}
QLabel[papel="pilula"] {{ font-family: "{FONTE_MONO}"; font-size: 12px; color: {c['texto2']}; }}
QLabel[papel="h2"] {{ font-size: 16px; font-weight: 600; }}
QLabel[papel="h1-pagina"] {{ font-size: 30px; font-weight: 600; }}
QLabel[papel="sub-pagina"] {{ font-size: 15px; color: {c['texto2']}; }}
QLabel[papel="voz-titulo"] {{ font-size: 26px; font-weight: 600; }}
QLabel[papel="voz-fala"] {{ font-size: 17px; }}
QLabel[papel="etiqueta"] {{ font-family: "{FONTE_MONO}"; font-size: 11px; color: {c['escuro']}; background: {c['apoio']};
    border-radius: 6px; padding: 3px 8px; font-weight: 500; }}
QLabel[papel="espera"] {{ font-family: "{FONTE_MONO}"; font-size: 11px; color: {c['texto']}; border: 1px solid {c['apoio']};
    border-radius: 11px; padding: 2px 10px; }}
QLabel[papel="mensagem-ia"] {{ font-size: 15px; color: {c['texto']}; }}
QLabel[papel="pensamento"] {{ font-size: 13px; color: {c['mudo']}; font-style: italic; }}
QLabel[papel="ferramenta"] {{ font-family: "{FONTE_MONO}"; font-size: 12px; color: {c['apoio']}; }}
QLabel[papel="ferramenta-ok"] {{ font-family: "{FONTE_MONO}"; font-size: 12px; color: {c['verde']}; }}
QLabel[papel="aviso-linha"] {{ font-size: 13px; color: {c['apoio']}; }}
QLabel[papel="erro-linha"] {{ font-size: 13px; color: #FF9B9B; }}

QFrame[papel="bloco-codigo"] {{ background: #0E1428; border: 1px solid {c['borda']}; border-radius: 8px; }}
QFrame[papel="bloco-codigo-topo"] {{ background: {c['cartao']}; border: 0; border-bottom: 1px solid {c['borda']};
    border-top-left-radius: 7px; border-top-right-radius: 7px; }}
QLabel[papel="bloco-codigo-lingua"] {{ font-size: 12px; color: {c['texto2']}; background: transparent; }}
QPlainTextEdit[papel="bloco-codigo-texto"] {{ background: #0E1428; color: {c['texto']}; border: 0; padding: 4px 8px;
    border-bottom-left-radius: 7px; border-bottom-right-radius: 7px; selection-background-color: {c['borda']}; }}
QPlainTextEdit[papel="bloco-codigo-texto"] QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QPlainTextEdit[papel="bloco-codigo-texto"] QScrollBar::handle:horizontal {{ background: {c['borda']}; border-radius: 4px; min-width: 30px; }}
QPlainTextEdit[papel="bloco-codigo-texto"] QScrollBar::add-line:horizontal, QPlainTextEdit[papel="bloco-codigo-texto"] QScrollBar::sub-line:horizontal {{ width: 0; }}
QPushButton[papel="copiar-codigo"] {{ background: {c['fundo']}; border: 1px solid {c['borda2']}; border-radius: 6px;
    padding: 2px 10px; font-size: 12px; color: {c['texto']}; }}
QPushButton[papel="copiar-codigo"]:hover {{ background: {c['destaque']}; }}
QFrame[papel="bolha"] {{ background: #25345E; border: 0; border-radius: 14px; border-bottom-right-radius: 4px; }}
QFrame[papel="cartao-etapas"] {{ background: {c['cartao']}; border: 1px solid {c['borda']}; border-radius: 12px; }}
QFrame[papel="linha-etapa"] {{ background: transparent; border: 0; }}
QFrame[papel="linha-etapa"][ativa="true"] {{ background: {c['destaque']}; }}
QFrame[papel="cartao-aprovacao"] {{ background: #1F2B52; border: 1.5px solid {c['apoio']}; border-radius: 12px; }}
QFrame[papel="comando"] {{ background: {c['fundo']}; border: 0; border-radius: 8px; }}
QFrame[papel="pilula-modelo"] {{ background: {c['cartao']}; border: 1px solid {c['borda2']}; border-radius: 16px; }}
QFrame[papel="aviso-versao"] {{ background: {c['cartao']}; border: 1px solid {c['borda2']}; border-radius: 10px; }}
QFrame[papel="compositor"] {{ background: {c['cartao']}; border: 1px solid {c['borda2']}; border-radius: 18px; }}
QFrame[papel="compositor"][foco="true"] {{ border: 1px solid {c['apoio']}; }}
QFrame[papel="segmentos"] {{ background: {c['lateral']}; border: 1px solid {c['linha']}; border-radius: 10px; }}
QFrame[papel="anexo"] {{ background: {c['cartao']}; border: 1px solid {c['borda2']}; border-radius: 16px; }}
QFrame[papel="secao"] {{ background: {c['cartao']}; border: 1px solid {c['borda']}; border-radius: 14px; }}
QFrame[papel="cartao-modelo"] {{ background: {c['fundo']}; border: 1px solid {c['borda']}; border-radius: 12px; }}
QFrame[papel="cartao-modelo"]:hover {{ border-color: {c['borda3']}; }}
QFrame[papel="linha-lista"] {{ background: {c['fundo']}; border: 0; border-radius: 8px; }}
QFrame[papel="faixa-voz"] {{ background: {c['cartao']}; border: 1px solid {c['borda2']}; border-radius: 14px; }}

QPushButton[papel="nova"] {{
    background: {c['cartao']}; border: 1px solid {c['borda2']}; border-radius: 10px; min-height: 44px;
    padding: 0 14px; text-align: left; font-size: 14px; font-weight: 500;
}}
QPushButton[papel="nova"]:hover {{ background: {c['destaque']}; }}
QPushButton[papel="item-historico"] {{
    background: transparent; border: 0; border-radius: 8px; min-height: 40px; padding: 0 12px;
    text-align: left; font-size: 14px; font-weight: 400; color: {c['texto2']};
}}
QPushButton[papel="item-historico"]:hover {{ background: #1A2446; }}
QPushButton[papel="item-historico"][atual="true"] {{ background: {c['destaque']}; color: {c['texto']}; font-weight: 500; }}
QPushButton[papel="rodape-lateral"] {{
    background: transparent; border: 0; border-radius: 8px; min-height: 44px; padding: 0 12px;
    text-align: left; font-size: 14px; font-weight: 400; color: {c['texto2']};
}}
QPushButton[papel="rodape-lateral"]:hover {{ background: #1A2446; }}
QPushButton[papel="rodape-lateral"][atual="true"] {{ background: {c['destaque']}; color: {c['texto']}; font-weight: 500; }}
QPushButton[papel="parar"] {{
    background: transparent; border: 1.5px solid {c['texto']}; border-radius: 10px; min-height: 40px; padding: 0 16px;
    font-size: 14px; font-weight: 600;
}}
QPushButton[papel="parar"]:hover {{ background: {c['destaque']}; }}
QPushButton[papel="atualizar"] {{
    background: {c['verde']}; color: {c['escuro']}; border: 0; border-radius: 8px; min-height: 40px;
    font-size: 13px; font-weight: 600;
}}
QPushButton[papel="atualizar"]:hover {{ background: #74E28E; }}
QPushButton[papel="atualizar"]:disabled {{ background: {c['borda']}; color: {c['apoio']}; }}
QPushButton[papel="icone"] {{ background: transparent; border: 0; border-radius: 12px; }}
QPushButton[papel="icone"]:hover {{ background: {c['destaque']}; }}
QPushButton[papel="icone-contorno"] {{ background: transparent; border: 1px solid {c['borda3']}; border-radius: 12px; }}
QPushButton[papel="icone-contorno"]:hover {{ background: {c['destaque']}; }}
QPushButton[papel="icone-contorno"]:disabled {{ border-color: {c['borda']}; }}
QPushButton[papel="microfone"] {{ background: {c['verde']}; border: 0; border-radius: 26px; }}
QPushButton[papel="microfone"]:hover {{ background: #74E28E; }}
QPushButton[papel="microfone"][ativo="true"] {{ background: #FFFFFF; border: 3px solid {c['verde']}; }}
QPushButton[papel="segmento"] {{
    background: transparent; border: 0; border-radius: 8px; min-height: 36px; padding: 0 12px;
    font-size: 12.5px; font-weight: 400; color: {c['apoio']};
}}
QPushButton[papel="segmento"]:checked {{ background: {c['borda2']}; color: {c['texto']}; font-weight: 500; }}
QPushButton[papel="segmento"]:hover:!checked {{ background: #1A2446; }}
QPushButton[papel="segmento-grande"] {{
    background: transparent; border: 0; border-radius: 9px; min-height: 44px; padding: 0 20px;
    font-size: 14px; font-weight: 400; color: {c['apoio']};
}}
QPushButton[papel="segmento-grande"]:checked {{ background: {c['borda2']}; color: {c['texto']}; font-weight: 500; }}
QPushButton[papel="nav-config"] {{
    background: transparent; border: 0; border-radius: 8px; min-height: 44px; padding: 0 12px; text-align: left;
    font-size: 14px; font-weight: 400; color: {c['texto2']};
}}
QPushButton[papel="nav-config"]:hover {{ background: #1A2446; }}
QPushButton[papel="nav-config"]:checked {{ background: {c['destaque']}; color: {c['texto']}; font-weight: 500; }}
QPushButton[papel="link"] {{ background: transparent; border: 0; color: {c['apoio']}; text-decoration: underline; min-height: 28px; }}

QPlainTextEdit#entrada {{
    background: transparent; border: 0; font-size: 15px; selection-background-color: {c['borda3']};
}}
QLineEdit#busca {{
    background: transparent; border: 0; min-height: 40px; padding: 0; font-family: "{FONTE_TEXTO}"; font-size: 14px;
}}
QToolButton[papel="mais"] {{ background: transparent; border: 0; color: {c['apoio']}; font-size: 12px; }}
QToolButton[papel="mais"]:hover {{ color: {c['texto']}; }}
QMenu {{ background: {c['cartao']}; border: 1px solid {c['borda2']}; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 8px 14px; border-radius: 6px; font-size: 13px; }}
QMenu::item:selected {{ background: {c['destaque']}; }}
QMenu::separator {{ height: 1px; background: {c['linha']}; margin: 6px 8px; }}
QComboBox {{
    background: {c['fundo']}; border: 1px solid {c['borda2']}; border-radius: 8px; min-height: 40px; padding: 0 12px; font-size: 14px;
}}
QComboBox QAbstractItemView {{ background: {c['cartao']}; border: 1px solid {c['borda2']}; selection-background-color: {c['destaque']}; }}
QCheckBox {{ font-size: 14px; spacing: 10px; }}
QCheckBox::indicator {{ width: 22px; height: 22px; border-radius: 6px; border: 1.5px solid {c['borda3']}; background: {c['fundo']}; }}
QCheckBox::indicator:checked {{ background: {c['verde']}; border-color: {c['verde']}; }}
QSlider::groove:horizontal {{ height: 6px; background: {c['lateral']}; border-radius: 3px; }}
QSlider::sub-page:horizontal {{ background: {c['verde']}; border-radius: 3px; }}
QSlider::handle:horizontal {{ background: {c['texto']}; width: 20px; height: 20px; margin: -8px 0; border-radius: 10px; }}
"""


# ------------------------------------------------------------
# Peças
# ------------------------------------------------------------

# Altura de linha de cada papel, em px (o corpo do mockup usa 1,5 vezes o tamanho da fonte;
# títulos 1,15). O Qt não tem line-height em QSS, então vai por HTML no próprio rótulo.
ALTURA_DE_LINHA = {
    "texto": 24, "slogan": 21, "erro": 21, "alerta": 21,
    "nota": 20, "mono-claro": 20, "linha": 23,
}


class Rotulo(QLabel):
    """QLabel com altura de linha fixa (ver ALTURA_DE_LINHA)."""

    def __init__(self, texto="", papel=""):
        super().__init__()
        self._altura = ALTURA_DE_LINHA.get(papel, 0)
        self._plano = ""
        self.setProperty("papel", papel)
        self.setTextFormat(Qt.RichText)
        self.setText(texto)

    def setText(self, texto):
        self._plano = str(texto)
        corpo = html.escape(self._plano)
        super().setText(f'<p style="line-height:{self._altura}px; margin:0">{corpo}</p>' if self._altura else corpo)

    def plano(self):
        return self._plano


def rotulo(texto, papel, quebra=False, maximo=None, html_pronto=False):
    if quebra or papel in ALTURA_DE_LINHA:
        r = Rotulo(texto, papel)
    else:
        r = QLabel(texto)
        r.setProperty("papel", papel)
    if quebra:
        r.setWordWrap(True)
    if maximo:
        r.setMaximumWidth(maximo)
    if papel == "kicker":
        fonte = r.font()
        fonte.setLetterSpacing(QFont.AbsoluteSpacing, 0.96)   # 0,08 em de 12 px
        r.setFont(fonte)
    return r


def aplicar_papel(widget, papel):
    """Troca o papel (QSS por propriedade) de um widget que já existe."""
    widget.setProperty("papel", papel)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class Marcador(QWidget):
    """A bolinha dos passos: feito (verde com visto), ativo (anel verde com ponto) ou pendente (anel apagado)."""

    def __init__(self, estado="pendente", tamanho=28, parent=None):
        super().__init__(parent)
        self._estado = estado
        self.setFixedSize(tamanho, tamanho)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    @property
    def estado(self):
        return self._estado

    def definir(self, estado):
        if estado != self._estado:
            self._estado = estado
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        lado = float(self.width())
        if self._estado == "feito":
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(CORES["verde"]))
            p.drawEllipse(QRectF(0, 0, lado, lado))
            k = lado / 2 * 0.5 / 12      # o visto ocupa metade do círculo (grade de 24 do mockup)
            caminho = QPainterPath()
            caminho.moveTo(QPointF(5 * k, 12.5 * k))
            caminho.lineTo(QPointF(9.5 * k, 17 * k))
            caminho.lineTo(QPointF(19 * k, 7 * k))
            p.translate(lado / 2 - 12 * k, lado / 2 - 12 * k)
            caneta = QPen(QColor(CORES["escuro"]), max(2.0, lado * 0.115))
            caneta.setCapStyle(Qt.RoundCap)
            caneta.setJoinStyle(Qt.RoundJoin)
            p.setPen(caneta)
            p.setBrush(Qt.NoBrush)
            p.drawPath(caminho)
        else:
            cor = CORES["verde"] if self._estado == "ativo" else CORES["borda3"]
            p.setPen(QPen(QColor(cor), 2))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QRectF(1, 1, lado - 2, lado - 2))
            if self._estado == "ativo":
                miolo = lado * 0.36
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(CORES["verde"]))
                p.drawEllipse(QRectF((lado - miolo) / 2, (lado - miolo) / 2, miolo, miolo))
        p.end()
