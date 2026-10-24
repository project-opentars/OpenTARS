"""5.2: atalhos globais no macOS (RegisterEventHotKey do Carbon, o único jeito sem a permissão de Monitoramento de Entrada).
Como no Windows, quem escuta é o próprio openTARS: o atalho vale enquanto ele estiver aberto (ou no ícone da barra de menus).
O Carbon entrega o evento pelo laço de eventos do Cocoa, o mesmo que o Qt roda: o aviso chega na thread da janela."""
import ctypes

import tars_atalho

ByteCount = ctypes.c_ulong
MANIPULADOR = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)


class EventHotKeyID(ctypes.Structure):
    _fields_ = [("signature", ctypes.c_uint32), ("id", ctypes.c_uint32)]


class EventTypeSpec(ctypes.Structure):
    _fields_ = [("eventClass", ctypes.c_uint32), ("eventKind", ctypes.c_uint32)]


def _codigo(quatro_letras):
    return int.from_bytes(quatro_letras.encode("ascii"), "big")


ASSINATURA = _codigo("oTAR")
NAO_TRATADO = -9874                     # eventNotHandledErr


class AtalhosMac:
    def __init__(self, ao_atalho):
        self.ao_atalho, self.comandos, self.refs = ao_atalho, {}, {}
        c = self.carbon = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/Carbon.framework/Carbon")
        c.GetApplicationEventTarget.restype = ctypes.c_void_p
        c.InstallEventHandler.argtypes = [ctypes.c_void_p, MANIPULADOR, ctypes.c_uint32, ctypes.POINTER(EventTypeSpec),
                                          ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
        c.RegisterEventHotKey.argtypes = [ctypes.c_uint32, ctypes.c_uint32, EventHotKeyID, ctypes.c_void_p, ctypes.c_uint32,
                                          ctypes.POINTER(ctypes.c_void_p)]
        c.UnregisterEventHotKey.argtypes = [ctypes.c_void_p]
        c.GetEventParameter.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ByteCount,
                                        ctypes.c_void_p, ctypes.c_void_p]
        self._manipulador = MANIPULADOR(self._ao_evento)      # guardado: se o Python o recolher, o Carbon chama lixo
        tipo = EventTypeSpec(_codigo("keyb"), 5)               # kEventClassKeyboard, kEventHotKeyPressed
        c.InstallEventHandler(c.GetApplicationEventTarget(), self._manipulador, 1, ctypes.byref(tipo), None, None)

    def registrar(self, combinacao, comando):
        """True se o macOS aceitou (falha quando outro programa já usa a combinação)."""
        convertido = tars_atalho.para_macos(combinacao)
        if not convertido:
            return False
        ident = max(self.comandos, default=0) + 1
        ref = ctypes.c_void_p()
        erro = self.carbon.RegisterEventHotKey(convertido[1], convertido[0], EventHotKeyID(ASSINATURA, ident),
                                               self.carbon.GetApplicationEventTarget(), 0, ctypes.byref(ref))
        if erro:
            return False
        self.comandos[ident], self.refs[ident] = comando, ref
        return True

    def limpar(self):
        for ref in self.refs.values():
            self.carbon.UnregisterEventHotKey(ref)
        self.comandos.clear()
        self.refs.clear()

    def _ao_evento(self, _chamada, evento, _dados):
        qual = EventHotKeyID()
        erro = self.carbon.GetEventParameter(evento, _codigo("----"), _codigo("hkid"), None, ctypes.sizeof(qual), None,
                                             ctypes.byref(qual))
        if erro or qual.signature != ASSINATURA or qual.id not in self.comandos:
            return NAO_TRATADO
        self.ao_atalho(self.comandos[qual.id])
        return 0
