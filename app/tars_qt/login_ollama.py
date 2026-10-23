"""5.1: entrar na nuvem com a conta do Ollama, sem chave de API (Configurações > Nuvem e o primeiro uso).

O botão roda `ollama signin`, abre a página de login no navegador e fica conferindo (POST /api/me) até a conta aparecer.
Depois oferece baixar um modelo da nuvem (só o manifesto). Nada liga sozinho: o modelo da nuvem só é usado quando a
pessoa o escolhe pelo nome no seletor de modelo, e o rodapé da conversa avisa que a resposta vem da nuvem."""

import threading
import time

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

import tars_primeiro_uso as pu
from tars_i18n import t

from . import fio
from .tema import rotulo

ESPERA_LOGIN_SEG = 300


def _botao(texto, papel, ao_clicar):
    b = QPushButton(texto)
    b.setProperty("papel", papel)
    b.clicked.connect(ao_clicar)
    return b


class LoginOllama(QWidget):
    """Estado da conta + Entrar/Sair + baixar o modelo da nuvem. host: função que devolve o endereço do Ollama."""

    def __init__(self, host, abrir_link=None, ao_mudar=None):
        super().__init__()
        self.host, self.ao_mudar = host, ao_mudar
        self.abrir_link = abrir_link or self._abrir_no_navegador
        self._esperando_ate = 0
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        self.estado = rotulo(t("nuvem.login.conferindo"), "texto", quebra=True)
        v.addWidget(self.estado)
        linha = QHBoxLayout()
        linha.setSpacing(10)
        self.b_entrar = _botao(t("nuvem.login.entrar"), "primario", self.entrar)
        self.b_sair = _botao(t("nuvem.login.sair"), "chip", self.sair)
        self.b_modelo = _botao(t("nuvem.login.baixar", modelo=pu.MODELO_NUVEM_PADRAO), "chip", self.baixar)
        for b in (self.b_entrar, self.b_sair, self.b_modelo):
            b.hide()
            linha.addWidget(b)
        linha.addStretch(1)
        v.addLayout(linha)
        self.nota = rotulo(t("nuvem.login.nota"), "nota", quebra=True)
        v.addWidget(self.nota)
        self._relogio = QTimer(self)
        self._relogio.timeout.connect(self._conferir_login)

    @staticmethod
    def _abrir_no_navegador(url):
        import webbrowser
        webbrowser.open(url)

    def _fundo(self, trabalho, pronto):
        def corpo():
            try:
                r = trabalho()
            except Exception as e:      # noqa: BLE001
                r = e
            fio.no_principal(lambda: pronto(r))
        threading.Thread(target=corpo, daemon=True).start()

    def atualizar(self):
        host = self.host()

        def trabalho():
            return pu.conta_ollama(host), pu.modelos_de_nuvem(pu.modelos_instalados(host))

        def pronto(r):
            conta, nuvem = r if not isinstance(r, Exception) else (None, [])
            self.mostrar(conta, nuvem)
        self._fundo(trabalho, pronto)

    def mostrar(self, conta, nuvem):
        if conta:
            texto = t("nuvem.login.conectado", conta=conta)
            texto += " " + (t("nuvem.login.modelos", lista=", ".join(nuvem)) if nuvem else t("nuvem.login.sem_modelo"))
            self.estado.setText(texto)
        elif self._esperando_ate:
            self.estado.setText(t("nuvem.login.esperando"))
        else:
            self.estado.setText(t("nuvem.login.desconectado"))
        self.b_entrar.setVisible(not conta)
        self.b_entrar.setEnabled(not self._esperando_ate)
        self.b_sair.setVisible(bool(conta))
        self.b_modelo.setVisible(bool(conta) and not nuvem)

    def entrar(self):
        self.b_entrar.setEnabled(False)

        def pronto(r):
            ja, url, erro = r if not isinstance(r, Exception) else (None, None, str(r))
            if ja:
                self.atualizar()
                return
            if url:
                self.abrir_link(url)
                self._esperando_ate = time.monotonic() + ESPERA_LOGIN_SEG
                self.estado.setText(t("nuvem.login.esperando"))
                self._relogio.start(3000)
            else:
                self.estado.setText(t("nuvem.login.erro", erro=erro or "?"))
                self.b_entrar.setEnabled(True)
        self._fundo(pu.iniciar_login, pronto)

    def _conferir_login(self):
        if time.monotonic() > self._esperando_ate:
            self._relogio.stop()
            self._esperando_ate = 0
            self.estado.setText(t("nuvem.login.desistiu"))
            self.b_entrar.setEnabled(True)
            return
        host = self.host()

        def pronto(conta):
            if conta and not isinstance(conta, Exception):
                self._relogio.stop()
                self._esperando_ate = 0
                self.atualizar()
                if self.ao_mudar:
                    self.ao_mudar()
        self._fundo(lambda: pu.conta_ollama(host), pronto)

    def sair(self):
        def pronto(_r):
            self.atualizar()
            if self.ao_mudar:
                self.ao_mudar()
        self._fundo(pu.sair_da_conta, pronto)

    def baixar(self):
        host = self.host()
        self.b_modelo.setEnabled(False)

        def trabalho():
            ok, erro = pu.baixar_modelo(pu.MODELO_NUVEM_PADRAO, host)
            if not ok:
                return False, erro
            ok, texto, _seg = pu.testar_gargantua(host, pu.MODELO_NUVEM_PADRAO)
            return ok, texto

        def pronto(r):
            ok, detalhe = r if not isinstance(r, Exception) else (False, str(r))
            self.b_modelo.setEnabled(True)
            self.atualizar()
            self.nota.setText(t("nuvem.login.pronto", modelo=pu.MODELO_NUVEM_PADRAO) if ok
                              else t("nuvem.login.erro", erro=detalhe))
            if ok and self.ao_mudar:
                self.ao_mudar()
        self._fundo(trabalho, pronto)
