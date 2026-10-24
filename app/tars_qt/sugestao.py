"""5.2 (F4): o cartão de sugestão pelo programa em uso (mock-up "contexto do programa ativo"). Aparece no canto, por cima,
sem tirar o foco do programa onde a pessoa escreve (o "Revisar" depois lê a seleção dele)."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QVBoxLayout

from tars_i18n import t

from . import tema
from .tema import CORES

LARGURA = 360


class CartaoSugestao(QFrame):
    revisar = Signal()
    silenciar = Signal()

    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setObjectName("cartao-sugestao")
        self.setFixedWidth(LARGURA)
        self.setStyleSheet(f"QFrame#cartao-sugestao {{ background: {CORES['fundo']}; border: 1px solid {CORES['borda2']}; "
                           "border-radius: 14px; }")
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 14, 16, 12)
        v.setSpacing(10)
        topo = QHBoxLayout()
        topo.addWidget(tema.svg_widget(tema.monolito_svg(), 20), 0, Qt.AlignVCenter)
        topo.addWidget(tema.rotulo(t("ctx.titulo"), "titulo-cartao"))
        topo.addStretch(1)
        v.addLayout(topo)
        self.texto = tema.rotulo("", "texto", quebra=True)
        v.addWidget(self.texto)
        botoes = QHBoxLayout()
        for texto, papel, acao in ((t("ctx.revisar"), "primario", self.revisar.emit), (t("ctx.agora_nao"), "contorno", self.hide)):
            b = QPushButton(texto)
            b.setProperty("papel", papel)
            b.setMinimumHeight(36)
            b.clicked.connect(acao)
            botoes.addWidget(b)
        botoes.addStretch(1)
        v.addLayout(botoes)
        parar = QPushButton(t("ctx.parar"))
        parar.setProperty("papel", "link")
        parar.clicked.connect(self.silenciar.emit)
        v.addWidget(parar, 0, Qt.AlignLeft)
        v.addWidget(tema.rotulo(t("ctx.nota"), "nota", quebra=True))

    def mostrar(self, sugestao):
        self.texto.setText(t(f"ctx.{sugestao}"))
        self.adjustSize()
        tela = QGuiApplication.primaryScreen()
        if tela is not None:
            area = tela.availableGeometry()
            self.move(area.right() - self.width() - 16, area.bottom() - self.height() - 16)
        self.show()
