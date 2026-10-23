"""5.2: o painel das ações de texto (atalho global com um texto selecionado em qualquer programa).

Reescrever (corrigir, mais formal, mais simples), resumir, traduzir (pt/en) e perguntar sobre o trecho, como nos mock-ups
aprovados em 20/10. Texto entra, texto sai: nenhuma ferramenta, nada é executado. O pedido ao modelo segue o contrato do
treino (`tars_acoes_texto`); a resposta chega aos pedaços, numa thread, e é desenhada pela fila do `fio`."""
import threading

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextBrowser,
                               QVBoxLayout, QWidget)

import tars_acoes_texto as acoes_lib
import tars_assistente as assistente
import tars_plataforma as plataforma
from tars_i18n import t

from . import fio, icones, tema
from .tema import CORES

LARGURA = 440
ABAS = ("reescrever", "resumir", "traduzir", "perguntar")
OPCOES = {"reescrever": ("corrigir", "formal", "informal"), "traduzir": ("para_en", "para_pt")}


class PainelAcoes(QFrame):
    pedaco = Signal(str)
    terminou = Signal(str, str)        # (texto final, erro)
    substituir = Signal(str)           # quem cola é a janela principal (ela tem o pyautogui do núcleo)

    def __init__(self, host, modelos_instalados, lite, principal):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setObjectName("painel-acoes")
        self.setWindowTitle("openTARS")
        self.setFixedWidth(LARGURA)
        self.setStyleSheet(f"QFrame#painel-acoes {{ background: {CORES['fundo']}; border: 1px solid {CORES['borda2']}; "
                           "border-radius: 16px; }")
        self.host, self.instalados, self.lite, self.principal = host, modelos_instalados, lite, principal
        self.texto, self.resultado, self.aba, self.opcao = "", "", "reescrever", "corrigir"
        self._cancelar = threading.Event()
        self._fio = None

        v = QVBoxLayout(self)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(12)

        topo = QHBoxLayout()
        topo.setSpacing(10)
        topo.addWidget(tema.svg_widget(tema.monolito_svg(), 24), 0, Qt.AlignVCenter)
        topo.addWidget(tema.rotulo("openTARS", "titulo-cartao"))
        self.modelo = QLabel()
        self.modelo.setProperty("papel", "pilula")
        topo.addWidget(self.modelo)
        topo.addStretch(1)
        fechar = QPushButton()
        fechar.setProperty("papel", "icone")
        fechar.setIcon(icones.icone("fechar", CORES["apoio"], 16))
        fechar.setAccessibleName(t("acoes.fechar"))
        fechar.setFixedSize(36, 36)
        fechar.clicked.connect(self.fechar)
        topo.addWidget(fechar)
        v.addLayout(topo)

        self.abas = QButtonGroup(self)
        self.linha_abas = QWidget()
        linha = QHBoxLayout(self.linha_abas)
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(6)
        for aba in ABAS:
            b = QPushButton(t(f"acoes.aba.{aba}"))
            b.setProperty("papel", "segmento")
            b.setCheckable(True)
            b.setMinimumHeight(40)
            self.abas.addButton(b)
            b.clicked.connect(lambda _=False, a=aba: self.escolher_aba(a))
            linha.addWidget(b, 1)
        v.addWidget(self.linha_abas)

        self.chips = QHBoxLayout()
        self.chips.setSpacing(8)
        v.addLayout(self.chips)
        self._botoes_opcao = {}

        self.trecho = tema.rotulo("", "nota", quebra=True)
        v.addWidget(self.trecho)

        self.linha_pergunta = QWidget()
        lp = QHBoxLayout(self.linha_pergunta)
        lp.setContentsMargins(0, 0, 0, 0)
        self.pergunta = QLineEdit()
        self.pergunta.setPlaceholderText(t("acoes.pergunta_dica"))
        self.pergunta.setAccessibleName(t("acoes.pergunta_dica"))
        self.pergunta.returnPressed.connect(self.rodar)
        perguntar = QPushButton()
        perguntar.setProperty("papel", "primario")
        perguntar.setIcon(icones.icone("enviar", CORES["escuro"], 20, 2.2))
        perguntar.setAccessibleName(t("acoes.enviar_pergunta"))
        perguntar.setFixedSize(40, 40)
        perguntar.clicked.connect(self.rodar)
        lp.addWidget(self.pergunta, 1)
        lp.addWidget(perguntar)
        v.addWidget(self.linha_pergunta)

        self.caixa = caixa = QFrame()
        caixa.setProperty("papel", "painel")
        cv = QVBoxLayout(caixa)
        cv.setContentsMargins(14, 12, 14, 12)
        cv.setSpacing(6)
        self.titulo_resultado = tema.rotulo("", "nota")
        self.saida = QTextBrowser()
        self.saida.setOpenLinks(False)
        self.saida.setFrameShape(QFrame.NoFrame)
        self.saida.setMinimumHeight(90)
        self.saida.setMaximumHeight(260)
        self.saida.setStyleSheet(f"background: transparent; color: {CORES['texto']}; font-size: 15px;")
        cv.addWidget(self.titulo_resultado)
        cv.addWidget(self.saida)
        v.addWidget(caixa)

        botoes = QHBoxLayout()
        self.botao_substituir = QPushButton(t("acoes.substituir"))
        self.botao_substituir.setProperty("papel", "primario")
        self.botao_substituir.setMinimumHeight(40)
        self.botao_substituir.clicked.connect(self._substituir)
        self.botao_copiar = QPushButton(t("acoes.copiar"))
        self.botao_copiar.setProperty("papel", "contorno")
        self.botao_copiar.setMinimumHeight(40)
        self.botao_copiar.clicked.connect(self._copiar)
        descartar = QPushButton(t("acoes.descartar"))
        descartar.setProperty("papel", "link")
        descartar.clicked.connect(self.fechar)
        botoes.addWidget(self.botao_substituir, 1)
        botoes.addWidget(self.botao_copiar)
        botoes.addWidget(descartar)
        v.addLayout(botoes)

        self.rodape = tema.rotulo(t("acoes.rodape", atalho=t(f"acoes.atalho_{plataforma.sistema()}")), "nota", quebra=True)
        v.addWidget(self.rodape)

        self.pedaco.connect(self._acrescentar)
        self.terminou.connect(self._terminou)

    # -- abrir ------------------------------------------------------------------------------------------
    def abrir(self, texto):
        """Mostra o painel para este trecho. Sem trecho, só explica como usar."""
        self.texto = str(texto or "").strip()
        self.resultado = ""
        self.saida.clear()
        if not self.texto:
            self._estado_vazio()
        else:
            resumo = " ".join(self.texto.split())
            self.trecho.setText(t("acoes.trecho", trecho=resumo[:140] + ("…" if len(resumo) > 140 else "")))
            if len(self.texto) > acoes_lib.LIMITE_TEXTO:
                self.trecho.setText(self.trecho.text() + " " + t("acoes.cortado", n=acoes_lib.LIMITE_TEXTO))
            self.escolher_aba("reescrever")
        self._posicionar()
        self.show()
        self.raise_()
        self.activateWindow()

    def _estado_vazio(self):
        self.linha_abas.hide()
        self.caixa.hide()
        self.modelo.hide()
        self._limpar_chips()
        self.linha_pergunta.hide()
        self.trecho.setText(t("acoes.sem_texto"))
        self.titulo_resultado.setText("")
        self.botao_substituir.hide()
        self.botao_copiar.hide()

    def _posicionar(self):
        """Perto do ponteiro, sem sair da tela."""
        self.adjustSize()
        tela = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        area = tela.availableGeometry()
        p = QCursor.pos() + QPoint(24, 24)
        x = min(max(area.left() + 12, p.x()), area.right() - self.width() - 12)
        y = min(max(area.top() + 12, p.y()), area.bottom() - self.height() - 12)
        self.move(x, y)

    # -- abas e opções --------------------------------------------------------------------------------
    def escolher_aba(self, aba):
        self.aba = aba
        for parte in (self.linha_abas, self.caixa, self.modelo):
            parte.show()
        for b, nome in zip(self.abas.buttons(), ABAS):
            b.setChecked(nome == aba)
        self._limpar_chips()
        for opcao in OPCOES.get(aba, ()):
            b = QPushButton(t(f"acoes.opcao.{opcao}"))
            b.setProperty("papel", "chip")
            b.setCheckable(True)
            b.setMinimumHeight(36)
            b.clicked.connect(lambda _=False, o=opcao: self.escolher_opcao(o))
            self.chips.addWidget(b)
            self._botoes_opcao[opcao] = b
        self.chips.addStretch(1)
        perguntar = aba == "perguntar"
        self.linha_pergunta.setVisible(perguntar)
        self.botao_substituir.setVisible(not perguntar)     # perguntar só responde: nada é colado de volta
        self.botao_copiar.setVisible(True)
        self.titulo_resultado.setText(t(f"acoes.resultado.{aba}"))
        self.saida.clear()
        if perguntar:
            self.pergunta.setFocus()
            return
        opcao = {"reescrever": "corrigir", "traduzir": acoes_lib.acao_de_traduzir(self.texto)}.get(aba, aba)
        self.escolher_opcao(opcao)

    def _limpar_chips(self):
        while self.chips.count():
            item = self.chips.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._botoes_opcao = {}

    def escolher_opcao(self, opcao):
        self.opcao = opcao
        for nome, b in self._botoes_opcao.items():
            b.setChecked(nome == opcao)
        self.rodar()

    # -- o modelo -----------------------------------------------------------------------------------------
    def acao_atual(self):
        return "perguntar" if self.aba == "perguntar" else self.opcao

    def rodar(self):
        if not self.texto:
            return
        pergunta = self.pergunta.text().strip() if self.aba == "perguntar" else None
        if self.aba == "perguntar" and not pergunta:
            return
        self._cancelar.set()
        self._cancelar = threading.Event()
        cancelar = self._cancelar
        self.resultado = ""
        self.saida.setPlainText(t("acoes.pensando"))
        self._recebeu = False
        modelo = acoes_lib.escolher_modelo(self.instalados, self.lite, self.principal)
        manter = assistente.ligado()
        self.modelo.setText(t("acoes.modelo", modelo=_nome_curto(modelo)))
        acao = self.acao_atual()

        def trabalho():
            erro, texto = "", ""
            try:
                texto = acoes_lib.rodar(acao, self.texto, modelo, self.host, pergunta=pergunta, cancelar=cancelar, manter=manter,
                                        ao_pedaco=lambda p: not cancelar.is_set() and fio.emitir(self.pedaco, p))
            except Exception as e:  # noqa: BLE001  (Ollama fora, modelo faltando: vira texto na janela)
                erro = str(e) or type(e).__name__
            if not cancelar.is_set():
                fio.emitir(self.terminou, texto, erro)

        self._fio = threading.Thread(target=trabalho, daemon=True)
        self._fio.start()

    def _acrescentar(self, pedaco):
        if not self._recebeu:
            self._recebeu = True
            self.saida.clear()
        self.resultado += pedaco
        self.saida.setPlainText(self.resultado)

    def _terminou(self, texto, erro):
        if erro:
            self.resultado = ""
            self.saida.setPlainText(t("acoes.erro", erro=erro[:200]))
            return
        self.resultado = texto
        self.saida.setPlainText(texto or t("acoes.vazio"))

    # -- botões -------------------------------------------------------------------------------------------
    def _copiar(self):
        if self.resultado:
            try:
                plataforma.escrever_area_de_transferencia(self.resultado)
            except OSError:
                QGuiApplication.clipboard().setText(self.resultado)
            self.botao_copiar.setText(t("acoes.copiado"))
            QTimer.singleShot(1500, lambda: self.botao_copiar.setText(t("acoes.copiar")))

    def _substituir(self):
        if self.resultado and self.aba != "perguntar":
            texto = self.resultado
            self.fechar()
            self.substituir.emit(texto)

    def fechar(self):
        self._cancelar.set()
        self.hide()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.fechar()
            return
        super().keyPressEvent(e)


def _nome_curto(modelo):
    """'ProjectOpenTARS/Gargantua-2:lite' -> 'Gargantua-2:lite' (a pílula é pequena)."""
    return str(modelo or "").rsplit("/", 1)[-1].replace(":latest", "")
