"""A tela de voz (mockup "Voz"): ondas ao redor do microfone, o que a pessoa disse, e os modos."""

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

import tars_i18n
from tars_i18n import t

from . import icones, tema
from .controlador_voz import MODOS
from .tema import CORES


class Ondas(QWidget):
    """Três anéis e o círculo verde com o microfone (260 px). Pulsa enquanto ouve."""

    def __init__(self):
        super().__init__()
        self.setFixedSize(260, 260)
        self._fase = 0.0
        self._ativo = True
        self._mudo = False
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._passo)

    def definir(self, ativo, mudo=False):
        self._ativo, self._mudo = ativo, mudo
        if ativo and not mudo:
            self._timer.start()
        else:
            self._timer.stop()
            self._fase = 0.0
        self.update()

    def _passo(self):
        self._fase = (self._fase + 0.04) % 1.0
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        centro = QPointF(130, 130)
        import math
        pulso = (math.sin(self._fase * 2 * math.pi) + 1) / 2 if self._ativo and not self._mudo else 0.0
        for raio, cor, esp, opac in ((130, CORES["borda"], 1.5, 1.0), (102, "#3A4C86", 1.5, 1.0), (74 + 4 * pulso, CORES["verde"], 2.0, 0.5)):
            c = QColor(cor)
            c.setAlphaF(opac)
            caneta = QPen(c, esp)
            p.setPen(caneta)
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(centro, raio - esp, raio - esp)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(CORES["borda3"] if self._mudo else CORES["verde"]))
        p.drawEllipse(centro, 56, 56)
        pm = icones.pixmap("silenciar" if self._mudo else "microfone", CORES["escuro"], 44, 2.2)
        p.drawPixmap(int(centro.x() - 22), int(centro.y() - 22), pm)


class TelaVoz(QWidget):
    voltar = Signal()
    parar = Signal()
    silenciar = Signal()
    modo_mudou = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("principal")
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)

        cab = QFrame()
        cab.setObjectName("cabecalho")
        cab.setFixedHeight(68)
        h = QHBoxLayout(cab)
        h.setContentsMargins(32, 0, 32, 0)
        marca = QHBoxLayout()
        marca.setSpacing(12)
        marca.addWidget(tema.svg_widget(tema.monolito_svg(), 36))
        nome = QLabel(f'open<span style="color:{CORES["verde"]}">TARS</span>')
        nome.setTextFormat(Qt.RichText)
        nome.setStyleSheet("font-size: 17px; font-weight: 600;")
        marca.addWidget(nome)
        h.addLayout(marca)
        h.addStretch(1)
        self.pilula = QFrame()
        self.pilula.setProperty("papel", "pilula-modelo")
        pl = QHBoxLayout(self.pilula)
        pl.setContentsMargins(14, 6, 14, 6)
        pl.setSpacing(8)
        self.ponto = QLabel()
        self.ponto.setFixedSize(8, 8)
        self.ponto.setStyleSheet(f"background: {CORES['verde']}; border-radius: 4px;")
        self.status = QLabel(t("tv.ativo"))
        self.status.setProperty("papel", "pilula")
        pl.addWidget(self.ponto)
        pl.addWidget(self.status)
        self.pilula.setFixedHeight(34)
        h.addWidget(self.pilula, 0, Qt.AlignVCenter)
        h.addStretch(1)
        self.b_voltar = QPushButton(t("tv.voltar_texto"))
        self.b_voltar.setProperty("papel", "contorno")
        self.b_voltar.setCursor(Qt.PointingHandCursor)
        self.b_voltar.clicked.connect(self.voltar)
        h.addWidget(self.b_voltar)
        raiz.addWidget(cab)

        centro = QVBoxLayout()
        centro.setSpacing(0)
        centro.addStretch(1)
        self.ondas = Ondas()
        centro.addWidget(self.ondas, 0, Qt.AlignHCenter)
        centro.addSpacing(26)
        self.titulo = QLabel(t("tv.ouvindo"))
        self.titulo.setProperty("papel", "voz-titulo")
        self.titulo.setAlignment(Qt.AlignHCenter)
        self.sub = QLabel(t("tv.sub_ouvindo"))
        self.sub.setStyleSheet(f"color: {CORES['apoio']}; font-size: 14px;")
        self.sub.setAlignment(Qt.AlignHCenter)
        centro.addWidget(self.titulo)
        centro.addSpacing(6)
        centro.addWidget(self.sub)
        centro.addSpacing(26)
        self.faixa = QFrame()
        self.faixa.setProperty("papel", "faixa-voz")
        self.faixa.setFixedWidth(620)
        fl = QVBoxLayout(self.faixa)
        fl.setContentsMargins(22, 18, 22, 18)
        fl.setSpacing(6)
        rot = QLabel(t("tv.voce_disse").upper())
        rot.setProperty("papel", "mono")
        self.fala = QLabel("")
        self.fala.setProperty("papel", "voz-fala")
        self.fala.setWordWrap(True)
        fl.addWidget(rot)
        fl.addWidget(self.fala)
        centro.addWidget(self.faixa, 0, Qt.AlignHCenter)
        centro.addStretch(1)
        raiz.addLayout(centro, 1)

        rodape = QVBoxLayout()
        rodape.setContentsMargins(0, 0, 0, 28)
        rodape.setSpacing(14)
        self.segmentos = QFrame()
        self.segmentos.setProperty("papel", "segmentos")
        sl = QHBoxLayout(self.segmentos)
        sl.setContentsMargins(4, 4, 4, 4)
        sl.setSpacing(0)
        self.grupo = QButtonGroup(self)
        self.grupo.setExclusive(True)
        self.botoes_modo = {}
        for modo, chave in zip(MODOS, ("tv.segurar", "tv.continua", "tv.tars")):
            b = QPushButton(t(chave))
            b.setProperty("papel", "segmento-grande")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, m=modo: self.modo_mudou.emit(m))
            self.grupo.addButton(b)
            self.botoes_modo[modo] = b
            sl.addWidget(b)
        rodape.addWidget(self.segmentos, 0, Qt.AlignHCenter)
        acoes = QHBoxLayout()
        acoes.setSpacing(12)
        acoes.addStretch(1)
        self.b_silenciar = QPushButton(t("tv.silenciar"))
        self.b_silenciar.setProperty("papel", "contorno")
        self.b_silenciar.setCursor(Qt.PointingHandCursor)
        self.b_silenciar.clicked.connect(self.silenciar)
        self.b_parar = QPushButton("  " + t("tv.parar"))
        self.b_parar.setProperty("papel", "parar")
        self.b_parar.setIcon(icones.icone("parar", CORES["texto"], 14))
        self.b_parar.setCursor(Qt.PointingHandCursor)
        self.b_parar.setMinimumHeight(44)
        self.b_parar.clicked.connect(self.parar)
        acoes.addWidget(self.b_silenciar)
        acoes.addWidget(self.b_parar)
        acoes.addStretch(1)
        rodape.addLayout(acoes)
        self.info = QLabel(t("tv.rodape", idiomas=t("tv.idiomas")))
        self.info.setProperty("papel", "rodape")
        self.info.setAlignment(Qt.AlignHCenter)
        rodape.addWidget(self.info)
        raiz.addLayout(rodape)
        self.definir_modo("segurar")
        self.ao_estado("parado")

    def definir_modo(self, modo):
        self.botoes_modo[modo].setChecked(True)
        self.sub.setText(t({"segurar": "tv.sub_segurar", "continua": "tv.sub_ouvindo", "tars": "tv.sub_tars"}[modo]))

    def definir_fala(self, texto):
        self.fala.setText(texto)

    def ao_estado(self, estado):
        """Um estado do controlador de voz vira título e animação."""
        mudo = estado == "silenciado"
        chave = {"carregando": "tv.carregando", "ouvindo": "tv.ouvindo", "chamado": "tv.chamado",
                 "conversa": "tv.conversa", "transcrevendo": "tv.transcrevendo", "parado": "tv.parado",
                 "silenciado": "tv.silenciado", "falando": "tv.falando", "pensando": "tv.pensando"}.get(estado)
        if estado.startswith("erro:"):
            self.titulo.setText(t("tv.erro", erro=estado[5:]))
        elif chave:
            self.titulo.setText(t(chave))
        self.ondas.definir(estado in ("ouvindo", "chamado", "conversa", "transcrevendo", "falando"), mudo)
        self.b_silenciar.setText(t("tv.reativar") if mudo else t("tv.silenciar"))
        self.status.setText(t("tv.silenciado") if mudo else t("tv.ativo"))
        cor = CORES["borda3"] if mudo else CORES["verde"]
        self.ponto.setStyleSheet(f"background: {cor}; border-radius: 4px;")
