"""A janela principal do openTARS 5.0 (mockup "Main"): barra lateral com o histórico, cabeçalho com a IA em uso e o botão
Parar, a conversa (balões, ferramentas, etapas, aprovação) e o compositor com anexos e voz.

O núcleo (tars.py) continua sendo o da 4.6; a ponte (ponte.py) liga os dois."""

import datetime as dt
import os
import threading
import time

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QFont, QFontMetrics, QKeySequence, QShortcut, QTextCursor
from PySide6.QtWidgets import (QApplication, QButtonGroup, QFileDialog, QFrame, QHBoxLayout, QLabel, QMainWindow, QMenu,
                               QLineEdit, QPlainTextEdit, QPushButton, QScrollArea, QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget)

import tars_atalho
import tars_atualizacao
import tars_historico
import tars_i18n
import tars_acoes_texto as acoes_lib
import tars_assistente as assistente
import tars_modos as modos
import tars_plataforma as plataforma
import tars_primeiro_uso as pu
import tars_rotinas as agenda_lib
from tars_i18n import t

from . import fio, icones, tema
from .configuracoes import PaginaConfiguracoes
from .controlador_voz import ControladorVoz
from .avisos import Sino
from .acoes import PainelAcoes
from .barra_rapida import BarraRapida
from .conversa import AreaConversa, CartaoAprovacao, MensagemIA
from .mascote import Mascote
from .ponte import Ponte, limpar_saida
from .tela_voz import TelaVoz
from .tema import CORES, rotulo

LARGURA_LATERAL = 272
FERRAMENTAS_SO_OLHAM = {"take_screenshot", "list_elements", "get_screen_text", "describe_screen", "list_windows",
                        "get_clipboard", "read_file", "wait"}


MINUTOS_OCIOSO = float(os.environ.get("TARS_OCIOSO_MIN", "30"))


def _botao(texto, papel, ao_clicar=None):
    b = QPushButton(texto)
    b.setProperty("papel", papel)
    b.setCursor(Qt.PointingHandCursor)
    if ao_clicar:
        b.clicked.connect(ao_clicar)
    return b


def _repolir(w):
    w.style().unpolish(w)
    w.style().polish(w)


# ------------------------------------------------------------
# Barra lateral
# ------------------------------------------------------------


def _sem_erro(funcao, *args):
    """Para threads de fundo cujo erro não tem a quem mostrar (Ollama fora ao abrir, por exemplo)."""
    try:
        funcao(*args)
    except Exception:  # noqa: BLE001
        pass

class Lateral(QFrame):
    nova = Signal()
    abrir = Signal(str)
    apagar = Signal(str)
    buscar = Signal(str)
    memoria = Signal()
    probes = Signal()
    config = Signal()
    atualizar = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("lateral2")
        self.setFixedWidth(LARGURA_LATERAL)
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 20, 14, 16)
        v.setSpacing(0)

        marca = QHBoxLayout()
        marca.setContentsMargins(6, 0, 6, 18)
        marca.setSpacing(12)
        marca.addWidget(tema.svg_widget(tema.monolito_svg(), 40))
        col = QVBoxLayout()
        col.setSpacing(4)
        nome = QLabel(f'open<span style="color:{CORES["verde"]}">TARS</span>')
        nome.setTextFormat(Qt.RichText)
        nome.setStyleSheet("font-size: 19px; font-weight: 600;")
        selo = QHBoxLayout()
        selo.setSpacing(6)
        selo.addWidget(tema.svg_widget(tema.selo_svg(), 14))
        self.versao = rotulo("", "selo")
        self.versao.setStyleSheet(f"color: {CORES['apoio']};")
        selo.addWidget(self.versao)
        selo.addStretch(1)
        col.addWidget(nome)
        col.addLayout(selo)
        marca.addLayout(col, 1)
        v.addLayout(marca)

        self.b_nova = _botao("  " + t("jp.nova"), "nova", self.nova)
        self.b_nova.setIcon(icones.icone("mais", CORES["verde"], 18))
        self.b_nova.setIconSize(QSize(18, 18))
        v.addWidget(self.b_nova)
        v.addSpacing(12)

        caixa = QFrame()
        caixa.setStyleSheet(f"QFrame#caixa_busca {{ background: {CORES['fundo']}; border: 1px solid {CORES['linha']}; border-radius: 10px; }}")
        caixa.setObjectName("caixa_busca")
        caixa.setFixedHeight(44)
        self.caixa_busca = caixa
        ch = QHBoxLayout(caixa)
        ch.setContentsMargins(12, 0, 12, 0)
        ch.setSpacing(8)
        lupa = QLabel()
        lupa.setPixmap(icones.pixmap("busca", CORES["apoio"], 16))
        self.busca = QLineEdit()
        self.busca.setObjectName("busca")
        self.busca.setPlaceholderText(t("jp.buscar"))
        self.busca.setStyleSheet("font-size: 14px; background: transparent; border: 0; padding: 0;")
        self.busca.textChanged.connect(self._ao_buscar)
        ch.addWidget(lupa)
        ch.addWidget(self.busca, 1)
        v.addWidget(caixa)
        v.addSpacing(18)

        self.rolagem = QScrollArea()
        self.rolagem.setWidgetResizable(True)
        self.rolagem.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.rolagem.setFrameShape(QFrame.NoFrame)
        self.lista_w = QWidget()
        self.lista = QVBoxLayout(self.lista_w)
        self.lista.setContentsMargins(0, 0, 0, 0)
        self.lista.setSpacing(2)
        self.lista.addStretch(1)
        self.rolagem.setWidget(self.lista_w)
        v.addWidget(self.rolagem, 1)

        # cartão de versão nova (só aparece quando há)
        self.cartao_versao = QFrame()
        self.cartao_versao.setProperty("papel", "aviso-versao")
        cv = QVBoxLayout(self.cartao_versao)
        cv.setContentsMargins(14, 12, 14, 12)
        cv.setSpacing(2)
        self.v_titulo = QLabel("")
        self.v_titulo.setStyleSheet("font-size: 13px; font-weight: 600;")
        self.v_sub = QLabel(t("jp.nada_sem_clique"))
        self.v_sub.setWordWrap(True)
        self.v_sub.setStyleSheet(f"font-size: 12px; color: {CORES['apoio']};")
        self.b_atualizar = _botao(t("jp.atualizar"), "atualizar", self.atualizar)
        cv.addWidget(self.v_titulo)
        cv.addWidget(self.v_sub)
        cv.addSpacing(8)
        cv.addWidget(self.b_atualizar)
        self.cartao_versao.hide()
        v.addSpacing(10)
        v.addWidget(self.cartao_versao)
        v.addSpacing(10)

        linha = QFrame()
        linha.setFixedHeight(1)
        linha.setStyleSheet(f"background: {CORES['linha']};")
        v.addWidget(linha)
        v.addSpacing(10)
        self.b_memoria = _botao("  " + t("jp.memoria"), "rodape-lateral", self.memoria)
        self.b_memoria.setIcon(icones.icone("memoria", CORES["apoio"], 18))
        self.b_probes = _botao("  " + t("jp.probes"), "rodape-lateral", self.probes)
        self.b_probes.setIcon(icones.icone("sonda", CORES["apoio"], 18))
        self.b_config = _botao("  " + t("jp.config"), "rodape-lateral", self.config)
        self.b_config.setIcon(icones.icone("config", CORES["apoio"], 18))
        for b in (self.b_memoria, self.b_probes, self.b_config):
            b.setIconSize(QSize(18, 18))
            v.addWidget(b)
        self.atual = None
        self._itens = {}

    def _ao_buscar(self):
        self.buscar.emit(self.busca.text().strip())

    def mostrar_versao(self, versao):
        self.v_titulo.setText(t("jp.nova_versao", versao=versao))
        self.v_sub.setText(t("jp.nada_sem_clique"))
        self.b_atualizar.setEnabled(True)
        self.b_atualizar.setText(t("jp.atualizar"))
        self.cartao_versao.show()

    def estado_atualizacao(self, texto, botao=None, habilitado=False):
        self.v_sub.setText(texto)
        if botao is not None:
            self.b_atualizar.setText(botao)
        self.b_atualizar.setEnabled(habilitado)

    def definir_historico(self, grupos, atual=None, filtrando=False):
        """grupos: [(chave, [{'id','titulo'}])]."""
        while self.lista.count() > 1:
            item = self.lista.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._itens = {}
        self.atual = atual
        if not grupos:
            vazio = QLabel(t("jp.nenhum_resultado") if filtrando else t("jp.sem_conversas"))
            vazio.setProperty("papel", "nota")
            vazio.setContentsMargins(8, 4, 8, 0)
            vazio.setWordWrap(True)
            self.lista.insertWidget(0, vazio)
            return
        pos = 0
        metrica = QFontMetrics(self.font())
        for chave, itens in grupos:
            g = QLabel(t(f"jp.grupo.{chave}").upper())
            g.setProperty("papel", "grupo")
            g.setContentsMargins(0, 14 if pos else 0, 0, 6)
            fonte = g.font()
            fonte.setLetterSpacing(QFont.AbsoluteSpacing, 0.9)
            g.setFont(fonte)
            self.lista.insertWidget(pos, g)
            pos += 1
            for item in itens:
                b = _botao("", "item-historico")
                b.setToolTip(item["titulo"])
                b.setText(metrica.elidedText(item["titulo"], Qt.ElideRight, LARGURA_LATERAL - 28 - 28))
                b.setProperty("atual", item["id"] == atual)
                b.setContextMenuPolicy(Qt.CustomContextMenu)
                b.clicked.connect(lambda _=False, i=item["id"]: self.abrir.emit(i))
                b.customContextMenuRequested.connect(lambda _p, i=item["id"], bt=b: self._menu_item(i, bt))
                self._itens[item["id"]] = b
                self.lista.insertWidget(pos, b)
                pos += 1

    def _menu_item(self, id_, botao):
        m = QMenu(self)
        m.addAction(t("jp.apagar_conversa"), lambda: self.apagar.emit(id_))
        m.exec(botao.mapToGlobal(botao.rect().bottomLeft()))

    def marcar_atual(self, id_):
        self.atual = id_
        for i, b in self._itens.items():
            b.setProperty("atual", i == id_)
            _repolir(b)

    def marcar_pagina(self, memoria=False, config=False):
        for b, ativo in ((self.b_memoria, memoria), (self.b_config, config)):
            b.setProperty("atual", ativo)
            _repolir(b)


# ------------------------------------------------------------
# Cabeçalho
# ------------------------------------------------------------

class Cabecalho(QFrame):
    parar = Signal()
    escolher_modelo = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("cabecalho")
        self.setFixedHeight(68)
        h = QHBoxLayout(self)
        h.setContentsMargins(32, 0, 32, 0)
        h.setSpacing(16)
        col = QVBoxLayout()
        col.setSpacing(0)
        self.titulo = QLabel(t("jp.sem_titulo"))
        self.titulo.setProperty("papel", "titulo-conversa")
        self.sub = QLabel(t("jp.pronto"))
        self.sub.setProperty("papel", "mono")
        col.addStretch(1)
        col.addWidget(self.titulo)
        col.addWidget(self.sub)
        col.addStretch(1)
        h.addLayout(col, 1)
        self.sino = Sino()                      # 5.1: avisos dos Probes (escondido no Lite, em aplicar_modo)
        h.addWidget(self.sino)
        self.pilula = QPushButton()
        self.pilula.setCursor(Qt.PointingHandCursor)
        self.pilula.setToolTip(t("jp.escolher_modelo"))
        self.pilula.setStyleSheet(
            f"QPushButton {{ background: {CORES['cartao']}; border: 1px solid {CORES['borda2']}; border-radius: 16px; "
            f"padding: 6px 14px 6px 28px; font-family: 'IBM Plex Mono'; font-size: 12px; color: {CORES['texto2']}; text-align: left; }}"
            f"QPushButton:hover {{ background: {CORES['destaque']}; }}")
        self.pilula.clicked.connect(self.escolher_modelo)
        self.ponto = QLabel(self.pilula)
        self.ponto.setFixedSize(8, 8)
        self.ponto.move(12, 12)
        self.ponto.setStyleSheet(f"background: {CORES['verde']}; border-radius: 4px;")
        h.addWidget(self.pilula)
        self.b_parar = _botao("  " + t("jp.parar"), "parar", self.parar)
        self.b_parar.setIcon(icones.icone("parar", CORES["texto"], 14))
        self.b_parar.setMinimumHeight(44)
        self.b_parar.hide()
        h.addWidget(self.b_parar)
        self.definir_modelo(t("jp.modelo_auto"), False)

    def definir_modelo(self, texto, nuvem):
        self.pilula.setText(texto)
        cor = CORES["apoio"] if nuvem else CORES["verde"]
        self.ponto.setStyleSheet(f"background: {cor}; border-radius: 4px;")
        self.pilula.adjustSize()
        self.pilula.setFixedHeight(32)
        self.pilula.setFixedWidth(max(60, QFontMetrics(self.pilula.font()).horizontalAdvance(texto) + 46))


# ------------------------------------------------------------
# Faixa de aviso (rotinas concluídas, paradas, puladas)
# ------------------------------------------------------------

class Faixa(QFrame):
    abrir = Signal()

    def __init__(self):
        super().__init__()
        self.setProperty("papel", "aviso-versao")
        h = QHBoxLayout(self)
        h.setContentsMargins(32, 8, 20, 8)
        h.setSpacing(12)
        self.texto = QLabel("")
        self.texto.setWordWrap(True)
        self.texto.setStyleSheet("font-size: 13px;")
        self.b_abrir = _botao(t("rot.titulo"), "link", self.abrir)
        b = QPushButton()
        b.setProperty("papel", "icone")
        b.setFixedSize(28, 28)
        b.setIcon(icones.icone("fechar", CORES["apoio"], 12, 3))
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(self.hide)
        h.addWidget(self.texto, 1)
        h.addWidget(self.b_abrir)
        h.addWidget(b)
        self.hide()

    def mostrar(self, texto, botao=None):
        self.texto.setText(texto)
        self.b_abrir.setText(botao or t("rot.titulo"))
        self.destino = "probes" if botao else "rotinas"
        self.show()


# ------------------------------------------------------------
# Compositor
# ------------------------------------------------------------

class CaixaEntrada(QPlainTextEdit):
    """Texto que cresce até 5 linhas. Enter envia; Shift+Enter quebra a linha."""

    enviar = Signal()
    foco = Signal(bool)

    def __init__(self):
        super().__init__()
        self.setObjectName("entrada")
        self.setPlaceholderText(t("jp.entrada_ph"))
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setTabChangesFocus(True)
        self.document().contentsChanged.connect(self._ajustar)
        self._ajustar()

    def _ajustar(self):
        linhas = max(1, min(5, int(self.document().size().height())))
        altura = 24 * linhas + 8
        self.setFixedHeight(max(36, altura))

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter) and not (e.modifiers() & Qt.ShiftModifier):
            self.enviar.emit()
            return
        super().keyPressEvent(e)

    def focusInEvent(self, e):
        super().focusInEvent(e)
        self.foco.emit(True)

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self.foco.emit(False)


class ChipAnexo(QFrame):
    removido = Signal(object)

    def __init__(self, anexo):
        super().__init__()
        self.anexo = anexo
        self.setProperty("papel", "anexo")
        h = QHBoxLayout(self)
        h.setContentsMargins(12, 5, 8, 5)
        h.setSpacing(8)
        r = QLabel(anexo.nome)
        r.setStyleSheet(f"font-size: 13px; color: {CORES['texto2']};")
        b = QPushButton()
        b.setProperty("papel", "icone")
        b.setFixedSize(24, 24)
        b.setIcon(icones.icone("fechar", CORES["apoio"], 12, 3))
        b.setToolTip(t("jp.remover_anexo"))
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(lambda: self.removido.emit(self))
        h.addWidget(r)
        h.addWidget(b)


class Compositor(QWidget):
    enviar = Signal()
    anexar = Signal()
    modo_voz = Signal(str)
    microfone_apertado = Signal()
    microfone_solto = Signal()
    microfone_clicado = Signal()

    def __init__(self):
        super().__init__()
        self.setMaximumWidth(716)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.chips_w = QWidget()
        self.chips = QHBoxLayout(self.chips_w)
        self.chips.setContentsMargins(0, 0, 0, 10)
        self.chips.setSpacing(10)
        self.chips.addStretch(1)
        self.chips_w.hide()
        v.addWidget(self.chips_w)

        self.caixa = QFrame()
        self.caixa.setProperty("papel", "compositor")
        h = QHBoxLayout(self.caixa)
        h.setContentsMargins(10, 10, 10, 10)
        h.setSpacing(10)
        self.b_anexar = QPushButton()
        self.b_anexar.setProperty("papel", "icone")
        self.b_anexar.setFixedSize(44, 44)
        self.b_anexar.setIcon(icones.icone("clipe", CORES["apoio"], 20))
        self.b_anexar.setIconSize(QSize(20, 20))
        self.b_anexar.setToolTip(t("jp.anexar"))
        self.b_anexar.setCursor(Qt.PointingHandCursor)
        self.b_anexar.clicked.connect(self.anexar)
        self.entrada = CaixaEntrada()
        self.entrada.enviar.connect(self.enviar)
        self.entrada.foco.connect(self._foco)
        self.segmentos = QFrame()
        self.segmentos.setProperty("papel", "segmentos")
        sl = QHBoxLayout(self.segmentos)
        sl.setContentsMargins(3, 3, 3, 3)
        sl.setSpacing(0)
        self.grupo = QButtonGroup(self)
        self.grupo.setExclusive(True)
        self.b_modo = {}
        for modo, chave in zip(("segurar", "continua", "tars"), ("jp.voz_segurar", "jp.voz_continua", "jp.voz_tars")):
            b = _botao(t(chave), "segmento")
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, m=modo: self.modo_voz.emit(m))
            self.grupo.addButton(b)
            self.b_modo[modo] = b
            sl.addWidget(b)
        self.segmentos.setToolTip(t("jp.voz_modo"))
        self.b_modo["segurar"].setChecked(True)
        self.b_mic = QPushButton()
        self.b_mic.setProperty("papel", "microfone")
        self.b_mic.setFixedSize(52, 52)
        self.b_mic.setIcon(icones.icone("microfone", CORES["escuro"], 24, 2.2))
        self.b_mic.setIconSize(QSize(24, 24))
        self.b_mic.setToolTip(t("jp.falar"))
        self.b_mic.setCursor(Qt.PointingHandCursor)
        self.b_mic.pressed.connect(self.microfone_apertado)
        self.b_mic.released.connect(self.microfone_solto)
        self.b_mic.clicked.connect(self.microfone_clicado)
        self.b_enviar = QPushButton()
        self.b_enviar.setProperty("papel", "icone-contorno")
        self.b_enviar.setFixedSize(44, 44)
        self.b_enviar.setIcon(icones.icone("enviar", CORES["texto"], 20, 2.2))
        self.b_enviar.setIconSize(QSize(20, 20))
        self.b_enviar.setToolTip(t("jp.enviar"))
        self.b_enviar.setCursor(Qt.PointingHandCursor)
        self.b_enviar.clicked.connect(self.enviar)
        h.addWidget(self.b_anexar)
        h.addWidget(self.entrada, 1)
        h.addWidget(self.segmentos)
        h.addWidget(self.b_mic)
        h.addWidget(self.b_enviar)
        v.addWidget(self.caixa)
        self.rodape = QLabel(t("jp.rodape_local"))
        self.rodape.setProperty("papel", "rodape")
        self.rodape.setAlignment(Qt.AlignHCenter)
        self.rodape.setContentsMargins(0, 10, 0, 0)
        v.addWidget(self.rodape)
        self._anexos = []

    def _foco(self, sim):
        self.caixa.setProperty("foco", bool(sim))
        _repolir(self.caixa)

    # -- anexos --------------------------------------------------------------
    def adicionar_anexo(self, anexo):
        chip = ChipAnexo(anexo)
        chip.removido.connect(self._remover)
        self.chips.insertWidget(self.chips.count() - 1, chip)
        self._anexos.append(chip)
        self.chips_w.show()

    def _remover(self, chip):
        self._anexos.remove(chip)
        self.chips.removeWidget(chip)
        chip.deleteLater()
        self.chips_w.setVisible(bool(self._anexos))

    def anexos(self):
        return [c.anexo for c in self._anexos]

    def limpar_anexos(self):
        for c in list(self._anexos):
            self._remover(c)

    def texto(self):
        return self.entrada.toPlainText().strip()

    def definir_texto(self, texto):
        self.entrada.setPlainText(texto)
        self.entrada.moveCursor(QTextCursor.MoveOperation.End)

    def limpar(self):
        self.entrada.clear()

    def definir_ocupado(self, ocupado):
        self.b_enviar.setEnabled(not ocupado)
        self.entrada.setPlaceholderText(t("jp.entrada_ph"))

    def definir_modo(self, modo):
        self.b_modo[modo].setChecked(True)

    def microfone_ativo(self, ativo):
        self.b_mic.setProperty("ativo", bool(ativo))
        self.b_mic.setIcon(icones.icone("microfone", CORES["escuro"], 24, 2.2))
        _repolir(self.b_mic)


# ------------------------------------------------------------
# A janela
# ------------------------------------------------------------

class JanelaPrincipal(QMainWindow):
    pedido_externo = Signal(str)     # outra abertura do app pediu pra mostrar a janela ("mostrar" | "rapido")
    _executar = Signal(object)       # roda uma função na thread da janela (QTimer.singleShot de outra thread NUNCA dispara)

    def __init__(self, nucleo=None, historico=None, capturar_stdout=True):
        super().__init__()
        if nucleo is None:
            import tars as nucleo
        self.nucleo = nucleo
        self._executar.connect(lambda f: f())
        self.setWindowIcon(tema.icone_do_app())
        self.setWindowTitle(t("jp.janela"))
        self.resize(1200, 780)
        self.setMinimumSize(900, 600)
        self.historico = historico if historico is not None else tars_historico.Historico()
        self.ponte = Ponte(nucleo, self.historico, capturar_stdout=capturar_stdout)
        self.voz = ControladorVoz(nucleo)
        self._ia = None                # MensagemIA que está recebendo
        self._etapas_feitas = 0
        self._por_voz = False
        self._modelos = []
        self._busca = ""
        self._nova_versao = None
        self._cancelou = False
        self._ferramenta_atual = ""
        self._rotina_em_curso = None      # dict da rotina que está rodando agora
        self._avisou_ia = set()           # ids de rotinas criadas pela IA já avisadas
        self._saindo = False
        self._tray = None
        self._pedido_da_barra = False
        self._ultimo_uso = time.monotonic()
        self.agenda = nucleo.agenda
        self._montar()
        self.lateral.versao.setText(nucleo.VERSAO_EXIBIDA)
        self.aplicar_modo()
        self.pedido_externo.connect(self.trazer_para_frente)
        self._ligar()
        self._atalhos()
        self.mostrar_vazio()
        self.atualizar_historico()
        self.ponte.iniciar()
        QTimer.singleShot(1500, self._procurar_atualizacao)
        self._timer_atualizacao = QTimer(self)        # a janela pode ficar dias aberta (bandeja): procura de novo a cada 6 h
        self._timer_atualizacao.timeout.connect(self._procurar_atualizacao)
        self._timer_atualizacao.start(6 * 3600 * 1000)
        self._painel_acoes = None
        self.barra = BarraRapida()
        self.barra.enviar.connect(self._enviar_da_barra)
        self.barra.parar.connect(self.parar)
        self.barra.abrir_janela.connect(lambda: self.trazer_para_frente("mostrar"))
        self._criar_bandeja()
        self._atalhos = None
        if plataforma.sistema() == "windows":      # no Windows e no macOS o atalho global é escutado pela própria janela
            from .atalhos_windows import AtalhosWindows
            self._atalhos = AtalhosWindows(self.trazer_para_frente)
            QApplication.instance().installNativeEventFilter(self._atalhos)
        elif plataforma.sistema() == "macos":
            from .atalhos_macos import AtalhosMac
            try:
                self._atalhos = AtalhosMac(self.trazer_para_frente)
            except OSError:          # sem o Carbon (não deveria acontecer): fica sem atalho, a janela abre igual
                self._atalhos = None
        self._registrar_atalhos_globais()
        if assistente.ligado():      # 5.2: o modelo das ações de texto volta para a memória quando o openTARS abre
            host, modelo = self.nucleo.OLLAMA_HOST, self._modelo_das_acoes()
            threading.Thread(target=lambda: _sem_erro(assistente.manter_carregado, host, modelo, True), daemon=True).start()
        self._ocioso = QTimer(self)
        self._ocioso.timeout.connect(self._checar_ocioso)
        self._ocioso.start(60000)
        self._relogio = QTimer(self)
        self._relogio.timeout.connect(self._tick_agenda)
        self._relogio.start(20000)
        QTimer.singleShot(2500, self._tick_agenda)

    # -- montagem --------------------------------------------------------------
    def _montar(self):
        raiz = QWidget()
        raiz.setObjectName("raiz")
        self.setCentralWidget(raiz)
        topo = QVBoxLayout(raiz)
        topo.setContentsMargins(0, 0, 0, 0)
        self.pilha = QStackedWidget()
        topo.addWidget(self.pilha)

        # 0: conversa
        conversa = QWidget()
        h = QHBoxLayout(conversa)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        self.lateral = Lateral()
        h.addWidget(self.lateral)
        principal = QWidget()
        principal.setObjectName("principal")
        pv = QVBoxLayout(principal)
        pv.setContentsMargins(0, 0, 0, 0)
        pv.setSpacing(0)
        self.cabecalho = Cabecalho()
        pv.addWidget(self.cabecalho)
        self.faixa = Faixa()
        pv.addWidget(self.faixa)
        self.area = AreaConversa()
        pv.addWidget(self.area, 1)
        self.vazio = self._montar_vazio()
        self.area.adicionar_widget(self.vazio)
        rodape = QHBoxLayout()
        rodape.setContentsMargins(32, 0, 32, 18)
        self.compositor = Compositor()
        rodape.addStretch(1)
        rodape.addWidget(self.compositor, 1000)
        rodape.addStretch(1)
        pv.addLayout(rodape)
        h.addWidget(principal, 1)
        self.mascote = Mascote(principal, referencia=self.compositor)      # anda por cima da conversa, junto do campo de escrever
        self.pilha.addWidget(conversa)             # 0

        self.tela_voz = TelaVoz()
        self.pilha.addWidget(self.tela_voz)        # 1
        self.config = PaginaConfiguracoes(self.nucleo, self.voz, self.historico, self.ponte)
        self.pilha.addWidget(self.config)          # 2

    def aplicar_modo(self):
        """5.1: o modo Lite esconde o histórico, a memória e a escolha de modelo (e volta ao automático)."""
        historico = modos.mostra("historico")
        self.lateral.caixa_busca.setVisible(historico)
        self.lateral.lista_w.setVisible(historico)          # a área continua ocupando o lugar (o rodapé fica embaixo)
        self.lateral.b_memoria.setVisible(modos.mostra("memoria"))
        self.lateral.b_probes.setVisible(modos.mostra("cfg.probes"))
        self.cabecalho.sino.setVisible(modos.mostra("cfg.probes"))
        seletor = modos.mostra("seletor_modelo")
        self.cabecalho.pilula.setVisible(seletor)
        if not seletor and self.ponte.modo_atual()[0] != "AUTO" and not self.ponte.esta_ocupado:
            self._escolher_modelo(None)

    def _montar_vazio(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 40, 0, 0)
        v.setSpacing(0)
        v.addWidget(tema.svg_widget(tema.monolito_svg(), 64), 0, Qt.AlignHCenter)
        v.addSpacing(18)
        titulo = QLabel(t("jp.vazio_titulo"))
        titulo.setStyleSheet("font-size: 26px; font-weight: 600;")
        titulo.setAlignment(Qt.AlignHCenter)
        texto = QLabel(t("jp.vazio_texto"))
        texto.setProperty("papel", "texto")
        texto.setWordWrap(True)
        texto.setAlignment(Qt.AlignHCenter)
        texto.setFixedWidth(540)
        texto.setMinimumHeight(54)
        v.addWidget(titulo)
        v.addSpacing(8)
        v.addWidget(texto, 0, Qt.AlignHCenter)
        v.addSpacing(24)
        for chave in ("jp.ex1", "jp.ex2", "jp.ex3"):
            b = _botao(t(chave), "chip", lambda _=False, c=chave: self._usar_exemplo(t(c)))
            b.setMaximumWidth(460)
            v.addWidget(b, 0, Qt.AlignHCenter)
            v.addSpacing(8)
        v.addStretch(1)
        return w

    def _atalhos(self):
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self.nova_conversa)
        QShortcut(QKeySequence("Ctrl+K"), self, activated=lambda: self.lateral.busca.setFocus())
        QShortcut(QKeySequence("Ctrl+,"), self, activated=lambda: self.abrir_config())
        QShortcut(QKeySequence("Ctrl+M"), self, activated=self._mic_atalho)
        QShortcut(QKeySequence("Esc"), self, activated=self._esc)

    def _ligar(self):
        p = self.ponte
        p.evento.connect(self._ao_evento)
        p.texto.connect(self._ao_texto)
        p.ocupado.connect(self._ao_ocupado)
        p.aprovacao.connect(self._ao_aprovacao)
        p.iniciado.connect(self._ao_iniciado)
        p.modelos.connect(self._ao_modelos)
        p.concluido.connect(self._ao_concluido)
        p.conversa_mudou.connect(self.atualizar_historico)
        l = self.lateral
        l.nova.connect(self.nova_conversa)
        l.abrir.connect(self.abrir_conversa)
        l.apagar.connect(self._apagar_conversa)
        l.buscar.connect(self._buscar)
        l.memoria.connect(lambda: self.abrir_config("memoria"))
        l.probes.connect(lambda: self.abrir_config("probes"))
        l.config.connect(lambda: self.abrir_config("geral"))
        l.atualizar.connect(self._atualizar_agora)
        self.cabecalho.parar.connect(self.parar)
        self.cabecalho.escolher_modelo.connect(self._menu_modelos)
        c = self.compositor
        c.enviar.connect(self.enviar)
        c.anexar.connect(self.escolher_anexos)
        c.modo_voz.connect(self._mudar_modo_voz)
        c.microfone_apertado.connect(self._mic_apertado)
        c.microfone_solto.connect(self._mic_solto)
        c.microfone_clicado.connect(self._mic_clicado)
        self.config.voltar.connect(lambda: self.pilha.setCurrentIndex(0))
        self.config.mudou_modo.connect(self.aplicar_modo)
        self.config.mudou_idioma.connect(self._ao_mudar_idioma)
        self.config.mudou_mascote.connect(self.mascote.mostrar_de_novo)
        self.config.modelos_mudaram.connect(self.ponte.atualizar_modelos)
        self.config.assistente_mudou.connect(self._atualizar_bandeja)
        self.config.assistente_mudou.connect(self._registrar_atalhos_globais)
        self.config.rodar_rotina.connect(self._rodar_agora)
        self.config.rotinas_mudaram.connect(self._atualizar_bandeja)
        self.faixa.abrir.connect(lambda: self.cabecalho.sino.click() if getattr(self.faixa, "destino", "") == "probes"
                                 else self.abrir_config("rotinas"))
        self.cabecalho.sino.configurar.connect(lambda: self.abrir_config("probes"))
        self.cabecalho.sino.chegou.connect(self._aviso_de_probe)
        v = self.voz
        v.estado.connect(self._ao_estado_voz)
        v.pedido.connect(self._ao_pedido_voz)
        tv = self.tela_voz
        tv.voltar.connect(self._sair_da_voz)
        tv.parar.connect(self._parar_voz_ou_resposta)
        tv.silenciar.connect(self.voz.alternar_silencio)
        tv.modo_mudou.connect(self._mudar_modo_voz)

    # -- conversa ----------------------------------------------------------------
    def mostrar_vazio(self):
        self.area.limpar()
        self.vazio = self._montar_vazio()
        self.area.adicionar_widget(self.vazio)
        self._ia = None
        self.cabecalho.titulo.setText(t("jp.sem_titulo"))
        self.cabecalho.sub.setText(t("jp.pronto"))

    def _usar_exemplo(self, texto):
        self.compositor.definir_texto(texto)
        self.compositor.entrada.setFocus()

    def nova_conversa(self):
        if self.ponte.esta_ocupado:
            return
        self.pilha.setCurrentIndex(0)
        self.ponte.nova_conversa()
        self.mostrar_vazio()
        self.lateral.marcar_atual(None)
        self.lateral.marcar_pagina()
        self.compositor.entrada.setFocus()

    def abrir_conversa(self, id_):
        self.pilha.setCurrentIndex(0)
        mensagens = self.ponte.abrir_conversa(id_)
        if mensagens is None:
            return
        self.area.limpar()
        self.vazio = None
        self.lateral.marcar_atual(id_)
        self.lateral.marcar_pagina()
        self.cabecalho.titulo.setText(tars_historico.titulo_da(mensagens) or t("jp.sem_titulo"))
        self.cabecalho.sub.setText(t("jp.pronto"))
        self._ia = None
        self.mostrar_mensagens(mensagens)
        self.area.rolar_ao_fim()

    def mostrar_mensagens(self, mensagens):
        """Desenha uma conversa guardada (as automáticas do núcleo e os resultados de ferramenta ficam de fora)."""
        ia = None
        for m in mensagens:
            papel = m.get("role")
            conteudo = m.get("content") or ""
            if papel == "user":
                if conteudo.lstrip().startswith("["):
                    continue
                ia = None
                self.area.adicionar_pessoa(conteudo.split("\n\n[Files attached")[0].strip())
            elif papel == "assistant":
                if ia is None:
                    ia = self.area.adicionar_ia()
                if conteudo.strip():
                    ia.fim_do_trecho()
                    ia.acrescentar_texto(conteudo)
                    ia.fim_do_trecho()
                for ch in m.get("tool_calls") or []:
                    nome = (ch.get("function") or {}).get("name", "")
                    linha = ia.ferramenta(self.nucleo.nome_ferramenta(nome), "")
                    linha.sucesso = True
        return ia

    def enviar(self, texto=None, por_voz=False):
        if self.ponte.esta_ocupado:
            return False
        texto = (texto if texto is not None else self.compositor.texto()).strip()
        anexos = self.compositor.anexos()
        if not texto and not anexos:
            return False
        if self.vazio is not None:
            self.area.limpar()
            self.vazio = None
        self._por_voz = por_voz
        self._cancelou = False
        self.area.adicionar_pessoa(texto or t("jp.escolher_arquivos"))
        if not self.cabecalho.titulo.text() or self.cabecalho.titulo.text() == t("jp.sem_titulo"):
            resumo = " ".join(texto.split())
            self.cabecalho.titulo.setText(resumo[:60] + ("…" if len(resumo) > 60 else ""))
        self._ia = self.area.adicionar_ia()
        self._etapas_feitas = 0
        self.compositor.limpar()
        self.compositor.limpar_anexos()
        return self.ponte.enviar(texto, anexos)

    def parar(self):
        self._cancelou = True
        self.cabecalho.b_parar.setText("  " + t("jp.parando"))
        self.cabecalho.b_parar.setEnabled(False)
        self.ponte.parar()

    def _esc(self):
        if self.pilha.currentIndex() == 0 and self.ponte.esta_ocupado:
            self.parar()
        elif self.pilha.currentIndex() in (1, 2):
            self.pilha.setCurrentIndex(0)

    # -- eventos do núcleo ---------------------------------------------------------------
    def _garantir_ia(self):
        if self._ia is None:
            self._ia = self.area.adicionar_ia()
        return self._ia

    def _ao_evento(self, tipo, d):
        n = self.nucleo
        if d.get("segundo_plano") or (tipo in ("carregando", "carregado") and not self.ponte.esta_ocupado):
            # aquecimento do modelo / troca manual de modelo: não é uma resposta, então não cria balão de IA vazio
            if tipo == "carregando":
                self.cabecalho.sub.setText(t("gui.carregando", modelo=d.get("modelo", "")))
            elif tipo == "carregado":
                self.cabecalho.sub.setText(t("jp.pronto"))
            return
        self.mascote.reagir(tipo, d, n.nome_ferramenta(d.get("nome", "")) if tipo == "ferramenta" else "")
        ia = self._garantir_ia()
        if tipo == "tarefa":
            modelo = d.get("modelo") or ""
            self._mostrar_modelo_em_uso(modelo)
        elif tipo == "carregando":
            self.cabecalho.sub.setText(t("gui.carregando", modelo=d.get("modelo", "")))
        elif tipo == "carregado":
            self.cabecalho.sub.setText(t("jp.em_andamento"))
        elif tipo == "pensamento":
            ia.acrescentar_raciocinio(d.get("texto", ""))
        elif tipo == "resposta":
            ia.acrescentar_texto(d.get("texto", ""))
            if self._pedido_da_barra:
                self.barra.acrescentar(d.get("texto", ""))
        elif tipo == "resposta_era_pensamento":
            ia.virar_raciocinio()
        elif tipo == "fim_stream":
            ia.fim_do_trecho()
        elif tipo == "ferramenta":
            ia.ferramenta(n.nome_ferramenta(d.get("nome", "")), d.get("resumo") or "")
            if self._pedido_da_barra:
                self.barra.definir_ocupado(True, n.nome_ferramenta(d.get("nome", "")))
            self._ferramenta_atual = d.get("nome", "")
        elif tipo == "ferramenta_fim":
            ia.ferramenta_fim(d.get("sucesso"), float(d.get("segundos") or 0))
            if d.get("sucesso") and d.get("nome", self._ferramenta_atual_nome()) not in FERRAMENTAS_SO_OLHAM and ia.etapas is not None:
                self._etapas_feitas += 1
                ia.etapas.definir_feitas(min(self._etapas_feitas, ia.etapas.total() - 1))
                self._atualizar_subtitulo(ia)
        elif tipo == "plano":
            etapas = list(d.get("etapas") or [])
            if len(etapas) >= 2:
                ia.definir_etapas(etapas)
                self._atualizar_subtitulo(ia)

    def _ferramenta_atual_nome(self):
        return getattr(self, "_ferramenta_atual", "")

    def _atualizar_subtitulo(self, ia):
        if ia.etapas is not None:
            atual = min(ia.etapas.feitas + 1, ia.etapas.total())
            self.cabecalho.sub.setText(t("jp.etapa_de", atual=atual, total=ia.etapas.total()))
        else:
            self.cabecalho.sub.setText(t("jp.em_andamento"))

    def _ao_texto(self, texto):
        linhas = limpar_saida(texto)
        if not linhas:
            return
        ia = self._garantir_ia()
        for l in linhas:
            minus = l.lower()
            erro = "✗" in l or "erro" in minus or "error" in minus or "falhou" in minus or "failed" in minus
            ia.aviso(l.replace("[openTARS] ", "", 1), erro=erro)

    def _ao_ocupado(self, ocupado):
        self.mascote.ocupado(ocupado)
        self.compositor.definir_ocupado(ocupado)
        if self._pedido_da_barra:
            self.barra.definir_ocupado(ocupado, t("gui.trabalhando"))
        b = self.cabecalho.b_parar
        b.setVisible(ocupado)
        if ocupado:
            b.setText("  " + t("jp.parar"))
            b.setEnabled(True)
            self.cabecalho.sub.setText(t("jp.em_andamento"))

    def _ao_aprovacao(self, aprovacao):
        self.mascote.espera()
        if self._pedido_da_barra:       # a pergunta de segurança mora na janela: ela vem pra frente
            self.barra.precisa_de_voce()
            self.barra.esconder()
            self.trazer_para_frente("mostrar")
        ia = self._garantir_ia()
        cartao = ia.aprovacao(aprovacao.comando)
        cartao.respondeu.connect(aprovacao.responder)
        self.area.rolar_ao_fim()
        self.cabecalho.sub.setText(t("jp.espera_voce"))
        self.pilha.setCurrentIndex(0) if self.pilha.currentIndex() == 1 else None

    def _ao_concluido(self, resposta):
        if resposta and not self._cancelou:
            self.mascote.concluido(resposta)
        rotina = self._rotina_em_curso
        if rotina is not None:
            self._terminar_rotina(rotina, resposta)
        ia = self._ia
        if ia is not None:
            ia.fim_do_trecho()
            if ia.etapas is not None and resposta and not self._cancelou:
                ia.etapas.concluir_tudo()
        self.cabecalho.sub.setText(t("jp.pronto"))
        self._mostrar_modelo_em_uso()
        self._avisar_rotinas_da_ia()
        if self._pedido_da_barra:
            self.barra.concluir(resposta if not self._cancelou else "")
            self._pedido_da_barra = False
        if resposta and rotina is None and (self._por_voz or self.nucleo.config_voz().get("falar")):
            self.voz.falar(resposta, forcar=self._por_voz)
        self._por_voz = False
        self._ia = None
        self.lateral.marcar_atual(self.ponte.id_conversa)

    # -- início, modelos ---------------------------------------------------------------------
    def _ao_iniciado(self, info):
        if not info.get("online"):
            self._aviso_inicial(t("jp.ollama_fora"))
        elif info.get("n_modelos", 0) == 0:
            self._aviso_inicial(t("jp.sem_modelo"))
        for aviso in info.get("avisos", [])[:2]:
            if aviso and aviso not in (t("jp.sem_modelo"),):
                self._aviso_inicial(aviso)

    def _aviso_inicial(self, texto):
        if self.vazio is not None:
            r = rotulo(texto, "nota", quebra=True)
            r.setAlignment(Qt.AlignHCenter)
            r.setStyleSheet("color: #FFD479;")
            self.vazio.layout().insertWidget(self.vazio.layout().count() - 1, r)

    def _ao_modelos(self, itens):
        self._modelos = itens

    def _mostrar_modelo_em_uso(self, modelo=None):
        modo, manual = self.ponte.modo_atual()
        n = self.nucleo
        if modo == "MANUAL" and manual:
            api = n.api.eh_modelo_api(manual)
            nuvem = api or n.eh_modelo_de_nuvem(manual)     # 5.1: gpt-oss:20b-cloud também sai do computador
            nome = manual[len(n.api.PREFIXO):] if api else manual
            self.cabecalho.definir_modelo(t("jp.modelo_nuvem" if nuvem else "jp.modelo_local", modelo=nome), nuvem)
            self._rodape_nuvem("ollama" if nuvem and not api else nuvem)
        else:
            usado = modelo if modelo and not n.api.eh_modelo_api(modelo) else None
            self.cabecalho.definir_modelo(t("jp.modelo_local", modelo=usado) if usado else t("jp.modelo_auto"), False)
            self._rodape_nuvem(False)

    def _rodape_nuvem(self, nuvem):
        if nuvem:
            prov = "Ollama Cloud" if nuvem == "ollama" else pu.provedor(pu.carregar_nuvem().get("provedor", "outro"))["nome"]
            self.compositor.rodape.setText(t("jp.rodape_nuvem", provedor=prov))
        else:
            self.compositor.rodape.setText(t("jp.rodape_local"))

    def _menu_modelos(self):
        if self.ponte.esta_ocupado:
            return
        m = QMenu(self)
        modo, manual = self.ponte.modo_atual()
        a = m.addAction(("✓ " if modo == "AUTO" else "") + t("jp.menu_auto"))
        a.triggered.connect(lambda: self._escolher_modelo(None))
        locais = [(r, tag) for r, tag, nuvem in self._modelos if not nuvem]
        nuvem_itens = [(r, tag) for r, tag, nuvem in self._modelos if nuvem]
        if locais:
            m.addSeparator()
            m.addAction(t("jp.menu_local")).setEnabled(False)
            for r, tag in locais:
                act = m.addAction(("✓ " if manual == tag else "") + r)
                act.triggered.connect(lambda _=False, x=tag: self._escolher_modelo(x))
        m.addSeparator()
        if nuvem_itens:
            m.addAction(t("jp.menu_nuvem")).setEnabled(False)
            for r, tag in nuvem_itens:
                act = m.addAction(("✓ " if manual == tag else "") + r)
                act.triggered.connect(lambda _=False, x=tag: self._escolher_modelo(x))
        else:
            m.addAction(t("jp.menu_sem_nuvem")).setEnabled(False)
        m.exec(self.cabecalho.pilula.mapToGlobal(self.cabecalho.pilula.rect().bottomLeft()))

    def _escolher_modelo(self, tag):
        self.ponte.escolher_modelo(tag)
        self._mostrar_modelo_em_uso()

    # -- histórico ---------------------------------------------------------------------
    def atualizar_historico(self):
        itens = self.historico.listar(self._busca)
        grupos = tars_historico.agrupar_por_dia(itens)
        self.lateral.definir_historico(grupos, atual=self.ponte.id_conversa, filtrando=bool(self._busca))

    def _buscar(self, texto):
        self._busca = texto
        self.atualizar_historico()

    def _apagar_conversa(self, id_):
        era_a_atual = id_ == self.ponte.id_conversa
        if self.ponte.apagar_conversa(id_) and era_a_atual:
            self.mostrar_vazio()

    # -- anexos ---------------------------------------------------------------------------------
    def escolher_anexos(self):
        arquivos, _ = QFileDialog.getOpenFileNames(self, t("jp.escolher_arquivos"))
        if arquivos:
            self.anexar_arquivos(arquivos)

    def anexar_arquivos(self, caminhos):
        ja = self.compositor.anexos()
        try:
            novos, erros = self.nucleo.anexar_arquivos(caminhos, ja_anexados=ja)
        except Exception as e:
            novos, erros = [], [str(e)]
        for a in novos:
            self.compositor.adicionar_anexo(a)
        if erros:
            self.cabecalho.sub.setText(t("jp.anexos_erro", erro="; ".join(str(e) for e in erros)[:120]))
        return novos

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        caminhos = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if caminhos:
            self.anexar_arquivos(caminhos)

    # -- voz ---------------------------------------------------------------------------------------
    def _mudar_modo_voz(self, modo):
        self.voz.modo = modo
        self.compositor.definir_modo(modo)
        self.tela_voz.definir_modo(modo)
        self.nucleo.i18n.salvar_config(voz_modo=modo)
        if self.pilha.currentIndex() == 1 and modo != "segurar":
            self.voz.iniciar(modo)

    def _voz_pronta_ou_avisar(self):
        if self.voz.pronta():
            return True
        itens = self.nucleo.descrever_falta_voz(self.voz.faltando())
        self.cabecalho.sub.setText(t("tv.falta", itens=itens))
        self.abrir_config("voz")
        return False

    def _mic_apertado(self):
        if self.voz.modo != "segurar" or self.ponte.esta_ocupado:
            return
        if not self._voz_pronta_ou_avisar():
            return
        self.compositor.microfone_ativo(True)
        self.voz.iniciar("segurar")

    def _mic_solto(self):
        if self.voz.modo == "segurar":
            self.voz.soltar()
            self.compositor.microfone_ativo(False)

    def _mic_clicado(self):
        if self.voz.modo == "segurar":
            return
        if not self._voz_pronta_ou_avisar():
            return
        if self.voz.ativo() and self.pilha.currentIndex() != 1:
            self.pilha.setCurrentIndex(1)
            return
        self.voz.iniciar(self.voz.modo)
        self.tela_voz.definir_modo(self.voz.modo)
        self.pilha.setCurrentIndex(1)

    def _mic_atalho(self):
        if self.voz.modo == "segurar":
            if self.voz.ativo():
                self.voz.soltar()
            elif self._voz_pronta_ou_avisar():
                self.compositor.microfone_ativo(True)
                self.voz.iniciar("segurar")
        else:
            self._mic_clicado()

    def _ao_estado_voz(self, estado):
        self.tela_voz.ao_estado(estado)
        if estado == "parado" and self.voz.modo == "segurar":
            self.compositor.microfone_ativo(False)
        if estado.startswith("erro:"):
            self.compositor.microfone_ativo(False)
            self.cabecalho.sub.setText(t("tv.erro", erro=estado[5:]))

    def _ao_pedido_voz(self, texto):
        self.tela_voz.definir_fala(texto)
        self.compositor.microfone_ativo(False)
        if self.ponte.esta_ocupado:
            return
        if self.voz.modo == "segurar":
            self.pilha.setCurrentIndex(0)
        self.enviar(texto, por_voz=True)
        self.tela_voz.ao_estado("pensando")

    def _sair_da_voz(self):
        self.voz.parar()
        self.compositor.microfone_ativo(False)
        self.pilha.setCurrentIndex(0)

    def _parar_voz_ou_resposta(self):
        if self.ponte.esta_ocupado:
            self.parar()
        self.voz.parar()
        self.pilha.setCurrentIndex(0)

    # -- rotinas agendadas ---------------------------------------------------------------------------
    def _tick_agenda(self):
        """A cada 20 s: roda o que está na hora, avisa o que foi pulado (computador ou openTARS desligado)."""
        try:
            rodar, perdidas = self.agenda.devidas()
        except Exception:
            return
        for p in perdidas:
            quando = (p.get("ultima") or {}).get("quando", "")
            hora = quando[11:16] if len(quando) >= 16 else "?"
            self._notificar(t("rot.aviso_perdida", nome=p["nome"], hora=hora))
        if perdidas:
            self.config.paginas["rotinas"].ao_abrir()
        if not rodar or self._rotina_em_curso is not None or self.ponte.esta_ocupado or self.voz.ativo():
            return          # fica na fila: devidas() devolve de novo até estourar a tolerância
        if not self.agenda.reservar(rodar[0]["id"], rodar[0]["prevista"]):
            return          # outra janela/processo já pegou esta execução
        self._executar_rotina(rodar[0])

    def _rodar_agora(self, id_):
        r = self.agenda.obter(id_)
        if r is None or self._rotina_em_curso is not None or self.ponte.esta_ocupado:
            return
        self.pilha.setCurrentIndex(0)
        self._executar_rotina(dict(r, agora=True))

    def _executar_rotina(self, r):
        n = self.nucleo
        self.nova_conversa()
        self._rotina_em_curso = r
        n.ROTINA_BLOQUEOU.clear()
        n.ROTINA_ATUAL = r
        try:
            self.cabecalho.titulo.setText(t("rot.titulo_conversa", nome=r["nome"]))
            if not self.enviar(r["pedido"]):
                raise RuntimeError("busy")
        except Exception:
            # não começou: sem isto ROTINA_ATUAL ficava preso e todo comando arriscado das conversas normais era negado
            n.ROTINA_ATUAL = None
            n.ROTINA_BLOQUEOU.clear()
            self._rotina_em_curso = None
            try:
                self.agenda.registrar(r["id"], "erro", "—") if not r.get("agora") else None
            except Exception:
                pass

    def _terminar_rotina(self, r, resposta):
        n = self.nucleo
        bloqueou = list(n.ROTINA_BLOQUEOU)
        n.ROTINA_ATUAL = None
        n.ROTINA_BLOQUEOU.clear()
        self._rotina_em_curso = None
        if bloqueou:
            resultado, detalhe = "parou", bloqueou[0][:120]
            aviso = t("rot.aviso_parou", nome=r["nome"], comando=detalhe)
        elif self._cancelou:
            resultado, detalhe = "parou", t("jp.parando").rstrip("…")
            aviso = t("rot.aviso_erro", nome=r["nome"], detalhe=detalhe)
        elif not resposta:
            resultado, detalhe = "erro", "—"
            aviso = t("rot.aviso_erro", nome=r["nome"], detalhe=detalhe)
        else:
            resultado, detalhe = "ok", ""
            aviso = t("rot.aviso_ok", nome=r["nome"])
        try:
            if not r.get("agora"):
                self.agenda.registrar(r["id"], resultado, detalhe)
            else:      # "Rodar agora" não mexe no calendário, só anota o resultado
                self.agenda.anotar_ultima(r["id"], resultado, detalhe)
        except Exception:
            pass       # disco cheio etc.: o resto (avisos, estado da janela) tem que acontecer mesmo assim
        try:
            self.historico.renomear(self.ponte.id_conversa, t("rot.titulo_conversa", nome=r["nome"]))
        except Exception:
            pass
        self.ponte.conversa_mudou.emit()
        self.config.paginas["rotinas"].ao_abrir()
        self._notificar(aviso)

    def _avisar_rotinas_da_ia(self):
        """A IA criou uma rotina pela conversa: ela está desligada até a pessoa aprovar."""
        for r in self.agenda.listar():
            if r.get("origem") == "ia" and not r.get("aprovada") and r["id"] not in self._avisou_ia:
                self._avisou_ia.add(r["id"])
                self._notificar(t("rot.aviso_ia", nome=r["nome"]))
                self.config.paginas["rotinas"].ao_abrir()

    def _aviso_de_probe(self, texto):
        """Um Probe avisou (o serviço já mandou a notificação do sistema): aqui só a faixa, com o botão do painel."""
        self.faixa.mostrar(texto, t("avisos.ver"))
        QTimer.singleShot(30000, lambda: self.faixa.texto.text() == texto and self.faixa.hide())

    def _notificar(self, texto):
        self.faixa.mostrar(texto)
        QTimer.singleShot(30000, lambda: self.faixa.texto.text() == texto and self.faixa.hide())
        if self._tray is not None and not self.isVisible():
            self._tray.showMessage("openTARS", texto)
        elif not self.isActiveWindow():
            try:
                plataforma.notificar("openTARS", texto)
            except OSError:
                pass

    # -- bandeja do sistema (rotinas ligadas continuam rodando com a janela fechada) -----------------------
    def _bandeja_disponivel(self):
        return QSystemTrayIcon.isSystemTrayAvailable()

    def _criar_bandeja(self):
        if not self._bandeja_disponivel():
            return
        self._tray = QSystemTrayIcon(tema.icone_do_app(), self)
        self._tray.setToolTip(t("rot.tray_dica"))
        menu = QMenu(self)
        a = QAction(t("rot.tray_abrir"), menu)
        a.triggered.connect(lambda: self.trazer_para_frente("mostrar"))
        b = QAction(t("rot.tray_sair"), menu)
        b.triggered.connect(self._sair_de_vez)
        acoes = QAction(t("rot.tray_acoes"), menu)
        acoes.triggered.connect(self._abrir_acoes)
        self._acao_assistente = QAction(t("rot.tray_assistente"), menu)
        self._acao_assistente.setCheckable(True)
        self._acao_assistente.triggered.connect(self._alternar_assistente)
        menu.addAction(a)
        menu.addAction(acoes)
        menu.addAction(self._acao_assistente)
        menu.addSeparator()
        menu.addAction(b)
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(lambda motivo: self.trazer_para_frente("mostrar")
                                     if motivo == QSystemTrayIcon.Trigger else None)
        self._menu_bandeja = menu
        self._atualizar_bandeja()

    def _atualizar_bandeja(self):
        if self._tray is None:
            return
        self._acao_assistente.setChecked(assistente.ligado())
        self._tray.setVisible(self._fica_na_bandeja())

    def _tem_rotinas_ligadas(self):
        return any(r.get("ativa") for r in self.agenda.listar())

    def _fica_na_bandeja(self):
        """Rotinas ligadas ou o assistente ligado: fechar a janela deixa o openTARS no ícone perto do relógio."""
        return self._tem_rotinas_ligadas() or assistente.ligado()

    def _modelo_das_acoes(self):
        garg = self.nucleo.MODELO_GARGANTUA.split(":")[0]
        try:
            instalados = self.nucleo.listar_modelos_instalados()
        except Exception:  # noqa: BLE001
            instalados = []
        return acoes_lib.escolher_modelo(instalados, garg + ":lite", garg + ":latest")

    def _registrar_atalhos_globais(self):
        if self._atalhos is None:
            return
        self._atalhos.limpar()
        config = tars_i18n.ler_config()
        self._atalhos.registrar(config.get("atalho") or tars_atalho.PADRAO, "rapido")
        if config.get("atalho_acoes_registrado"):
            self._atalhos.registrar(config.get("atalho_acoes") or tars_atalho.ACOES_PADRAO, "acoes")

    def _alternar_assistente(self, ativo):
        host, modelo = self.nucleo.OLLAMA_HOST, self._modelo_das_acoes()

        def trabalho():
            try:
                assistente.ligar(ativo, host, modelo)
            except Exception:  # noqa: BLE001  (Ollama fora: a escolha fica guardada e vale na próxima abertura)
                pass
            self.depois(self._atualizar_bandeja)
        threading.Thread(target=trabalho, daemon=True).start()

    def _sair_de_vez(self):
        self._saindo = True
        self.close()

    # -- configurações -----------------------------------------------------------------------------
    def abrir_config(self, pagina="geral"):
        self.config.ir(pagina)
        self.pilha.setCurrentIndex(2)

    def _ao_mudar_idioma(self):
        """Trocou o idioma: reconstrói a janela com os textos novos."""
        self.reconstruir = True
        self._saindo = True
        self.close()

    def depois(self, funcao):
        """Roda `funcao` na thread da janela; pode ser chamado de qualquer thread."""
        try:
            fio.no_principal(funcao)
        except (RuntimeError, TypeError):     # a janela já fechou
            pass

    # -- atualização ------------------------------------------------------------------------------------
    def _procurar_atualizacao(self):
        def trabalho():
            try:
                nova = tars_atualizacao.procurar_atualizacao(self.nucleo.VERSAO)
            except Exception:
                nova = None
            if nova:
                self._nova_versao = nova
                self.depois(lambda: self.lateral.mostrar_versao(nova["versao"]))

        threading.Thread(target=trabalho, daemon=True).start()

    def _atualizar_agora(self):
        nova = self._nova_versao
        if not nova:
            return
        self.lateral.estado_atualizacao(t("jp.conferindo"), t("jp.atualizar"), False)
        tipo = "appimage" if os.environ.get("APPIMAGE") and "appimage" in nova["arquivos"] else \
            "deb" if "deb" in nova["arquivos"] else next(iter(nova["arquivos"]))
        arquivo = nova["arquivos"][tipo]
        destino = os.path.join(os.path.expanduser("~/.cache/opentars"), os.path.basename(arquivo["nome"]))

        def pronto(ok, motivo):
            if ok:
                self.lateral.estado_atualizacao(t("jp.atualizado"), t("jp.atualizar"), False)
            else:
                texto = t(f"jp.motivo.{motivo}") if tars_i18n.t(f"jp.motivo.{motivo}") != f"jp.motivo.{motivo}" else motivo
                self.lateral.estado_atualizacao(t("jp.atualizar_erro", motivo=texto), t("jp.atualizar"), True)

        def trabalho():
            def andamento(feito, total):
                pct = int(100 * feito / total) if total else 0
                self.depois(lambda: self.lateral.estado_atualizacao(t("jp.baixando", pct=pct), None, False))

            ok, motivo = tars_atualizacao.baixar_verificado(arquivo["url"], destino, arquivo["sha256"], ao_progredir=andamento, git_sha=arquivo.get("git_sha"))
            if ok:
                ok, motivo = tars_atualizacao.instalar_arquivo(
                    destino, sha256=arquivo.get("sha256", ""), git_sha=arquivo.get("git_sha", ""))
                if ok:
                    motivo = ""
                    tars_atualizacao.marcar_instalada(arquivo.get("id") or arquivo["sha256"])
            self.depois(lambda: pronto(ok, motivo))

        threading.Thread(target=trabalho, daemon=True).start()

    def _enviar_da_barra(self, texto):
        self._ultimo_uso = time.monotonic()
        if self.ponte.esta_ocupado or self._rotina_em_curso is not None:
            self.barra.recusar(texto)      # a janela está respondendo outra coisa: devolve o texto e avisa
            return
        if self.barra.perguntas <= 1:        # primeira pergunta desta abertura: conversa nova; as outras continuam nela
            self.nova_conversa()
        self._pedido_da_barra = True
        self.enviar(texto)

    def _abrir_acoes(self):
        """5.2: o painel das ações de texto com o que está selecionado agora (lido antes de o painel aparecer)."""
        texto = acoes_lib.ler_selecao()
        if not texto.strip():          # nada selecionado: o atalho vira o lançador (a barra rápida pede qualquer coisa)
            self.barra.mostrar()
            return
        if self._painel_acoes is None:
            n = self.nucleo
            garg = n.MODELO_GARGANTUA.split(":")[0]
            try:
                instalados = n.listar_modelos_instalados()
            except Exception:  # noqa: BLE001  (Ollama fora: o painel mostra o erro ao rodar)
                instalados = []
            self._painel_acoes = PainelAcoes(n.OLLAMA_HOST, instalados, garg + ":lite", garg + ":latest")
            self._painel_acoes.substituir.connect(self._colar_resultado)
        self._painel_acoes.abrir(texto)

    def _colar_resultado(self, texto):
        """Depois que o painel some, o foco volta ao programa de antes: cola lá (numa thread, para não travar a janela)."""
        teclas = lambda *k: self.nucleo.pyautogui.hotkey(*k)  # noqa: E731
        QTimer.singleShot(200, lambda: threading.Thread(target=acoes_lib.colar, args=(texto, teclas), daemon=True).start())

    def _checar_ocioso(self):
        """Aberto só pela barra rápida e sem uso há muito tempo: encerra."""
        parado = time.monotonic() - self._ultimo_uso > MINUTOS_OCIOSO * 60
        painel = self._painel_acoes is not None and self._painel_acoes.isVisible()
        if parado and not self.isVisible() and not self.barra.isVisible() and not painel and not self.ponte.esta_ocupado \
                and not self._fica_na_bandeja() and self._rotina_em_curso is None:
            self._sair_de_vez()

    def trazer_para_frente(self, comando="mostrar"):
        self._ultimo_uso = time.monotonic()
        if comando == "rapido":
            self.barra.mostrar()
            return
        if comando == "acoes":
            self._abrir_acoes()
            return
        if comando == "residente":      # início com o sistema: só o ícone perto do relógio, nenhuma janela
            return
        self.pilha.setCurrentIndex(0)
        self.setWindowState(self.windowState() & ~Qt.WindowMinimized)
        self.show()
        self.raise_()
        self.activateWindow()

    # -- fechar ------------------------------------------------------------------------------------------------
    def _descarregar_modelos(self):
        """Ao fechar o openTARS, tira os modelos da memória (como a janela Tk já fazia). Roda numa thread e espera
        no máximo ~8 s, para a janela nunca ficar presa se o Ollama demorar."""
        def _tarefa():
            try:
                self.nucleo.cancelar_resposta()
            except Exception:
                pass
            try:
                if self.nucleo.lock_modelo.acquire(timeout=2):   # modelo ainda carregando: deixa o keep_alive vencer
                    self.nucleo.lock_modelo.release()
                    self.nucleo.encerrar_todas_ias(so_do_tars=True)
            except Exception:
                pass
        import threading
        th = threading.Thread(target=_tarefa, daemon=True)
        th.start()
        th.join(timeout=8)

    def closeEvent(self, e):
        if not self._saindo and self._tray is not None and self._tray.isVisible() and self._fica_na_bandeja():
            e.ignore()          # rotinas ou o assistente ligados: fica na bandeja
            self.hide()
            return
        try:
            self._relogio.stop()
            self._ocioso.stop()
            self.barra.hide()
            if self._rotina_em_curso is not None:
                self.nucleo.ROTINA_ATUAL = None
            self.voz.parar()
            self.ponte.parar()
            self.ponte.encerrar()
            self.nucleo.salvar_sessoes()
            if self._tray is not None:
                self._tray.hide()
        except Exception:
            pass
        if not getattr(self, "reconstruir", False):   # trocar de idioma só refaz a janela: não descarrega
            self._descarregar_modelos()
        super().closeEvent(e)
        QApplication.instance().quit()
