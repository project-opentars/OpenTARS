"""5.2: atalhos globais no Windows (RegisterHotKey). No Linux quem escuta a tecla é o ambiente de trabalho (tars_atalho);
no Windows é a própria janela do openTARS, então o atalho vale enquanto ela estiver aberta (ou no ícone perto do relógio)."""
import ctypes
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter

import tars_atalho

WM_HOTKEY = 0x0312
MOD_NOREPEAT = 0x4000


class AtalhosWindows(QAbstractNativeEventFilter):
    def __init__(self, ao_atalho):
        super().__init__()
        self.ao_atalho, self.comandos = ao_atalho, {}
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)

    def registrar(self, combinacao, comando):
        """True se o Windows aceitou (falha quando outro programa já usa a combinação)."""
        convertido = tars_atalho.para_windows(combinacao)
        if not convertido:
            return False
        ident = max(self.comandos, default=0) + 1
        if not self.user32.RegisterHotKey(None, ident, convertido[0] | MOD_NOREPEAT, convertido[1]):
            return False
        self.comandos[ident] = comando
        return True

    def limpar(self):
        for ident in list(self.comandos):
            self.user32.UnregisterHotKey(None, ident)
        self.comandos.clear()

    def nativeEventFilter(self, tipo, mensagem):
        if bytes(tipo) == b"windows_generic_MSG":
            msg = wintypes.MSG.from_address(int(mensagem))
            if msg.message == WM_HOTKEY and msg.wParam in self.comandos:
                self.ao_atalho(self.comandos[msg.wParam])
                return True, 0
        return False, 0
