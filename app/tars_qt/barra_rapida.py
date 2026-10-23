"""A barra rápida (atalho global ou `opentars-gui --rapido`): uma caixa flutuante no alto da tela.
Pergunta, vê a resposta, some. Quem trabalha é a janela principal; a barra só espelha a conversa."""

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QTextBrowser, QVBoxLayout

from tars_i18n import t

from . import tema
from .conversa import abrir_link_seguro
from .tema import CORES

LARGURA = 680
ALTURA_MAXIMA_RESPOSTA = 340


class BarraRapida(QFrame):
    enviar = Signal(str)
    parar = Signal()
    abrir_janela = Signal()

    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint)
        self.setObjectName("barra-rapida")
        self.setAttribute(Qt.WA_ShowWithoutActivating, False)
        self.setWindowTitle("openTARS")
        self.setFixedWidth(LARGURA)
        self.setStyleSheet(
            f"QFrame#barra-rapida {{ background: {CORES['cartao']}; border: 1px solid {CORES['borda2']}; border-radius: 16px; }}")
        v = QVBoxLayout(self)
        v.setContentsMargins(18, 14, 18, 12)
        v.setSpacing(8)

        topo = QHBoxLayout()
        topo.setSpacing(12)
        topo.addWidget(tema.svg_widget(tema.monolito_svg(), 28), 0, Qt.AlignVCenter)
        from .principal import CaixaEntrada      # a mesma caixa da janela: Enter envia, Shift+Enter quebra
        self.entrada = CaixaEntrada()
        self.entrada.setPlaceholderText(t("rapido.dica"))
        self.entrada.enviar.connect(self._enviar)
        topo.addWidget(self.entrada, 1)
        v.addLayout(topo)

        self.resposta = QTextBrowser()
        self.resposta.setOpenLinks(False)
        self.resposta.setOpenExternalLinks(False)
        self.resposta.anchorClicked.connect(lambda u: abrir_link_seguro(u.toString()))
        self.resposta.setFrameShape(QFrame.NoFrame)
        self.resposta.setStyleSheet("background: transparent; border: 0; font-size: 14px;")
        self.resposta.hide()
        # contentsChanged dispara VÁRIAS vezes no meio do setMarkdown, com o documento pela metade: mexer no layout e
        # no tamanho da janela aí dentro é frágil. Só marca e ajusta uma vez, depois que o setMarkdown terminou.
        self._ajuste_marcado = False
        self.resposta.document().contentsChanged.connect(self._marcar_ajuste)
        v.addWidget(self.resposta)

        rodape = QHBoxLayout()
        self.status = QLabel(t("rapido.ajuda"))
        self.status.setProperty("papel", "mono")
        self.link = QPushButton(t("rapido.abrir_janela") + " ↗")
        self.link.setProperty("papel", "link")
        self.link.setCursor(Qt.PointingHandCursor)
        self.link.clicked.connect(self._abrir_janela)
        rodape.addWidget(self.status, 1)
        rodape.addWidget(self.link)
        v.addLayout(rodape)

        self.perguntas = 0
        self._recebeu = False
        self._ocupado = False
        self._texto = ""
        self._sujo = False
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._desenhar)

    # -- uso ---------------------------------------------------------------------------------------
    def tem_resposta(self):
        return self.resposta.isVisibleTo(self)

    def mostrar(self):
        if not self.isVisible():
            self.perguntas = 0
            self._texto = ""
            self.resposta.hide()
            self.resposta.clear()
            tela = QApplication.primaryScreen().availableGeometry() if QApplication.primaryScreen() else None
            if tela is not None:
                self.adjustSize()
                self.move(QPoint(tela.x() + (tela.width() - self.width()) // 2, tela.y() + int(tela.height() * 0.2)))
        self.show()
        self.raise_()
        self.activateWindow()
        self.entrada.setFocus()

    def esconder(self):
        self.hide()

    def _enviar(self):
        texto = self.entrada.toPlainText().strip()
        if not texto or self._ocupado:
            return
        self.entrada.clear()
        self.perguntas += 1
        self._recebeu = False
        self._texto = f"**{texto}**\n\n"
        self.resposta.show()
        self._desenhar()
        self.enviar.emit(texto)

    def recusar(self, texto):
        """A janela principal estava ocupada e não aceitou a pergunta: devolve o texto à caixa e avisa."""
        self.perguntas = max(0, self.perguntas - 1)
        self.resposta.hide()
        self._texto = ""
        self.entrada.setPlainText(texto)
        self.definir_ocupado(False)
        self.status.setText(t("rapido.ocupado"))

    def _abrir_janela(self):
        self.esconder()
        self.abrir_janela.emit()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            if self._ocupado:
                self.parar.emit()
            else:
                self.esconder()
            return
        if e.key() in (Qt.Key_Return, Qt.Key_Enter) and e.modifiers() & Qt.ControlModifier:
            self._abrir_janela()
            return
        super().keyPressEvent(e)

    # -- o que a janela principal manda -----------------------------------------------------------------------
    def definir_ocupado(self, ocupado, texto=""):
        self._ocupado = ocupado
        self.status.setText(texto if ocupado and texto else t("rapido.ajuda"))
        self.entrada.setReadOnly(ocupado)

    def acrescentar(self, trecho):
        self._recebeu = True
        self._texto += trecho
        self._sujo = True
        if not self._timer.isActive():
            self._timer.start()

    def concluir(self, texto_final=""):
        """Resposta pronta: se nada chegou em pedaços, mostra o texto inteiro."""
        if texto_final and not self._recebeu:
            self._texto += texto_final
        self._timer.stop()
        self._desenhar()
        self.definir_ocupado(False)

    def precisa_de_voce(self):
        self._texto += "\n\n_" + t("jp.espera_voce") + "_"
        self._desenhar()

    def _desenhar(self):
        self.resposta.setMarkdown(self._texto)
        self._sujo = False

    def _marcar_ajuste(self):
        if not self._ajuste_marcado:
            self._ajuste_marcado = True
            QTimer.singleShot(0, self._ajustar)

    def _ajustar(self):
        self._ajuste_marcado = False
        if not self.resposta.isVisibleTo(self):
            return
        altura = int(self.resposta.document().size().height()) + 10
        self.resposta.setFixedHeight(max(40, min(ALTURA_MAXIMA_RESPOSTA, altura)))
        self.adjustSize()
        self.resposta.verticalScrollBar().setValue(self.resposta.verticalScrollBar().maximum())
