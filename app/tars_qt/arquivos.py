"""5.2 (F4): o painel das ações em arquivos (atalho global com arquivos selecionados no gerenciador de arquivos), como no
mock-up aprovado em 20/10: resumir, renomear pelo conteúdo, mover para uma pasta e mandar para a lixeira. Tudo mostra a
prévia antes e só muda algo com o clique de confirmação; renomear e mover dá para desfazer enquanto o painel está aberto.
O texto dos arquivos vai ao modelo pelo contrato das ações de texto (é dado, nunca instrução)."""
import shutil
import threading
from pathlib import Path

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import (QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextBrowser, QVBoxLayout,
                               QWidget)

import tars_acoes_arquivos as aa
import tars_acoes_texto as acoes_lib
from tars_i18n import idioma_atual, t

from . import icones, tema
from .tema import CORES

LARGURA = 500
ACOES = ("resumir", "renomear", "mover", "lixeira")
MAXIMO_RESUMOS = 5


class PainelArquivos(QFrame):
    nomes_prontos = Signal(int, object)        # (rodada, [(caminho, novo | None)])
    resumo_pronto = Signal(int, str)

    def __init__(self, host, modelos_instalados, lite, principal):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setObjectName("painel-arquivos")
        self.setWindowTitle("openTARS")
        self.setFixedWidth(LARGURA)
        self.setStyleSheet(f"QFrame#painel-arquivos {{ background: {CORES['fundo']}; border: 1px solid {CORES['borda2']}; "
                           "border-radius: 16px; }")
        self.host, self.instalados, self.lite, self.principal = host, modelos_instalados, lite, principal
        self.arquivos, self.acao, self.feitos, self.campos = [], "renomear", [], []
        self.rodada = 0
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(12)

        topo = QHBoxLayout()
        topo.setSpacing(10)
        topo.addWidget(tema.svg_widget(tema.monolito_svg(), 24), 0, Qt.AlignVCenter)
        self.titulo = tema.rotulo("", "titulo-cartao")
        topo.addWidget(self.titulo)
        topo.addStretch(1)
        self.modelo = QLabel()
        self.modelo.setProperty("papel", "pilula")
        topo.addWidget(self.modelo)
        fechar = QPushButton()
        fechar.setProperty("papel", "icone")
        fechar.setIcon(icones.icone("fechar", CORES["apoio"], 16))
        fechar.setAccessibleName(t("acoes.fechar"))
        fechar.setFixedSize(36, 36)
        fechar.clicked.connect(self.hide)
        topo.addWidget(fechar)
        v.addLayout(topo)

        chips = QGridLayout()          # 2 x 2: numa linha só os quatro não cabem e o texto some
        chips.setSpacing(6)
        self.botoes_acao = {}
        for i, acao in enumerate(ACOES):
            b = QPushButton(t(f"arq.acao.{acao}"))
            b.setProperty("papel", "chip")
            b.setCheckable(True)
            b.setMinimumHeight(36)
            b.clicked.connect(lambda _=False, a=acao: self.escolher(a))
            chips.addWidget(b, i // 2, i % 2)
            self.botoes_acao[acao] = b
        v.addLayout(chips)

        caixa = QFrame()
        caixa.setProperty("papel", "painel")
        self.caixa = QVBoxLayout(caixa)
        self.caixa.setContentsMargins(14, 12, 14, 12)
        self.caixa.setSpacing(8)
        v.addWidget(caixa)
        self.aviso = tema.rotulo("", "nota", quebra=True)
        v.addWidget(self.aviso)

        botoes = QHBoxLayout()
        self.botao_aplicar = QPushButton()
        self.botao_aplicar.setProperty("papel", "primario")
        self.botao_aplicar.setMinimumHeight(40)
        self.botao_aplicar.clicked.connect(self.aplicar)
        self.botao_desfazer = QPushButton(t("arq.desfazer"))
        self.botao_desfazer.setProperty("papel", "contorno")
        self.botao_desfazer.setMinimumHeight(40)
        self.botao_desfazer.clicked.connect(self.desfazer)
        cancelar = QPushButton(t("arq.cancelar"))
        cancelar.setProperty("papel", "link")
        cancelar.clicked.connect(self.hide)
        botoes.addWidget(self.botao_aplicar, 1)
        botoes.addWidget(self.botao_desfazer)
        botoes.addWidget(cancelar)
        v.addLayout(botoes)
        v.addWidget(tema.rotulo(t("arq.rodape"), "nota", quebra=True))
        self.nomes_prontos.connect(self._nomes_prontos)
        self.resumo_pronto.connect(self._resumo_pronto)

    # -- abrir e escolher -------------------------------------------------------------------------------
    def abrir(self, arquivos):
        self.arquivos = [str(a) for a in arquivos]
        self.feitos = []
        self.titulo.setText(t("arq.titulo", n=len(self.arquivos)))
        self.modelo.setText(acoes_lib.escolher_modelo(self.instalados, self.lite, self.principal).split("/")[-1])
        self.escolher("renomear")
        self.adjustSize()
        tela = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        area = tela.availableGeometry()
        p = QCursor.pos() + QPoint(24, 24)
        self.move(min(max(area.left() + 12, p.x()), area.right() - self.width() - 12),
                  min(max(area.top() + 12, p.y()), area.bottom() - self.height() - 12))
        self.show()
        self.raise_()
        self.activateWindow()

    def _limpar(self):
        while self.caixa.count():
            item = self.caixa.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.campos = []

    def _linha(self, esquerda, direita=None):
        linha = QWidget()
        h = QHBoxLayout(linha)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        nome = QLabel(esquerda)
        nome.setStyleSheet(f"color: {CORES['apoio']}; font-size: 13px;")
        h.addWidget(nome, 1)
        if direita is not None:
            h.addWidget(QLabel("→"))
            h.addWidget(direita, 2)
        self.caixa.addWidget(linha)

    def escolher(self, acao):
        self.acao = acao
        self.rodada += 1
        for nome, b in self.botoes_acao.items():
            b.setChecked(nome == acao)
        self._limpar()
        self.botao_desfazer.setVisible(bool(self.feitos))
        self.caixa.addWidget(tema.rotulo(t(f"arq.previa.{acao}"), "nota"))
        n = len(self.arquivos)
        if acao == "renomear":
            for caminho in self.arquivos:
                campo = QLineEdit(t("arq.pensando"))
                campo.setEnabled(False)
                campo.setAccessibleName(t("arq.novo_nome", nome=Path(caminho).name))
                self.campos.append((caminho, campo))
                self._linha(Path(caminho).name, campo)
            self.botao_aplicar.setText(t("arq.renomear_n", n=n))
            self.botao_aplicar.setEnabled(False)
            self.aviso.setText(t("arq.aviso_renomear"))
            self._sugerir()
        elif acao == "resumir":
            self.saida = QTextBrowser()
            self.saida.setFrameShape(QFrame.NoFrame)
            self.saida.setMinimumHeight(140)
            self.saida.setStyleSheet(f"background: transparent; color: {CORES['texto']}; font-size: 14px;")
            self.caixa.addWidget(self.saida)
            self.botao_aplicar.setText(t("arq.resumir"))
            self.botao_aplicar.setEnabled(True)
            self.aviso.setText(t("arq.aviso_resumir", n=MAXIMO_RESUMOS))
        else:
            for caminho in self.arquivos:
                self._linha(Path(caminho).name)
            self.botao_aplicar.setText(t("arq.escolher_pasta") if acao == "mover" else t("arq.lixeira_n", n=n))
            self.botao_aplicar.setEnabled(True)
            self.aviso.setText(t(f"arq.aviso_{acao}"))
        self.adjustSize()

    # -- o modelo -------------------------------------------------------------------------------------
    def _modelo(self):
        return acoes_lib.escolher_modelo(self.instalados, self.lite, self.principal)

    def _sugerir(self):
        rodada, arquivos, modelo = self.rodada, list(self.arquivos), self._modelo()
        idioma = "pt_BR" if idioma_atual().startswith("pt") else "en"

        def trabalho():
            try:
                pares = aa.sugerir_nomes(arquivos, modelo, self.host, idioma=idioma)
            except Exception:  # noqa: BLE001  (Ollama fora: os campos ficam editáveis, com o nome de hoje)
                pares = [(c, None) for c in arquivos]
            self.nomes_prontos.emit(rodada, pares)
        threading.Thread(target=trabalho, daemon=True).start()

    def _nomes_prontos(self, rodada, pares):
        if rodada != self.rodada:
            return
        sugeridos = dict(pares)
        for caminho, campo in self.campos:
            novo = sugeridos.get(caminho)
            campo.setText(novo or Path(caminho).name)
            campo.setCursorPosition(0)         # o começo do nome é o que diz o que é
            campo.setEnabled(True)            # a pessoa pode editar qualquer nome antes de aplicar ("Editar nomes")
            if novo is None:
                campo.setToolTip(t("arq.sem_texto"))
        if any(n is None for n in sugeridos.values()):
            self.aviso.setText(t("arq.aviso_renomear") + " " + t("arq.sem_texto"))
        self.botao_aplicar.setEnabled(True)

    def _resumo_pronto(self, rodada, texto):
        if rodada == self.rodada:
            self.saida.setMarkdown(texto)
            self.botao_aplicar.setEnabled(True)

    # -- aplicar -------------------------------------------------------------------------------------------
    def aplicar(self):
        if self.acao == "renomear":
            pares = [(c, campo.text().strip()) for c, campo in self.campos if campo.text().strip() != Path(c).name]
            self.feitos = aa.renomear(pares)
            mapa = dict(self.feitos)
            self.arquivos = [mapa.get(c, c) for c in self.arquivos]
            self.aviso.setText(t("arq.feito_renomear", n=len(self.feitos)))
            self.botao_aplicar.setEnabled(False)
            self.botao_desfazer.setVisible(bool(self.feitos))
        elif self.acao == "mover":
            pasta = QFileDialog.getExistingDirectory(self, t("arq.escolher_pasta"), str(Path(self.arquivos[0]).parent))
            if not pasta:
                return
            self.feitos, pulados = aa.mover(self.arquivos, pasta)
            mapa = dict(self.feitos)
            self.arquivos = [mapa.get(c, c) for c in self.arquivos]
            self.aviso.setText(t("arq.feito_mover", n=len(self.feitos), pasta=pasta)
                               + (" " + t("arq.pulados", n=len(pulados)) if pulados else ""))
            self.botao_desfazer.setVisible(bool(self.feitos))
        elif self.acao == "lixeira":
            enviados, erros = aa.para_lixeira(self.arquivos)
            self.arquivos = [c for c in self.arquivos if c not in enviados]
            self.aviso.setText(t("arq.feito_lixeira", n=len(enviados)) + (" " + "; ".join(erros) if erros else ""))
            self.botao_aplicar.setEnabled(False)
        else:
            self.botao_aplicar.setEnabled(False)
            self.saida.setPlainText(t("arq.pensando"))
            rodada, arquivos, modelo = self.rodada, self.arquivos[:MAXIMO_RESUMOS], self._modelo()

            def trabalho():
                partes = []
                for caminho in arquivos:
                    try:
                        resumo = aa.resumir(caminho, modelo, self.host) or t("arq.sem_texto")
                    except Exception as e:  # noqa: BLE001
                        resumo = str(e)
                    partes.append(f"**{Path(caminho).name}**\n\n{resumo}")
                self.resumo_pronto.emit(rodada, "\n\n".join(partes))
            threading.Thread(target=trabalho, daemon=True).start()

    def desfazer(self):
        if self.acao == "mover":
            for antigo, novo in reversed(self.feitos):
                if Path(novo).exists() and not Path(antigo).exists():
                    shutil.move(novo, antigo)          # pode ser outro disco: rename não serve
        else:
            aa.desfazer(self.feitos)
        volta = {novo: antigo for antigo, novo in self.feitos}
        self.arquivos = [volta.get(c, c) for c in self.arquivos]
        self.feitos = []
        self.aviso.setText(t("arq.desfeito"))
        self.escolher(self.acao)
