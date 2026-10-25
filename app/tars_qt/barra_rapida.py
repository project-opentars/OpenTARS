"""A barra rápida (atalho global ou `opentars-gui --rapido`): uma caixa flutuante no alto da tela.
Pergunta, vê a resposta, some. Quem trabalha é a janela principal; a barra só espelha a conversa.

5.2 (F4): é também o lançador do assistente: vazia, mostra as capacidades do mock-up (tarefa, tela, buscar arquivo,
web, lembrete). "Buscar um arquivo" roda aqui mesmo, sem modelo (tars_busca_arquivos); as outras preenchem o pedido."""
import datetime
import threading
from pathlib import Path

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QTextBrowser, QVBoxLayout, QWidget

import tars_busca_arquivos as busca
import tars_plataforma as plataforma
from tars_i18n import t

from . import tema
from .conversa import abrir_link_seguro
from .tema import CORES

LARGURA = 680
ALTURA_MAXIMA_RESPOSTA = 340


CAPACIDADES = ("tarefa", "tela", "arquivo", "foto", "web", "lembrete")


class BarraRapida(QFrame):
    enviar = Signal(str)
    parar = Signal()
    abrir_janela = Signal()
    arquivos_achados = Signal(object)
    editar_foto = Signal()                  # 25/10: "Editar uma foto": o assistente abre o seletor e o painel da foto

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
        self.entrada.textChanged.connect(self._ao_digitar)
        topo.addWidget(self.entrada, 1)
        v.addLayout(topo)

        self.capacidades = QWidget()
        lista = QVBoxLayout(self.capacidades)
        lista.setContentsMargins(0, 2, 0, 2)
        lista.setSpacing(2)
        for cap in CAPACIDADES:
            b = QPushButton()          # um botão de verdade (Tab e Enter chegam nele), com título e explicação dentro
            b.setAccessibleName(t(f"rapido.cap.{cap}"))
            b.setCursor(Qt.PointingHandCursor)
            b.setMinimumHeight(52)
            b.setStyleSheet(f"QPushButton {{ border: 0; border-radius: 10px; background: transparent; }} "
                            f"QPushButton:hover, QPushButton:focus {{ background: {CORES['destaque']}; }}")
            dentro = QVBoxLayout(b)
            dentro.setContentsMargins(12, 6, 12, 6)
            dentro.setSpacing(1)
            for texto, estilo in ((t(f"rapido.cap.{cap}"), f"font-size: 14px; font-weight: 600; color: {CORES['texto']};"),
                                  (t(f"rapido.cap.{cap}_desc"), f"font-size: 12px; color: {CORES['apoio']};")):
                rot = QLabel(texto)
                rot.setStyleSheet(estilo + " background: transparent;")
                rot.setAttribute(Qt.WA_TransparentForMouseEvents)
                dentro.addWidget(rot)
            b.clicked.connect(lambda _=False, c=cap: self._escolher(c))
            lista.addWidget(b)
        v.addWidget(self.capacidades)
        self.modo = "pedido"
        self.achados = []
        self.arquivos_achados.connect(self._mostrar_arquivos)

        self.resposta = QTextBrowser()
        self.resposta.setOpenLinks(False)
        self.resposta.setOpenExternalLinks(False)
        self.resposta.anchorClicked.connect(self._link)
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
            self.modo = "pedido"
            self.entrada.setPlaceholderText(t("rapido.dica"))
            self.capacidades.setVisible(not self.entrada.toPlainText().strip())
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

    # -- lançador (5.2, F4) --------------------------------------------------------------------------
    def _ao_digitar(self):
        if self.entrada.toPlainText().strip() or self.resposta.isVisibleTo(self):
            self.capacidades.hide()

    def _escolher(self, cap):
        self.capacidades.hide()
        if cap == "foto":
            self.hide()
            self.editar_foto.emit()
            return
        if cap == "arquivo":
            self.modo = "arquivo"
            self.entrada.setPlaceholderText(t("busca.dica"))
        elif cap != "tarefa":
            self.entrada.setPlainText(t(f"rapido.pref.{cap}"))
            self.entrada.moveCursor(self.entrada.textCursor().End)
        self.entrada.setFocus()
        self.adjustSize()

    def _buscar_arquivos(self, frase):
        self.status.setText(t("busca.procurando"))
        self._texto = f"**{frase}**\n\n*{t('busca.procurando')}*"
        self.resposta.show()
        self._desenhar()
        threading.Thread(target=lambda: self.arquivos_achados.emit(busca.buscar(frase)), daemon=True).start()

    def _mostrar_arquivos(self, achados):
        self.achados = achados
        self.status.setText(t("rapido.ajuda"))
        if not achados:
            self._texto = t("busca.nada")
        else:
            casa = str(Path.home())
            linhas = [t("busca.achados", n=len(achados)), ""]
            for i, a in enumerate(achados):        # no markdown do Qt, _texto_ sai sublinhado como link: itálico com *
                pasta = a["pasta"].replace(casa, "~", 1)
                data = datetime.date.fromtimestamp(a["modificado"]).strftime("%d/%m/%Y")
                detalhe = f"{pasta} · {data}" + (f" · {t('busca.sem_texto')}" if a["sem_texto"] else "")
                linhas += [f"**{a['nome']}** · [{t('busca.abrir')}](opentars-abrir:{i}) · "
                           f"[{t('busca.pasta')}](opentars-pasta:{i})  ", detalhe + ("  " if a["trecho"] else "")] + \
                          ([f"*{a['trecho']}*"] if a["trecho"] else []) + ["", "&nbsp;", ""]      # o markdown do Qt não dá margem
            linhas.append(f"*{t('busca.nota')}*")
            self._texto = "\n".join(linhas)
        self._desenhar()

    def _link(self, url):
        """Os links dos resultados da busca abrem só o que a busca achou (pelo número); o resto vai pelo caminho seguro."""
        texto = url.toString()
        esquema, _, numero = texto.partition(":")
        if esquema in ("opentars-abrir", "opentars-pasta") and numero.isdigit() and int(numero) < len(self.achados):
            achado = self.achados[int(numero)]
            plataforma.abrir(achado["caminho"] if esquema == "opentars-abrir" else achado["pasta"])
            return
        abrir_link_seguro(texto)

    def _enviar(self):
        texto = self.entrada.toPlainText().strip()
        if not texto or self._ocupado:
            return
        if self.modo == "arquivo":
            self.entrada.clear()
            self._buscar_arquivos(texto)
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
