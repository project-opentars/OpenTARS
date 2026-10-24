"""Backend do Windows (F5 do PLANO_5.2.md), em ctypes e PowerShell, sem dependência nova. Testado no CI do Windows; o que
depende de uma pessoa na frente (seleção, notificação) só no notebook do Enzo.

O que ainda falta aqui (acessibilidade UIA, janelas, bandeja) levanta NaoSuportado com a fase, pelo __getattr__."""
import ctypes
import os
import subprocess
import time
from pathlib import Path

from . import NaoSuportado

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
CREATE_NO_WINDOW = 0x08000000
# Ctrl+C num console interrompe o programa que roda nele: lá a seleção não é lida
CONSOLES = ("ConsoleWindowClass", "CASCADIA_HOSTING_WINDOW_CLASS", "mintty", "VirtualConsoleClass", "PuTTY")
APP = Path(__file__).resolve().parent.parent


def _dlls():
    from ctypes import wintypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.GetClipboardData.restype = wintypes.HANDLE
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    return user32, kernel32


def abrir(alvo):
    os.startfile(str(alvo))  # noqa: S606  (só existe no Windows)


def teclas_de_colar():
    return ("ctrl", "v")


# ------------------------------------------------------------
# Área de transferência
# ------------------------------------------------------------
def _abrir_area(user32):
    for _ in range(20):          # outro programa pode estar com ela aberta por um instante
        if user32.OpenClipboard(None):
            return
        time.sleep(0.03)
    raise OSError("a área de transferência está em uso por outro programa")


def ler_area_de_transferencia():
    user32, kernel32 = _dlls()
    _abrir_area(user32)
    try:
        dado = user32.GetClipboardData(CF_UNICODETEXT)
        if not dado:
            return ""
        ponteiro = kernel32.GlobalLock(dado)
        try:
            return ctypes.wstring_at(ponteiro) if ponteiro else ""
        finally:
            kernel32.GlobalUnlock(dado)
    finally:
        user32.CloseClipboard()


def escrever_area_de_transferencia(texto):
    buffer = ctypes.create_unicode_buffer(str(texto))
    user32, kernel32 = _dlls()
    _abrir_area(user32)
    try:
        user32.EmptyClipboard()
        memoria = kernel32.GlobalAlloc(GMEM_MOVEABLE, ctypes.sizeof(buffer))
        ponteiro = kernel32.GlobalLock(memoria)
        ctypes.memmove(ponteiro, buffer, ctypes.sizeof(buffer))
        kernel32.GlobalUnlock(memoria)
        if not user32.SetClipboardData(CF_UNICODETEXT, memoria):
            raise OSError(f"SetClipboardData falhou ({ctypes.get_last_error()})")
    finally:
        user32.CloseClipboard()


# ------------------------------------------------------------
# Seleção: Ctrl+C simulado, devolvendo o que a pessoa tinha copiado
# ------------------------------------------------------------
def _classe_da_janela_ativa(user32):
    nome = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(user32.GetForegroundWindow(), nome, 256)
    return nome.value


def _esperar_soltar_teclas(user32, limite=1.0):
    """O atalho (Ctrl+Alt+R) ainda está apertado quando o openTARS acorda: Ctrl+C com o Alt no dedo vira Ctrl+Alt+C."""
    fim = time.time() + limite
    teclas = (0x10, 0x11, 0x12, 0x5B, 0x5C)          # Shift, Ctrl, Alt, Win esquerda e direita
    while time.time() < fim and any(user32.GetAsyncKeyState(k) & 0x8000 for k in teclas):
        time.sleep(0.02)


def ler_selecao():
    """shortcut: só texto volta para a área de transferência (imagem copiada antes se perde); trocar por salvar todos os
    formatos se alguém reclamar."""
    user32, _kernel32 = _dlls()
    if _classe_da_janela_ativa(user32) in CONSOLES:
        return ""
    _esperar_soltar_teclas(user32)
    try:
        antes = ler_area_de_transferencia()
    except OSError:
        antes = None
    numero = user32.GetClipboardSequenceNumber()
    for tecla, solta in ((0x11, 0), (0x43, 0), (0x43, 2), (0x11, 2)):    # Ctrl desce, C desce, C sobe, Ctrl sobe
        user32.keybd_event(tecla, 0, solta, 0)
    fim = time.time() + 0.6
    while time.time() < fim and user32.GetClipboardSequenceNumber() == numero:
        time.sleep(0.03)
    if user32.GetClipboardSequenceNumber() == numero:
        return ""                # nada copiado: não havia seleção (ou era campo de senha, que não deixa copiar)
    time.sleep(0.03)
    texto = ler_area_de_transferencia()
    if antes is not None:
        escrever_area_de_transferencia(antes)
    return texto


# ------------------------------------------------------------
# Lixeira, notificação, início automático
# ------------------------------------------------------------
def lixeira(caminho):
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT), ("pFrom", wintypes.LPCWSTR),
                    ("pTo", wintypes.LPCWSTR), ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", wintypes.BOOL),
                    ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", wintypes.LPCWSTR)]

    alvo = os.path.abspath(str(caminho))
    if not os.path.lexists(alvo):
        raise OSError(f"não existe: {alvo}")
    # FO_DELETE com FOF_ALLOWUNDO = Lixeira; sem perguntar, sem janela de progresso, sem caixa de erro
    operacao = SHFILEOPSTRUCTW(wFunc=3, pFrom=alvo + "\0", fFlags=0x40 | 0x10 | 0x4 | 0x400)
    codigo = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operacao))
    if codigo or operacao.fAnyOperationsAborted:
        raise OSError(f"não consegui mandar para a Lixeira (código {codigo})")


_TOAST = (
    "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null;"
    "$m = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent("
    "[Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
    "$t = $m.GetElementsByTagName('text');"
    "$t.Item(0).AppendChild($m.CreateTextNode($env:TARS_TITULO)) > $null;"
    "$t.Item(1).AppendChild($m.CreateTextNode($env:TARS_TEXTO)) > $null;"
    "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("
    "'{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe')"
    ".Show([Windows.UI.Notifications.ToastNotification]::new($m))"
)


def notificar(titulo, texto):
    # o texto vai por variável de ambiente: nada do que a pessoa (ou um site) escreveu vira comando do PowerShell
    subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-Command", _TOAST],
                     env=dict(os.environ, TARS_TITULO=str(titulo), TARS_TEXTO=str(texto)),
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW)


def arquivo_autostart(nome):
    base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    return base / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / f"{nome}.lnk"


def autostart(nome, titulo, comando, ligado):
    atalho = arquivo_autostart(nome)
    if not ligado:
        atalho.unlink(missing_ok=True)
        return False
    atalho.parent.mkdir(parents=True, exist_ok=True)
    roteiro = ("$a = (New-Object -ComObject WScript.Shell).CreateShortcut($env:TARS_LNK); $a.TargetPath = $env:TARS_ALVO;"
               "$a.Arguments = $env:TARS_ARGS; $a.WorkingDirectory = $env:TARS_PASTA; $a.Description = $env:TARS_TITULO;"
               "$a.WindowStyle = 7; $a.Save()")
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", roteiro], capture_output=True, timeout=60,
                   check=True, creationflags=CREATE_NO_WINDOW,
                   env=dict(os.environ, TARS_LNK=str(atalho), TARS_ALVO=str(comando[0]), TARS_TITULO=str(titulo),
                            TARS_ARGS=subprocess.list2cmdline([str(c) for c in comando[1:]]), TARS_PASTA=str(APP)))
    return atalho.exists()


def __getattr__(funcao):
    """O que ainda não existe aqui levanta NaoSuportado com a fase, em vez de falhar em silêncio."""
    if funcao.startswith("__"):
        raise AttributeError(funcao)

    def falta(*_args, **_kwargs):
        raise NaoSuportado(f"{funcao} ainda não existe no windows: entra na fase F5 da 5.2")
    return falta
