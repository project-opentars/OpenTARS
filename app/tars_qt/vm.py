"""5.3 (F7): a janela das missões em VM, aberta pela página Probes.

A pessoa escreve o pedido; o Gargantua Pro (regra do Enzo: Probes em VM usam o Pro) decide cada passo olhando a tela de uma
máquina virtual descartável (tars_vm_missao.executar). A janela mostra a tela da VM ao vivo, os passos e os sites visitados.
O que o agente deixou na pasta de saída fica em quarentena: só vai para o PC se a pessoa marcar e clicar em "Trazer"; o resto é
apagado com a VM. Antes, a janela mostra o que falta (Linux com KVM, a imagem da VM, o modelo Pro) com um botão para cada coisa."""

import shutil
import threading

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QCheckBox, QFrame, QHBoxLayout, QLabel, QListWidget, QPlainTextEdit, QPushButton, QVBoxLayout,
                               QWidget)

import tars_primeiro_uso as pu
import tars_vm
import tars_vm_agente as agente
import tars_vm_missao as missao_vm
from tars_i18n import t
from tars_vm_cli import PASTA_LIBERADA

from . import fio, tema
from .tema import CORES, rotulo

MOTIVOS = {"terminou": "vm.motivo.terminou", "cancelada": "vm.motivo.cancelada", "tempo esgotado": "vm.motivo.tempo",
           "limite de passos": "vm.motivo.passos"}


def passo_legivel(feito):
    """O executor descreve cada ação em português curto ("atalho ctrl+alt+t", "clicar 120,40"); aqui vira texto do idioma do app."""
    tipo, _, resto = feito.partition(" ")
    if tipo in ("clicar", "duplo", "direito", "atalho"):
        return t(f"vm.passo.{tipo}", detalhe=resto)
    if tipo.startswith("digitou"):
        return t("vm.passo.digitou")
    return t(f"vm.passo.{tipo}") if tipo in ("rolou", "esperou") else feito


def _botao(texto, papel, ao_clicar):
    b = QPushButton(texto)
    b.setProperty("papel", papel)
    b.setCursor(Qt.PointingHandCursor)
    b.clicked.connect(ao_clicar)
    return b


class JanelaVM(QWidget):
    def __init__(self, host, rodar=missao_vm.executar, construir=tars_vm.construir_base, baixar=pu.baixar_modelo,
                 instalados=pu.modelos_instalados, falta=tars_vm.o_que_falta, base=tars_vm.imagem_base):
        super().__init__(None, Qt.Window)
        self.host = host                         # função: o endereço do motor pode mudar depois da migração
        self._rodar, self._construir, self._baixar, self._instalados, self._falta, self._base = \
            rodar, construir, baixar, instalados, falta, base
        self.cancelar = None
        self.resultado = None
        self.ocupado = False
        self.setObjectName("janela-vm")
        self.setWindowTitle(t("vm.janela.titulo"))
        self.setStyleSheet(f"QWidget#janela-vm {{ background: {CORES['fundo']}; }} "
                           f"QListWidget {{ background: {CORES['cartao']}; color: {CORES['texto2']}; border: 1px solid {CORES['borda2']}; "
                           f"border-radius: 10px; padding: 6px; font-size: 14px; }} QListWidget::item {{ padding: 3px 2px; }}")
        self.resize(1100, 720)
        v = QVBoxLayout(self)
        v.setContentsMargins(22, 18, 22, 18)
        v.setSpacing(12)

        topo = QHBoxLayout()
        topo.addWidget(tema.svg_widget(tema.monolito_svg(), 24), 0, Qt.AlignVCenter)
        topo.addWidget(rotulo(t("vm.janela.titulo"), "titulo-cartao"))
        topo.addStretch(1)
        modelo = QLabel(agente.MODELO.split("/")[-1])
        modelo.setProperty("papel", "pilula")
        topo.addWidget(modelo)
        v.addLayout(topo)
        v.addWidget(rotulo(t("vm.janela.sub"), "nota", quebra=True))

        # o que falta (some quando está tudo pronto)
        self.falta = QFrame()
        self.falta.setProperty("papel", "linha-lista")
        f = QHBoxLayout(self.falta)
        f.setContentsMargins(16, 10, 16, 10)
        self.falta_texto = rotulo("", "texto", quebra=True)
        f.addWidget(self.falta_texto, 1)
        self.b_base = _botao(t("vm.janela.montar"), "primario", self._montar_base)
        self.b_pro = _botao(t("vm.janela.baixar_pro"), "primario", self._baixar_pro)
        f.addWidget(self.b_base)
        f.addWidget(self.b_pro)
        v.addWidget(self.falta)

        # o pedido
        linha = QHBoxLayout()
        self.pedido = QPlainTextEdit()
        self.pedido.setPlaceholderText(t("vm.janela.pedido_ph"))
        self.pedido.setFixedHeight(64)
        self.pedido.setAccessibleName(t("vm.janela.pedido_ph"))
        linha.addWidget(self.pedido, 1)
        coluna = QVBoxLayout()
        self.b_comecar = _botao(t("vm.janela.comecar"), "primario", self._comecar)
        self.b_parar = _botao(t("vm.janela.parar"), "parar", self._parar)
        self.b_parar.hide()
        coluna.addWidget(self.b_comecar)
        coluna.addWidget(self.b_parar)
        self.c_internet = QCheckBox(t("vm.janela.internet"))
        self.c_internet.setChecked(True)
        coluna.addWidget(self.c_internet)
        linha.addLayout(coluna)
        v.addLayout(linha)

        # a tela da VM e os passos
        meio = QHBoxLayout()
        meio.setSpacing(14)
        self.tela = QLabel(t("vm.janela.sem_tela"))
        self.tela.setAlignment(Qt.AlignCenter)
        self.tela.setMinimumSize(640, 400)
        self.tela.setStyleSheet(f"background: {CORES['cartao']}; border: 1px solid {CORES['borda2']}; border-radius: 12px; "
                                f"color: {CORES['mudo']};")
        self.tela.setAccessibleName(t("vm.janela.tela"))
        meio.addWidget(self.tela, 3)
        lado = QVBoxLayout()
        lado.addWidget(rotulo(t("vm.janela.passos"), "kicker"))
        self.passos = QListWidget()
        lado.addWidget(self.passos, 2)
        lado.addWidget(rotulo(t("vm.janela.sites"), "kicker"))
        self.sites = QListWidget()
        lado.addWidget(self.sites, 1)
        meio.addLayout(lado, 2)
        v.addLayout(meio, 1)

        self.estado = rotulo("", "estado", quebra=True)
        v.addWidget(self.estado)

        # a quarentena
        self.saida = QFrame()
        self.saida.setProperty("papel", "linha-lista")
        s = QVBoxLayout(self.saida)
        s.setContentsMargins(16, 12, 16, 12)
        self.saida_titulo = rotulo("", "texto", quebra=True)
        s.addWidget(self.saida_titulo)
        self.caixas = QVBoxLayout()
        s.addLayout(self.caixas)
        botoes = QHBoxLayout()
        self.b_trazer = _botao(t("vm.janela.trazer", pasta=str(PASTA_LIBERADA).replace(str(PASTA_LIBERADA.home()), "~")),
                               "primario", self._trazer)
        self.b_descartar = _botao(t("vm.janela.descartar"), "chip",
                                  lambda: (self._descartar(), self.estado.setText(t("vm.janela.descartados"))))
        botoes.addWidget(self.b_trazer)
        botoes.addWidget(self.b_descartar)
        botoes.addStretch(1)
        s.addLayout(botoes)
        self.saida.hide()
        v.addWidget(self.saida)

    # -- o que falta ------------------------------------------------------------------------------------
    def showEvent(self, e):
        super().showEvent(e)
        if not self.ocupado:
            self.conferir()

    def conferir(self):
        """Mostra o que falta e liga o botão Começar só com tudo pronto. O modelo é conferido em segundo plano (pergunta ao motor)."""
        falta = self._falta()
        self.b_base.setVisible(not falta and not self._base().exists())
        self.b_pro.hide()
        if falta:
            self._mostrar_falta(t("vm.janela.falta", falta=", ".join(falta)))
            return
        if not self._base().exists():
            self._mostrar_falta(t("vm.janela.sem_base"))
            return
        self._mostrar_falta(t("vm.janela.conferindo"))

        def trabalho():
            try:
                nomes = [n.lower() for n in self._instalados(self.host())]
            except Exception:  # noqa: BLE001  (motor fora: diz que falta o modelo)
                nomes = []
            fio.no_principal(self._pro_conferido, agente.MODELO.lower() in nomes)
        threading.Thread(target=trabalho, daemon=True).start()

    def _pro_conferido(self, tem):
        if self.ocupado:
            return
        if tem:
            self.falta.hide()
            self.b_comecar.setEnabled(True)
        else:
            self.b_pro.show()
            self._mostrar_falta(t("vm.janela.sem_pro"))

    def _mostrar_falta(self, texto):
        self.falta_texto.setText(texto)
        self.falta.show()
        self.b_comecar.setEnabled(False)

    def _montar_base(self):
        self._em_trabalho(self.b_base, t("vm.janela.montando"))

        def trabalho():
            try:
                self._construir(ao_progresso=lambda feito, total: fio.no_principal(
                    self.falta_texto.setText, t("vm.janela.montando_pct", pct=int(100 * feito / total) if total else 0)),
                    avisar=lambda texto: fio.no_principal(self.falta_texto.setText, str(texto)))
                erro = None
            except Exception as e:  # noqa: BLE001
                erro = str(e)
            fio.no_principal(self._fim_trabalho, erro)
        threading.Thread(target=trabalho, daemon=True).start()

    def _baixar_pro(self):
        self._em_trabalho(self.b_pro, t("vm.janela.baixando"))

        def trabalho():
            def andamento(p):
                fio.no_principal(self.falta_texto.setText, t("cfg.baixando", pct=int(100 * p.fracao)))
            try:
                ok, erro = self._baixar(agente.MODELO, self.host(), ao_progredir=andamento)
            except Exception as e:  # noqa: BLE001
                ok, erro = False, str(e)
            fio.no_principal(self._fim_trabalho, None if ok else erro)
        threading.Thread(target=trabalho, daemon=True).start()

    def _em_trabalho(self, botao, texto):
        self.ocupado = True
        botao.setEnabled(False)
        self.falta_texto.setText(texto)

    def _fim_trabalho(self, erro):
        self.ocupado = False
        self.b_base.setEnabled(True)
        self.b_pro.setEnabled(True)
        self.conferir()
        if erro:
            self.falta_texto.setText(t("vm.janela.erro", erro=erro))

    # -- a missão -----------------------------------------------------------------------------------------
    def _comecar(self):
        pedido = self.pedido.toPlainText().strip()
        if not pedido or self.ocupado:
            return
        self._descartar()
        self.ocupado = True
        self.passos.clear()
        self.sites.clear()
        self.tela.setText(t("vm.janela.ligando"))
        self.estado.setText(t("vm.janela.ligando"))
        self.b_comecar.hide()
        self.b_parar.show()
        self.b_parar.setEnabled(True)
        self.pedido.setReadOnly(True)
        self.cancelar = threading.Event()
        host = self.host()
        decidir = agente.por_modelo(pedido, perguntar=lambda png, texto, sistema: agente.perguntar_modelo(png, texto, sistema, host=host))

        def decisor(tela, historico):
            try:
                with open(tela, "rb") as arq:       # a tela some com a VM: a janela guarda os bytes
                    fio.no_principal(self._mostrar_tela, arq.read())
            except OSError:
                pass
            return decidir(tela, historico)

        def trabalho():
            try:
                r = self._rodar(decisor, internet=self.c_internet.isChecked(), cancelar=self.cancelar,
                                ao_passo=lambda i, feito: fio.no_principal(self.passos.addItem, f"{i + 1}. {passo_legivel(feito)}"))
            except Exception as e:  # noqa: BLE001
                r = {"erro": str(e)}
            fio.no_principal(self._terminou, r)
        threading.Thread(target=trabalho, daemon=True).start()

    def _mostrar_tela(self, dados):
        imagem = QPixmap()
        if imagem.loadFromData(dados):
            self.tela.setPixmap(imagem.scaled(self.tela.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
            self.estado.setText(t("vm.janela.trabalhando"))

    def _parar(self):
        if self.cancelar is not None:
            self.cancelar.set()
            self.b_parar.setEnabled(False)
            self.estado.setText(t("vm.janela.parando"))

    def _terminou(self, r):
        self.ocupado = False
        self.cancelar = None
        self.b_parar.hide()
        self.b_comecar.show()
        self.pedido.setReadOnly(False)
        if "erro" in r:
            self.estado.setText(t("vm.janela.erro", erro=r["erro"]))
            return
        self.resultado = r
        motivo = t(MOTIVOS[r["motivo"]]) if r["motivo"] in MOTIVOS else r["motivo"]
        self.estado.setText(t("vm.janela.fim", motivo=motivo, segundos=r["segundos"], resultado=r["resultado"] or "-"))
        for acesso in r["acessos"]:
            self.sites.addItem(str(acesso))
        if r["arquivos"]:
            self.saida_titulo.setText(t("vm.janela.arquivos", n=len(r["arquivos"])))
            for a in r["arquivos"]:
                c = QCheckBox(f"{a['nome']}  ({a['tamanho']:,} B)".replace(",", "."))
                c.setChecked(False)          # nada vem marcado: a pessoa escolhe o que entra no PC
                c.arquivo = a
                self.caixas.addWidget(c)
            self.saida.show()

    # -- a quarentena -------------------------------------------------------------------------------------
    def _caixas(self):
        return [self.caixas.itemAt(i).widget() for i in range(self.caixas.count())]

    def _trazer(self):
        trazidos = []
        for c in self._caixas():
            if c.isChecked():
                trazidos.append(str(missao_vm.liberar(c.arquivo, PASTA_LIBERADA / c.arquivo["nome"])))
        self._descartar()
        self.estado.setText(t("vm.janela.trazidos", n=len(trazidos), pasta=str(PASTA_LIBERADA)) if trazidos
                            else t("vm.janela.descartados"))

    def _descartar(self):
        """Apaga a quarentena (o que não foi trazido some com a VM) e limpa a lista."""
        if self.resultado and self.resultado.get("quarentena"):
            shutil.rmtree(self.resultado["quarentena"], ignore_errors=True)
        self.resultado = None
        for c in self._caixas():
            c.setParent(None)
            c.deleteLater()
        self.saida.hide()

    def closeEvent(self, e):
        if self.cancelar is not None:
            self.cancelar.set()            # fechar a janela para a missão; a VM é apagada pelo executor
        if not self.ocupado:
            self._descartar()
        super().closeEvent(e)
