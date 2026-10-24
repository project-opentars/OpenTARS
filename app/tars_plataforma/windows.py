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


_ARQUIVOS = []      # os arquivos da última cópia simulada (Explorer), lidos antes de devolver a área de transferência


def _arquivos_na_area(user32):
    """Os caminhos que o Explorer pôs na área de transferência (CF_HDROP), ou []."""
    from ctypes import wintypes
    shell32 = ctypes.WinDLL("shell32")
    shell32.DragQueryFileW.argtypes = [wintypes.HANDLE, wintypes.UINT, wintypes.LPWSTR, wintypes.UINT]
    shell32.DragQueryFileW.restype = wintypes.UINT
    if not user32.IsClipboardFormatAvailable(15) or not user32.OpenClipboard(None):     # 15 = CF_HDROP
        return []
    try:
        lista = user32.GetClipboardData(15)
        saida = []
        for i in range(shell32.DragQueryFileW(lista, 0xFFFFFFFF, None, 0) if lista else 0):
            tamanho = shell32.DragQueryFileW(lista, i, None, 0) + 1
            nome = ctypes.create_unicode_buffer(tamanho)
            shell32.DragQueryFileW(lista, i, nome, tamanho)
            saida.append(nome.value)
        return saida
    finally:
        user32.CloseClipboard()


def arquivos_selecionados():
    lista = list(_ARQUIVOS)
    _ARQUIVOS.clear()
    return lista


def ler_selecao():
    """shortcut: só texto volta para a área de transferência (imagem copiada antes se perde); trocar por salvar todos os
    formatos se alguém reclamar. Se o que estava selecionado eram arquivos (Explorer), eles ficam em _ARQUIVOS."""
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
    _ARQUIVOS[:] = _arquivos_na_area(user32)
    texto = "" if _ARQUIVOS else ler_area_de_transferencia()
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


# ------------------------------------------------------------
# Janelas (ctypes): as de aplicativo, como na barra de tarefas
# ------------------------------------------------------------
def _api_janelas():
    from ctypes import wintypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.EnumWindows.argtypes = [ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM), wintypes.LPARAM]
    user32.EnumChildWindows.argtypes = [wintypes.HWND, ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM),
                                        wintypes.LPARAM]
    for nome in ("GetWindowTextW", "GetClassNameW"):
        getattr(user32, nome).argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    for nome in ("IsWindowVisible", "IsIconic", "GetWindowTextLengthW", "SetForegroundWindow", "IsZoomed"):
        getattr(user32, nome).argtypes = [wintypes.HWND]
    user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetWindow.restype = wintypes.HWND
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.MoveWindow.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.BOOL]
    return user32, wintypes


def _camuflada(hwnd):
    """Apps da loja deixam janelas "camufladas" (existem, não aparecem): DWMWA_CLOAKED."""
    from ctypes import wintypes
    valor = wintypes.DWORD()
    try:
        ctypes.windll.dwmapi.DwmGetWindowAttribute(wintypes.HWND(hwnd), 14, ctypes.byref(valor), ctypes.sizeof(valor))
    except OSError:
        return False
    return bool(valor.value)


def _nome_do_processo(pid):
    try:
        import psutil
        return psutil.Process(pid).name().rsplit(".", 1)[0]
    except Exception:  # noqa: BLE001  (processo que acabou, sem permissão)
        return ""


def _processo_do_quadro(user32, wintypes, hwnd, pid):
    """Apps da loja (Calculadora, Configurações) moram dentro do ApplicationFrameHost: o app é o dono da janela filha."""
    outros = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def filho(h, _):
        dono = wintypes.DWORD()
        user32.GetWindowThreadProcessId(h, ctypes.byref(dono))
        if dono.value != pid:
            outros.append(dono.value)
            return False
        return True

    user32.EnumChildWindows(hwnd, filho, 0)
    return outros[0] if outros else pid


def janelas():
    user32, wintypes = _api_janelas()
    achadas = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cada(hwnd, _):
        if not user32.IsWindowVisible(hwnd) or user32.GetWindow(hwnd, 4) or _camuflada(hwnd):    # 4 = GW_OWNER
            return True
        if user32.GetWindowLongW(hwnd, -20) & 0x80:                                              # WS_EX_TOOLWINDOW
            return True
        tamanho = user32.GetWindowTextLengthW(hwnd)
        titulo = ctypes.create_unicode_buffer(tamanho + 1)
        user32.GetWindowTextW(hwnd, titulo, tamanho + 1)
        if not titulo.value:
            return True
        classe = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, classe, 256)
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if classe.value == "ApplicationFrameWindow":
            pid = wintypes.DWORD(_processo_do_quadro(user32, wintypes, hwnd, pid.value))
        caixa = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(caixa))
        achadas.append({"id": int(hwnd), "titulo": titulo.value, "classe": f"{classe.value} {_nome_do_processo(pid.value)}",
                        "pid": pid.value or None, "x": caixa.left, "y": caixa.top, "largura": caixa.right - caixa.left,
                        "altura": caixa.bottom - caixa.top, "minimizada": bool(user32.IsIconic(hwnd))})
        return True

    user32.EnumWindows(cada, 0)
    return list(reversed(achadas))          # o EnumWindows vai da frente para trás; o app espera da mais antiga à mais nova


def janela_ativa():
    user32, _ = _api_janelas()
    return int(user32.GetForegroundWindow() or 0) or None


def focar_janela(id_janela):
    user32, _ = _api_janelas()
    if user32.IsIconic(id_janela):
        user32.ShowWindow(id_janela, 9)                       # SW_RESTORE
    # o Windows só deixa trazer para a frente quem acabou de receber uma tecla: um Alt solto destrava (truque conhecido)
    user32.keybd_event(0x12, 0, 0, 0)
    user32.keybd_event(0x12, 0, 2, 0)
    if not user32.SetForegroundWindow(id_janela):
        raise OSError("o Windows não deixou trazer a janela para a frente")


def fechar_janela(id_janela):
    user32, _ = _api_janelas()
    user32.PostMessageW(id_janela, 0x0010, 0, 0)            # WM_CLOSE: como clicar no X (o app pode perguntar se salva)


def mover_janela(id_janela, x=None, y=None, largura=None, altura=None, maximizar=None):
    user32, wintypes = _api_janelas()
    if maximizar is not None:
        user32.ShowWindow(id_janela, 3 if maximizar else 9)   # SW_MAXIMIZE / SW_RESTORE
        return
    if user32.IsZoomed(id_janela):
        user32.ShowWindow(id_janela, 9)
    caixa = wintypes.RECT()
    user32.GetWindowRect(id_janela, ctypes.byref(caixa))
    user32.MoveWindow(id_janela, caixa.left if x is None else int(x), caixa.top if y is None else int(y),
                      (caixa.right - caixa.left) if largura is None else int(largura),
                      (caixa.bottom - caixa.top) if altura is None else int(altura), True)


def area_util():
    from ctypes import wintypes
    caixa = wintypes.RECT()
    ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(caixa), 0)    # SPI_GETWORKAREA: sem a barra de tarefas
    return caixa.left, caixa.top, caixa.right - caixa.left, caixa.bottom - caixa.top


# ------------------------------------------------------------
# Programas: o Menu Iniciar inteiro (inclusive os apps da loja, como a Calculadora), com o nome no idioma do Windows
# ------------------------------------------------------------
_PROGRAMAS = {"lista": None, "quando": 0.0}
SISTEMA = (("Calculator", ["calculadora", "calc"], "calc.exe"), ("Notepad", ["bloco de notas", "editor de texto",
           "text editor", "notepad"], "notepad.exe"), ("Paint", ["paint", "mspaint"], "mspaint.exe"),
           ("File Explorer", ["explorador de arquivos", "arquivos", "files", "explorer"], "explorer.exe"),
           ("Command Prompt", ["prompt de comando", "terminal", "cmd"], "cmd.exe"),
           ("Task Manager", ["gerenciador de tarefas", "taskmgr"], "taskmgr.exe"))


def programas():
    """[{'nome', 'outros_nomes', 'comando', 'id'}]: o Get-StartApps (5 min de cache) e os programas do próprio Windows."""
    if _PROGRAMAS["lista"] is not None and time.time() - _PROGRAMAS["quando"] < 300:
        return _PROGRAMAS["lista"]
    lista = []
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                            "[Console]::OutputEncoding = [Text.Encoding]::UTF8; Get-StartApps | ConvertTo-Json -Compress"],
                           capture_output=True, timeout=60, creationflags=CREATE_NO_WINDOW)
        import json
        dados = json.loads(r.stdout.decode("utf-8", "replace") or "[]")
        for item in dados if isinstance(dados, list) else [dados]:
            if item.get("Name") and item.get("AppID"):
                lista.append({"nome": item["Name"], "outros_nomes": [], "id": item["AppID"],
                              "comando": ["explorer.exe", "shell:AppsFolder\\" + item["AppID"]]})
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    pasta = Path(os.environ.get("SystemRoot") or "C:\\Windows") / "System32"
    for nome, outros, exe in SISTEMA:
        if (pasta / exe).exists() or exe == "explorer.exe":
            lista.append({"nome": nome, "outros_nomes": outros, "id": exe, "comando": [exe]})
    _PROGRAMAS.update(lista=lista, quando=time.time())
    return lista


def __getattr__(funcao):
    """O que ainda não existe aqui levanta NaoSuportado com a fase, em vez de falhar em silêncio."""
    if funcao.startswith("__"):
        raise AttributeError(funcao)

    def falta(*_args, **_kwargs):
        raise NaoSuportado(f"{funcao} ainda não existe no windows: entra na fase F5 da 5.2")
    return falta
