"""5.1: os avisos dos Probes. O mesmo painel aparece em dois lugares: no sino do cabeçalho da janela e no ícone perto do
relógio (a bandeja, que é o próprio serviço dos Probes rodando com tela; ver rodar_bandeja). O número do selo é
avisos não lidos + pedidos de lixeira esperando. Tudo vem de tars_probes (probes.json): a janela e a bandeja são dois
processos e se entendem pelo arquivo."""

import datetime as dt
import html
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QPoint, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QCursor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel, QMenu, QPushButton, QScrollArea,
                               QSystemTrayIcon, QVBoxLayout, QWidget)

import tars_probes as probes_lib
from tars_i18n import t

from . import icones, tema
from .tema import CORES

AMBAR = "#F2B84B"          # o mesmo âmbar do site: o que pede a sua atenção


def icone_com_selo(n, lado=64, forma="sino", fundo=True):
    """O sino dos avisos (com fundo, na bandeja; sem, no cabeçalho) e um selo âmbar com o número. n=0: sem selo."""
    pixmap = QPixmap(lado, lado)
    pixmap.fill(Qt.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    if fundo:
        p.setBrush(QColor(CORES["fundo"]))
        p.drawRoundedRect(QRectF(0, 0, lado, lado), lado * 0.22, lado * 0.22)
    p.drawPixmap(int(lado * 0.14), int(lado * 0.14), icones.pixmap(forma, CORES["texto2"], int(lado * 0.72), 2.0, dpr=1))
    if n:
        r = lado * 0.27
        p.setBrush(QColor(AMBAR))
        p.drawEllipse(QRectF(lado - 2 * r, 0, 2 * r, 2 * r))
        fonte = QFont(tema.FONTE_TEXTO)
        fonte.setPixelSize(int(r * 1.25))
        fonte.setBold(True)
        p.setFont(fonte)
        p.setPen(QColor(CORES["escuro"]))
        p.drawText(QRectF(lado - 2 * r, 0, 2 * r, 2 * r), Qt.AlignCenter, "9+" if n > 9 else str(n))
    p.end()
    return QIcon(pixmap)


def _quando(iso):
    try:
        d = dt.datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return ""
    return (t("jp.grupo.hoje") if d.date() == dt.date.today() else d.strftime("%d/%m")) + d.strftime(" %H:%M")


def _botao(texto, papel, ao_clicar):
    b = QPushButton(texto)
    b.setProperty("papel", papel)
    b.setCursor(Qt.PointingHandCursor)
    b.clicked.connect(ao_clicar)
    return b


class PainelAvisos(QFrame):
    """A lista de avisos (mais novos primeiro, os não lidos com um ponto âmbar) e os pedidos de lixeira com os botões.
    Abrir o painel marca os avisos como lidos."""

    configurar = Signal()
    mudou = Signal()

    def __init__(self, probes=None, parent=None):
        super().__init__(parent)
        self.probes = probes or probes_lib.Probes()
        self.setObjectName("painel-avisos")
        self.setStyleSheet(f"QFrame#painel-avisos {{ background: {CORES['cartao']}; border: 1px solid {CORES['borda2']};"
                           " border-radius: 14px; }")
        self.setFixedWidth(400)
        v = QVBoxLayout(self)
        v.setContentsMargins(18, 14, 18, 14)
        v.setSpacing(10)
        topo = QHBoxLayout()
        titulo = QLabel(t("avisos.titulo"))
        titulo.setProperty("papel", "h2")
        topo.addWidget(titulo, 1)
        self.b_limpar = _botao(t("avisos.limpar"), "link", self._limpar)
        topo.addWidget(self.b_limpar)
        v.addLayout(topo)
        self.lista = QVBoxLayout()
        self.lista.setSpacing(8)
        miolo = QWidget()
        miolo.setLayout(self.lista)
        self.rolagem = QScrollArea()
        self.rolagem.setWidgetResizable(True)
        self.rolagem.setFrameShape(QFrame.NoFrame)
        self.rolagem.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.rolagem.setWidget(miolo)
        self.rolagem.setMaximumHeight(440)
        v.addWidget(self.rolagem)
        rodape = QHBoxLayout()
        rodape.addWidget(_botao(t("avisos.configurar"), "chip", self.configurar))
        rodape.addStretch(1)
        v.addLayout(rodape)

    def atualizar(self, marcar_lidos=True):
        while self.lista.count():
            it = self.lista.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        pendentes = self.probes.pendentes()
        avisos = self.probes.avisos()
        for p, x in pendentes:
            self.lista.addWidget(self._pedido(p, x))
        for a in avisos:
            self.lista.addWidget(self._aviso(a))
        if not pendentes and not avisos:
            vazio = tema.rotulo(t("avisos.vazio"), "nota", quebra=True)
            self.lista.addWidget(vazio)
        self.b_limpar.setVisible(bool(avisos))
        self.rolagem.widget().adjustSize()
        self.rolagem.setFixedHeight(min(440, self.rolagem.widget().sizeHint().height() + 4))
        self.adjustSize()
        if marcar_lidos and any(not a["lido"] for a in avisos):
            self.probes.marcar_lidos([a["id"] for a in avisos])
            self.mudou.emit()

    def _cartao(self):
        f = QFrame()
        f.setProperty("papel", "linha-lista")
        v = QVBoxLayout(f)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(4)
        return f, v

    def _aviso(self, a):
        f, v = self._cartao()
        topo = QLabel(("<span style='color:%s'>•</span> " % AMBAR if not a["lido"] else "")
                      + f"<b>{html.escape(tema.seguro(a['nome'], True))}</b> <span style='color:{CORES['mudo']}'>· {_quando(a['quando'])}</span>")
        topo.setTextFormat(Qt.RichText)
        topo.setProperty("papel", "nota")
        v.addWidget(topo)
        v.addWidget(tema.rotulo(tema.seguro(a["mensagem"], True), "texto", quebra=True))
        for item in a["itens"][:3]:
            if probes_lib.tipo_do_alvo(item) == "url":
                link = QLabel(f"<a style='color:{CORES['apoio']}' href='{html.escape(item, quote=True)}'>"
                              f"{html.escape(tema.seguro(item[:70], True))}</a>")
                link.setTextFormat(Qt.RichText)
                link.setOpenExternalLinks(True)         # só abre com o clique da pessoa
                link.setProperty("papel", "nota")
                v.addWidget(link)
            else:
                v.addWidget(tema.rotulo(tema.seguro(Path(item).name, True), "mono"))
        return f

    def _pedido(self, p, x):
        f, v = self._cartao()
        f.setStyleSheet(f"QFrame {{ border: 1px solid {AMBAR}; }} QLabel {{ border: 0; }}")
        v.addWidget(tema.rotulo(tema.seguro(t("probes.pede", nome=p["plano"]["name"], arquivo=Path(x["item"]).name), True),
                                "texto", quebra=True))
        linha = QHBoxLayout()
        linha.addWidget(_botao(t("probes.permitir"), "primario", lambda _=False: self._resolver(p["id"], x["id"], True)))
        linha.addWidget(_botao(t("probes.negar"), "chip", lambda _=False: self._resolver(p["id"], x["id"], False)))
        linha.addStretch(1)
        v.addLayout(linha)
        return f

    def _resolver(self, id_probe, id_pendente, aprovado):
        self.probes.resolver(id_probe, id_pendente, aprovado)
        self.atualizar()
        self.mudou.emit()

    def _limpar(self):
        self.probes.limpar_avisos()
        self.atualizar()
        self.mudou.emit()

    def abrir_em(self, ponto):
        """Mostra como popup (fecha ao clicar fora), com o canto de cima perto de `ponto`, dentro da tela."""
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.atualizar()
        tela = QApplication.screenAt(ponto) or QApplication.primaryScreen()
        area = tela.availableGeometry()
        x = min(max(area.left() + 8, ponto.x() - self.width() + 24), area.right() - self.width() - 8)
        y = ponto.y() + 8 if ponto.y() < area.center().y() else ponto.y() - self.height() - 8
        self.move(x, max(area.top() + 8, y))
        self.show()
        self.raise_()


class Sino(QPushButton):
    """O sino do cabeçalho: mostra o número de avisos e abre o painel. Olha o arquivo a cada 10 s; quando chega um
    aviso novo, emite `chegou` com o texto (a janela mostra na faixa)."""

    chegou = Signal(str)
    configurar = Signal()

    def __init__(self, probes=None):
        super().__init__()
        self.probes = probes or probes_lib.Probes()
        self.setProperty("papel", "icone")
        self.setFixedSize(40, 40)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(t("avisos.titulo"))
        self.painel = PainelAvisos(self.probes)
        self.painel.configurar.connect(lambda: (self.painel.hide(), self.configurar.emit()))
        self.painel.mudou.connect(self.olhar)
        self.clicked.connect(self._abrir)
        self._vistos = None
        self._relogio = QTimer(self)
        self._relogio.timeout.connect(self.olhar)
        self._relogio.start(10000)
        self.olhar()

    def olhar(self):
        try:
            avisos = self.probes.avisos()
            n = self.probes.nao_lidos()
        except Exception:                 # probes.json quebrado ou disco cheio: o sino não derruba a janela
            return
        self.setIcon(icone_com_selo(n, 64, "sino", fundo=False))
        self.setIconSize(QSize(34, 34))
        self.setToolTip(t("avisos.dica_sino", n=n))
        ids = {a["id"] for a in avisos}
        if self._vistos is not None:
            for a in avisos:
                if a["id"] not in self._vistos and not a["lido"]:
                    self.chegou.emit(tema.seguro(t("probes.titulo_aviso", nome=a["nome"]) + ": " + a["mensagem"], True))
                    break
        self._vistos = ids

    def _abrir(self):
        self.painel.abrir_em(self.mapToGlobal(QPoint(self.width(), self.height())))
        self.olhar()


# ------------------------------------------------------------
# A bandeja: o serviço dos Probes com um ícone perto do relógio
# ------------------------------------------------------------

class _Ponte(QObject):
    aviso = Signal(str, str)
    fim = Signal(int)


def bandeja_possivel():
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def rodar_bandeja(host, instalados_de, comando_abrir=None):
    """`opentars --probes` com tela: o mesmo laço de tars_probes.servico numa thread, e na thread da tela um ícone com o
    número de avisos, o painel ao clicar e a notificação do sistema a cada aviso. Sem bandeja no painel do sistema
    (GNOME sem a extensão de indicadores), o ícone não aparece, mas o serviço e as notificações continuam.
    Devolve o código do serviço (3: já havia um rodando)."""
    from .primeiro_uso import criar_aplicativo
    app = criar_aplicativo(["opentars-probes"])
    app.setQuitOnLastWindowClosed(False)
    probes = probes_lib.Probes()
    ponte = _Ponte()
    parar = threading.Event()
    resultado = {"codigo": 0}
    tray = QSystemTrayIcon(icone_com_selo(0))
    painel = PainelAvisos(probes)
    menu = QMenu()

    def abrir_app():
        subprocess.Popen(comando_abrir or ([shutil.which("opentars")] if shutil.which("opentars") else
                                           [sys.executable, str(Path(__file__).resolve().parent.parent / "tars.py")]),
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)

    def olhar():
        try:
            n = probes.nao_lidos()
            ligados = sum(1 for p in probes.listar() if p["ativo"])
        except Exception:
            return
        tray.setIcon(icone_com_selo(n))
        tray.setToolTip(t("avisos.dica_bandeja", n=n, ligados=ligados))

    def abrir_painel():
        painel.abrir_em(QCursor.pos())
        olhar()

    def sair():
        parar.set()          # só desta vez: o início automático continua ligado (desligar é na página Probes)

    painel.configurar.connect(lambda: (painel.hide(), abrir_app()))
    painel.mudou.connect(olhar)
    for texto, funcao in ((t("avisos.ver"), abrir_painel), (t("avisos.abrir_app"), abrir_app),
                          (t("avisos.pausar"), lambda: (probes.desligar_todos(), olhar())), (t("avisos.sair"), sair)):
        acao = QAction(texto, menu)
        acao.triggered.connect(funcao)
        menu.addAction(acao)
    tray.setContextMenu(menu)
    tray.activated.connect(lambda motivo: abrir_painel() if motivo in (QSystemTrayIcon.Trigger,
                                                                         QSystemTrayIcon.DoubleClick) else None)
    tray.messageClicked.connect(abrir_painel)
    ponte.aviso.connect(lambda titulo, texto: (tray.showMessage(titulo, texto, icone_com_selo(1), 8000)
                                               if tray.isVisible() and tray.supportsMessages()
                                               else probes_lib.avisar_desktop(titulo, texto), olhar()))
    ponte.fim.connect(lambda codigo: (resultado.update(codigo=codigo), app.quit()))

    def laco():
        codigo = probes_lib.servico(host, instalados_de, parar=parar.is_set,
                                    avisar=lambda titulo, texto, aviso=None: ponte.aviso.emit(titulo, texto), t=t)
        ponte.fim.emit(codigo)

    threading.Thread(target=laco, daemon=True, name="probes").start()
    if QSystemTrayIcon.isSystemTrayAvailable():
        tray.show()
    relogio = QTimer()
    relogio.timeout.connect(olhar)
    relogio.start(5000)
    olhar()
    app.exec()
    parar.set()
    return resultado["codigo"]
