"""Configurações do openTARS 5.0 (barra lateral de 240 px + páginas), no desenho do mockup "Memória":
Geral, Voz, Memória e privacidade, Nuvem (opcional), Atualizações e Sobre. 5.1: os modos Lite, Base e Pro escondem
páginas (tars_modos.py), e o Pro ganha Ajustes avançados e Diagnóstico."""

import contextlib
import html
import datetime as dt
import io
import os
import re
import threading
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QSlider, QSpinBox, QStackedWidget,
                               QVBoxLayout, QWidget)

import tars_acoes_texto as acoes_lib
import tars_assistente as assistente
import tars_atalho
import tars_atualizacao
import tars_contexto
import tars_gerenciar_modelos as gm
import tars_i18n
import tars_imagem as imagem_lib
import tars_mais_modelos as mm
import tars_modos as modos
import tars_primeiro_uso as pu
import tars_probes as probes_lib
import tars_web as web_lib
import tars_rotinas as agenda_lib
import tars_voz as voz_lib
from tars_i18n import t

from . import fio, icones, tema
from .login_ollama import LoginOllama
from .tema import CORES, rotulo

PAGINAS = ("geral", "assistente", "voz", "memoria", "rotinas", "probes", "nuvem", "modelos", "gerenciar", "avancado", "diagnostico", "atualizacoes", "sobre")


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


def _secao(titulo, sub=None):
    """Um cartão com título (h2) e um layout vertical pra pôr o conteúdo."""
    f = QFrame()
    f.setProperty("papel", "secao")
    v = QVBoxLayout(f)
    v.setContentsMargins(24, 22, 24, 22)
    v.setSpacing(12)
    h = QLabel(titulo)
    h.setProperty("papel", "h2")
    v.addWidget(h)
    if sub:
        v.addWidget(rotulo(sub, "nota", quebra=True))
    return f, v


class Pagina(QScrollArea):
    """Título, subtítulo e uma coluna de até 860 px."""

    def __init__(self, titulo, sub):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        miolo = QWidget()
        externo = QHBoxLayout(miolo)
        externo.setContentsMargins(40, 36, 40, 40)
        externo.addStretch(1)
        self.coluna = QVBoxLayout()
        self.coluna.setSpacing(18)
        caixa = QWidget()
        caixa.setMaximumWidth(860)
        caixa.setLayout(self.coluna)
        externo.addWidget(caixa, 1000)
        externo.addStretch(1)
        h1 = QLabel(titulo)
        h1.setProperty("papel", "h1-pagina")
        self.coluna.addWidget(h1)
        self.coluna.addWidget(rotulo(sub, "sub-pagina", quebra=True))
        self.coluna.addSpacing(6)
        self.fim = None
        self.setWidget(miolo)

    def adicionar(self, widget):
        self.coluna.addWidget(widget)

    def terminar(self):
        self.coluna.addStretch(1)

    def ao_abrir(self):
        """Chamado quando a página aparece (recarrega o que muda)."""


class PaginaConfiguracoes(QWidget):
    voltar = Signal()
    mudou_idioma = Signal()
    mudou_mascote = Signal()
    modelos_mudaram = Signal()
    rodar_rotina = Signal(str)          # id da rotina: "Rodar agora"
    rotinas_mudaram = Signal()
    mudou_modo = Signal()
    assistente_mudou = Signal()
    versao_achada = Signal(object)          # a página Atualizações achou uma versão nova: a janela avisa na barra lateral
    instalar_atualizacao = Signal()         # o botão Atualizar da página: a janela baixa, confere e instala
    _executar = Signal(object)

    def __init__(self, nucleo, voz, historico, ponte):
        super().__init__()
        self.nucleo, self.voz, self.historico, self.ponte = nucleo, voz, historico, ponte
        self._executar.connect(lambda f: f())
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        h.addWidget(self._montar_lateral())
        self.pilha = QStackedWidget()
        self.pilha.setObjectName("principal")
        h.addWidget(self.pilha, 1)
        self.paginas = {
            "geral": PGeral(self), "assistente": PAssistente(self), "voz": PVoz(self), "memoria": PMemoria(self), "rotinas": PRotinas(self),
            "probes": PProbes(self),
            "nuvem": PNuvem(self), "modelos": PModelos(self), "gerenciar": PGerenciar(self), "avancado": PAvancado(self), "diagnostico": PDiagnostico(self),
            "atualizacoes": PAtualizacoes(self), "sobre": PSobre(self),
        }
        for nome in PAGINAS:
            self.pilha.addWidget(self.paginas[nome])
        self.aplicar_modo()
        self.ir("geral")

    def aplicar_modo(self):
        """5.1: cada modo mostra só as páginas dele (Lite: o básico; Pro: tudo)."""
        for nome in PAGINAS:
            self.nav[nome].setVisible(modos.mostra(f"cfg.{nome}"))
        atual = next((n for n, p in self.paginas.items() if p is self.pilha.currentWidget()), None)
        if atual and not modos.mostra(f"cfg.{atual}"):
            self.ir("geral")

    def _montar_lateral(self):
        f = QFrame()
        f.setObjectName("lateral2")
        f.setFixedWidth(240)
        v = QVBoxLayout(f)
        v.setContentsMargins(14, 20, 14, 16)
        v.setSpacing(2)
        b = _botao("  " + t("cfg.voltar"), "nav-config", self.voltar)
        b.setIcon(icones.icone("voltar", CORES["apoio"], 18))
        b.setIconSize(QSize(18, 18))
        v.addWidget(b)
        v.addSpacing(14)
        self.nav = {}
        self.grupo = QButtonGroup(self)
        self.grupo.setExclusive(True)
        for nome in PAGINAS:
            bt = _botao(t(f"cfg.nav.{nome}"), "nav-config", lambda _=False, n=nome: self.ir(n))
            bt.setCheckable(True)
            self.grupo.addButton(bt)
            self.nav[nome] = bt
            v.addWidget(bt)
        v.addStretch(1)
        cartao = QFrame()
        cartao.setProperty("papel", "aviso-versao")
        cv = QVBoxLayout(cartao)
        cv.setContentsMargins(14, 12, 14, 12)
        cv.setSpacing(2)
        a = QLabel(f"{self.nucleo.VERSAO_EXIBIDA}")
        a.setStyleSheet("font-size: 13px; font-weight: 600;")
        b2 = QLabel(t("cfg.codigo_aberto"))
        b2.setStyleSheet(f"font-size: 12px; color: {CORES['apoio']};")
        cv.addWidget(a)
        cv.addWidget(b2)
        v.addWidget(cartao)
        return f

    def ir(self, nome):
        if nome not in self.paginas or not modos.mostra(f"cfg.{nome}"):
            nome = "geral"
        self.nav[nome].setChecked(True)
        self.pilha.setCurrentWidget(self.paginas[nome])
        self.paginas[nome].ao_abrir()

    def depois(self, funcao):
        """Roda `funcao` na thread da janela (pode ser chamado de outra thread)."""
        try:
            fio.no_principal(funcao)
        except (RuntimeError, TypeError):     # a janela já fechou
            pass

    def em_segundo_plano(self, trabalho, ao_fim):
        def corpo():
            try:
                r = trabalho()
            except Exception as e:
                r = e
            self.depois(lambda: ao_fim(r))
        threading.Thread(target=corpo, daemon=True).start()


# ------------------------------------------------------------
# Geral
# ------------------------------------------------------------

class PGeral(Pagina):
    def __init__(self, cfg):
        super().__init__(t("cfg.geral.titulo"), t("cfg.geral.sub"))
        self.cfg = cfg
        sm, vm = _secao(t("cfg.modo"), t("cfg.modo_sub"))
        lm = QHBoxLayout()
        lm.setSpacing(10)
        self.chips_modo = {}
        grupo_modo = QButtonGroup(self)
        grupo_modo.setExclusive(True)
        for m in modos.MODOS:
            b = _botao(t(f"modo.{m}.nome"), "chip")
            b.setMinimumWidth(96)
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, x=m: self._trocar_modo(x))
            grupo_modo.addButton(b)
            self.chips_modo[m] = b
            lm.addWidget(b)
        lm.addStretch(1)
        vm.addLayout(lm)
        self.desc_modo = rotulo("", "nota", quebra=True)
        vm.addWidget(self.desc_modo)
        self._marcar_modo()
        self.adicionar(sm)

        s, v = _secao(t("cfg.idioma"), t("cfg.idioma_sub"))
        linha = QHBoxLayout()
        linha.setSpacing(10)
        self.chips = {}
        grupo = QButtonGroup(self)
        grupo.setExclusive(True)
        atual = tars_i18n.idioma_atual()
        for codigo, nome in tars_i18n.idiomas_disponiveis().items():
            b = _botao(nome, "chip")
            b.setMinimumWidth(len(nome) * 9 + 44)
            b.setCheckable(True)
            b.setChecked(codigo == atual)
            b.clicked.connect(lambda _=False, c=codigo: self._trocar(c))
            grupo.addButton(b)
            self.chips[codigo] = b
            linha.addWidget(b)
        linha.addStretch(1)
        v.addLayout(linha)
        self.adicionar(s)

        s3, v3 = _secao(t("cfg.mascote"), t("cfg.mascote_sub"))
        self.mascote = QCheckBox(t("cfg.mascote_mostrar"))
        self.mascote.setChecked(bool(tars_i18n.ler_config().get("mascote", True)))
        self.mascote.toggled.connect(self._mascote)
        v3.addWidget(self.mascote)
        self.adicionar(s3)

        s2, v2 = _secao(t("cfg.ia"), t("cfg.ia_sub"))
        self.estado = QLabel("…")
        self.estado.setWordWrap(True)
        self.estado.setProperty("papel", "texto")
        v2.addWidget(self.estado)
        self.barra = QLabel("")
        self.barra.setProperty("papel", "nota")
        v2.addWidget(self.barra)
        self._baixar_o_2 = False
        self.b_gargantua = _botao(t("cfg.baixar_gargantua"), "primario", self._baixar)
        self.b_gargantua.setMaximumWidth(260)
        self.b_gargantua.hide()
        v2.addWidget(self.b_gargantua)
        self.adicionar(s2)
        self.terminar()

    def _marcar_modo(self):
        atual = modos.modo_atual()
        self.chips_modo[atual].setChecked(True)
        self.desc_modo.setText(t(f"modo.{atual}.desc"))

    def _trocar_modo(self, modo):
        if modo != modos.modo_atual():
            modos.definir_modo(modo)
            self.cfg.aplicar_modo()
            self.cfg.mudou_modo.emit()
        self._marcar_modo()

    def _mascote(self, ligado):
        tars_i18n.salvar_config(mascote=bool(ligado))
        self.cfg.mudou_mascote.emit()

    def _trocar(self, codigo):
        if codigo != tars_i18n.idioma_atual():
            tars_i18n.definir_idioma(codigo)
            self.cfg.mudou_idioma.emit()

    def ao_abrir(self):
        n = self.cfg.nucleo
        self._marcar_modo()
        self.mascote.blockSignals(True)             # ele pode ter sido escondido pelo menu do próprio mascote
        self.mascote.setChecked(bool(tars_i18n.ler_config().get("mascote", True)))
        self.mascote.blockSignals(False)

        def trabalho():
            achou = pu.achar_ollama([n.OLLAMA_HOST], tem_comando=None)
            modelos = pu.modelos_instalados(n.OLLAMA_HOST) if achou["responde"] else []
            return achou, modelos

        def pronto(r):
            if isinstance(r, Exception):
                self.estado.setText(str(r))
                return
            achou, modelos = r
            if not achou["responde"]:
                self.estado.setText(t("cfg.ollama_fora"))
                self.b_gargantua.hide()
                return
            tem = pu.tem_gargantua_desta_maquina(modelos)
            # 18/10: quem tem só o Gargantua 1.x ou o Lite é convidado a baixar o 2 (menor e enxerga a tela, o que o Lite não faz)
            novo = tem and not pu.tem_gargantua_2(modelos)
            self._baixar_o_2 = novo
            self.estado.setText(t("cfg.ollama_ok", versao=achou.get("versao") or "?", n=len(modelos)) + "\n" +
                                (t("cfg.gargantua_novo") if novo else t("cfg.gargantua_ok") if tem else t("cfg.gargantua_falta")))
            self.b_gargantua.setText(t("cfg.baixar_gargantua2") if novo else t("cfg.baixar_gargantua"))
            self.b_gargantua.setVisible(not tem or novo)

        self.cfg.em_segundo_plano(trabalho, pronto)

    def _baixar(self):
        n = self.cfg.nucleo
        self.b_gargantua.setEnabled(False)

        def trabalho():
            def andamento(p):
                pct = int(100 * p.fracao)
                self.cfg.depois(lambda: self.barra.setText(t("cfg.baixando", pct=pct)))
            alvo = pu.MODELO_GARGANTUA if getattr(self, "_baixar_o_2", False) else pu.gargantua_desta_maquina()
            return pu.baixar_modelo(alvo, n.OLLAMA_HOST, ao_progredir=andamento)

        def pronto(r):
            ok, erro = r if not isinstance(r, Exception) else (False, str(r))
            self.barra.setText("" if ok else t("cfg.baixar_erro", erro=erro))
            self.b_gargantua.setEnabled(True)
            self.ao_abrir()
            self.cfg.modelos_mudaram.emit()

        self.cfg.em_segundo_plano(trabalho, pronto)


# ------------------------------------------------------------
# Mais modelos (21/10): lista pronta, um clique baixa pelo Ollama com barra de progresso
# ------------------------------------------------------------

class _CartaoModelo(QFrame):
    """Um modelo da lista: nome, tamanho, o que sabe fazer e um botão. Clicar no cartão também baixa."""
    clicou = Signal()

    def __init__(self, nome, gb, capacidades, destaque=False):
        super().__init__()
        self.setProperty("papel", "cartao-modelo")
        self.setProperty("destaque", destaque)
        self.gb = gb
        self.estado = "livre"
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(8)
        topo = QHBoxLayout()
        topo.setSpacing(12)
        col = QVBoxLayout()
        col.setSpacing(2)
        titulo = QLabel(nome)
        titulo.setStyleSheet("font-size: 15px; font-weight: 600;")
        if destaque:
            linha_t = QHBoxLayout()
            linha_t.setSpacing(8)
            linha_t.addWidget(titulo)
            selo = QLabel(t("cfg.modelos.destaque"))
            selo.setProperty("papel", "selo-destaque")
            linha_t.addWidget(selo)
            linha_t.addStretch(1)
            col.addLayout(linha_t)
            col.addWidget(rotulo(t("cfg.modelos.destaque_nota"), "nota", quebra=True))
        else:
            col.addWidget(titulo)
        col.addWidget(rotulo(" · ".join([mm.tamanho_texto(gb)] + [t(f"cfg.modelos.cap.{c}") for c in capacidades]), "nota"))
        topo.addLayout(col, 1)
        self.botao = _botao("", "chip", self.clicou.emit)
        self.botao.setMinimumWidth(150)
        topo.addWidget(self.botao)
        v.addLayout(topo)
        self.barra = QProgressBar()
        self.barra.setRange(0, 100)
        self.barra.setTextVisible(False)
        self.barra.hide()
        v.addWidget(self.barra)
        self.info = rotulo("", "nota", quebra=True)
        self.info.hide()
        v.addWidget(self.info)
        self.definir_estado("livre")

    def definir_estado(self, estado):
        """livre (baixar), instalado, baixando (o botão cancela) ou bloqueado (outro download em andamento)."""
        self.estado = estado
        self.setCursor(Qt.PointingHandCursor if estado == "livre" else Qt.ArrowCursor)
        self.botao.setEnabled(estado in ("livre", "baixando"))
        self.botao.setText({"livre": t("cfg.modelos.baixar", tamanho=mm.tamanho_texto(self.gb)),
                            "instalado": t("cfg.modelos.instalado"), "baixando": t("cfg.modelos.cancelar"),
                            "bloqueado": t("cfg.modelos.baixar", tamanho=mm.tamanho_texto(self.gb))}[estado])
        self.barra.setVisible(estado == "baixando")
        if estado == "baixando":
            self.barra.setValue(0)
            self.nota(t("cfg.modelos.baixando", pct=0, feito="0 MB", total=mm.tamanho_texto(self.gb), resto=t("pu.calculando")))
        elif estado == "instalado":
            self.nota("")

    def progresso(self, pct, texto):
        self.barra.setValue(pct)
        self.nota(texto)

    def nota(self, texto):
        self.info.setText(texto)
        self.info.setVisible(bool(texto))

    def erro(self, texto):
        self.nota(texto)

    def mousePressEvent(self, e):
        if self.estado == "livre" and e.button() == Qt.LeftButton:
            e.accept()                       # sem aceitar o clique, o soltar do mouse nunca chega aqui
        else:
            super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        if self.estado == "livre" and e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            e.accept()
            self.clicou.emit()
            return
        super().mouseReleaseEvent(e)


class _CartaoBonsai(QFrame):
    """25/10 (decisão do Enzo): o Bonsai Image 4B, que gera imagens. Não é modelo do Ollama: instala o programa deles e o
    modelo (~9,5 GB) numa pasta do openTARS, com confirmação (o botão pede o segundo clique e mostra o tamanho)."""

    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.setProperty("papel", "cartao-modelo")
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(8)
        topo = QHBoxLayout()
        col = QVBoxLayout()
        col.setSpacing(2)
        titulo = QLabel("Bonsai Image 4B")
        titulo.setStyleSheet("font-size: 15px; font-weight: 600;")
        col.addWidget(titulo)
        col.addWidget(rotulo(t("cfg.bonsai.sub", tamanho=mm.tamanho_texto(imagem_lib.TAMANHO_GB)), "nota", quebra=True))
        topo.addLayout(col, 1)
        self.b_instalar = _Confirma(t("cfg.bonsai.instalar", tamanho=mm.tamanho_texto(imagem_lib.TAMANHO_GB)), self.instalar)
        self.b_remover = _Confirma(t("cfg.bonsai.remover"), self.remover)
        topo.addWidget(self.b_instalar)
        topo.addWidget(self.b_remover)
        v.addLayout(topo)
        self.info = rotulo("", "nota", quebra=True)
        v.addWidget(self.info)
        self.atualizar()

    def atualizar(self, instalando=False):
        pronto = imagem_lib.instalado()
        pode, motivo = (True, "") if pronto or instalando else imagem_lib.pode_instalar()
        self.b_instalar.setVisible(not pronto)
        self.b_instalar.setEnabled(pode and not instalando)
        self.b_remover.setVisible(pronto)
        if pronto:
            self.info.setText(t("cfg.bonsai.pronto"))
        elif not pode:
            chave = {"placa": "cfg.bonsai.nao_da.placa", "apple_silicon": "cfg.bonsai.nao_da.apple_silicon",
                     "disco": "cfg.bonsai.nao_da.disco"}.get(motivo, "cfg.bonsai.nao_da.falta")
            self.info.setText(t(chave, programa=motivo.split(":")[-1]))
        elif not instalando:
            self.info.setText(t("cfg.bonsai.nota"))

    def instalar(self):
        self.atualizar(instalando=True)
        self.info.setText(t("cfg.bonsai.instalando", linha=""))

        def linha(texto):
            if texto.strip():
                self.cfg.depois(lambda: self.info.setText(t("cfg.bonsai.instalando", linha=texto.strip()[:140])))

        def pronto(r):
            ok, erro = r if not isinstance(r, Exception) else (False, str(r))
            self.atualizar()
            if not ok:
                self.info.setText(t("cfg.bonsai.erro", erro=erro))
        self.cfg.em_segundo_plano(lambda: imagem_lib.instalar(linha), pronto)

    def remover(self):
        imagem_lib.remover()
        self.atualizar()


class PModelos(Pagina):
    def __init__(self, cfg):
        super().__init__(t("cfg.modelos.titulo"), t("cfg.modelos.sub"))
        self.cfg = cfg
        self.estado = rotulo("", "nota", quebra=True)
        self.estado.hide()
        self.adicionar(self.estado)
        self.cartoes = {}
        self._baixando = None
        self._cancelar = False
        self._instalados = []
        self._ollama_ok = True
        for grupo, itens in mm.GRUPOS:
            s, v = _secao(t(f"cfg.modelos.g.{grupo}"), t(f"cfg.modelos.g.{grupo}_sub"))
            if grupo == "imagem":
                self.bonsai = _CartaoBonsai(cfg)
                v.addWidget(self.bonsai)
            for tag, nome, gb, capacidades in itens:
                c = _CartaoModelo(nome, gb, capacidades, destaque=(tag == mm.DESTAQUE))
                c.clicou.connect(lambda tag=tag: self._clicou(tag))
                self.cartoes[tag] = c
                v.addWidget(c)
            self.adicionar(s)
        self.terminar()

    def ao_abrir(self):
        n = self.cfg.nucleo

        def trabalho():
            achou = pu.achar_ollama([n.OLLAMA_HOST], tem_comando=None)
            return achou["responde"], (pu.modelos_instalados(n.OLLAMA_HOST) if achou["responde"] else [])

        def pronto(r):
            ok, lista = (False, []) if isinstance(r, Exception) else r
            self._ollama_ok, self._instalados = ok, lista
            self.estado.setText(t("cfg.ollama_fora"))
            self.estado.setVisible(not ok)
            self._atualizar()

        self.cfg.em_segundo_plano(trabalho, pronto)

    def _atualizar(self):
        for tag, c in self.cartoes.items():
            if tag == self._baixando:
                continue
            if mm.instalado(tag, self._instalados):
                c.definir_estado("instalado")
            elif self._baixando or not self._ollama_ok:
                c.definir_estado("bloqueado")
            else:
                c.definir_estado("livre")

    def _clicou(self, tag):
        c = self.cartoes[tag]
        if self._baixando == tag:             # o botão do cartão que baixa é o "Cancelar"
            self._cancelar = True
            return
        if self._baixando or not self._ollama_ok:
            return
        livre = pu.espaco_livre_gb()
        if not mm.cabe(c.gb, livre):
            c.erro(t("cfg.modelos.sem_espaco", precisa=mm.tamanho_texto(mm.espaco_necessario(c.gb)),
                     livre=mm.tamanho_texto(livre)))
            return
        self._baixando, self._cancelar = tag, False
        c.definir_estado("baixando")
        self._atualizar()
        host = self.cfg.nucleo.OLLAMA_HOST

        def trabalho():
            def andamento(p):
                pct = int(100 * p.fracao)
                texto = t("cfg.modelos.baixando", pct=pct, feito=mm.tamanho_texto(p.feito / 1e9),
                          total=mm.tamanho_texto(p.total / 1e9) if p.total else mm.tamanho_texto(c.gb),
                          resto=pu.formatar_tempo(p.segundos_restantes(), t))
                self.cfg.depois(lambda: c.progresso(pct, texto))
            return pu.baixar_modelo(tag, host, ao_progredir=andamento, cancelado=lambda: self._cancelar)

        def pronto(r):
            ok, erro = r if not isinstance(r, Exception) else (False, str(r))
            self._baixando = None
            if ok:
                self._instalados.append(tag)
                c.definir_estado("instalado")
            else:
                c.definir_estado("livre")
                c.erro(t("cfg.modelos.cancelado") if erro == "cancelado" else t("cfg.baixar_erro", erro=erro))
            self._atualizar()
            if ok:
                self.cfg.modelos_mudaram.emit()

        self.cfg.em_segundo_plano(trabalho, pronto)


# ------------------------------------------------------------
# Gerenciar modelos (21/10): o que está instalado, atualizar e apagar
# ------------------------------------------------------------

class _CartaoInstalado(QFrame):
    """Um modelo instalado: nome, detalhes, selos e os botões Atualizar e Apagar (o apagar pergunta antes, no próprio cartão)."""
    atualizar = Signal()
    apagar = Signal()

    def __init__(self, m):
        super().__init__()
        self.m = m
        self.setProperty("papel", "cartao-modelo")
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(8)
        topo = QHBoxLayout()
        topo.setSpacing(12)
        col = QVBoxLayout()
        col.setSpacing(2)
        titulo = QLabel(m["nome"])
        titulo.setStyleSheet("font-size: 15px; font-weight: 600;")
        titulo.setTextInteractionFlags(Qt.TextSelectableByMouse)
        col.addWidget(titulo)
        selos = [t("cfg.gerenciar.selo.oficial")] if m["oficial"] else []
        selos += [t("cfg.gerenciar.selo.nuvem")] if m["nuvem"] else []
        detalhe = gm.detalhe(m, mm.tamanho_texto)
        col.addWidget(rotulo(" · ".join(([detalhe] if detalhe else []) + selos), "nota", quebra=True))
        topo.addLayout(col, 1)
        self.b_atualizar = _botao(t("cfg.gerenciar.atualizar"), "chip", self.atualizar.emit)
        self.b_atualizar.setVisible(not m["nuvem"])
        self.b_apagar = _botao(t("cfg.gerenciar.apagar"), "chip", self._pedir_confirmacao)
        topo.addWidget(self.b_atualizar)
        topo.addWidget(self.b_apagar)
        v.addLayout(topo)
        self.barra = QProgressBar()
        self.barra.setRange(0, 100)
        self.barra.setTextVisible(False)
        self.barra.hide()
        v.addWidget(self.barra)
        self.info = rotulo("", "nota", quebra=True)
        self.info.hide()
        v.addWidget(self.info)
        # a pergunta de confirmação (escondida até clicar em Apagar)
        self.confirmacao = QFrame()
        c = QVBoxLayout(self.confirmacao)
        c.setContentsMargins(0, 4, 0, 0)
        c.setSpacing(8)
        chave = "cfg.gerenciar.pergunta_oficial" if m["oficial"] else "cfg.gerenciar.pergunta"
        c.addWidget(rotulo(t(chave, nome=m["nome"], tamanho=mm.tamanho_texto(m["gb"])), "nota", quebra=True))
        linha = QHBoxLayout()
        linha.setSpacing(10)
        self.b_confirmar = _botao(t("cfg.gerenciar.confirmar"), "primario", self.apagar.emit)
        self.b_manter = _botao(t("cfg.gerenciar.manter"), "chip", self._cancelar_confirmacao)
        linha.addWidget(self.b_confirmar)
        linha.addWidget(self.b_manter)
        linha.addStretch(1)
        c.addLayout(linha)
        self.confirmacao.hide()
        v.addWidget(self.confirmacao)

    def _pedir_confirmacao(self):
        self.confirmacao.show()
        self.b_apagar.setEnabled(False)

    def _cancelar_confirmacao(self):
        self.confirmacao.hide()
        self.b_apagar.setEnabled(True)

    def ocupado(self, sim):
        """Enquanto outro cartão atualiza ou apaga, os botões ficam parados."""
        self.b_atualizar.setEnabled(not sim)
        self.b_apagar.setEnabled(not sim and not self.confirmacao.isVisible())

    def progresso(self, pct, texto):
        self.barra.setVisible(True)
        self.barra.setValue(pct)
        self.nota(texto)

    def nota(self, texto):
        self.info.setText(texto)
        self.info.setVisible(bool(texto))


# ------------------------------------------------------------
# Assistente (5.2): o modelo das ações de texto na memória, o atalho e o início com o sistema
# ------------------------------------------------------------

class PAssistente(Pagina):
    def __init__(self, cfg):
        super().__init__(t("cfg.assist.titulo"), t("cfg.assist.sub"))
        self.cfg = cfg
        s, v = _secao(t("cfg.assist.ligado_titulo"))
        self.ligado = QCheckBox(t("cfg.assist.ligado"))
        self.ligado.toggled.connect(self._ligar)
        v.addWidget(self.ligado)
        self.ligado_nota = rotulo("", "nota", quebra=True)
        v.addWidget(self.ligado_nota)
        self.adicionar(s)

        s, v = _secao(t("cfg.assist.atalho_titulo"), t("cfg.assist.atalho_sub"))
        self.atalho = rotulo("", "texto", quebra=True)
        v.addWidget(self.atalho)
        linha = QHBoxLayout()
        self.b_atalho = _botao(t("cfg.assist.atalho_cadastrar", atalho=tars_atalho.legivel(tars_atalho.ACOES_PADRAO)), "chip",
                               self._cadastrar)
        self.b_remover = _botao(t("cfg.assist.atalho_remover"), "link", self._remover)
        linha.addWidget(self.b_atalho)
        linha.addWidget(self.b_remover)
        linha.addStretch(1)
        v.addLayout(linha)
        v.addWidget(rotulo(t("cfg.assist.atalho_nota"), "nota", quebra=True))
        self.adicionar(s)

        s, v = _secao(t("cfg.assist.sistema_titulo"))
        self.sistema = QCheckBox(t("cfg.assist.sistema"))
        self.sistema.toggled.connect(self._iniciar_com_sistema)
        v.addWidget(self.sistema)
        v.addWidget(rotulo(t("cfg.assist.sistema_nota"), "nota", quebra=True))
        self.adicionar(s)

        s, v = _secao(t("cfg.assist.ctx_titulo"))
        self.contexto = QCheckBox(t("cfg.assist.ctx"))
        self.contexto.toggled.connect(self._sugestoes)
        v.addWidget(self.contexto)
        v.addWidget(rotulo(t("ctx.nota_config"), "nota", quebra=True))
        self.adicionar(s)

        s, v = _secao(t("cfg.assist.acoes_titulo"), t("cfg.assist.acoes_sub"))
        self.modelo_acoes = rotulo("", "nota", quebra=True)
        v.addWidget(self.modelo_acoes)
        self.adicionar(s)
        self.terminar()

    def _modelo(self):
        n = self.cfg.nucleo
        garg = n.MODELO_GARGANTUA.split(":")[0]
        try:
            instalados = n.listar_modelos_instalados()
        except Exception:  # noqa: BLE001
            instalados = []
        return acoes_lib.escolher_modelo(instalados, garg + ":lite", garg + ":latest")

    def ao_abrir(self):
        modelo = self._modelo()
        for caixa, valor in ((self.ligado, assistente.ligado()), (self.sistema, assistente.inicia_com_sistema()),
                             (self.contexto, tars_contexto.ligado())):
            caixa.blockSignals(True)
            caixa.setChecked(valor)
            caixa.blockSignals(False)
        self.ligado_nota.setText(t("cfg.assist.ligado_nota", modelo=modelo))
        self.modelo_acoes.setText(t("cfg.assist.acoes_modelo", modelo=modelo))
        config = tars_i18n.ler_config()
        registrado = bool(config.get("atalho_acoes_registrado"))
        self.atalho.setText(t("atalho.acoes_registrado", atalho=tars_atalho.legivel(config.get("atalho_acoes") or
                                                                                   tars_atalho.ACOES_PADRAO))
                            if registrado else t("cfg.assist.atalho_nenhum"))
        self.b_remover.setVisible(registrado)

    def _ligar(self, ativo):
        self.ligado.setEnabled(False)
        modelo = self._modelo()

        def pronto(r):
            self.ligado.setEnabled(True)
            self.ligado_nota.setText(t("cfg.assist.erro", erro=str(r)[:160]) if isinstance(r, Exception)
                                     else t("cfg.assist.ligado_nota", modelo=modelo))
            self.cfg.assistente_mudou.emit()      # a janela principal mostra (ou some com) o ícone na bandeja

        self.cfg.em_segundo_plano(lambda: assistente.ligar(ativo, self.cfg.nucleo.OLLAMA_HOST, modelo), pronto)

    def _cadastrar(self):
        ok, mensagem = tars_atalho.registrar_acoes()
        self.ao_abrir()
        self.atalho.setText(mensagem)
        self.cfg.assistente_mudou.emit()      # no Windows a janela registra o atalho de novo

    def _remover(self):
        tars_atalho.remover_acoes()
        self.ao_abrir()
        self.cfg.assistente_mudou.emit()

    def _sugestoes(self, ativo):
        tars_contexto.ligar(ativo)
        self.cfg.assistente_mudou.emit()      # a janela principal liga ou desliga a olhada no programa em uso

    def _iniciar_com_sistema(self, ativo):
        try:
            assistente.iniciar_com_sistema(ativo)
        except OSError as e:
            self.sistema.blockSignals(True)
            self.sistema.setChecked(False)
            self.sistema.blockSignals(False)
            self.ligado_nota.setText(t("cfg.assist.erro", erro=str(e)[:160]))


class PGerenciar(Pagina):
    def __init__(self, cfg):
        super().__init__(t("cfg.gerenciar.titulo"), t("cfg.gerenciar.sub"))
        self.cfg = cfg
        self.resumo = rotulo("", "nota", quebra=True)
        self.adicionar(self.resumo)
        self.secao, self.lista = _secao(t("cfg.gerenciar.instalados"))
        self.adicionar(self.secao)
        self.cartoes = {}
        self._ocupado = False
        self.terminar()

    def ao_abrir(self):
        host = self.cfg.nucleo.OLLAMA_HOST

        def trabalho():
            return gm.listar(host)

        def pronto(r):
            if isinstance(r, Exception):
                self._montar([], fora=True)
                return
            self._montar(r)

        self.cfg.em_segundo_plano(trabalho, pronto)

    def _montar(self, modelos, fora=False):
        for c in self.cartoes.values():
            self.lista.removeWidget(c)
            c.deleteLater()
        self.cartoes = {}
        for m in modelos:
            c = _CartaoInstalado(m)
            c.atualizar.connect(lambda nome=m["nome"]: self._atualizar(nome))
            c.apagar.connect(lambda nome=m["nome"]: self._apagar(nome))
            self.cartoes[m["nome"]] = c
            self.lista.addWidget(c)
        if modelos:
            livre = pu.espaco_livre_gb()
            self.resumo.setText(t("cfg.gerenciar.resumo", n=len(modelos), usado=mm.tamanho_texto(gm.total_gb(modelos)),
                                  livre=mm.tamanho_texto(livre) if livre is not None else "?"))
        else:
            self.resumo.setText(t("cfg.ollama_fora") if fora else t("cfg.gerenciar.vazio"))
        self._modelos = modelos

    def _parar_todos(self, sim):
        self._ocupado = sim
        for c in self.cartoes.values():
            c.ocupado(sim)

    def _apagar(self, nome):
        if self._ocupado or nome not in self.cartoes:
            return
        c = self.cartoes[nome]
        self._parar_todos(True)
        host = self.cfg.nucleo.OLLAMA_HOST

        def pronto(r):
            ok, erro = r if not isinstance(r, Exception) else (False, str(r))
            self._parar_todos(False)
            if not ok:
                c._cancelar_confirmacao()
                c.nota(t("cfg.gerenciar.erro", erro=erro))
                return
            self.cfg.modelos_mudaram.emit()
            self.ao_abrir()                       # lista de novo: o tamanho total e o espaço livre mudaram

        self.cfg.em_segundo_plano(lambda: gm.apagar(nome, host), pronto)

    def _atualizar(self, nome):
        if self._ocupado or nome not in self.cartoes:
            return
        c = self.cartoes[nome]
        self._parar_todos(True)
        c.progresso(0, t("cfg.gerenciar.atualizando"))
        host = self.cfg.nucleo.OLLAMA_HOST
        total_visto = [0]

        def trabalho():
            def andamento(p):
                total_visto[0] = p.total
                pct = int(100 * p.fracao)
                texto = t("cfg.modelos.baixando", pct=pct, feito=mm.tamanho_texto(p.feito / 1e9),
                          total=mm.tamanho_texto(p.total / 1e9), resto=pu.formatar_tempo(p.segundos_restantes(), t))
                self.cfg.depois(lambda: c.progresso(pct, texto) if p.total else None)
            return pu.baixar_modelo(nome, host, ao_progredir=andamento)

        def pronto(r):
            ok, erro = r if not isinstance(r, Exception) else (False, str(r))
            self._parar_todos(False)
            c.barra.hide()
            if not ok:
                c.nota(t("cfg.baixar_erro", erro=erro))
                return
            c.nota(t("cfg.gerenciar.atualizado") if total_visto[0] else t("cfg.gerenciar.em_dia"))
            self.cfg.modelos_mudaram.emit()

        self.cfg.em_segundo_plano(trabalho, pronto)


# ------------------------------------------------------------
# Voz
# ------------------------------------------------------------

class PVoz(Pagina):
    def __init__(self, cfg):
        super().__init__(t("cfg.voz.titulo"), t("cfg.voz.sub"))
        self.cfg = cfg
        n = cfg.nucleo
        s, v = _secao(t("cfg.voz.motor"), t("cfg.voz.motor_sub"))
        self.estado = QLabel("")
        self.estado.setWordWrap(True)
        self.estado.setProperty("papel", "texto")
        v.addWidget(self.estado)
        self.andamento = QLabel("")
        self.andamento.setProperty("papel", "nota")
        self.andamento.setWordWrap(True)
        v.addWidget(self.andamento)
        self.b_instalar = _botao(t("cfg.voz.instalar"), "primario", self._instalar)
        self.b_instalar.setMaximumWidth(260)
        v.addWidget(self.b_instalar)
        self.adicionar(s)

        s2, v2 = _secao(t("cfg.voz.fala"))
        self.falar = QCheckBox(t("cfg.voz.responder_falando"))
        self.falar.setChecked(n.config_voz()["falar"])
        self.falar.toggled.connect(lambda x: n.salvar_config_voz(falar=x))
        v2.addWidget(self.falar)
        linha = QHBoxLayout()
        linha.addWidget(QLabel(t("cfg.voz.voz")))
        self.caixa = QComboBox()
        self.caixa.setMinimumWidth(240)
        self._preencher_vozes()
        self.caixa.activated.connect(self._escolher_voz)
        linha.addWidget(self.caixa)
        linha.addStretch(1)
        v2.addLayout(linha)
        lv = QHBoxLayout()
        lv.addWidget(QLabel(t("cfg.voz.velocidade")))
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(int(voz_lib.VELOCIDADE_MIN * 100), int(voz_lib.VELOCIDADE_MAX * 100))
        self.slider.setValue(int(n.preferencias_voz()["velocidade"] * 100))
        self.slider.setMaximumWidth(280)
        self.rot_vel = QLabel(f"{self.slider.value() / 100:.2f}×")
        self.rot_vel.setProperty("papel", "mono")
        self.slider.valueChanged.connect(lambda x: self.rot_vel.setText(f"{x / 100:.2f}×"))
        self.slider.sliderReleased.connect(lambda: n.definir_velocidade_voz(self.slider.value() / 100))
        lv.addWidget(self.slider)
        lv.addWidget(self.rot_vel)
        lv.addStretch(1)
        v2.addLayout(lv)
        self.b_testar = _botao(t("cfg.voz.testar"), "chip", self._testar)
        self.b_testar.setMaximumWidth(200)
        v2.addWidget(self.b_testar)
        self.adicionar(s2)
        self.adicionar(rotulo(t("cfg.voz.nota"), "nota", quebra=True))
        self.terminar()

    def _preencher_vozes(self):
        n = self.cfg.nucleo
        idioma = tars_i18n.idioma_atual()
        idioma = idioma if idioma in voz_lib.VOZES_DISPONIVEIS else "en"
        atual = n.voz_atual()
        self.caixa.clear()
        for nome, (_arq, desc) in voz_lib.VOZES_DISPONIVEIS[idioma].items():
            self.caixa.addItem(f"{nome.capitalize()} — {desc}", nome)
            if nome == atual:
                self.caixa.setCurrentIndex(self.caixa.count() - 1)

    def ao_abrir(self):
        falta = self.cfg.nucleo.o_que_falta_voz()
        if falta:
            self.estado.setText(t("cfg.voz.falta", itens=self.cfg.nucleo.descrever_falta_voz(falta)))
        else:
            self.estado.setText(t("cfg.voz.pronta"))
        self.b_instalar.setVisible(bool(falta) and falta != ["idioma"] and not set(falta) & {"gravador", "tocador"})
        self.b_instalar.setEnabled(True)
        self.b_testar.setEnabled(not falta)

    def _instalar(self):
        n = self.cfg.nucleo
        self.b_instalar.setEnabled(False)
        self.andamento.setText(t("cfg.voz.instalando"))

        def trabalho():
            return n.instalar_voz(avisar=lambda msg: self.cfg.depois(lambda: self.andamento.setText(str(msg))))

        def pronto(r):
            ok, erro = r if not isinstance(r, Exception) else (False, str(r))
            self.andamento.setText(t("cfg.voz.instalada") if ok else t("cfg.voz.erro", erro=erro))
            self.ao_abrir()

        self.cfg.em_segundo_plano(trabalho, pronto)

    def _escolher_voz(self, i):
        nome = self.caixa.itemData(i)
        n = self.cfg.nucleo

        def pronto(r):
            ok, msg = r if not isinstance(r, Exception) else (False, str(r))
            self.andamento.setText(msg)

        self.cfg.em_segundo_plano(lambda: n.escolher_voz(nome), pronto)

    def _testar(self):
        n = self.cfg.nucleo
        self.cfg.em_segundo_plano(lambda: n.falador().falar(n.frase_de_teste_voz(), tars_i18n.idioma_atual()), lambda _r: None)


# ------------------------------------------------------------
# Memória e privacidade
# ------------------------------------------------------------

class _Confirma(QPushButton):
    """Botão de duas batidas ("Apagar" → "Confirmar?") em vez de caixa de diálogo."""

    def __init__(self, texto, ao_confirmar, papel="chip"):
        super().__init__(texto)
        self.setProperty("papel", papel)
        self.setCursor(Qt.PointingHandCursor)
        self._texto, self._ao_confirmar, self._armado = texto, ao_confirmar, False
        self._relogio = QTimer(self)
        self._relogio.setSingleShot(True)
        self._relogio.timeout.connect(self._desarmar)
        self.clicked.connect(self._clique)

    def _clique(self):
        if self._armado:
            self._desarmar()
            self._ao_confirmar()
        else:
            self._armado = True
            self.setText(t("cfg.confirmar"))
            self._relogio.start(4000)

    def _desarmar(self):
        self._armado = False
        self.setText(self._texto)


class _Msg(QLabel):
    """Linha de resultado: só ocupa lugar quando tem texto."""

    def __init__(self):
        super().__init__("")
        self.setProperty("papel", "nota")
        self.setWordWrap(True)
        self.hide()

    def setText(self, texto):
        super().setText(texto)
        self.setVisible(bool(texto))


class PMemoria(Pagina):
    def __init__(self, cfg):
        super().__init__(t("cfg.memoria.titulo"), t("cfg.memoria.sub"))
        self.cfg = cfg
        s, v = _secao(t("cfg.memoria.lembra"), t("cfg.memoria.lembra_sub"))
        self.lista = QVBoxLayout()
        self.lista.setSpacing(6)
        v.addLayout(self.lista)
        self.b_tudo = _Confirma(t("cfg.memoria.apagar_tudo"), self._apagar_memoria)
        self.b_tudo.setMaximumWidth(260)
        v.addWidget(self.b_tudo)
        self.adicionar(s)

        s2, v2 = _secao(t("cfg.dados.titulo"), t("cfg.dados.sub"))
        self.msg = _Msg()
        linha = QHBoxLayout()
        linha.setSpacing(10)
        b = _botao(t("cfg.dados.exportar"), "chip", self._exportar)
        self.b_hist = _Confirma(t("cfg.dados.apagar_historico"), self._apagar_historico)
        self.b_geral = _Confirma(t("cfg.dados.apagar_tudo"), self._apagar_tudo)
        for w in (b, self.b_hist, self.b_geral):
            linha.addWidget(w)
        linha.addStretch(1)
        v2.addLayout(linha)
        v2.addWidget(self.msg)
        v2.addWidget(rotulo(t("cfg.dados.onde"), "nota", quebra=True))
        self.adicionar(s2)
        self.terminar()

    def ao_abrir(self):
        self._listar()

    def _listar(self):
        while self.lista.count():
            it = self.lista.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        itens = self.cfg.nucleo.memoria.listar()
        if not itens:
            self.lista.addWidget(rotulo(t("cfg.memoria.vazia"), "nota", quebra=True))
        for texto in itens:
            f = QFrame()
            f.setProperty("papel", "linha-lista")
            h = QHBoxLayout(f)
            h.setContentsMargins(14, 8, 8, 8)
            r = QLabel(texto)
            r.setWordWrap(True)
            b = QPushButton()
            b.setProperty("papel", "icone")
            b.setFixedSize(34, 34)
            b.setIcon(icones.icone("lixeira", CORES["apoio"], 16))
            b.setToolTip(t("cfg.memoria.esquecer"))
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, x=texto: self._esquecer(x))
            h.addWidget(r, 1)
            h.addWidget(b)
            self.lista.addWidget(f)
        self.b_tudo.setVisible(bool(itens))

    def _esquecer(self, texto):
        self.cfg.nucleo.memoria.esquecer(texto)
        self._listar()

    def _apagar_memoria(self):
        self.cfg.nucleo.memoria.esquecer("*")
        self._listar()
        self.msg.setText(t("cfg.memoria.apagada"))

    def _exportar(self):
        destino, _ = QFileDialog.getSaveFileName(self, t("cfg.dados.exportar"), "opentars-conversas.json", "JSON (*.json)")
        if destino:
            n = self.cfg.historico.exportar(destino)
            self.msg.setText(t("cfg.dados.exportado", n=n))

    def _apagar_historico(self):
        n = self.cfg.historico.apagar_tudo()
        self.cfg.ponte.conversa_mudou.emit()
        self.msg.setText(t("cfg.dados.historico_apagado", n=n))

    def _apagar_tudo(self):
        self._apagar_historico()
        self.cfg.nucleo.memoria.esquecer("*")
        self._listar()
        self.msg.setText(t("cfg.dados.tudo_apagado"))


# ------------------------------------------------------------
# Rotinas
# ------------------------------------------------------------

def _formatar_quando(iso):
    try:
        d = dt.datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return "?"
    hoje = dt.date.today()
    dia = t("jp.grupo.hoje") if d.date() == hoje else d.strftime("%d/%m")
    return f"{dia} {d.strftime('%H:%M')}"


class PRotinas(Pagina):
    def __init__(self, cfg):
        super().__init__(t("rot.titulo"), t("rot.sub"))
        self.cfg = cfg
        self._editando = None
        topo = QHBoxLayout()
        self.b_nova = _botao(t("rot.nova"), "primario", lambda: self._abrir_form(None))
        self.b_nova.setMaximumWidth(220)
        topo.addWidget(self.b_nova)
        topo.addStretch(1)
        c = QWidget()
        c.setLayout(topo)
        self.adicionar(c)
        self.form = self._montar_form()
        self.form.hide()
        self.adicionar(self.form)
        self.lista = QVBoxLayout()
        self.lista.setSpacing(12)
        c2 = QWidget()
        c2.setLayout(self.lista)
        self.adicionar(c2)
        self.adicionar(rotulo(t("rot.fundo_nota"), "nota", quebra=True))
        self.terminar()

    # -- formulário -----------------------------------------------------------------
    def _montar_form(self):
        f, v = _secao(t("rot.nova"))
        self.titulo_form = f.findChild(QLabel)
        v.addWidget(QLabel(t("rot.nome")))
        self.f_nome = QLineEdit()
        self.f_nome.setPlaceholderText(t("rot.nome_ph"))
        self.f_nome.setMaxLength(agenda_lib.LIMITE_NOME)
        v.addWidget(self.f_nome)
        v.addWidget(QLabel(t("rot.pedido")))
        self.f_pedido = QPlainTextEdit()
        self.f_pedido.setPlaceholderText(t("rot.pedido_ph"))
        self.f_pedido.setFixedHeight(84)
        v.addWidget(self.f_pedido)
        v.addWidget(QLabel(t("rot.quando")))
        linha = QHBoxLayout()
        linha.setSpacing(10)
        self.grupo_tipo = QButtonGroup(self)
        self.grupo_tipo.setExclusive(True)
        self.b_tipo = {}
        for tipo in agenda_lib.TIPOS:
            b = _botao(t(f"rot.tipo_{tipo}"), "chip")
            b.setCheckable(True)
            b.setMinimumWidth(len(b.text()) * 9 + 44)
            b.clicked.connect(self._mostrar_campos)
            self.grupo_tipo.addButton(b)
            self.b_tipo[tipo] = b
            linha.addWidget(b)
        linha.addStretch(1)
        v.addLayout(linha)
        self.b_tipo["diaria"].setChecked(True)
        self.w_hora = QWidget()
        lh = QVBoxLayout(self.w_hora)
        lh.setContentsMargins(0, 0, 0, 0)
        lh.addWidget(QLabel(t("rot.hora")))
        self.f_hora = QLineEdit("08:00")
        self.f_hora.setMaximumWidth(160)
        lh.addWidget(self.f_hora)
        v.addWidget(self.w_hora)
        self.w_dias = QWidget()
        ld = QHBoxLayout(self.w_dias)
        ld.setContentsMargins(0, 0, 0, 0)
        ld.setSpacing(8)
        self.b_dia = []
        for i, nome in enumerate(agenda_lib.DIAS):
            b = _botao(t(f"rot.dia_{nome}"), "chip")
            b.setCheckable(True)
            b.setMinimumWidth(60)
            self.b_dia.append(b)
            ld.addWidget(b)
        ld.addStretch(1)
        v.addWidget(self.w_dias)
        self.w_min = QWidget()
        lm = QVBoxLayout(self.w_min)
        lm.setContentsMargins(0, 0, 0, 0)
        lm.addWidget(QLabel(t("rot.minutos")))
        self.f_min = QLineEdit("60")
        self.f_min.setMaximumWidth(160)
        lm.addWidget(self.f_min)
        v.addWidget(self.w_min)
        self.w_data = QWidget()
        lt = QVBoxLayout(self.w_data)
        lt.setContentsMargins(0, 0, 0, 0)
        lt.addWidget(QLabel(t("rot.data")))
        self.f_data = QLineEdit()
        self.f_data.setMaximumWidth(260)
        lt.addWidget(self.f_data)
        v.addWidget(self.w_data)
        v.addWidget(QLabel(t("rot.perm_titulo")))
        self.c_perm = {}
        for nome in agenda_lib.PERMISSOES:
            c = QCheckBox(t(f"rot.perm_{nome}"))
            self.c_perm[nome] = c
            v.addWidget(c)
        v.addWidget(rotulo(t("rot.perm_nota"), "nota", quebra=True))
        self.erro = QLabel("")
        self.erro.setProperty("papel", "erro-linha")
        self.erro.setWordWrap(True)
        self.erro.hide()
        v.addWidget(self.erro)
        botoes = QHBoxLayout()
        botoes.setSpacing(10)
        self.b_salvar = _botao(t("rot.salvar"), "primario", self._salvar)
        botoes.addWidget(self.b_salvar)
        botoes.addWidget(_botao(t("rot.cancelar"), "chip", lambda: self.form.hide()))
        botoes.addStretch(1)
        v.addLayout(botoes)
        self._mostrar_campos()
        return f

    def _tipo(self):
        return next((k for k, b in self.b_tipo.items() if b.isChecked()), "diaria")

    def _mostrar_campos(self):
        tipo = self._tipo()
        self.w_hora.setVisible(tipo in ("diaria", "semanal"))
        self.w_dias.setVisible(tipo == "semanal")
        self.w_min.setVisible(tipo == "intervalo")
        self.w_data.setVisible(tipo == "uma_vez")

    def _abrir_form(self, rotina):
        self._editando = rotina["id"] if rotina else None
        self.titulo_form.setText(t("rot.editar_titulo") if rotina else t("rot.nova"))
        self.erro.hide()
        r = rotina or {"nome": "", "pedido": "", "quando": {"tipo": "diaria", "hora": "08:00"}, "permitidas": []}
        self.f_nome.setText(r["nome"])
        self.f_pedido.setPlainText(r["pedido"])
        q = r["quando"]
        self.b_tipo[q["tipo"]].setChecked(True)
        self.f_hora.setText(q.get("hora", "08:00"))
        for i, b in enumerate(self.b_dia):
            b.setChecked(i in q.get("dias", []))
        self.f_min.setText(str(q.get("cada_minutos", 60)))
        self.f_data.setText(q.get("data", "").replace("T", " ")[:16])
        for nome, c in self.c_perm.items():
            c.setChecked(nome in r.get("permitidas", []))
        self._mostrar_campos()
        self.form.show()
        self.f_nome.setFocus()

    def _quando_do_form(self):
        tipo = self._tipo()
        q = {"tipo": tipo}
        if tipo in ("diaria", "semanal"):
            q["hora"] = self.f_hora.text()
        if tipo == "semanal":
            q["dias"] = [i for i, b in enumerate(self.b_dia) if b.isChecked()]
        if tipo == "intervalo":
            q["cada_minutos"] = self.f_min.text().strip()
        if tipo == "uma_vez":
            q["data"] = self.f_data.text().strip().replace(" ", "T")
        return q

    def _salvar(self):
        agenda = self.cfg.nucleo.agenda
        permitidas = [n for n, c in self.c_perm.items() if c.isChecked()]
        quando = self._quando_do_form()
        if self._editando:
            r, erro = agenda.atualizar(self._editando, nome=self.f_nome.text(), pedido=self.f_pedido.toPlainText(),
                                       quando=quando, permitidas=permitidas, aprovada=True)
        else:
            r, erro = agenda.criar(self.f_nome.text(), self.f_pedido.toPlainText(), quando, permitidas=permitidas)
        if erro:
            self.erro.setText(t(f"rot.erro_{erro}") if erro in ("nome", "pedido", "limite", "tipo", "hora", "dias", "intervalo", "data") else erro)
            self.erro.show()
            return
        self.form.hide()
        self._listar()
        self.cfg.rotinas_mudaram.emit()

    # -- lista ----------------------------------------------------------------------------------
    def ao_abrir(self):
        self._listar()

    def _listar(self):
        while self.lista.count():
            it = self.lista.takeAt(0)
            w = it.widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        rotinas = self.cfg.nucleo.agenda.listar()
        if not rotinas:
            self.lista.addWidget(rotulo(t("rot.vazia"), "nota", quebra=True))
        for r in rotinas:
            self.lista.addWidget(self._cartao(r))

    def _cartao(self, r):
        f = QFrame()
        f.setProperty("papel", "secao")
        v = QVBoxLayout(f)
        v.setContentsMargins(22, 18, 22, 18)
        v.setSpacing(6)
        nome = QLabel(r["nome"])
        nome.setProperty("papel", "h2")
        v.addWidget(nome)
        v.addWidget(rotulo(agenda_lib.descrever_quando(r["quando"], t), "texto", quebra=True))
        v.addWidget(rotulo(r["pedido"], "nota", quebra=True))
        if not r["aprovada"]:
            v.addWidget(rotulo(t("rot.pendente"), "nota", quebra=True))
        elif r["ativa"] and r.get("proxima"):
            v.addWidget(rotulo(t("rot.proxima", quando=_formatar_quando(r["proxima"])), "nota", quebra=True))
        elif r["ativa"]:
            v.addWidget(rotulo(t("rot.sem_proxima"), "nota", quebra=True))
        u = r.get("ultima")
        if u:
            quando = _formatar_quando(u["quando"])
            chave = {"ok": "rot.ultima_ok", "parou": "rot.ultima_parou", "erro": "rot.ultima_erro", "perdida": "rot.ultima_perdida"}.get(u["resultado"])
            if chave:
                v.addWidget(rotulo(t(chave, quando=quando, detalhe=u.get("detalhe", "")), "nota", quebra=True))
        if r.get("permitidas"):
            v.addWidget(rotulo(t("rot.perm_titulo") + ": " + ", ".join(t(f"rot.perm_{p}") for p in r["permitidas"]), "nota", quebra=True))
        linha = QHBoxLayout()
        linha.setSpacing(10)
        if not r["aprovada"]:
            linha.addWidget(_botao(t("rot.aprovar"), "primario", lambda _=False, i=r["id"]: self._aprovar(i)))
            linha.addWidget(_Confirma(t("rot.descartar"), lambda i=r["id"]: self._apagar(i)))
        else:
            ligada = QCheckBox(t("rot.ligada"))
            ligada.setChecked(r["ativa"])
            ligada.toggled.connect(lambda x, i=r["id"]: self._ligar(i, x))
            linha.addWidget(ligada)
            linha.addWidget(_botao(t("rot.rodar_agora"), "chip", lambda _=False, i=r["id"]: self.cfg.rodar_rotina.emit(i)))
        linha.addWidget(_botao(t("rot.editar"), "chip", lambda _=False, x=r: self._abrir_form(x)))
        if r["aprovada"]:
            linha.addWidget(_Confirma(t("rot.apagar"), lambda i=r["id"]: self._apagar(i)))
        linha.addStretch(1)
        v.addSpacing(6)
        v.addLayout(linha)
        return f

    def _aprovar(self, id_):
        self.cfg.nucleo.agenda.atualizar(id_, aprovada=True, ativa=True)
        self._listar()
        self.cfg.rotinas_mudaram.emit()

    def _ligar(self, id_, ligada):
        self.cfg.nucleo.agenda.atualizar(id_, ativa=ligada)
        self._listar()
        self.cfg.rotinas_mudaram.emit()

    def _apagar(self, id_):
        self.cfg.nucleo.agenda.apagar(id_)
        self._listar()
        self.cfg.rotinas_mudaram.emit()


# ------------------------------------------------------------
# Nuvem
# ------------------------------------------------------------

class PNuvem(Pagina):
    def __init__(self, cfg):
        super().__init__(t("cfg.nuvem.titulo"), t("cfg.nuvem.sub"))
        self.cfg = cfg
        s0, v0 = _secao(t("nuvem.login.titulo"), t("nuvem.login.sub"))
        self.login = LoginOllama(lambda: cfg.nucleo.OLLAMA_HOST, ao_mudar=self._modelos_mudaram)
        v0.addWidget(self.login)
        self.adicionar(s0)
        s, v = _secao(t("cfg.nuvem.cartao"), t("cfg.nuvem.cartao_sub"))
        self.ativa = QCheckBox(t("cfg.nuvem.ativar"))
        v.addWidget(self.ativa)
        linha = QHBoxLayout()
        linha.setSpacing(10)
        self.grupo = QButtonGroup(self)
        self.grupo.setExclusive(True)
        self.chips = {}
        for prov in pu.PROVEDORES:
            b = _botao(prov["nome"], "chip")
            b.setMinimumWidth(len(prov["nome"]) * 9 + 44)
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, p=prov["id"]: self._escolheu(p))
            self.grupo.addButton(b)
            self.chips[prov["id"]] = b
            linha.addWidget(b)
        linha.addStretch(1)
        v.addLayout(linha)
        self.aviso = rotulo(t("cfg.nuvem.a_confirmar"), "nota", quebra=True)
        v.addWidget(self.aviso)
        v.addWidget(QLabel(t("cfg.nuvem.endereco")))
        self.endereco = QLineEdit()
        self.endereco.setPlaceholderText("https://…/v1")
        v.addWidget(self.endereco)
        v.addWidget(QLabel(t("cfg.nuvem.chave")))
        self.chave = QLineEdit()
        self.chave.setEchoMode(QLineEdit.Password)
        v.addWidget(self.chave)
        v.addWidget(rotulo(t("cfg.nuvem.chave_nota"), "nota", quebra=True))
        botoes = QHBoxLayout()
        botoes.setSpacing(10)
        self.b_testar = _botao(t("cfg.nuvem.testar"), "chip", self._testar)
        self.b_salvar = _botao(t("cfg.nuvem.salvar"), "primario", self._salvar)
        botoes.addWidget(self.b_testar)
        botoes.addWidget(self.b_salvar)
        botoes.addStretch(1)
        v.addLayout(botoes)
        self.resultado = QLabel("")
        self.resultado.setWordWrap(True)
        self.resultado.setProperty("papel", "nota")
        v.addWidget(self.resultado)
        self.adicionar(s)

        # 5.1: pesquisa web pelo SearXNG (desligada por padrão)
        s2, v2 = _secao(t("web.titulo"), t("web.sub"))
        self.web = QCheckBox(t("web.ligar"))
        v2.addWidget(self.web)
        v2.addWidget(QLabel(t("web.endereco")))
        self.web_endereco = QLineEdit()
        self.web_endereco.setPlaceholderText(web_lib.ENDERECO_PADRAO)
        v2.addWidget(self.web_endereco)
        bw = QHBoxLayout()
        bw.setSpacing(10)
        self.b_web_testar = _botao(t("web.testar"), "chip", self._testar_web)
        bw.addWidget(self.b_web_testar)
        bw.addWidget(_botao(t("cfg.nuvem.salvar"), "primario", self._salvar_web))
        bw.addStretch(1)
        v2.addLayout(bw)
        self.web_resultado = _Msg()
        v2.addWidget(self.web_resultado)
        v2.addWidget(rotulo(t("web.nota"), "nota", quebra=True))
        self.adicionar(s2)
        self.terminar()
        self._salva = False

    def _modelos_mudaram(self):
        self.cfg.nucleo.catalogar_modelos(forcar=True)
        self.cfg.modelos_mudaram.emit()

    def _testar_web(self):
        endereco = self.web_endereco.text().strip() or web_lib.ENDERECO_PADRAO
        self.b_web_testar.setEnabled(False)
        self.web_resultado.setText(t("cfg.nuvem.testando"))

        def pronto(r):
            self.b_web_testar.setEnabled(True)
            self.web_resultado.setText(t("web.ok", n=len(r)) if isinstance(r, list) else t("web.erro", erro=r))
        self.cfg.em_segundo_plano(lambda: web_lib.buscar("openTARS", endereco), pronto)

    def _salvar_web(self):
        web_lib.salvar_config(self.web.isChecked(), self.web_endereco.text().strip() or web_lib.ENDERECO_PADRAO)
        self.web_resultado.setText(t("web.salva_ligada" if self.web.isChecked() else "web.salva_desligada"))

    def ao_abrir(self):
        self.login.atualizar()
        w = web_lib.config()
        self.web.setChecked(w["ligada"])
        self.web_endereco.setText(w["endereco"])
        self.web_resultado.setText("")
        d = pu.carregar_nuvem()
        self._salva = bool(d["chave"])
        self.ativa.setChecked(d["ativa"])
        inicial = d["provedor"] if d["provedor"] in self.chips else "ollama"
        self.chips[inicial].setChecked(True)
        self.endereco.setText(d["endereco"] or pu.provedor(inicial)["endereco"])
        self.chave.clear()
        self.chave.setPlaceholderText(t("cfg.nuvem.chave_salva") if self._salva else "")
        self.aviso.setVisible(pu.provedor(inicial)["a_confirmar"])
        self.resultado.setText("")

    def _escolheu(self, id_):
        self.endereco.setText(pu.provedor(id_)["endereco"])
        self.aviso.setVisible(pu.provedor(id_)["a_confirmar"])

    def _provedor(self):
        return next((i for i, b in self.chips.items() if b.isChecked()), "outro")

    def _chave_em_uso(self):
        return self.chave.text().strip() or pu.carregar_nuvem()["chave"]

    def _testar(self):
        endereco, chave = self.endereco.text().strip(), self._chave_em_uso()
        self.b_testar.setEnabled(False)
        self.resultado.setText(t("cfg.nuvem.testando"))

        def pronto(r):
            self.b_testar.setEnabled(True)
            ok, motivo = r if not isinstance(r, Exception) else (False, "rede")
            self.resultado.setText(t("cfg.nuvem.ok") if ok else t(f"cfg.nuvem.erro_{motivo}") if motivo in ("chave", "endereço", "rede") else t("cfg.nuvem.erro_rede"))

        self.cfg.em_segundo_plano(lambda: pu.testar_nuvem(endereco, chave), pronto)

    def _salvar(self):
        chave = self._chave_em_uso()
        pu.salvar_nuvem(self.ativa.isChecked(), self._provedor(), self.endereco.text().strip(), chave)
        self.chave.clear()
        self.chave.setPlaceholderText(t("cfg.nuvem.chave_salva") if chave else "")
        self.resultado.setText(t("cfg.nuvem.salva"))
        self.cfg.nucleo._cache_modelos_nuvem["dados"] = None
        self.cfg.modelos_mudaram.emit()


# ------------------------------------------------------------
# 5.1: Probes (modos Base e Pro). A lógica fica em tars_probes.py; o serviço é outro processo (opentars --probes).
# ------------------------------------------------------------

def descrever_check(check):
    if "daily_at" in check:
        return t("probes.check_dia", hora=check["daily_at"])
    if check.get("on_change"):
        return t("probes.check_mudar")
    return t("probes.check_minutos", n=check.get("every_minutes", 30))


class _Bloco(QPushButton):
    """Um cartão clicável do passo 1 ("O que vigiar?"): título e uma linha de exemplo."""

    def __init__(self, titulo, exemplo):
        super().__init__()
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(74)
        self.setStyleSheet(
            f"QPushButton {{ background: {CORES['fundo']}; border: 1px solid {CORES['borda']}; border-radius: 12px; }}"
            f"QPushButton:hover {{ border-color: {CORES['borda3']}; }}"
            f"QPushButton:checked {{ border: 2px solid {CORES['verde']}; background: {CORES['destaque']}; }}")
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 10, 14, 10)
        v.setSpacing(2)
        a = QLabel(titulo)
        a.setProperty("papel", "h2")
        b = rotulo(exemplo, "nota", quebra=True)
        for w in (a, b):
            w.setAttribute(Qt.WA_TransparentForMouseEvents)
            v.addWidget(w)


def _campo(rotulo_texto, widget, dica=None):
    """Um campo do passo 2: rótulo em cima, o widget e uma dica embaixo (opcional)."""
    w = QWidget()
    v = QVBoxLayout(w)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(6)
    v.addWidget(rotulo(rotulo_texto, "texto"))
    v.addWidget(widget)
    if dica:
        v.addWidget(rotulo(dica, "nota", quebra=True))
    return w


def _com_botao(campo, texto, ao_clicar):
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(8)
    h.addWidget(campo, 1)
    h.addWidget(_botao(texto, "chip", ao_clicar))
    return w


class PProbes(Pagina):
    """Três partes: o interruptor geral (o serviço, com o ícone perto do relógio), o passo a passo para criar (o que
    vigiar → os detalhes → a frase do que ele vai fazer → "Criar e ligar") e os cartões dos Probes. O passo a passo
    monta o plano sem IA (tars_probes.plano_do_passo_a_passo); só "Com as minhas palavras" passa pelo Gargantua."""

    TIPOS = ("pasta", "web", "feed", "sistema", "programa", "git", "palavras")

    def __init__(self, cfg):
        super().__init__(t("probes.titulo"), t("probes.sub"))
        self.cfg = cfg
        self.probes = probes_lib.Probes()
        self._plano = None                  # (missão, plano) do "com as minhas palavras", depois de entender

        # 1) o interruptor geral
        s, v = _secao(t("probes.servico"))
        linha = QHBoxLayout()
        linha.setSpacing(12)
        self.estado = QLabel("")
        self.estado.setProperty("papel", "h2")
        self.estado.setTextFormat(Qt.RichText)
        linha.addWidget(self.estado, 1)
        self.b_servico = _botao("", "primario", self._alternar_servico)
        self.b_servico.setMinimumWidth(170)
        linha.addWidget(self.b_servico)
        v.addLayout(linha)
        self.estado_sub = rotulo("", "nota", quebra=True)
        v.addWidget(self.estado_sub)
        linha2 = QHBoxLayout()
        linha2.setSpacing(10)
        self.b_lite = _botao(t("probes.baixar_lite"), "chip", self._baixar_lite)
        self.b_lite.hide()
        linha2.addWidget(self.b_lite)
        self.b_parar = _Confirma(t("probes.parar_tudo"), self._parar_tudo)
        linha2.addWidget(self.b_parar)
        linha2.addStretch(1)
        v.addLayout(linha2)
        self.adicionar(s)

        # 2) o passo a passo
        s2, v2 = _secao(t("probes.nova"), t("probes.nova_sub"))
        v2.addWidget(rotulo(t("probes.passo1"), "kicker"))
        grade = QGridLayout()
        grade.setSpacing(10)
        self.blocos = {}
        self.grupo = grupo = QButtonGroup(self)
        for i, tipo in enumerate(self.TIPOS):
            b = _Bloco(t(f"probes.tipo.{tipo}"), t(f"probes.tipo.{tipo}_ex"))
            b.clicked.connect(lambda _=False, x=tipo: self._escolher(x))
            grupo.addButton(b)
            grade.addWidget(b, i // 2, i % 2)
            self.blocos[tipo] = b
        v2.addLayout(grade)

        self.passo2 = QWidget()
        p2 = QVBoxLayout(self.passo2)
        p2.setContentsMargins(0, 10, 0, 0)
        p2.setSpacing(12)
        p2.addWidget(rotulo(t("probes.passo2"), "kicker"))
        self.formularios = QStackedWidget()
        self.formularios.currentChanged.connect(lambda i: self.formularios.setFixedHeight(
            self.formularios.widget(i).sizeHint().height()))
        self._montar_formularios()
        p2.addWidget(self.formularios)

        self.resumo = QLabel("")             # QLabel e não Rotulo: o HTML é nosso (o que vem do modelo é escapado)
        self.resumo.setProperty("papel", "texto")
        self.resumo.setWordWrap(True)
        self.resumo.setTextFormat(Qt.RichText)
        self.caixa_resumo = QFrame()
        self.caixa_resumo.setProperty("papel", "linha-lista")
        cr = QVBoxLayout(self.caixa_resumo)
        cr.setContentsMargins(16, 12, 16, 12)
        cr.setSpacing(8)
        cr.addWidget(self.resumo)
        self.acoes = QWidget()               # mover e lixeira: só para pasta
        ac = QVBoxLayout(self.acoes)
        ac.setContentsMargins(0, 4, 0, 0)
        ac.setSpacing(6)
        self.c_mover = QCheckBox(t("probes.acao_mover"))
        self.destino = QLineEdit()
        self.destino.setPlaceholderText(t("probes.destino_ph"))
        self.destino.setEnabled(False)
        self.c_mover.toggled.connect(self.destino.setEnabled)
        self.c_lixeira = QCheckBox(t("probes.acao_lixeira"))
        for w in (rotulo(t("probes.acoes_titulo"), "nota"), self.c_mover, self.destino, self.c_lixeira):
            ac.addWidget(w)
        cr.addWidget(self.acoes)
        p2.addWidget(self.caixa_resumo)
        linha3 = QHBoxLayout()
        self.b_criar = _botao(t("probes.criar_e_ligar"), "primario", self._criar)
        self.b_criar.setMinimumWidth(200)
        linha3.addWidget(self.b_criar)
        linha3.addStretch(1)
        p2.addLayout(linha3)
        self.passo2.hide()
        v2.addWidget(self.passo2)
        self.msg = _Msg()
        v2.addWidget(self.msg)
        self.adicionar(s2)

        # 3) os Probes
        self.titulo_lista = rotulo(t("probes.seus"), "kicker")
        self.adicionar(self.titulo_lista)
        self.lista = QVBoxLayout()
        self.lista.setSpacing(12)
        c = QWidget()
        c.setLayout(self.lista)
        self.adicionar(c)
        self.adicionar(rotulo(t("probes.nota"), "nota", quebra=True))
        self.terminar()
        self._relogio = QTimer(self)
        self._relogio.timeout.connect(self._listar)
        self._instalados = []

    # -- passo 2: um formulário por tipo -------------------------------------------------------
    def _montar_formularios(self):
        self.f = {}

        def pagina(*campos):
            w = QWidget()
            v = QVBoxLayout(w)
            v.setContentsMargins(0, 0, 0, 0)
            v.setSpacing(12)
            for c in campos:
                v.addWidget(c)
            v.addStretch(1)
            self.formularios.addWidget(w)
            return w

        def texto(ph="", valor=""):
            e = QLineEdit(valor)
            e.setPlaceholderText(ph)
            e.textChanged.connect(self._atualizar_resumo)
            return e

        def escolha(pares):
            c = QComboBox()
            for chave, rot in pares:
                c.addItem(rot, chave)
            c.currentIndexChanged.connect(self._atualizar_resumo)
            return c

        def numero(minimo, maximo, valor, sufixo):
            n = QSpinBox()
            n.setRange(minimo, maximo)
            n.setValue(valor)
            n.setSuffix(sufixo)
            n.setMaximumWidth(160)
            n.valueChanged.connect(self._atualizar_resumo)
            return n

        f = self.f
        f["pasta"] = texto("~/Downloads", "~/Downloads")
        f["filtro"] = texto(t("probes.f.filtro_ph"))
        pagina(_campo(t("probes.f.pasta"), _com_botao(f["pasta"], t("probes.f.escolher"), lambda: self._pasta(f["pasta"]))),
               _campo(t("probes.f.filtro"), f["filtro"], t("probes.f.filtro_dica")))
        f["url"] = texto("https://")
        f["texto"] = texto(t("probes.f.texto_ph"))
        f["minutos"] = escolha([(15, t("probes.f.min15")), (60, t("probes.f.min60")), (360, t("probes.f.min360")),
                                (1440, t("probes.f.min1440"))])
        f["minutos"].setCurrentIndex(1)
        pagina(_campo(t("probes.f.url"), f["url"]), _campo(t("probes.f.texto"), f["texto"], t("probes.f.texto_dica")),
               _campo(t("probes.f.frequencia"), f["minutos"]))
        f["feed"] = texto("https://github.com/ollama/ollama")
        pagina(_campo(t("probes.f.feed"), f["feed"], t("probes.f.feed_dica")))
        f["condicao"] = escolha([(x, t(f"probes.f.sis_{x}")) for x in probes_lib.CONDICOES_DO_SISTEMA])
        f["limite_sis"] = numero(1, 120, 20, "")
        f["condicao"].currentIndexChanged.connect(self._limite_do_sistema)
        self.campo_limite_sis = _campo(t("probes.f.limite"), f["limite_sis"])
        pagina(_campo(t("probes.f.condicao"), f["condicao"]), self.campo_limite_sis)
        f["programa"] = texto(t("probes.f.programa_ph"))
        f["evento"] = escolha([(x, t(f"probes.f.prog_{x}")) for x in probes_lib.EVENTOS_DO_PROGRAMA])
        f["limite_mb"] = numero(100, 64000, 2000, " MB")
        f["evento"].currentIndexChanged.connect(lambda: self.campo_limite_mb.setVisible(f["evento"].currentData() == "memoria"))
        self.campo_limite_mb = _campo(t("probes.f.limite_mb"), f["limite_mb"])
        self.campo_limite_mb.hide()
        pagina(_campo(t("probes.f.programa"), f["programa"], t("probes.f.programa_dica")),
               _campo(t("probes.f.evento"), f["evento"]), self.campo_limite_mb)
        f["repo"] = texto("~/projetos/meu-app")
        f["hora"] = texto("18:00", "18:00")
        f["hora"].setMaximumWidth(120)
        pagina(_campo(t("probes.f.repo"), _com_botao(f["repo"], t("probes.f.escolher"), lambda: self._pasta(f["repo"]))),
               _campo(t("probes.f.hora"), f["hora"]))
        self.missao = QPlainTextEdit()
        self.missao.setPlaceholderText(t("probes.missao_ph"))
        self.missao.setFixedHeight(84)
        self.missao.textChanged.connect(self._missao_mudou)
        self.b_entender = _botao(t("probes.entender"), "chip", self._entender)
        self.b_entender.setMaximumWidth(260)
        pagina(_campo(t("probes.f.missao"), self.missao, t("probes.nova_palavras")), self.b_entender)

    def _pasta(self, campo):
        pasta = QFileDialog.getExistingDirectory(self, t("probes.f.escolher"), os.path.expanduser(campo.text() or "~"))
        if pasta:
            campo.setText(pasta.replace(str(Path.home()), "~", 1))

    def _limite_do_sistema(self):
        cond = self.f["condicao"].currentData()
        self.campo_limite_sis.setVisible(cond in ("bateria", "temperatura", "cpu"))
        valor, sufixo = {"bateria": (20, " %"), "temperatura": (85, " °C"), "cpu": (90, " %")}.get(cond, (0, ""))
        self.f["limite_sis"].blockSignals(True)
        self.f["limite_sis"].setSuffix(sufixo)
        if valor:
            self.f["limite_sis"].setValue(valor)
        self.f["limite_sis"].blockSignals(False)
        self._atualizar_resumo()

    def _escolher(self, tipo):
        self.tipo = tipo
        self.formularios.setCurrentIndex(self.TIPOS.index(tipo))
        self.formularios.setFixedHeight(self.formularios.currentWidget().sizeHint().height())
        self.acoes.setVisible(tipo == "pasta")
        self.c_mover.setChecked(False)
        self.c_lixeira.setChecked(False)
        self.msg.setText("")
        self.passo2.show()
        if tipo == "sistema":
            self._limite_do_sistema()
        self._atualizar_resumo()
        QTimer.singleShot(50, lambda: self.ensureWidgetVisible(self.b_criar, 0, 40))

    def _campos(self):
        """(campos para plano_do_passo_a_passo, erro em texto ou None)."""
        f, tipo = self.f, self.tipo
        if tipo == "pasta":
            pasta = f["pasta"].text().strip()
            if not pasta or not Path(os.path.expanduser(pasta)).is_dir():
                return None, t("probes.f.erro_pasta")
            if probes_lib.caminho_proibido(pasta):
                return None, t("probes.proibido", caminho=pasta)
            return {"pasta": pasta, "filtro": f["filtro"].text()}, None
        if tipo == "web":
            url = f["url"].text().strip()
            if not url.lower().startswith(("http://", "https://")) or len(url) < 12:
                return None, t("probes.f.erro_url")
            return {"url": url, "texto": f["texto"].text(), "minutos": f["minutos"].currentData()}, None
        if tipo == "feed":
            url = f["feed"].text().strip()
            if not url.lower().startswith(("http://", "https://")) or len(url) < 12:
                return None, t("probes.f.erro_url")
            return {"url": url}, None
        if tipo == "sistema":
            return {"condicao": f["condicao"].currentData(), "limite": f["limite_sis"].value()}, None
        if tipo == "programa":
            nome = f["programa"].text().strip()
            if not nome:
                return None, t("probes.f.erro_programa")
            return {"programa": nome, "evento": f["evento"].currentData(), "limite": f["limite_mb"].value()}, None
        if tipo == "git":
            repo = f["repo"].text().strip()
            if not (Path(os.path.expanduser(repo)) / ".git").exists():
                return None, t("probes.f.erro_repo")
            if not agenda_lib.ler_hora(f["hora"].text()):
                return None, t("probes.f.erro_hora")
            return {"repo": repo, "hora": f["hora"].text()}, None
        return None, None

    def _atualizar_resumo(self):
        if getattr(self, "tipo", None) is None:
            return
        if self.tipo == "palavras":
            if self._plano:
                self.resumo.setText(self._resumo(self._plano[1]))
            self.caixa_resumo.setVisible(bool(self._plano))
            self.b_criar.setEnabled(bool(self._plano))
            return
        campos, erro = self._campos()
        self.caixa_resumo.setVisible(True)
        self.b_criar.setEnabled(erro is None)
        if erro:
            self.resumo.setText(f"<span style='color:{CORES['apoio']}'>{html.escape(erro)}</span>")
            return
        _missao, bruto, _regra = probes_lib.plano_do_passo_a_passo(self.tipo, campos, t)
        plano, _ = probes_lib.validar_plano(bruto)
        self.resumo.setText(t("probes.frase", quando=html.escape(plano["alert"]["when"]),
                              check=html.escape(descrever_check(plano["check"])), n=plano["alert"]["max_per_day"]))

    def _missao_mudou(self):
        self._plano = None
        self._atualizar_resumo()

    # -- o interruptor geral -------------------------------------------------------------------
    def ao_abrir(self):
        self._listar()
        self._relogio.start(30000)
        n = self.cfg.nucleo

        def trabalho():
            return pu.modelos_instalados(n.OLLAMA_HOST)

        def pronto(instalados):
            self._instalados = [] if isinstance(instalados, Exception) else instalados
            precisa_modelo = any(not p.get("regra") for p in self.probes.listar())
            self.b_lite.setVisible(precisa_modelo and not any(probes_lib._variante(m) == "lite" for m in self._instalados))
            self._mostrar_estado()
        self.cfg.em_segundo_plano(trabalho, pronto)
        self._mostrar_estado()

    def _mostrar_estado(self):
        ligado = probes_lib.servico_ligado()
        rodando = bool(probes_lib.servico_rodando())
        ativos = sum(1 for p in self.probes.listar() if p["ativo"])
        cor = CORES["verde"] if ligado and rodando else CORES["mudo"]
        if ligado and rodando:
            titulo = t("probes.estado_ligado", n=ativos)
            sub = t("probes.estado_ligado_sub")
        elif ligado:
            titulo, sub = t("probes.estado_iniciando"), t("probes.estado_iniciando_sub")
        else:
            titulo, sub = t("probes.estado_desligado"), t("probes.estado_desligado_sub")
        self.estado.setText(f"<span style='color:{cor}'>•</span>&nbsp; {html.escape(titulo)}")
        self.estado_sub.setText(sub)
        self.b_servico.setText(t("probes.desligar_servico") if ligado else t("probes.ligar_servico"))
        self.b_servico.setProperty("papel", "chip" if ligado else "primario")
        _repolir(self.b_servico)
        self.b_parar.setVisible(ligado or ativos > 0)

    def hideEvent(self, e):
        self._relogio.stop()
        super().hideEvent(e)

    def _alternar_servico(self):
        probes_lib.ligar_servico(not probes_lib.servico_ligado())
        self._mostrar_estado()
        QTimer.singleShot(1500, self._mostrar_estado)

    def _parar_tudo(self):
        self.probes.desligar_todos()
        probes_lib.ligar_servico(False)
        self.ao_abrir()

    def _baixar_lite(self):
        n = self.cfg.nucleo
        self.b_lite.setEnabled(False)

        def trabalho():
            def andamento(p):
                pct = int(100 * p.fracao)
                self.cfg.depois(lambda: self.b_lite.setText(t("cfg.baixando", pct=pct)))
            return pu.baixar_modelo(pu.MODELO_GARGANTUA_LITE, n.OLLAMA_HOST, ao_progredir=andamento)

        def pronto(r):
            ok, erro = r if not isinstance(r, Exception) else (False, str(r))
            self.b_lite.setText(t("probes.baixar_lite"))
            self.b_lite.setEnabled(True)
            if not ok:
                self.estado_sub.setText(t("cfg.baixar_erro", erro=erro))
            self.ao_abrir()
        self.cfg.em_segundo_plano(trabalho, pronto)

    # -- "com as minhas palavras": missão -> plano -----------------------------------------------
    def _entender(self):
        missao = self.missao.toPlainText().strip()
        if not missao:
            return
        n = self.cfg.nucleo
        self.b_entender.setEnabled(False)
        self.msg.setText(t("probes.entendendo"))

        def trabalho():
            return probes_lib.planejar(missao, n.OLLAMA_HOST, pu.modelos_instalados(n.OLLAMA_HOST))

        def pronto(r):
            self.b_entender.setEnabled(True)
            plano, erro = r if not isinstance(r, Exception) else (None, str(r))
            if erro:
                self.msg.setText(self._erro(erro))
                return
            self.msg.setText(t("probes.confira"))
            self._plano = (missao, plano)
            self.acoes.setVisible(any(probes_lib.tipo_do_alvo(w) == "caminho" for w in plano["watch"]))
            self._atualizar_resumo()
        self.cfg.em_segundo_plano(trabalho, pronto)

    def _erro(self, erro):
        if erro.startswith("recusa:"):
            return t("probes.recusou", motivo=erro.split(":", 1)[1])
        if erro.startswith("proibido:"):
            return t("probes.proibido", caminho=erro.split(":", 1)[1])
        return t(f"probes.erro_{erro}") if erro in ("json", "ferramentas", "sem_modelo", "sem_resposta", "missao",
                                                     "limite", "destino") else erro

    def _resumo(self, plano):
        esc = lambda x: html.escape(tema.seguro(x, True))  # noqa: E731
        plano = {k: (esc(v) if isinstance(v, str) else [esc(x) for x in v] if isinstance(v, list)
                     else {a: esc(b) if isinstance(b, str) else b for a, b in v.items()} if isinstance(v, dict) else v)
                 for k, v in plano.items()}       # o plano vem do modelo: nada dele vira HTML (nem glifo fora da Plex)
        return "<br>".join([
            f"<b>{plano['name']}</b>",
            t("probes.r_olha", onde=", ".join(plano["watch"]) or "—"),
            t("probes.r_quando", quando=descrever_check(plano["check"])),
            t("probes.r_avisa", quando=plano["alert"]["when"], n=plano["alert"]["max_per_day"]),
        ] + ([t("probes.r_nao_faz", lista="; ".join(plano["will_not"]))] if plano["will_not"] else []))

    # -- criar e ligar -------------------------------------------------------------------------
    def _criar(self):
        if getattr(self, "tipo", None) is None:
            return
        if self.tipo == "palavras":
            if not self._plano:
                return
            missao, plano = self._plano
            regra = plano.get("regra")       # plano montado por regras (planejar): o Probe não chama modelo
        else:
            campos, erro = self._campos()
            if erro:
                self.msg.setText(erro)
                return
            missao, plano, regra = probes_lib.plano_do_passo_a_passo(self.tipo, campos, t)
        destino = self.destino.text().strip() if self.acoes.isVisible() and self.c_mover.isChecked() else None
        p, erro = self.probes.criar(missao, plano, mover_para=destino, regra=regra,
                                    lixeira=self.acoes.isVisible() and self.c_lixeira.isChecked())
        if erro:
            self.msg.setText(self._erro(erro))
            return
        _p, erro = self.probes.ligar(p["id"], True)
        partes = [t("probes.criado_ligado", nome=p["plano"]["name"]) if not erro else
                  t("probes.criado", nome=p["plano"]["name"]) + " " + self._erro(erro)]
        if not erro and not probes_lib.servico_ligado():
            probes_lib.ligar_servico(True)
            partes.append(t("probes.servico_ligado_agora"))
        if not regra and not probes_lib.modelo_para_rodar(self._instalados):
            partes.append(t("probes.precisa_modelo"))
        self.msg.setText(tema.seguro(" ".join(partes), True))
        self._plano = None
        self.missao.clear()
        self.passo2.hide()
        self.grupo.setExclusive(False)        # num grupo exclusivo não dá para desmarcar todos
        for b in self.blocos.values():
            b.setChecked(False)
        self.grupo.setExclusive(True)
        self.tipo = None
        self.ao_abrir()
        QTimer.singleShot(1500, self._mostrar_estado)

    # -- os cartões ----------------------------------------------------------------------------
    def _listar(self):
        while self.lista.count():
            it = self.lista.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        probes = self.probes.listar()
        self.titulo_lista.setVisible(bool(probes))
        for p in probes:
            self.lista.addWidget(self._cartao(p))
        if hasattr(self, "estado"):
            self._mostrar_estado()

    def _cartao(self, p):
        f = QFrame()
        f.setProperty("papel", "secao")
        v = QVBoxLayout(f)
        v.setContentsMargins(22, 16, 22, 16)
        v.setSpacing(6)
        topo = QHBoxLayout()
        nome = QLabel(tema.seguro(p["plano"]["name"], True))
        nome.setProperty("papel", "h2")
        topo.addWidget(nome, 1)
        ligado = QCheckBox(t("probes.ligado"))
        ligado.setChecked(p["ativo"])
        ligado.toggled.connect(lambda x, i=p["id"]: self._ligar(i, x))
        topo.addWidget(ligado)
        v.addLayout(topo)
        v.addWidget(rotulo(tema.seguro(p["missao"], True), "texto", quebra=True))
        detalhes = [descrever_check(p["plano"]["check"])]
        if p["plano"]["watch"]:
            detalhes.append(", ".join(p["plano"]["watch"]))
        detalhes.append(t("probes.sem_ia") if p.get("regra") else t("probes.com_ia"))
        if p.get("ultima"):
            detalhes.append(t("probes.ultima", quando=_formatar_quando(p["ultima"])))
        v.addWidget(rotulo(tema.seguro(" · ".join(detalhes), True), "nota", quebra=True))
        acoes = p.get("acoes") or {}
        if acoes.get("mover_para") or acoes.get("lixeira"):
            partes = ([t("probes.tem_mover", pasta=acoes["mover_para"])] if acoes.get("mover_para") else []) + \
                     ([t("probes.tem_lixeira")] if acoes.get("lixeira") else [])
            v.addWidget(rotulo(tema.seguro(" · ".join(partes), True), "nota", quebra=True))
        for h in (p.get("historico") or [])[-2:][::-1]:
            v.addWidget(rotulo(tema.seguro(self._linha_historico(h), True), "nota", quebra=True))
        linha = QHBoxLayout()
        linha.setSpacing(10)
        linha.addWidget(_botao(t("probes.rodar_agora"), "chip", lambda _=False, i=p["id"]: self._rodar_agora(i)))
        linha.addWidget(_Confirma(t("probes.apagar"), lambda i=p["id"]: (self.probes.apagar(i), self._listar())))
        linha.addStretch(1)
        v.addSpacing(4)
        v.addLayout(linha)
        return f

    def _linha_historico(self, h):
        quando = _formatar_quando(h["quando"])
        if h.get("movidos"):
            return t("probes.h_movidos", quando=quando, n=len(h["movidos"]))
        if h.get("lixeira"):
            return t("probes.h_lixeira", quando=quando, arquivo=Path(h["lixeira"]).name)
        if h.get("negado"):
            return t("probes.h_negado", quando=quando, arquivo=Path(h["negado"]).name)
        return f"{quando} · {h.get('mensagem', '')}" + (" " + t("probes.h_calado") if h.get("calado") else "")

    def _ligar(self, id_, ligado):
        _p, erro = self.probes.ligar(id_, ligado)
        if erro:
            self.msg.setText(self._erro(erro))
        elif ligado and not probes_lib.servico_ligado():
            probes_lib.ligar_servico(True)
            self.msg.setText(t("probes.servico_ligado_agora"))
        self._listar()

    def _rodar_agora(self, id_):
        n = self.cfg.nucleo
        self.msg.setText(t("probes.rodando_agora"))

        def trabalho():
            p = self.probes.obter(id_)
            modelo = None if p.get("regra") else probes_lib.modelo_para_rodar(pu.modelos_instalados(n.OLLAMA_HOST))
            if not p.get("regra") and not modelo:
                return t("probes.erro_sem_modelo")
            r = probes_lib.rodar(p, lambda s, pedido, e: probes_lib.perguntar_ollama(n.OLLAMA_HOST, modelo, s, pedido, e), t=t)
            aviso = self.probes.registrar(id_, r)
            if aviso:
                self.probes.aplicar_acoes(id_, aviso["itens"])
                return aviso["mensagem"]
            return t("probes.nada_a_avisar") if r["motivo"] in ("nada", "sem_mudanca") else t("probes.sem_decisao")

        def pronto(texto):
            self.msg.setText(tema.seguro(texto, True))
            self._listar()
        self.cfg.em_segundo_plano(trabalho, pronto)


# ------------------------------------------------------------
# 5.1, só no Pro: Ajustes avançados e Diagnóstico
# ------------------------------------------------------------

TEMPERATURAS = (0.0, 0.1, 0.2, 0.3, 0.5, 0.7, 1.0)


class PAvancado(Pagina):
    def __init__(self, cfg):
        super().__init__(t("cfg.avancado.titulo"), t("cfg.avancado.sub"))
        self.cfg = cfg
        self.aviso = _Msg()
        self.adicionar(self.aviso)

        s, v = _secao(t("cfg.av.temperatura"), t("cfg.av.temperatura_sub"))
        self.temperatura = QComboBox()
        self.temperatura.setMaximumWidth(220)
        self.temperatura.addItem(t("cfg.av.automatico"), None)
        for x in TEMPERATURAS:
            self.temperatura.addItem(f"{x:.1f}", x)
        v.addWidget(self.temperatura)
        self.adicionar(s)

        s2, v2 = _secao(t("cfg.av.contexto"), t("cfg.av.contexto_sub"))
        self.contexto = QComboBox()
        self.contexto.setMaximumWidth(220)
        self.contexto.addItem(t("cfg.av.automatico"), None)
        for x in modos.CONTEXTOS:
            self.contexto.addItem(f"{x:,}".replace(",", "."), x)
        v2.addWidget(self.contexto)
        self.adicionar(s2)

        s3, v3 = _secao(t("cfg.av.instrucoes"), t("cfg.av.instrucoes_sub"))
        self.instrucoes = QPlainTextEdit()
        self.instrucoes.setFixedHeight(110)
        v3.addWidget(self.instrucoes)
        self.adicionar(s3)

        s4, v4 = _secao(t("cfg.av.ferramentas"), t("cfg.av.ferramentas_sub"))
        self.caixas = {}
        for f in cfg.nucleo.ferramentas_gargantua():
            nome = f["function"]["name"]
            c = QCheckBox(f"{nome} — {f['function']['description']}")
            self.caixas[nome] = c
            v4.addWidget(c)
        self.adicionar(s4)

        linha = QHBoxLayout()
        linha.setSpacing(10)
        linha.addWidget(_botao(t("cfg.av.salvar"), "primario", self._salvar))
        linha.addWidget(_Confirma(t("cfg.av.restaurar"), self._restaurar))
        linha.addStretch(1)
        self.coluna.addLayout(linha)
        self.msg = _Msg()
        self.adicionar(self.msg)
        self.terminar()

    def ao_abrir(self):
        a = modos.avancado_gravado()
        self.temperatura.setCurrentIndex(max(0, self.temperatura.findData(a["temperatura"])))
        self.contexto.setCurrentIndex(max(0, self.contexto.findData(a["contexto"])))
        self.instrucoes.setPlainText(a["instrucoes"])
        for nome, c in self.caixas.items():
            c.setChecked(nome not in a["ferramentas_desligadas"])
        modo = modos.modo_atual()
        self.aviso.setText("" if modo == "pro" else t("cfg.av.so_pro", modo=t(f"modo.{modo}.nome")))
        self.msg.setText("")

    def _salvar(self):
        modos.salvar_avancado(temperatura=self.temperatura.currentData(), contexto=self.contexto.currentData(),
                              instrucoes=self.instrucoes.toPlainText(),
                              ferramentas_desligadas=[n for n, c in self.caixas.items() if not c.isChecked()])
        self.ao_abrir()
        self.msg.setText(t("cfg.av.salvo"))

    def _restaurar(self):
        tars_i18n.salvar_config(avancado={})
        self.ao_abrir()
        self.msg.setText(t("cfg.av.salvo"))


_LINHA_FERRAMENTA = re.compile(r"^\d{4}-\d\d-\d\d (\d\d:\d\d:\d\d),\d+ \w+ ferramenta=(\S+) args=(.*?) sucesso=(True|False)")
_CORES_ANSI = re.compile(r"\033\[[0-9;]*m")


def ultimas_ferramentas(caminho, quantas=40):
    """As últimas ferramentas do log, uma por linha ("12:03:44 ✓ open_application {"app": "calc"}")."""
    try:
        with open(caminho, encoding="utf-8", errors="replace") as f:
            linhas = f.readlines()[-4000:]
    except OSError:
        return []
    saida = []
    for linha in linhas:
        m = _LINHA_FERRAMENTA.match(linha)
        if m:
            hora, nome, args, ok = m.groups()
            args = args if len(args) <= 90 else args[:87] + "..."
            saida.append(f"{hora} {'✓' if ok == 'True' else '×'} {nome} {args}")
    return saida[-quantas:]


class PDiagnostico(Pagina):
    def __init__(self, cfg):
        super().__init__(t("cfg.diag.titulo"), t("cfg.diag.sub"))
        self.cfg = cfg
        s, v = _secao(t("cfg.diag.log"), t("cfg.diag.log_sub"))
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setProperty("papel", "bloco-codigo-texto")
        self.log.setFixedHeight(280)
        v.addWidget(self.log)
        b = _botao(t("cfg.diag.atualizar"), "chip", self.ao_abrir)
        b.setMaximumWidth(200)
        v.addWidget(b)
        self.adicionar(s)

        s2, v2 = _secao(t("cfg.diag.ambiente"), t("cfg.diag.ambiente_sub"))
        self.b_conferir = _botao(t("cfg.diag.conferir"), "primario", self._conferir)
        self.b_conferir.setMaximumWidth(220)
        v2.addWidget(self.b_conferir)
        self.relatorio = QPlainTextEdit()
        self.relatorio.setReadOnly(True)
        self.relatorio.setProperty("papel", "bloco-codigo-texto")
        self.relatorio.setFixedHeight(280)
        self.relatorio.hide()
        v2.addWidget(self.relatorio)
        self.adicionar(s2)
        self.terminar()

    def ao_abrir(self):
        linhas = ultimas_ferramentas(self.cfg.nucleo.ARQUIVO_LOG)
        self.log.setPlainText("\n".join(linhas) if linhas else t("cfg.diag.vazio"))
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    def _conferir(self):
        n = self.cfg.nucleo
        self.b_conferir.setEnabled(False)
        self.b_conferir.setText(t("cfg.diag.conferindo"))

        def trabalho():
            import tars_autoteste
            saida = io.StringIO()
            with contextlib.redirect_stdout(saida):
                tars_autoteste.executar(n, completo=False)
            return _CORES_ANSI.sub("", saida.getvalue()).strip()

        def pronto(r):
            self.relatorio.setPlainText(str(r))
            self.relatorio.show()
            self.b_conferir.setEnabled(True)
            self.b_conferir.setText(t("cfg.diag.conferir"))

        self.cfg.em_segundo_plano(trabalho, pronto)


# ------------------------------------------------------------
# Atualizações
# ------------------------------------------------------------

class PAtualizacoes(Pagina):
    """25/10 (pedido do Enzo): a barra lateral avisa que há versão nova e leva até aqui; procurar e instalar são desta página."""

    def __init__(self, cfg):
        super().__init__(t("cfg.atual.titulo"), t("cfg.atual.sub"))
        self.cfg = cfg
        s, v = _secao(t("cfg.atual.versao", versao=cfg.nucleo.VERSAO_EXIBIDA))
        self.msg = QLabel(t("cfg.atual.nunca"))
        self.msg.setWordWrap(True)
        self.msg.setProperty("papel", "texto")
        v.addWidget(self.msg)
        linha = QHBoxLayout()
        linha.setSpacing(10)
        self.b = _botao(t("cfg.atual.procurar"), "chip", self._procurar)
        self.b.setMaximumWidth(240)
        self.b_instalar = _botao(t("jp.atualizar"), "atualizar", lambda: cfg.instalar_atualizacao.emit())
        self.b_instalar.setMaximumWidth(240)
        self.b_instalar.hide()
        linha.addWidget(self.b)
        linha.addWidget(self.b_instalar)
        linha.addStretch(1)
        v.addLayout(linha)
        v.addWidget(rotulo(t("cfg.atual.nota"), "nota", quebra=True))
        self.adicionar(s)
        self.terminar()

    def mostrar_versao(self, nova):
        """Há uma versão: diz qual e mostra o botão que instala (ou, se foi instalado por script, copia o comando)."""
        self.msg.setText(t("jp.comando_atualizar", comando=nova["comando"]) if nova.get("comando")
                         else t("cfg.atual.nova", versao=nova["versao"]))
        self.b_instalar.setEnabled(True)
        self.b_instalar.setText(t("jp.atualizar_copiar") if nova.get("comando") else t("jp.atualizar"))
        self.b_instalar.show()

    def estado(self, texto, botao=None, habilitado=False):
        """O andamento da instalação (conferindo, baixando 40%, atualizado, erro) no lugar da frase."""
        self.msg.setText(texto)
        if botao is not None:
            self.b_instalar.setText(botao)
        self.b_instalar.setEnabled(habilitado)
        self.b_instalar.show()

    def _procurar(self):
        self.b.setEnabled(False)
        self.msg.setText(t("cfg.atual.procurando"))

        def pronto(r):
            self.b.setEnabled(True)
            if isinstance(r, Exception) or r is None:
                self.msg.setText(t("cfg.atual.em_dia"))
                self.b_instalar.hide()
            else:
                self.cfg.versao_achada.emit(r)          # a janela guarda a versão, avisa na barra lateral e volta aqui

        self.cfg.em_segundo_plano(lambda: tars_atualizacao.procurar_atualizacao(self.cfg.nucleo.VERSAO), pronto)


# ------------------------------------------------------------
# Sobre
# ------------------------------------------------------------

class PSobre(Pagina):
    def __init__(self, cfg):
        super().__init__(t("cfg.sobre.titulo"), t("cfg.sobre.sub"))
        s, v = _secao("openTARS")
        topo = QHBoxLayout()
        topo.setSpacing(16)
        topo.addWidget(tema.svg_widget(tema.monolito_svg(), 64), 0, Qt.AlignTop)
        col = QVBoxLayout()
        nome = QLabel(f'open<span style="color:{CORES["verde"]}">TARS</span>')
        nome.setTextFormat(Qt.RichText)
        nome.setStyleSheet("font-size: 24px; font-weight: 600;")
        ver = QLabel(f"{cfg.nucleo.VERSAO_EXIBIDA}")
        ver.setProperty("papel", "mono")
        col.addWidget(nome)
        col.addWidget(ver)
        topo.addLayout(col, 1)
        v.addLayout(topo)
        v.addWidget(rotulo(t("cfg.sobre.texto"), "texto", quebra=True))
        v.addWidget(rotulo(t("cfg.sobre.local"), "nota", quebra=True))
        link = _botao(tars_atualizacao.REPOSITORIO, "link")
        link.clicked.connect(lambda: __import__("webbrowser").open(f"https://github.com/{tars_atualizacao.REPOSITORIO}"))
        v.addWidget(link, 0, Qt.AlignLeft)
        self.adicionar(s)
        self.terminar()
