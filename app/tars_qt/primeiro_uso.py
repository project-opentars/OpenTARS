"""O assistente de primeiro uso do openTARS 5.0, na janela Qt do mockup.

Cinco passos: idioma, Ollama, nuvem (opcional), Gargantua e teste rápido,
mais uma tela final. Aqui só se desenha e se liga botão a função; tudo o que
mexe no Ollama, no disco e na rede está em tars_primeiro_uso.py.

Trabalho demorado (procurar o Ollama, instalar, baixar, testar) roda em
thread e volta pra janela por sinais, então a janela nunca trava.
"""

import os
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFrame, QHBoxLayout, QLineEdit, QMainWindow, QProgressBar, QPushButton,
    QStackedWidget, QVBoxLayout, QWidget, QButtonGroup, QLabel,
)

import tars_atualizacao
import tars_i18n
import tars_modos as modos
import tars_primeiro_uso as pu
from tars_i18n import t

from . import fio, tema
from .login_ollama import LoginOllama
from .tema import CORES, Marcador, aplicar_papel, rotulo

LARGURA = 620          # largura do conteúdo, como no mockup
TOTAL_PASSOS = len(pu.PASSOS)

# nome da tela -> índice do passo na barra lateral (a tela da chave é parte do passo da nuvem)
PASSO_DA_TELA = {"idioma": 0, "modo": 1, "ollama": 2, "nuvem": 3, "chave": 3, "gargantua": 4, "teste": 5,
                 "pronto": TOTAL_PASSOS}


def limitar(filho, largura=LARGURA):
    """Põe `filho` à esquerda, com no máximo `largura` de largura."""
    c = QWidget()
    lay = QHBoxLayout(c)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)
    filho.setMaximumWidth(largura)
    lay.addWidget(filho, 1000)
    lay.addStretch(1)
    return c


def botao(texto, papel, ao_clicar=None):
    b = QPushButton(texto)
    b.setProperty("papel", papel)
    b.setCursor(Qt.PointingHandCursor)
    if ao_clicar:
        b.clicked.connect(ao_clicar)
    return b


def formatar_gb(bytes_):
    texto = f"{bytes_ / 1e9:.1f}"
    return texto.replace(".", ",") if tars_i18n.idioma_atual().startswith("pt") else texto


class Sinais(QObject):
    ollama = Signal(dict)
    instalado = Signal(bool, str)
    iniciado = Signal(bool, str)
    ja_tem = Signal(bool)
    # bytes feitos e totais vão como object: Signal(int) é de 32 bits (máximo ~2,1 GB) e o Gargantua tem ~2,5 GB;
    # com int o Qt estoura (OverflowError), a atualização se perde e a barra fica em 0% o download inteiro
    progresso = Signal(float, object, object, object)
    baixado = Signal(bool, str)
    teste = Signal(bool, str, float)
    nuvem = Signal(bool, str)


class LinhaStatus(QWidget):
    """Bolinha + texto, como nas listas do mockup."""

    def __init__(self, estado, texto, tamanho=20, papel="linha"):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        self.marcador = Marcador(estado, tamanho)
        self.texto = rotulo(texto, papel, quebra=True)
        lay.addWidget(self.marcador, 0, Qt.AlignTop)
        lay.addWidget(self.texto, 1)

    def definir(self, estado, texto):
        self.marcador.definir(estado)
        self.texto.setText(texto)


class CartaoOpcao(QFrame):
    """Cartão de escolha com bolinha de rádio. Um grupo (GrupoCartoes) garante uma só marcada."""

    toggled = Signal(bool)

    def __init__(self, titulo, descricao):
        super().__init__()
        self.setObjectName("cartao")
        self.setProperty("marcado", False)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(22, 19, 22, 19)
        lay.setSpacing(16)
        self.marca = Marcador("pendente", 24)
        lay.addWidget(self.marca, 0, Qt.AlignTop)
        coluna = QVBoxLayout()
        coluna.setSpacing(4)
        self.titulo = rotulo(titulo, "titulo-cartao", quebra=True)
        self.descricao = rotulo(descricao, "desc-cartao", quebra=True)
        for r in (self.titulo, self.descricao):
            r.setAttribute(Qt.WA_TransparentForMouseEvents)
            coluna.addWidget(r)
        lay.addLayout(coluna, 1)
        self.grupo = None

    def isChecked(self):
        return bool(self.property("marcado"))

    def setChecked(self, valor):
        if bool(valor) == self.isChecked():
            return
        self.setProperty("marcado", bool(valor))
        self.marca.definir("ativo" if valor else "pendente")
        self.style().unpolish(self)
        self.style().polish(self)
        self.toggled.emit(bool(valor))

    def mousePressEvent(self, evento):
        if evento.button() == Qt.LeftButton:
            self._escolher()

    def keyPressEvent(self, evento):
        if evento.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
            self._escolher()
        else:
            super().keyPressEvent(evento)

    def _escolher(self):
        if self.grupo:
            self.grupo.escolher(self)
        else:
            self.setChecked(True)


class GrupoCartoes:
    def __init__(self, cartoes, inicial=0):
        self.cartoes = list(cartoes)
        for c in self.cartoes:
            c.grupo = self
        self.escolher(self.cartoes[inicial])

    def escolher(self, cartao):
        for c in self.cartoes:
            c.setChecked(c is cartao)

    def marcado(self):
        return next(i for i, c in enumerate(self.cartoes) if c.isChecked())


# ------------------------------------------------------------
# Telas
# ------------------------------------------------------------

class Pagina(QWidget):
    """Cabeçalho (passo, título, texto), corpo e a linha de botões de baixo."""

    nome = ""

    def __init__(self, jan, titulo, texto):
        super().__init__()
        self.jan = jan
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.kicker = rotulo("", "kicker")
        self.kicker.setFixedHeight(18)
        v.addWidget(self.kicker)
        v.addSpacing(10)
        self.h1 = rotulo(titulo, "h1", quebra=True)
        self.h1.setFixedHeight(39)
        v.addWidget(self.h1)
        v.addSpacing(12)
        self.p = rotulo(texto, "texto", quebra=True)
        v.addWidget(limitar(self.p, 560))
        v.addSpacing(32)
        self.corpo = QVBoxLayout()
        self.corpo.setContentsMargins(0, 0, 0, 0)
        self.corpo.setSpacing(14)
        corpo_w = QWidget()
        corpo_w.setLayout(self.corpo)
        v.addWidget(limitar(corpo_w))
        v.addStretch(1)
        self.nav = QHBoxLayout()
        self.nav.setContentsMargins(0, 0, 0, 0)
        nav_w = QWidget()
        nav_w.setLayout(self.nav)
        v.addWidget(limitar(nav_w))
        self.construir()
        self.atualizar_kicker()

    def ajustar_titulo(self):
        """Título de uma ou duas linhas, cada uma com 39 px (34 px x 1,15), como no mockup."""
        largura = max(1, self.h1.width())
        linhas = 1 + (self.h1.fontMetrics().horizontalAdvance(self.h1.plano()) // largura)
        self.h1.setFixedHeight(39 * linhas)

    def resizeEvent(self, evento):
        super().resizeEvent(evento)
        self.ajustar_titulo()

    def showEvent(self, evento):
        super().showEvent(evento)
        self.ajustar_titulo()

    def atualizar_kicker(self):
        n = PASSO_DA_TELA.get(self.nome, TOTAL_PASSOS) + 1
        self.kicker.setText(t("pu.passo", n=n, total=TOTAL_PASSOS).upper() if n <= TOTAL_PASSOS else "")
        self.kicker.setVisible(n <= TOTAL_PASSOS)

    def construir(self):
        pass

    def ao_entrar(self):
        pass


class PaginaIdioma(Pagina):
    nome = "idioma"

    def __init__(self, jan):
        super().__init__(jan, t("pu.idioma.titulo"), t("pu.idioma.texto"))

    def construir(self):
        disponiveis = tars_i18n.idiomas_disponiveis()
        atual = tars_i18n.idioma_atual()
        self.codigos = list(disponiveis)
        cartoes = [CartaoOpcao(nome, "") for nome in disponiveis.values()]
        for c in cartoes:
            c.descricao.hide()
        inicial = self.codigos.index(atual) if atual in self.codigos else 0
        self.grupo = GrupoCartoes(cartoes, inicial)
        for c in cartoes:
            self.corpo.addWidget(c)
        self.nav.addStretch(1)
        self.nav.addWidget(botao(t("pu.continuar"), "primario", self.continuar))

    def continuar(self):
        self.jan.escolher_idioma(self.codigos[self.grupo.marcado()])


class PaginaModo(Pagina):
    """5.1: Lite, Base ou Pro. Muda depois em Configurações > Geral."""
    nome = "modo"

    def __init__(self, jan):
        super().__init__(jan, t("pu.modo.titulo"), t("pu.modo.texto"))

    def construir(self):
        cartoes = [CartaoOpcao(t(f"modo.{m}.nome"), t(f"modo.{m}.desc")) for m in modos.MODOS]
        self.grupo = GrupoCartoes(cartoes, modos.MODOS.index(modos.modo_atual()))
        for c in cartoes:
            self.corpo.addWidget(c)
        self.nav.addStretch(1)
        self.nav.addWidget(botao(t("pu.continuar"), "primario", self.continuar))

    def continuar(self):
        modos.definir_modo(modos.MODOS[self.grupo.marcado()])
        self.jan.ir("ollama")


class PaginaOllama(Pagina):
    nome = "ollama"

    def __init__(self, jan):
        super().__init__(jan, t("pu.ollama.titulo"), t("pu.ollama.texto"))

    def construir(self):
        self.linha = LinhaStatus("ativo", t("pu.ollama.procurando"))
        self.corpo.addWidget(self.linha)
        self.erro = rotulo("", "erro", quebra=True)
        self.erro.hide()
        self.corpo.addWidget(self.erro)
        botoes = QHBoxLayout()
        botoes.setSpacing(10)
        self.b_instalar = botao(t("pu.ollama.instalar"), "primario", self.instalar)
        self.b_iniciar = botao(t("pu.ollama.iniciar"), "primario", self.iniciar)
        self.b_procurar = botao(t("pu.ollama.procurar_de_novo"), "contorno", self.procurar)
        for b in (self.b_instalar, self.b_iniciar, self.b_procurar):
            botoes.addWidget(b)
        botoes.addStretch(1)
        acoes = QWidget()
        acoes.setLayout(botoes)
        self.corpo.addWidget(acoes)
        self.corpo.addStretch(0)
        self.b_voltar = botao(t("pu.voltar"), "contorno", lambda: self.jan.ir("idioma"))
        self.b_continuar = botao(t("pu.continuar"), "primario", lambda: self.jan.ir("nuvem"))
        self.nav.addWidget(self.b_voltar)
        self.nav.addStretch(1)
        self.nav.addWidget(self.b_continuar)
        self.mostrar("procurando")

    def mostrar(self, estado, texto=None, erro=""):
        """estado: procurando | ok | parado | faltando | instalando | iniciando"""
        self.estado = estado
        rotulos = {
            "procurando": ("ativo", t("pu.ollama.procurando")),
            "ok": ("feito", texto or ""),
            "parado": ("ativo", t("pu.ollama.parado")),
            "faltando": ("ativo", t("pu.ollama.faltando")),
            "instalando": ("ativo", t("pu.ollama.instalando")),
            "iniciando": ("ativo", t("pu.ollama.iniciando")),
        }
        self.linha.definir(*rotulos[estado])
        self.erro.setText(erro)
        self.erro.setVisible(bool(erro))
        parado = estado in ("procurando", "instalando", "iniciando")
        self.b_instalar.setVisible(estado == "faltando")
        self.b_iniciar.setVisible(estado == "parado")
        self.b_procurar.setVisible(estado in ("parado", "faltando"))
        self.b_procurar.setEnabled(not parado)
        self.b_continuar.setEnabled(estado == "ok")
        self.b_voltar.setEnabled(not parado)

    def ao_entrar(self):
        self.procurar()

    def procurar(self):
        self.mostrar("procurando")
        sinais = self.jan.sinais
        threading.Thread(target=lambda: fio.emitir(sinais.ollama, pu.achar_ollama()), daemon=True).start()

    def resultado(self, r):
        self.jan.estado["host"] = r["host"]
        if r["responde"]:
            self.mostrar("ok", t("pu.ollama.ok", versao=r["versao"]))
        elif r["instalado"]:
            self.mostrar("parado")
        else:
            self.mostrar("faltando")

    def instalar(self):
        self.mostrar("instalando")
        sinais = self.jan.sinais
        threading.Thread(target=lambda: fio.emitir(sinais.instalado, *pu.instalar_ollama()), daemon=True).start()

    def instalou(self, ok, msg):
        if ok:
            self.procurar()
        else:
            self.mostrar("faltando", erro=t("pu.ollama.erro_instalar", motivo=msg))

    def iniciar(self):
        self.mostrar("iniciando")
        sinais = self.jan.sinais
        threading.Thread(target=lambda: fio.emitir(sinais.iniciado, *pu.iniciar_ollama()), daemon=True).start()

    def iniciou(self, ok, msg):
        if ok:
            self.procurar()
        else:
            self.mostrar("parado", erro=t("pu.ollama.erro_iniciar", motivo=msg))


class PaginaNuvem(Pagina):
    nome = "nuvem"

    def __init__(self, jan):
        super().__init__(jan, t("pu.nuvem.titulo"), t("pu.nuvem.texto"))

    def construir(self):
        self.nao = CartaoOpcao(t("pu.nuvem.nao"), t("pu.nuvem.nao_desc"))
        self.sim = CartaoOpcao(t("pu.nuvem.sim"), t("pu.nuvem.sim_desc"))
        self.grupo = GrupoCartoes([self.nao, self.sim], 1 if self.jan.estado.get("nuvem_sim") else 0)
        self.corpo.addWidget(self.nao)
        self.corpo.addWidget(self.sim)
        self.corpo.addSpacing(4)
        self.corpo.addWidget(rotulo(t("pu.nuvem.aviso_treino"), "nota", quebra=True))
        self.nav.addWidget(botao(t("pu.voltar"), "contorno", lambda: self.jan.ir("ollama")))
        self.nav.addStretch(1)
        self.nav.addWidget(botao(t("pu.continuar"), "primario", self.continuar))

    def continuar(self):
        sim = self.grupo.marcado() == 1
        self.jan.estado["nuvem_sim"] = sim
        if sim:
            self.jan.ir("chave")
        else:
            pu.salvar_nuvem(False)
            self.jan.ir("gargantua")


class PaginaChave(Pagina):
    nome = "chave"

    def __init__(self, jan):
        super().__init__(jan, t("pu.chave.titulo"), t("pu.chave.texto"))

    def construir(self):
        # 5.1: o caminho principal é a conta do Ollama (sem chave); a chave de API fica como alternativa
        self.login = LoginOllama(lambda: self.jan.estado["host"])
        self.corpo.addWidget(self.login)
        self.corpo.addWidget(rotulo(t("pu.chave.ou_chave"), "campo"))
        salvo = pu.carregar_nuvem()
        self.grupo_chips = QButtonGroup(self)
        self.grupo_chips.setExclusive(True)
        linha = QHBoxLayout()
        linha.setSpacing(6)
        self.chips = {}
        for prov in pu.PROVEDORES:
            b = botao(prov["nome"], "chip")
            b.setCheckable(True)
            self.grupo_chips.addButton(b)
            self.chips[prov["id"]] = b
            b.clicked.connect(lambda _=False, i=prov["id"]: self.escolheu(i))
            linha.addWidget(b)
        linha.addStretch(1)
        chips_w = QWidget()
        chips_w.setLayout(linha)
        self.corpo.addWidget(rotulo(t("pu.chave.provedor"), "campo"))
        self.corpo.addWidget(chips_w)
        self.endereco = QLineEdit()
        self.endereco.setPlaceholderText(t("pu.chave.endereco_ph"))
        self.chave = QLineEdit()
        self.chave.setEchoMode(QLineEdit.Password)
        self.chave.setPlaceholderText("••••••••")
        self.nota = rotulo(t("pu.chave.a_confirmar"), "nota", quebra=True)
        self.corpo.addWidget(rotulo(t("pu.chave.endereco"), "campo"))
        self.corpo.addWidget(self.endereco)
        self.corpo.addWidget(self.nota)
        self.corpo.addWidget(rotulo(t("pu.chave.chave"), "campo"))
        self.corpo.addWidget(self.chave)
        teste = QHBoxLayout()
        teste.setSpacing(12)
        self.b_testar = botao(t("pu.chave.testar"), "contorno", self.testar)
        self.resultado = rotulo("", "erro", quebra=True)
        teste.addWidget(self.b_testar)
        teste.addWidget(self.resultado, 1)
        teste_w = QWidget()
        teste_w.setLayout(teste)
        self.corpo.addWidget(teste_w)
        self.corpo.addWidget(rotulo(t("pu.nuvem.aviso_treino"), "nota", quebra=True))
        self.nav.addWidget(botao(t("pu.voltar"), "contorno", lambda: self.jan.ir("nuvem")))
        self.nav.addStretch(1)
        self.nav.addWidget(botao(t("pu.continuar"), "primario", self.continuar))
        inicial = salvo["provedor"] if salvo["provedor"] in self.chips else "ollama"
        self.chips[inicial].setChecked(True)
        self.escolheu(inicial)
        if salvo["endereco"] and salvo["provedor"] == inicial:
            self.endereco.setText(salvo["endereco"])

    def escolheu(self, id_):
        prov = pu.provedor(id_)
        self.prov_id = id_
        self.endereco.setText(prov["endereco"])
        self.nota.setVisible(prov["a_confirmar"])
        self.resultado.setText("")

    def testar(self):
        self.resultado.setText(t("pu.chave.testando"))
        self.b_testar.setEnabled(False)
        endereco, chave, sinais = self.endereco.text(), self.chave.text(), self.jan.sinais
        threading.Thread(target=lambda: fio.emitir(sinais.nuvem, *pu.testar_nuvem(endereco, chave)), daemon=True).start()

    def testou(self, ok, motivo):
        self.b_testar.setEnabled(True)
        if ok:
            self.resultado.setText(t("pu.chave.ok"))
            return
        chave = {"chave": "pu.chave.erro_chave", "endereço": "pu.chave.erro_endereco",
                 "rede": "pu.chave.erro_rede", "limite": "pu.chave.erro_limite"}.get(motivo)
        self.resultado.setText(t(chave) if chave else t("pu.chave.erro_outro", motivo=motivo))

    def ao_entrar(self):
        self.login.atualizar()

    def continuar(self):
        sem_chave = not self.endereco.text().strip() or not self.chave.text().strip()
        if sem_chave and pu.conta_ollama(self.jan.estado["host"]):
            pu.salvar_nuvem(False)                 # a nuvem vem pela conta do Ollama: nenhuma chave guardada
            self.jan.estado["nuvem_conta"] = True
            self.jan.ir("gargantua")
            return
        if sem_chave:
            self.resultado.setText(t("pu.chave.falta"))
            return
        pu.salvar_nuvem(True, self.prov_id, self.endereco.text(), self.chave.text())
        self.jan.ir("gargantua")


class PaginaGargantua(Pagina):
    nome = "gargantua"

    def __init__(self, jan):
        super().__init__(jan, t("pu.garg.titulo"), t("pu.garg.texto"))

    def construir(self):
        self.pronto = False
        self.baixando = False
        self.livre = None
        painel = QFrame()
        painel.setProperty("papel", "painel")
        pv = QVBoxLayout(painel)
        pv.setContentsMargins(24, 22, 24, 22)
        pv.setSpacing(12)
        topo = QHBoxLayout()
        self.l_nome = rotulo(t("pu.garg.nome"), "titulo-cartao")
        topo.addWidget(self.l_nome)
        topo.addStretch(1)
        self.l_percentual = rotulo("0%", "mono-claro")
        topo.addWidget(self.l_percentual)
        pv.addLayout(topo)
        self.barra = QProgressBar()
        self.barra.setRange(0, 1000)
        self.barra.setTextVisible(False)
        self.barra.setAccessibleName(t("pu.garg.nome"))
        pv.addWidget(self.barra)
        base = QHBoxLayout()
        self.l_tamanho = rotulo(t("pu.garg.preparando"), "mono")
        self.l_restante = rotulo("", "mono")
        base.addWidget(self.l_tamanho)
        base.addStretch(1)
        base.addWidget(self.l_restante)
        pv.addLayout(base)
        self.corpo.addWidget(painel)
        self.corpo.addSpacing(6)
        self.l_ollama = LinhaStatus("feito", t("pu.garg.ollama_ok"))
        self.l_espaco = LinhaStatus("feito", t("pu.garg.espaco_ok"))
        self.corpo.addWidget(self.l_ollama)
        self.corpo.addWidget(self.l_espaco)
        if pu.maquina_fraca():          # 5.1: o Gargantua Lite, menor, em vez do 4B
            self.l_nome.setText(t("pu.garg.nome_lite"))
            self.corpo.addWidget(LinhaStatus("feito", t("pu.garg.lite_nota")))
        self.l_erro = rotulo("", "erro", quebra=True)
        self.l_erro.hide()
        self.corpo.addWidget(self.l_erro)
        self.b_pausar = botao(t("pu.pausar"), "contorno", self.alternar)
        self.b_continuar = botao(t("pu.continuar"), "primario", lambda: self.jan.ir("teste"))
        self.b_continuar.setEnabled(False)
        self.nav.addWidget(self.b_pausar)
        self.nav.addStretch(1)
        self.nav.addWidget(self.b_continuar)

    def ao_entrar(self):
        livre = pu.espaco_livre_gb()
        self.livre = livre
        precisa = pu.tamanho_gargantua_gb()
        if livre is not None and livre < precisa * 1.1:
            self.l_espaco.definir("ativo", t("pu.garg.espaco_pouco", livre=f"{livre:.1f}", precisa=f"{precisa:.1f}"))
        sinais, host = self.jan.sinais, self.jan.estado["host"]

        def trabalho():
            modelos = pu.modelos_instalados(host)
            fio.emitir(sinais.ja_tem, pu.tem_gargantua_desta_maquina(modelos))

        threading.Thread(target=trabalho, daemon=True).start()

    def ja_tinha(self, tem):
        if tem:
            self.h1.setText(t("pu.garg.titulo_ja"))
            self.p.setText(t("pu.garg.texto_ja"))
            self.concluir_barra()
        else:
            self.baixar()

    def concluir_barra(self):
        """O Gargantua está pronto (desde o Gargantua 2 ele enxerga a tela: não há mais um segundo download)."""
        self.barra.setValue(1000)
        self.l_percentual.setText("100%")
        self.l_tamanho.setText("")
        self.l_restante.setText("")
        self.liberar()

    def liberar(self):
        self.pronto = True
        self.b_pausar.hide()
        self.b_continuar.setEnabled(True)

    def baixar(self):
        self._iniciar_download(pu.gargantua_desta_maquina())

    def _iniciar_download(self, nome):
        self.baixando = True
        self.cancelar = False
        self.l_erro.hide()
        self.b_pausar.setText(t("pu.pausar"))
        self.b_continuar.setEnabled(False)
        host, sinais = self.jan.estado["host"], self.jan.sinais

        def ao_progredir(p):
            fio.emitir(sinais.progresso, p.fracao, p.feito, p.total, p.segundos_restantes())

        def trabalho():
            ok, erro = pu.baixar_modelo(nome, host, ao_progredir=ao_progredir, cancelado=lambda: self.cancelar)
            fio.emitir(sinais.baixado, ok, erro)

        threading.Thread(target=trabalho, daemon=True).start()

    def alternar(self):
        if self.baixando:
            self.cancelar = True
        else:
            self.baixar()

    def mostrar_progresso(self, fracao, feito, total, restante):
        self.barra.setValue(int(fracao * 1000))
        self.l_percentual.setText(f"{int(fracao * 100)}%")
        if total:
            self.l_tamanho.setText(t("pu.garg.feito", feito=formatar_gb(feito) + " GB", total=formatar_gb(total) + " GB"))
        self.l_restante.setText(t("pu.garg.restante", tempo=pu.formatar_tempo(restante, t)))

    def terminou(self, ok, erro):
        self.baixando = False
        if ok:
            self.concluir_barra()
        elif erro == "cancelado":
            self.l_erro.setText(t("pu.garg.pausado"))
            self.l_erro.show()
            self.b_pausar.setText(t("pu.retomar"))
        else:
            self.l_erro.setText(t("pu.garg.erro", motivo=erro))
            self.l_erro.show()
            self.b_pausar.setText(t("pu.tentar_de_novo"))

class PaginaTeste(Pagina):
    nome = "teste"

    def __init__(self, jan):
        super().__init__(jan, t("pu.teste.titulo"), t("pu.teste.texto"))

    def construir(self):
        self.linha = LinhaStatus("ativo", t("pu.teste.testando"))
        self.resposta = rotulo("", "mono-claro", quebra=True)
        self.resposta.hide()
        self.corpo.addWidget(self.linha)
        self.corpo.addWidget(self.resposta)
        self.b_tentar = botao(t("pu.tentar_de_novo"), "contorno", self.testar)
        self.b_pular = botao(t("pu.teste.pular"), "contorno", lambda: self.jan.ir("pronto"))
        self.b_continuar = botao(t("pu.continuar"), "primario", lambda: self.jan.ir("pronto"))
        self.nav.addWidget(self.b_tentar)
        self.nav.addWidget(self.b_pular)
        self.nav.addStretch(1)
        self.nav.addWidget(self.b_continuar)
        self.estado_visual("testando")

    def estado_visual(self, estado):
        self.b_tentar.setVisible(estado == "erro")
        self.b_pular.setVisible(estado == "erro")
        self.b_continuar.setEnabled(estado == "ok")

    def ao_entrar(self):
        self.testar()

    def testar(self):
        self.linha.definir("ativo", t("pu.teste.testando"))
        self.resposta.hide()
        self.estado_visual("testando")
        host, sinais = self.jan.estado["host"], self.jan.sinais

        def trabalho():
            nome = pu.nome_do_gargantua(pu.modelos_instalados(host))
            fio.emitir(sinais.teste, *pu.testar_gargantua(host, nome))

        threading.Thread(target=trabalho, daemon=True).start()

    def resultado(self, ok, texto, segundos):
        if ok:
            self.linha.definir("feito", t("pu.teste.ok", seg=f"{segundos:.1f}".replace(".", ",") if tars_i18n.idioma_atual().startswith("pt") else f"{segundos:.1f}"))
            self.resposta.setText(t("pu.teste.resposta", texto=texto[:200]))
            self.resposta.show()
            self.estado_visual("ok")
        else:
            self.linha.definir("ativo", t("pu.teste.erro", motivo=texto[:300]))
            self.estado_visual("erro")


class PaginaPronto(Pagina):
    nome = "pronto"

    def __init__(self, jan):
        super().__init__(jan, t("pu.pronto.titulo"), t("pu.pronto.texto"))

    def construir(self):
        self.resumo_nuvem = LinhaStatus("feito", "")
        self.corpo.addWidget(LinhaStatus("feito", t("pu.garg.ollama_ok")))
        self.corpo.addWidget(LinhaStatus("feito", t("pu.garg.nome")))
        self.corpo.addWidget(self.resumo_nuvem)
        self.nav.addStretch(1)
        self.nav.addWidget(botao(t("pu.pronto.abrir"), "primario", self.jan.terminar))

    def ao_entrar(self):
        if self.jan.estado.get("nuvem_conta"):
            self.resumo_nuvem.definir("feito", t("pu.pronto.nuvem_conta"))
        elif self.jan.estado.get("nuvem_sim"):
            n = pu.carregar_nuvem()
            self.resumo_nuvem.definir("feito", t("pu.pronto.nuvem_sim", provedor=pu.provedor(n["provedor"])["nome"]))
        else:
            self.resumo_nuvem.definir("feito", t("pu.pronto.nuvem_nao"))


# ------------------------------------------------------------
# Janela
# ------------------------------------------------------------

class JanelaPrimeiroUso(QMainWindow):
    concluido = Signal()

    ORDEM = (PaginaIdioma, PaginaModo, PaginaOllama, PaginaNuvem, PaginaChave, PaginaGargantua, PaginaTeste, PaginaPronto)

    def __init__(self):
        super().__init__()
        self.estado = {"host": pu.endereco_ollama(), "nuvem_sim": False}
        self.terminou = False
        self.sinais = Sinais()
        s = self.sinais
        s.ollama.connect(lambda r: self.paginas["ollama"].resultado(r))
        s.instalado.connect(lambda ok, m: self.paginas["ollama"].instalou(ok, m))
        s.iniciado.connect(lambda ok, m: self.paginas["ollama"].iniciou(ok, m))
        s.ja_tem.connect(lambda v: self.paginas["gargantua"].ja_tinha(v))
        s.progresso.connect(lambda *a: self.paginas["gargantua"].mostrar_progresso(*a))
        s.baixado.connect(lambda ok, e: self.paginas["gargantua"].terminou(ok, e))
        s.teste.connect(lambda ok, x, seg: self.paginas["teste"].resultado(ok, x, seg))
        s.nuvem.connect(lambda ok, m: self.paginas["chave"].testou(ok, m))
        self.setWindowIcon(tema.icone_do_app())
        self.resize(1200, 780)
        self.setMinimumSize(1000, 700)
        self.paginas = {}
        self.atual = "idioma"
        self.montar()

    # -- montagem ----------------------------------------------------

    def montar(self):
        self.setWindowTitle(t("pu.janela"))
        raiz = QWidget()
        raiz.setObjectName("raiz")
        horizontal = QHBoxLayout(raiz)
        horizontal.setContentsMargins(0, 0, 0, 0)
        horizontal.setSpacing(0)
        horizontal.addWidget(self.montar_lateral())
        principal = QWidget()
        principal.setObjectName("principal")
        pv = QVBoxLayout(principal)
        pv.setContentsMargins(72, 56, 72, 40)
        self.pilha = QStackedWidget()
        pv.addWidget(self.pilha)
        horizontal.addWidget(principal, 1)
        self.setCentralWidget(raiz)
        self.paginas = {}
        for classe in self.ORDEM:
            pagina = classe(self)
            self.paginas[pagina.nome] = pagina
            self.pilha.addWidget(pagina)
        self.mostrar(self.atual)

    def montar_lateral(self):
        lateral = QFrame()
        lateral.setObjectName("lateral")
        lateral.setFixedWidth(360)
        v = QVBoxLayout(lateral)
        v.setContentsMargins(36, 40, 36, 40)
        v.setSpacing(0)
        v.addWidget(tema.svg_widget(tema.monolito_svg(), 72), 0, Qt.AlignLeft)
        v.addSpacing(18)
        marca = QLabel(f'<p style="line-height:31px; margin:0">open<span style="color:{CORES["verde"]}">TARS</span></p>')
        marca.setProperty("papel", "marca")
        marca.setFixedHeight(31)
        marca.setTextFormat(Qt.RichText)
        v.addWidget(marca)
        v.addSpacing(6)
        v.addWidget(rotulo(t("pu.slogan"), "slogan", quebra=True))
        v.addSpacing(44)
        self.marcadores, self.nomes_passos = [], []
        for nome in pu.PASSOS:
            linha = QHBoxLayout()
            linha.setContentsMargins(0, 10, 0, 10)
            linha.setSpacing(14)
            marcador = Marcador("pendente", 28)
            texto = rotulo(t(f"pu.passo.{nome}"), "passo-futuro")
            linha.addWidget(marcador)
            linha.addWidget(texto, 1)
            self.marcadores.append(marcador)
            self.nomes_passos.append(texto)
            v.addLayout(linha)
            v.addSpacing(6)
        v.addStretch(1)
        rodape = QHBoxLayout()
        rodape.setSpacing(10)
        rodape.addWidget(tema.svg_widget(tema.selo_svg(), 18))
        rodape.addWidget(rotulo(versao_exibida(), "selo"))
        rodape.addStretch(1)
        v.addLayout(rodape)
        return lateral

    # -- navegação ---------------------------------------------------

    def mostrar(self, nome):
        self.atual = nome
        self.pilha.setCurrentWidget(self.paginas[nome])
        passo = PASSO_DA_TELA[nome]
        for i, (marcador, texto) in enumerate(zip(self.marcadores, self.nomes_passos)):
            marcador.definir("feito" if i < passo else "ativo" if i == passo else "pendente")
            aplicar_papel(texto, "passo" if i < passo else "passo-ativo" if i == passo else "passo-futuro")

    def ir(self, nome):
        self.mostrar(nome)
        self.paginas[nome].ao_entrar()

    def escolher_idioma(self, codigo):
        if codigo != tars_i18n.idioma_atual():
            tars_i18n.definir_idioma(codigo)
        self.atual = "modo"
        self.montar()
        self.paginas["modo"].ao_entrar()

    def terminar(self):
        pu.marcar_concluido()
        self.terminou = True
        self.concluido.emit()
        self.close()


def versao_exibida():
    """"5.1 Tesseract", lido do tars.py (a versão tem uma fonte só)."""
    try:
        v = tars_atualizacao.ler_versao((Path(__file__).resolve().parent.parent / "tars.py").read_text(encoding="utf-8"))
    except OSError:
        v = None
    return f"{v['versao']} {v['codinome']}".strip() if v else ""


def criar_aplicativo(argv):
    if QApplication.instance() is None:
        tema.preparar_fontconfig()
        # o mesmo que o lançador opentars-gui faz: pelo X (xcb), porque o plugin Wayland do PySide6 derruba o programa
        # em várias máquinas. Vale também para quem não passa pelo lançador (o serviço dos Probes, opentars --probes).
        if not os.environ.get("QT_QPA_PLATFORM") and os.environ.get("DISPLAY"):
            os.environ["QT_QPA_PLATFORM"] = "xcb"
    app = QApplication.instance() or QApplication((["opentars"] + list(argv[1:])) if argv else ["opentars"])
    # O menu e a barra de tarefas ligam a janela ao ícone pelo nome (WM_CLASS = Opentars, igual ao StartupWMClass do atalho).
    app.setApplicationName("Opentars")
    app.setDesktopFileName("opentars")
    tema.carregar_fontes()
    fonte = app.font()
    fonte.setFamily(tema.FONTE_TEXTO)
    fonte.setPixelSize(15)
    if os.environ.get("TARS_FONTES_SEM_SUBSTITUIR") == "1":
        # modo seguro (o lançador liga depois de uma queda): o Qt não procura outra fonte pro glifo que falta
        # (caminho que dá segfault no fontconfig de algumas máquinas); emoji e outros alfabetos viram quadradinhos
        fonte.setStyleStrategy(QFont.NoFontMerging)
    app.setFont(fonte)
    app.setStyleSheet(tema.folha_de_estilo())
    fio.iniciar(app)
    return app
