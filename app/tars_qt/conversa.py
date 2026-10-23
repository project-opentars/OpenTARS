"""As peças da conversa: balão da pessoa, resposta da IA (texto, ferramentas, raciocínio), cartão de
etapas e cartão de aprovação. Tudo igual ao mockup (Main). A lógica fica fora: aqui só se desenha."""

import re
from pathlib import Path
from urllib.parse import unquote

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QFont, QFontMetrics, QGuiApplication, QImage, QImageReader, QPixmap
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy,
                               QToolButton, QVBoxLayout, QWidget)

import tars_i18n
from tars_i18n import t

from . import icones, tema
from .tema import CORES, Marcador, aplicar_papel, rotulo

LARGURA_COLUNA = 780
LARGURA_BOLHA = 520


def _botao(texto, papel, ao_clicar=None):
    b = QPushButton(texto)
    b.setProperty("papel", papel)
    b.setCursor(Qt.PointingHandCursor)
    if ao_clicar:
        b.clicked.connect(ao_clicar)
    return b


def _rotulo_selecionavel(texto="", papel="mensagem-ia", markdown=False):
    r = QLabel()
    r.setProperty("papel", papel)
    r.setWordWrap(True)
    r.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
    r.setOpenExternalLinks(False)          # texto da IA (ou de uma página) não abre file:// nem esquema estranho
    r.linkActivated.connect(abrir_link_seguro)
    r.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
    r.setTextFormat(Qt.MarkdownText if markdown else Qt.PlainText)
    r.setText(texto)
    return r


def abrir_link_seguro(endereco):
    """Só abre http(s) e mailto; qualquer outro esquema (file:, smb:, javascript:, um protocolo do sistema) é ignorado."""
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices
    url = QUrl(str(endereco))
    if url.scheme().lower() in ("http", "https", "mailto"):
        QDesktopServices.openUrl(url)


# ------------------------------------------------------------
# A pessoa
# ------------------------------------------------------------

class Bolha(QFrame):
    def __init__(self, texto):
        super().__init__()
        self.setProperty("papel", "bolha")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        self.rotulo = _rotulo_selecionavel(texto, "mensagem-ia")
        lay.addWidget(self.rotulo)
        self.setMaximumWidth(LARGURA_BOLHA)
        self._ajustar()

    def _ajustar(self):
        """O QLabel com quebra de linha dentro de um balão alinhado à direita não pede altura para a largura
        que realmente terá: a 2ª linha ficava cortada. Mede o texto e fixa o tamanho."""
        r = self.rotulo
        r.ensurePolished()
        maximo = LARGURA_BOLHA - 32
        caixa = r.fontMetrics().boundingRect(0, 0, maximo, 100000, int(Qt.TextWordWrap | Qt.AlignLeft), r.text())
        r.setFixedSize(min(maximo, caixa.width() + 6), caixa.height() + 4)

    def showEvent(self, e):
        super().showEvent(e)
        self._ajustar()

    def texto(self):
        return self.rotulo.text()


# ------------------------------------------------------------
# A IA
# ------------------------------------------------------------

# A cerca começa a linha ("```ls```" no meio da frase não é bloco), igual ao Tk.
_RE_BLOCO_CODIGO = re.compile(r"^```([\w+#.-]*)[^\n]*\n(.*?)(?:```|\Z)", re.DOTALL | re.MULTILINE)
LINHAS_MAXIMAS_CODIGO = 24


def partir_em_blocos(texto):
    """[("texto", "..."), ("codigo", "...", "linguagem"), ...] na ordem em que aparecem; bloco de código vazio some."""
    saida, fim = [], 0
    for m in _RE_BLOCO_CODIGO.finditer(texto):
        antes = texto[fim:m.start()]
        if antes.strip():
            saida.append(("texto", antes.strip("\n")))
        codigo = m.group(2).rstrip("\n")
        if codigo.strip():
            saida.append(("codigo", codigo, m.group(1).lower()))
        fim = m.end()
    resto = texto[fim:]
    if resto.strip():
        saida.append(("texto", resto.strip("\n")))
    juntos = []
    for p in saida:     # um bloco vazio entre dois textos os deixa vizinhos: vira um texto só
        if p[0] == "texto" and juntos and juntos[-1][0] == "texto":
            juntos[-1] = ("texto", juntos[-1][1] + "\n\n" + p[1])
        else:
            juntos.append(p)
    return _com_imagens(juntos)


# Imagem que o modelo "manda": `![texto](/caminho/foto.png)`. Só arquivo local, já conferido: nada é baixado de
# endereço da internet (uma imagem remota seria um pixel de rastreio) e o que não passa vira link comum.
_RE_IMAGEM = re.compile(r"!\[([^\]\n]*)\]\(\s*(<[^>\n]+>|[^)\n]+?)(?:\s+\"[^\"\n]*\")?\s*\)")
EXTENSOES_IMAGEM = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
BYTES_MAXIMOS_IMAGEM = 25 * 1024 * 1024
PIXELS_MAXIMOS_IMAGEM = 100_000_000
TAMANHO_MAXIMO_IMAGEM = QSize(640, 480)


def caminho_de_imagem(destino):
    """O arquivo de imagem local a que `destino` aponta, ou None (endereço da internet, data:, caminho relativo,
    arquivo que não existe, grande demais ou de outro tipo)."""
    d = destino.strip()
    if d.startswith("<") and d.endswith(">"):
        d = d[1:-1]
    if d.lower().startswith("file://"):
        d = d[7:]
    elif re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", d) and not re.match(r"^[a-zA-Z]:[\\/]", d):
        return None                                     # http:, data:, ftp:... (C:\ é caminho, não esquema)
    try:
        p = Path(unquote(d)).expanduser()
        if not p.is_absolute():
            return None
        p = p.resolve()
        if p.suffix.lower() in EXTENSOES_IMAGEM and p.is_file() and p.stat().st_size <= BYTES_MAXIMOS_IMAGEM:
            return p
    except (OSError, ValueError):
        pass
    return None


def _neutralizar_imagens(texto):
    """Imagem que não é arquivo local válido vira link comum: o Markdown do Qt não tenta carregá-la."""
    def troca(m):
        if caminho_de_imagem(m.group(2)):
            return m.group(0)
        return f"[{m.group(1) or 'imagem'}]({m.group(2)})"
    return _RE_IMAGEM.sub(troca, texto)


def _com_imagens(pedacos):
    """Parte cada trecho de texto nas imagens locais que ele cita: ("imagem", Path, texto alternativo)."""
    saida = []
    for p in pedacos:
        if p[0] != "texto":
            saida.append(p)
            continue
        texto, fim, achou = _neutralizar_imagens(p[1]), 0, False
        for m in _RE_IMAGEM.finditer(texto):
            achou = True
            antes = texto[fim:m.start()]
            if antes.strip():
                saida.append(("texto", antes.strip("\n")))
            saida.append(("imagem", caminho_de_imagem(m.group(2)), m.group(1)))
            fim = m.end()
        if not achou:
            saida.append(("texto", texto))
        elif texto[fim:].strip():
            saida.append(("texto", texto[fim:].strip("\n")))
    return saida


class ImagemIA(QLabel):
    """Uma imagem que o modelo mandou, reduzida para caber na coluna (a leitura já nasce no tamanho final)."""

    def __init__(self, caminho, alt=""):
        super().__init__()
        self.caminho = Path(caminho)
        leitor = QImageReader(str(self.caminho))
        leitor.setAutoTransform(True)
        tam = leitor.size()
        img = QImage()
        if tam.isValid() and 0 < tam.width() * tam.height() <= PIXELS_MAXIMOS_IMAGEM:
            if tam.width() > TAMANHO_MAXIMO_IMAGEM.width() or tam.height() > TAMANHO_MAXIMO_IMAGEM.height():
                leitor.setScaledSize(tam.scaled(TAMANHO_MAXIMO_IMAGEM, Qt.KeepAspectRatio))
            img = leitor.read()
        nome = tema.seguro(alt or self.caminho.name)
        self.setAccessibleName(nome)
        self.setToolTip(self.caminho.name)
        if img.isNull():                                # não abriu: mostra o nome no lugar
            self.setProperty("papel", "aviso-linha")
            self.setText(nome)
        else:
            self.setPixmap(QPixmap.fromImage(img))
            self.setFixedSize(img.size())


class _CodigoSemRoda(QPlainTextEdit):
    """A roda do mouse rola a conversa, não o bloco (que não tem rolagem vertical própria até 24 linhas)."""

    def wheelEvent(self, e):
        if self.verticalScrollBar().maximum() > 0:
            super().wheelEvent(e)
        else:
            e.ignore()


class CaixaCodigo(QFrame):
    """Janelinha de código dentro da resposta, como no Tk: nome da linguagem, botão Copiar e o código em fonte fixa."""

    def __init__(self, codigo, linguagem=""):
        super().__init__()
        self.setProperty("papel", "bloco-codigo")
        self.codigo = codigo
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        topo = QFrame()
        topo.setProperty("papel", "bloco-codigo-topo")
        linha = QHBoxLayout(topo)
        linha.setContentsMargins(10, 4, 8, 4)
        self.titulo = QLabel(linguagem or t("gui.codigo"))
        self.titulo.setProperty("papel", "bloco-codigo-lingua")
        linha.addWidget(self.titulo)
        linha.addStretch(1)
        self.botao = _botao(t("gui.copiar"), "copiar-codigo", self.copiar)
        linha.addWidget(self.botao)
        lay.addWidget(topo)
        self.texto = _CodigoSemRoda()
        self.texto.setProperty("papel", "bloco-codigo-texto")
        self.texto.setReadOnly(True)
        self.texto.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.texto.setFrameShape(QFrame.NoFrame)
        self.texto.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.texto.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        fonte = QFont(tema.FONTE_MONO)
        fonte.setPixelSize(13)
        self.texto.setFont(fonte)
        self.texto.setPlainText(codigo)
        self.texto.setTabStopDistance(QFontMetrics(fonte).horizontalAdvance(" ") * 4)
        linhas = max(1, min(codigo.count("\n") + 1, LINHAS_MAXIMAS_CODIGO))
        self._altura = QFontMetrics(fonte).lineSpacing() * linhas + 18
        self.texto.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.texto.setFixedHeight(self._altura)
        lay.addWidget(self.texto)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.texto.horizontalScrollBar().rangeChanged.connect(lambda *_: self._ajustar_altura())

    def _ajustar_altura(self):
        """Linha mais larga que a caixa: a barra horizontal aparece e ganha o seu espaço (sem ela, nada sobra embaixo)."""
        barra = self.texto.horizontalScrollBar()
        extra = 14 if barra.maximum() > 0 else 0
        if self.texto.height() != self._altura + extra:
            self.texto.setFixedHeight(self._altura + extra)

    def copiar(self):
        QGuiApplication.clipboard().setText(self.codigo)
        self.botao.setText(tema.seguro(t("gui.copiado")) + " ✓")
        QTimer.singleShot(1600, lambda: self.botao.setText(t("gui.copiar")))


class BlocoTexto(QWidget):
    """A resposta, em Markdown, que cresce enquanto chega (redesenha no máximo 20 vezes por segundo)."""

    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._lay = lay
        self.rotulo = _rotulo_selecionavel("", "mensagem-ia", markdown=True)
        self._pecas = []
        # Enquanto a resposta chega ela é texto simples: Markdown reinterpretado 20x por segundo sobre um texto
        # pela metade (cerca de código aberta, tabela cortada) é o ponto mais frágil do Qt e relaiouta tudo a cada
        # tique. O Markdown de verdade entra uma vez só, em concluir().
        self.rotulo.setTextFormat(Qt.PlainText)
        lay.addWidget(self.rotulo)
        self._texto = ""
        self._sujo = False
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._atualizar)

    def acrescentar(self, trecho):
        self._texto += trecho
        self._sujo = True
        if not self._timer.isActive():
            self._timer.start()

    def _atualizar(self):
        if self._sujo:
            self.rotulo.setText(self._texto)
            self._sujo = False
        else:
            self._timer.stop()

    def concluir(self):
        self._timer.stop()
        self._sujo = False
        pedacos = partir_em_blocos(self._texto)
        if not any(p[0] in ("codigo", "imagem") for p in pedacos):
            self.rotulo.setTextFormat(Qt.MarkdownText)
            self.rotulo.setText(_neutralizar_imagens(self._texto))
            return
        # Tem código ou imagem: o texto vira uma peça por trecho, cada cerca uma janelinha com Copiar e cada
        # imagem local uma figura.
        self._lay.removeWidget(self.rotulo)
        self.rotulo.hide()
        self._lay.setSpacing(10)
        for p in pedacos:
            if p[0] == "texto":
                peca = _rotulo_selecionavel(p[1], "mensagem-ia", markdown=True)
            elif p[0] == "imagem":
                peca = ImagemIA(p[1], p[2])
            else:
                peca = CaixaCodigo(p[1], p[2])
            self._lay.addWidget(peca, 0, Qt.AlignLeft) if p[0] == "imagem" else self._lay.addWidget(peca)
            self._pecas.append(peca)

    def texto(self):
        return self._texto


class BlocoRaciocinio(QWidget):
    """O raciocínio do modelo, recolhido por padrão ("Mostrar o raciocínio")."""

    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.botao = QToolButton()
        self.botao.setProperty("papel", "mais")
        self.botao.setCursor(Qt.PointingHandCursor)
        self.botao.setCheckable(True)
        self.botao.toggled.connect(self._alternar)
        self.corpo = _rotulo_selecionavel("", "pensamento")
        self.corpo.hide()
        lay.addWidget(self.botao, 0, Qt.AlignLeft)
        lay.addWidget(self.corpo)
        self._texto = ""
        self._atualizar_rotulo()

    def acrescentar(self, trecho):
        self._texto += trecho
        self.corpo.setText(self._texto)

    def texto(self):
        return self._texto

    def _alternar(self, aberto):
        self.corpo.setVisible(aberto)
        self._atualizar_rotulo()

    def _atualizar_rotulo(self):
        self.botao.setText(("↓ " if self.botao.isChecked() else "› ") + t("jp.raciocinio") + "…")


class LinhaFerramenta(QWidget):
    """"› abrindo app  calculadora   ✓ 0,12 s", em letra de máquina."""

    def __init__(self, nome, resumo=""):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.nome = QLabel("› " + tema.seguro(nome))
        self.nome.setProperty("papel", "ferramenta")
        self.resumo = QLabel(tema.seguro(resumo))
        self.resumo.setProperty("papel", "ferramenta")
        self.resumo.setStyleSheet(f"color: {CORES['mudo']};")
        self.fim = QLabel("")
        self.fim.setProperty("papel", "ferramenta-ok")
        lay.addWidget(self.nome)
        lay.addWidget(self.resumo, 1)
        lay.addWidget(self.fim)
        self.sucesso = None

    def concluir(self, sucesso, segundos):
        self.sucesso = bool(sucesso)
        if sucesso:
            self.fim.setText(f"✓ {segundos:.2f}s".replace(".", ",") if tars_i18n.idioma_atual().startswith("pt") else f"✓ {segundos:.2f}s")
        else:
            self.fim.setText("× " + t("msg.falhou"))
            self.fim.setStyleSheet("color: #FF9B9B;")


class CartaoEtapas(QFrame):
    """"Etapas  2 de 4" com uma bolinha por etapa; a que espera a pessoa ganha a etiqueta "espera por você"."""

    def __init__(self, etapas):
        super().__init__()
        self.setProperty("papel", "cartao-etapas")
        self._linhas = []
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 6, 0, 6)
        raiz.setSpacing(0)
        cab = QHBoxLayout()
        cab.setContentsMargins(16, 10, 16, 8)
        self.titulo = rotulo(t("jp.etapas"), "kicker")
        self.contagem = QLabel("")
        self.contagem.setProperty("papel", "mono")
        cab.addWidget(self.titulo)
        cab.addStretch(1)
        cab.addWidget(self.contagem)
        raiz.addLayout(cab)
        for texto in etapas:
            linha = QFrame()
            linha.setProperty("papel", "linha-etapa")
            h = QHBoxLayout(linha)
            h.setContentsMargins(16, 8, 16, 8)
            h.setSpacing(12)
            marcador = Marcador("pendente", 22)
            r = QLabel(texto)
            r.setWordWrap(True)
            r.setProperty("papel", "passo")
            espera = QLabel(t("jp.espera_voce"))
            espera.setProperty("papel", "espera")
            espera.hide()
            h.addWidget(marcador, 0, Qt.AlignTop)
            h.addWidget(r, 1)
            h.addWidget(espera, 0, Qt.AlignTop)
            raiz.addWidget(linha)
            self._linhas.append((linha, marcador, r, espera))
        self.feitas = 0
        self.esperando = False
        self._pintar()

    def total(self):
        return len(self._linhas)

    def definir_feitas(self, n):
        self.feitas = max(0, min(int(n), self.total()))
        self._pintar()

    def concluir_tudo(self):
        self.esperando = False
        self.definir_feitas(self.total())

    def esperar_pessoa(self, sim):
        self.esperando = bool(sim)
        self._pintar()

    def _pintar(self):
        for i, (linha, marcador, texto, espera) in enumerate(self._linhas):
            feita = i < self.feitas
            ativa = i == self.feitas and self.feitas < self.total()
            marcador.definir("feito" if feita else "ativo" if ativa else "pendente")
            aplicar_papel(texto, "passo" if feita else "passo-ativo" if ativa else "passo-futuro")
            linha.setProperty("ativa", bool(ativa))
            linha.style().unpolish(linha)
            linha.style().polish(linha)
            espera.setVisible(bool(ativa and self.esperando))
        self.contagem.setText(t("jp.etapas_contagem", feitas=self.feitas, total=self.total()))


class CartaoAprovacao(QFrame):
    """"Posso fazer isto?": o comando, e Permitir / Negar. Depois de responder vira uma linha só."""

    respondeu = Signal(bool)

    LINHAS_VISIVEIS = 3

    def __init__(self, comando, etiqueta=None, pergunta=None):
        super().__init__()
        self.setProperty("papel", "cartao-aprovacao")
        self.comando = comando
        self.resposta = None
        self._linhas = [l for l in comando.splitlines() if l.strip()] or [comando]
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(0)
        topo = QHBoxLayout()
        topo.setSpacing(10)
        self.etiqueta = QLabel((etiqueta or t("jp.aprov_etiqueta")).upper())
        self.etiqueta.setProperty("papel", "etiqueta")
        self.pergunta = QLabel(pergunta or t("jp.aprov_pergunta"))
        self.pergunta.setStyleSheet("font-weight: 600; font-size: 15px;")
        self.pergunta.setWordWrap(True)
        topo.addWidget(self.etiqueta, 0, Qt.AlignTop)
        topo.addWidget(self.pergunta, 1)
        lay.addLayout(topo)
        lay.addSpacing(12)
        self.caixa = QFrame()
        self.caixa.setProperty("papel", "comando")
        cl = QVBoxLayout(self.caixa)
        cl.setContentsMargins(14, 10, 14, 10)
        self.texto = QLabel("")
        self.texto.setProperty("papel", "mono-claro")
        self.texto.setTextFormat(Qt.PlainText)
        self.texto.setWordWrap(True)
        self.texto.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.mais = QLabel("")
        self.mais.setProperty("papel", "mono")
        cl.addWidget(self.texto)
        cl.addWidget(self.mais)
        lay.addWidget(self.caixa)
        lay.addSpacing(14)
        self.botoes = QWidget()
        bl = QHBoxLayout(self.botoes)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(10)
        self.b_permitir = _botao(t("jp.permitir"), "primario", lambda: self.responder(True))
        self.b_permitir.setMinimumHeight(44)
        self.b_negar = _botao(t("jp.negar"), "contorno", lambda: self.responder(False))
        self.b_negar.setMinimumHeight(44)
        self.b_lista = _botao(t("jp.ver_lista"), "contorno", self._expandir)
        self.b_lista.setMinimumHeight(44)
        bl.addWidget(self.b_permitir)
        bl.addWidget(self.b_lista)
        bl.addWidget(self.b_negar)
        bl.addStretch(1)
        lay.addWidget(self.botoes)
        self.resultado = QLabel("")
        self.resultado.setProperty("papel", "nota")
        self.resultado.hide()
        lay.addWidget(self.resultado)
        self._expandido = False
        self._mostrar()
        self.b_negar.setFocus()

    def _mostrar(self):
        cortar = len(self._linhas) > self.LINHAS_VISIVEIS and not self._expandido
        visiveis = self._linhas[:self.LINHAS_VISIVEIS] if cortar else self._linhas
        self.texto.setText("\n".join(visiveis))
        self.mais.setText(t("jp.e_mais", n=len(self._linhas) - self.LINHAS_VISIVEIS) if cortar else "")
        self.mais.setVisible(cortar)
        self.b_lista.setVisible(cortar)

    def _expandir(self):
        self._expandido = True
        self._mostrar()

    def responder(self, ok):
        if self.resposta is not None:
            return
        self.resposta = bool(ok)
        self.botoes.hide()
        self.resultado.setText(t("jp.aprov_permitido") if ok else t("jp.aprov_negado"))
        self.resultado.show()
        self.respondeu.emit(self.resposta)


class MensagemIA(QWidget):
    """O avatar (monolito) e, ao lado, os blocos da resposta, na ordem em que chegam."""

    def __init__(self):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)
        lay.addWidget(tema.svg_widget(tema.monolito_svg(), 32), 0, Qt.AlignTop)
        self.coluna = QVBoxLayout()
        self.coluna.setSpacing(14)
        lay.addLayout(self.coluna, 1)
        self.blocos = []
        self._texto = None
        self._pensamento = None
        self._ferramentas = []
        self.etapas = None

    # -- o que chega --------------------------------------------------------
    def _adicionar(self, widget):
        self.coluna.addWidget(widget)
        self.blocos.append(widget)
        return widget

    def texto_atual(self):
        if self._texto is None:
            self._texto = self._adicionar(BlocoTexto())
        return self._texto

    def raciocinio_atual(self):
        if self._pensamento is None:
            self._pensamento = self._adicionar(BlocoRaciocinio())
        return self._pensamento

    def acrescentar_texto(self, trecho):
        self.texto_atual().acrescentar(trecho)

    def acrescentar_raciocinio(self, trecho):
        self.raciocinio_atual().acrescentar(trecho)

    def fim_do_trecho(self):
        """Terminou um trecho de fala: o próximo (depois de uma ferramenta) vira outro bloco."""
        if self._texto is not None:
            self._texto.concluir()
        self._texto = None
        self._pensamento = None

    def virar_raciocinio(self):
        """O que parecia resposta era raciocínio (o modelo pensou em voz alta): troca o bloco."""
        if self._texto is None:
            return
        texto = self._texto.texto()
        self._texto._timer.stop()
        self.coluna.removeWidget(self._texto)
        self.blocos.remove(self._texto)
        self._texto.deleteLater()
        self._texto = None
        self.raciocinio_atual().acrescentar(texto)

    def ferramenta(self, nome, resumo=""):
        self.fim_do_trecho()
        linha = self._adicionar(LinhaFerramenta(nome, resumo))
        self._ferramentas.append(linha)
        return linha

    def ferramenta_fim(self, sucesso, segundos):
        pendentes = [l for l in self._ferramentas if l.sucesso is None]
        if pendentes:
            pendentes[-1].concluir(sucesso, segundos)

    def aviso(self, texto, erro=False):
        r = QLabel(tema.seguro(texto))
        r.setProperty("papel", "erro-linha" if erro else "aviso-linha")
        r.setWordWrap(True)
        return self._adicionar(r)

    def definir_etapas(self, etapas):
        self.etapas = self._adicionar(CartaoEtapas(etapas))
        return self.etapas

    def aprovacao(self, comando):
        self.fim_do_trecho()
        cartao = self._adicionar(CartaoAprovacao(comando))
        if self.etapas is not None:
            self.etapas.esperar_pessoa(True)
            cartao.respondeu.connect(lambda _ok: self.etapas.esperar_pessoa(False))
        return cartao

    def texto_completo(self):
        return "\n".join(b.texto() for b in self.blocos if isinstance(b, BlocoTexto))


# ------------------------------------------------------------
# A área rolável
# ------------------------------------------------------------

class AreaConversa(QScrollArea):
    """Coluna central de até 780 px, rolando. Fica colada no fim enquanto a resposta chega,
    a menos que a pessoa tenha subido pra ler."""

    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.NoFrame)
        miolo = QWidget()
        miolo.setObjectName("principal")
        horizontal = QHBoxLayout(miolo)
        horizontal.setContentsMargins(0, 0, 0, 0)
        self.coluna_w = QWidget()
        self.coluna_w.setMaximumWidth(LARGURA_COLUNA)
        self.coluna = QVBoxLayout(self.coluna_w)
        self.coluna.setContentsMargins(32, 28, 32, 24)
        self.coluna.setSpacing(22)
        self.coluna.addStretch(1)
        horizontal.addStretch(1)
        horizontal.addWidget(self.coluna_w, 1000)
        horizontal.addStretch(1)
        self.setWidget(miolo)
        self._colar = True
        self.verticalScrollBar().valueChanged.connect(self._ao_rolar)
        self.verticalScrollBar().rangeChanged.connect(self._ao_crescer)
        self.itens = []
        self.vazio = None

    def _ao_rolar(self, valor):
        barra = self.verticalScrollBar()
        self._colar = valor >= barra.maximum() - 24

    def _ao_crescer(self, _minimo, maximo):
        if self._colar:
            self.verticalScrollBar().setValue(maximo)

    def _inserir(self, widget, alinhamento=None):
        self.coluna.insertWidget(self.coluna.count() - 1, widget, 0, alinhamento or Qt.Alignment())
        self.itens.append(widget)
        return widget

    def adicionar_pessoa(self, texto):
        self._colar = True
        return self._inserir(Bolha(texto), Qt.AlignRight)

    def adicionar_ia(self):
        m = MensagemIA()
        self._inserir(m)
        return m

    def adicionar_widget(self, widget):
        return self._inserir(widget)

    def limpar(self):
        for w in self.itens:
            self.coluna.removeWidget(w)
            w.hide()
            w.setParent(None)
            w.deleteLater()
        self.itens = []
        self._colar = True

    def rolar_ao_fim(self):
        self._colar = True
        QTimer.singleShot(0, lambda: self.verticalScrollBar().setValue(self.verticalScrollBar().maximum()))
