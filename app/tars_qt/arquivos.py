"""5.2 (F4): o painel das ações em arquivos (atalho global com arquivos selecionados no gerenciador de arquivos), como no
mock-up aprovado em 20/10: resumir, renomear pelo conteúdo, mover para uma pasta e mandar para a lixeira; com fotos, editar
a foto por frase (F4.8, mock-up aprovado em 24/10, tars_fotos: sempre cópia). Tudo mostra a prévia antes e só muda algo
com o clique de confirmação; renomear e mover dá para desfazer enquanto o painel está aberto.
O texto dos arquivos vai ao modelo pelo contrato das ações de texto (é dado, nunca instrução)."""
import shutil
import threading
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, Qt, Signal
from PySide6.QtGui import QCursor, QGuiApplication, QPixmap
from PySide6.QtWidgets import (QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextBrowser, QVBoxLayout,
                               QWidget)

import tars_acoes_arquivos as aa
import tars_acoes_texto as acoes_lib
import tars_fotos as fotos
from tars_i18n import idioma_atual, t

from . import icones, tema
from .tema import CORES

LARGURA = 500
ACOES = ("resumir", "foto", "renomear", "mover", "lixeira")
LUGAR = {"resumir": (0, 0), "foto": (0, 0), "renomear": (0, 1), "mover": (1, 0), "lixeira": (1, 1)}   # foto ou resumir
RAPIDOS = ("quadrado", "clara", "girar", "cinza", "email", "sem_fundo", "aumentar", "remover")
MAXIMO_RESUMOS = 5


class PainelArquivos(QFrame):
    nomes_prontos = Signal(int, object)        # (rodada, [(caminho, novo | None)])
    resumo_pronto = Signal(int, str)
    previa_pronta = Signal(int, object)        # (pedido, (png antes, png depois, tamanho antes, tamanho depois) | None)

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
        for acao in ACOES:
            b = QPushButton(t(f"arq.acao.{acao}"))
            b.setProperty("papel", "chip")
            b.setCheckable(True)
            b.setMinimumHeight(36)
            b.clicked.connect(lambda _=False, a=acao: self.escolher(a))
            chips.addWidget(b, *LUGAR[acao])
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
        self.previa_pronta.connect(self._previa_pronta)

    # -- abrir e escolher -------------------------------------------------------------------------------
    def abrir(self, arquivos):
        self.arquivos = [str(a) for a in arquivos]
        self.feitos = []
        so_fotos = all(fotos.e_foto(a) for a in self.arquivos)
        self.botoes_acao["foto"].setVisible(so_fotos)
        self.botoes_acao["resumir"].setVisible(not so_fotos)       # foto não tem texto para resumir
        self.titulo.setText(t("arq.titulo_fotos" if so_fotos else "arq.titulo", n=len(self.arquivos)))
        self.escolher("foto" if so_fotos else "renomear")
        self._encaixar()
        tela = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        area = tela.availableGeometry()
        p = QCursor.pos() + QPoint(24, 24)
        self.move(min(max(area.left() + 12, p.x()), area.right() - self.width() - 12),
                  min(max(area.top() + 12, p.y()), area.bottom() - self.height() - 12))
        self.show()
        self.raise_()
        self.activateWindow()

    def _encaixar(self):
        """A altura que o conteúdo pede (o adjustSize do Qt corta janelas em 2/3 da tela e o conteúdo se sobrepõe)."""
        self.resize(LARGURA, self.sizeHint().height())

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
        self.modelo.setText(t("arq.neste_computador") if acao == "foto" else t("arq.sem_modelo") if acao in ("mover", "lixeira") else
                            acoes_lib.escolher_modelo(self.instalados, self.lite, self.principal).split("/")[-1])
        n = len(self.arquivos)
        if acao == "foto":
            self._montar_foto()
        elif acao == "renomear":
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
        self._encaixar()

    # -- editar a foto (F4.8) ----------------------------------------------------------------------------
    def _montar_foto(self):
        self.pedido_foto = QLineEdit()
        self.pedido_foto.setPlaceholderText(t("foto.dica"))
        self.pedido_foto.setAccessibleName(t("foto.dica"))
        self.pedido_foto.setMinimumHeight(40)
        self.pedido_foto.returnPressed.connect(self._atualizar_foto)
        self.pedido_foto.textChanged.connect(lambda _texto: self.botao_aplicar.setEnabled(False))
        self.caixa.insertWidget(0, self.pedido_foto)
        rapidos = QWidget()
        r = QGridLayout(rapidos)          # 3 + 2: numa linha só os cinco não cabem
        r.setContentsMargins(0, 0, 0, 0)
        r.setSpacing(6)
        for i, chave in enumerate(RAPIDOS):
            b = QPushButton(t(f"foto.chip.{chave}"))
            b.setProperty("papel", "chip")
            b.setMinimumHeight(32)
            b.clicked.connect(lambda _=False, c=chave: self._rapido(c))
            r.addWidget(b, i // 3, i % 3)
        self.caixa.insertWidget(1, rapidos)
        lado = QHBoxLayout()
        self.img_antes, self.img_depois = QLabel(), QLabel()
        self.leg_antes, self.leg_depois = QLabel(), QLabel()
        for legenda in (self.leg_antes, self.leg_depois):
            legenda.setStyleSheet(f"color: {CORES['apoio']}; font-size: 12px;")
            legenda.setFixedHeight(18)
        for img, legenda in ((self.img_antes, self.leg_antes), (None, None), (self.img_depois, self.leg_depois)):
            if img is None:
                lado.addWidget(QLabel("→"), 0, Qt.AlignVCenter)
                continue
            coluna = QVBoxLayout()
            img.setFixedSize(176, 132)
            img.setAlignment(Qt.AlignCenter)
            coluna.addWidget(img)
            coluna.addWidget(legenda, 0, Qt.AlignHCenter)
            lado.addLayout(coluna)
        bloco = QWidget()
        bloco.setLayout(lado)
        bloco.setMinimumHeight(132 + 18 + 12)
        self.caixa.addWidget(bloco)
        self.entendido = tema.rotulo(t("foto.o_que_fazer"), "texto", quebra=True)
        self.caixa.addWidget(self.entendido)
        self.operacoes, self.extras, self.esperando_clique, self.tam_original = [], [], False, None
        self.img_antes.installEventFilter(self)
        n = len(self.arquivos)
        self.botao_aplicar.setText(t("foto.salvar", nome=fotos.nome_da_copia(self.arquivos[0], [], t("foto.sufixo")).name) if n == 1
                                   else t("foto.salvar_n", n=n))
        self.botao_aplicar.setEnabled(False)
        self.aviso.setText(t("foto.aviso"))
        self._atualizar_foto()

    def _rapido(self, chave):
        if chave == "remover":          # 25/10: não cabe numa frase; a pessoa clica no objeto na foto da esquerda
            self.esperando_clique = True
            self.img_antes.setCursor(Qt.CrossCursor)
            self.entendido.setText(t("foto.clique_no_objeto"))
            return
        atual = self.pedido_foto.text().strip()
        frase = t(f"foto.frase.{chave}")
        self.pedido_foto.setText(f"{atual}, {frase}" if atual else frase)
        self._atualizar_foto()

    def eventFilter(self, objeto, evento):
        if objeto is getattr(self, "img_antes", None) and evento.type() == QEvent.MouseButtonRelease and \
                self.esperando_clique and self.tam_original and objeto.pixmap() is not None and not objeto.pixmap().isNull():
            mapa = objeto.pixmap()
            x0, y0 = (objeto.width() - mapa.width()) / 2, (objeto.height() - mapa.height()) / 2   # a foto vem centrada
            px, py = (evento.position().x() - x0) / mapa.width(), (evento.position().y() - y0) / mapa.height()
            if 0 <= px <= 1 and 0 <= py <= 1:
                self.esperando_clique = False
                objeto.unsetCursor()
                self.extras = [op for op in self.extras if op[0] != "remover"] + \
                    [("remover", round(px * self.tam_original[0]), round(py * self.tam_original[1]))]
                self._atualizar_foto()
            return True
        return super().eventFilter(objeto, evento)

    def _atualizar_foto(self):
        texto = self.pedido_foto.text().strip()
        self.operacoes = fotos.entender(texto) + list(getattr(self, "extras", []))
        o_que = fotos.descrever(self.operacoes, "pt_BR" if idioma_atual().startswith("pt") else "en")
        self.entendido.setText(t("foto.entendi", o_que=o_que) if o_que else
                               t("foto.nao_entendi") if texto else t("foto.o_que_fazer"))
        self.pedido_previa = getattr(self, "pedido_previa", 0) + 1     # só a prévia do último pedido aparece
        numero, caminho, operacoes = self.pedido_previa, self.arquivos[0], list(self.operacoes)

        def trabalho():
            try:
                resultado = fotos.previa(caminho, operacoes)
            except Exception:  # noqa: BLE001  (arquivo que o Pillow não abre: sem prévia, o botão fica desligado)
                resultado = None
            try:
                self.previa_pronta.emit(numero, resultado)
            except RuntimeError:        # o painel fechou enquanto a prévia (que pode levar segundos) era feita
                pass
        threading.Thread(target=trabalho, daemon=True).start()

    def _previa_pronta(self, numero, resultado):
        if numero != self.pedido_previa or self.acao != "foto":
            return
        if resultado is None:
            self.entendido.setText(t("foto.nao_abre") if not any(op[0] in ("remover", "aumentar", "sem_fundo")
                                                                 for op in self.operacoes) else t("foto.modelinhos_faltando"))
            return
        antes, depois, tam_antes, tam_depois = resultado
        self.tam_original = tam_antes
        for img, dados in ((self.img_antes, antes), (self.img_depois, depois)):
            mapa = QPixmap()
            mapa.loadFromData(dados)
            img.setPixmap(mapa.scaled(img.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.leg_antes.setText(t("foto.antes", w=tam_antes[0], h=tam_antes[1]))
        self.leg_depois.setText(t("foto.depois", w=tam_depois[0], h=tam_depois[1]))
        self.botao_aplicar.setEnabled(bool(self.operacoes))
        if len(self.arquivos) == 1:
            self.botao_aplicar.setText(t("foto.salvar", nome=fotos.nome_da_copia(self.arquivos[0], self.operacoes, t("foto.sufixo")).name))
        self._encaixar()

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
        if self.acao == "foto":
            salvas, erros = [], []
            for caminho in self.arquivos:
                try:
                    salvas.append(fotos.salvar_copia(caminho, self.operacoes, t("foto.sufixo")).name)
                except Exception as e:  # noqa: BLE001  (formato que o Pillow não grava, disco cheio)
                    erros.append(f"{Path(caminho).name}: {e}")
            self.aviso.setText(t("foto.salvas", nomes=", ".join(salvas)) + (" " + "; ".join(erros) if erros else ""))
            self.botao_aplicar.setEnabled(False)       # uma cópia por clique; mudar a frase libera de novo
            return
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
