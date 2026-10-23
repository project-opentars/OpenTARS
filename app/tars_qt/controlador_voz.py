"""O controle da voz na janela: liga o Ouvinte (microfone + Whisper) do tars_voz.py aos sinais do Qt.

Três modos, como no mockup:
  segurar   -> "Segurar para falar": enquanto o botão está apertado, ouve; ao soltar, o que foi falado é o pedido;
  continua  -> "Conversa contínua": fica ouvindo, sem precisar dizer "TARS" a cada pedido;
  tars      -> "Palavra TARS": fica ouvindo e só age quando começa com "TARS" ("TARS, abre o Firefox").
Tudo local: o microfone e o Whisper rodam neste computador."""

import threading
import time

from PySide6.QtCore import QObject, Signal

from . import fio

MODOS = ("segurar", "continua", "tars")
CONVERSA_ABERTA_S = 10 ** 6       # "contínua": a conversa nunca fecha sozinha


class ControladorVoz(QObject):
    estado = Signal(str)          # carregando | ouvindo | chamado | conversa | transcrevendo | parado | erro:<motivo>
    pedido = Signal(str)          # o que a pessoa falou
    falando = Signal(bool)        # a IA está falando a resposta

    def __init__(self, nucleo):
        super().__init__()
        self.nucleo = nucleo
        self.modo = "segurar"
        self.ouvinte = None
        self.silenciado = False

    # -- o que existe ---------------------------------------------------------
    def faltando(self):
        """Lista do que falta instalar pra voz funcionar (vazia = pronta)."""
        try:
            return list(self.nucleo.o_que_falta_voz())
        except Exception:
            return ["voz"]

    def pronta(self):
        return not self.faltando()

    def ativo(self):
        return self.ouvinte is not None and self.ouvinte.ativo

    # -- ouvir ----------------------------------------------------------------
    def iniciar(self, modo=None):
        """Começa a ouvir. Devolve False se a voz não está pronta (falta instalar)."""
        if modo in MODOS:
            self.modo = modo
        if not self.pronta():
            return False
        self.parar()
        n = self.nucleo
        n.aplicar_preferencias_voz()
        self.silenciado = False
        modo_ouvinte = {"segurar": "uma_vez", "continua": "continua"}.get(self.modo, "ativacao")
        self.ouvinte = n.voz_lib.Ouvinte(
            self._ao_pedido, n.i18n.idioma_atual, modo=modo_ouvinte, ao_estado=self._ao_estado,
            falador=n.falador(), vocabulario=n.vocabulario_voz)
        self.ouvinte.iniciar()
        return True

    def soltar(self):
        """Soltou o botão do "segurar para falar"."""
        if self.ouvinte is not None and self.modo == "segurar":
            self.ouvinte.terminar_fala()

    def parar(self):
        if self.ouvinte is not None:
            self.ouvinte.parar()
            self.ouvinte = None
        try:
            self.nucleo.falador().parar()
        except Exception:
            pass

    def alternar_silencio(self):
        """Silenciar o microfone sem sair da tela de voz (e voltar a ouvir)."""
        if self.silenciado:
            self.silenciado = False
            return self.iniciar()
        self.silenciado = True
        if self.ouvinte is not None:
            self.ouvinte.parar()
            self.ouvinte = None
        fio.emitir(self.estado, "silenciado")
        return True

    def _ao_estado(self, estado):
        fio.emitir(self.estado, estado)

    def _ao_pedido(self, texto):
        fio.emitir(self.pedido, texto)

    # -- falar a resposta -----------------------------------------------------------
    def falar(self, texto, forcar=False):
        """Lê a resposta em voz alta (se a pessoa ligou "responder falando", ou se o pedido veio por voz).
        Depois, no modo contínuo/"TARS", reabre a conversa pra pessoa continuar sem dizer o nome."""
        n = self.nucleo
        if not texto or not self.pronta():
            return False

        def depois():
            fio.emitir(self.falando, False)
            if self.ouvinte is not None and self.modo == "tars":
                self.ouvinte.abrir_conversa(12.0)   # na "contínua" não precisa: todo trecho já é pedido

        def trabalho():
            fio.emitir(self.falando, True)
            try:
                falou = n.falar_resposta(texto, forcar=forcar, ao_terminar=depois)
            except Exception:
                falou = False
            if not falou:
                depois()

        threading.Thread(target=trabalho, daemon=True).start()
        return True
