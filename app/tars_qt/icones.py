"""Os ícones do mockup (traço de 2 px, pontas arredondadas), desenhados em SVG na cor pedida."""

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

# nome -> (conteúdo SVG numa grade de 24, preenchido?)
_FORMAS = {
    "mais": ('<path d="M12 5v14M5 12h14"/>', False),
    "busca": ('<circle cx="11" cy="11" r="6"/><path d="M20 20l-4.5-4.5"/>', False),
    "parar": ('<rect x="4" y="4" width="16" height="16" rx="3"/>', True),
    "clipe": ('<path d="M21 11.5l-8.6 8.6a5 5 0 0 1-7.1-7.1l8.6-8.6a3.4 3.4 0 0 1 4.8 4.8l-8.6 8.6a1.7 1.7 0 0 1-2.4-2.4l7.9-7.9"/>', False),
    "microfone": ('<rect x="9" y="3" width="6" height="12" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>', False),
    "enviar": ('<path d="M5 12h14M13 6l6 6-6 6"/>', False),
    "memoria": ('<path d="M4 7l8-4 8 4-8 4-8-4zM4 12l8 4 8-4M4 17l8 4 8-4"/>', False),
    "config": ('<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1"/>', False),
    "visto": ('<path d="M5 12.5l4.5 4.5L19 7"/>', False),
    "fechar": ('<path d="M6 6l12 12M18 6L6 18"/>', False),
    "lixeira": ('<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>', False),
    "voltar": ('<path d="M19 12H5M11 6l-6 6 6 6"/>', False),
    "sonda": ('<circle cx="12" cy="12" r="2"/><path d="M12 4a8 8 0 0 1 8 8M12 8a4 4 0 0 1 4 4M4 12a8 8 0 0 0 8 8"/>', False),
    "sino": ('<path d="M6 16v-5a6 6 0 0 1 12 0v5l2 2H4l2-2zM10 21a2 2 0 0 0 4 0"/>', False),
    "silenciar": ('<path d="M9 9v3a3 3 0 0 0 5.1 2.1M15 9.3V6a3 3 0 0 0-5.9-.8M5 11a7 7 0 0 0 11.2 5.6M19 11a7 7 0 0 1-.6 2.8M12 18v3M3 3l18 18"/>', False),
}


def svg_do_icone(nome, cor, espessura=2.0):
    corpo, cheio = _FORMAS[nome]
    preenchimento = cor if cheio else "none"
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        f'fill="{preenchimento}" stroke="{cor}" stroke-width="{espessura}" '
        f'stroke-linecap="round" stroke-linejoin="round">{corpo}</svg>'
    )


def pixmap(nome, cor, lado=20, espessura=2.0, dpr=2.0):
    renderizador = QSvgRenderer(QByteArray(svg_do_icone(nome, cor, espessura).encode()))
    pm = QPixmap(int(lado * dpr), int(lado * dpr))
    pm.fill(Qt.transparent)
    pintor = QPainter(pm)
    renderizador.render(pintor)
    pintor.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def icone(nome, cor, lado=20, espessura=2.0):
    return QIcon(pixmap(nome, cor, lado, espessura))
