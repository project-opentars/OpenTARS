"""Backend do macOS (F6 do PLANO_5.2.md). Programas que já vêm no Mac (pbcopy, pbpaste, osascript, open, launchctl) e o
pyobjc que o pyautogui já instala (Quartz, AppKit, Foundation). Testado no CI do macOS no que não pede permissão; a
seleção, os cliques e os títulos das janelas pedem Acessibilidade e Gravação de Tela (Ajustes > Privacidade e Segurança)."""
import os
import plistlib
import subprocess
import time
from pathlib import Path

from . import NaoSuportado

APP = Path(__file__).resolve().parent.parent


def abrir(alvo):
    subprocess.Popen(["open", str(alvo)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def teclas_de_colar():
    return ("command", "v")


# ------------------------------------------------------------
# Área de transferência e seleção
# ------------------------------------------------------------
def ler_area_de_transferencia():
    return subprocess.run(["pbpaste"], capture_output=True, timeout=10, check=True).stdout.decode("utf-8", "replace")


def escrever_area_de_transferencia(texto):
    subprocess.run(["pbcopy"], input=str(texto).encode("utf-8"), capture_output=True, timeout=10, check=True)


def _mudancas():
    from AppKit import NSPasteboard
    return NSPasteboard.generalPasteboard().changeCount()


def _apertar_cmd(tecla):
    """Cmd+tecla pelo Quartz (precisa da permissão de Acessibilidade)."""
    import Quartz
    codigos = {"c": 8, "v": 9}
    for desce in (True, False):
        evento = Quartz.CGEventCreateKeyboardEvent(None, codigos[tecla], desce)
        Quartz.CGEventSetFlags(evento, Quartz.kCGEventFlagMaskCommand)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, evento)


def _esperar_soltar_teclas(limite=1.0):
    """O atalho ainda está apertado quando o openTARS acorda: Cmd+C com o Ctrl e o Option no dedo não copia."""
    import Quartz
    fim = time.time() + limite
    while time.time() < fim and Quartz.CGEventSourceFlagsState(Quartz.kCGEventSourceStateHIDSystemState) & (
            Quartz.kCGEventFlagMaskControl | Quartz.kCGEventFlagMaskAlternate | Quartz.kCGEventFlagMaskShift
            | Quartz.kCGEventFlagMaskCommand):
        time.sleep(0.02)


_ARQUIVOS = []      # os arquivos da última cópia simulada (Finder), lidos antes de devolver a área de transferência


def _arquivos_na_area():
    from AppKit import NSPasteboard, NSPasteboardURLReadingFileURLsOnlyKey, NSURL
    urls = NSPasteboard.generalPasteboard().readObjectsForClasses_options_(
        [NSURL], {NSPasteboardURLReadingFileURLsOnlyKey: True}) or []
    return [str(u.path()) for u in urls]


def arquivos_selecionados():
    lista = list(_ARQUIVOS)
    _ARQUIVOS.clear()
    return lista


def ler_selecao():
    """Cmd+C simulado e a área de transferência devolvida. shortcut: só texto volta (imagem copiada antes se perde).
    Se o que estava selecionado eram arquivos (Finder, que também põe os nomes como texto), eles ficam em _ARQUIVOS."""
    _esperar_soltar_teclas()
    try:
        antes = ler_area_de_transferencia()
    except (OSError, subprocess.SubprocessError):
        antes = None
    numero = _mudancas()
    _apertar_cmd("c")
    fim = time.time() + 0.6
    while time.time() < fim and _mudancas() == numero:
        time.sleep(0.03)
    if _mudancas() == numero:
        return ""                 # nada copiado: não havia seleção, era campo de senha ou falta a permissão
    _ARQUIVOS[:] = _arquivos_na_area()
    texto = "" if _ARQUIVOS else ler_area_de_transferencia()
    if antes is not None:
        escrever_area_de_transferencia(antes)
    return texto


# ------------------------------------------------------------
# Lixeira, notificação, início automático
# ------------------------------------------------------------
def lixeira(caminho):
    from Foundation import NSFileManager, NSURL
    alvo = os.path.abspath(str(caminho))
    if not os.path.lexists(alvo):
        raise OSError(f"não existe: {alvo}")
    ok, _destino, erro = NSFileManager.defaultManager().trashItemAtURL_resultingItemURL_error_(
        NSURL.fileURLWithPath_(alvo), None, None)
    if not ok:
        raise OSError(f"não consegui mandar para a Lixeira: {erro}")


def notificar(titulo, texto):
    # título e texto vão como argumentos do script, nunca dentro dele: nada do que foi escrito vira AppleScript
    roteiro = ["-e", "on run argv", "-e", "display notification (item 2 of argv) with title (item 1 of argv)", "-e", "end run"]
    subprocess.Popen(["osascript", *roteiro, str(titulo), str(texto)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def arquivo_autostart(nome):
    return Path.home() / "Library" / "LaunchAgents" / f"{nome}.plist"


def autostart(nome, titulo, comando, ligado):
    arquivo = arquivo_autostart(nome)
    if not ligado:
        subprocess.run(["launchctl", "unload", str(arquivo)], capture_output=True, timeout=30)
        arquivo.unlink(missing_ok=True)
        return False
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_bytes(plistlib.dumps({"Label": nome, "ProgramArguments": [str(c) for c in comando], "RunAtLoad": True,
                                        "WorkingDirectory": str(APP), "ProcessType": "Interactive"}))
    return arquivo.exists()


# ------------------------------------------------------------
# Permissões (F3.5): Acessibilidade (clicar, digitar, colar, ler a seleção) e Gravação de Tela (ver a tela). O atalho pelo
# Carbon não pede Monitoramento de Entrada, e o microfone o próprio macOS pede quando a voz liga.
# ------------------------------------------------------------
AJUSTES = {"acessibilidade": "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
           "tela": "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"}


def permissoes():
    """{"acessibilidade": concedida?, "tela": concedida?}"""
    import ApplicationServices as AX
    import Quartz
    return {"acessibilidade": bool(AX.AXIsProcessTrusted()), "tela": bool(Quartz.CGPreflightScreenCaptureAccess())}


def pedir_permissao(qual):
    """Põe o openTARS na lista do macOS (sem isso ele nem aparece em Ajustes) e abre a página certa dos Ajustes."""
    if qual == "acessibilidade":
        import ApplicationServices as AX
        AX.AXIsProcessTrustedWithOptions({AX.kAXTrustedCheckOptionPrompt: True})
    else:
        import Quartz
        Quartz.CGRequestScreenCaptureAccess()
    abrir(AJUSTES[qual])


# ------------------------------------------------------------
# Janelas (Quartz; os títulos pedem a permissão de Gravação de Tela, sem ela fica o nome do app)
# ------------------------------------------------------------
def janelas():
    import Quartz
    opcoes = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
    saida = []
    for info in Quartz.CGWindowListCopyWindowInfo(opcoes, Quartz.kCGNullWindowID) or []:
        if info.get("kCGWindowLayer", 0) != 0:
            continue                      # barra de menus, Dock, menus abertos
        dono = info.get("kCGWindowOwnerName") or ""
        caixa = info.get("kCGWindowBounds") or {}
        saida.append({"id": int(info["kCGWindowNumber"]), "titulo": info.get("kCGWindowName") or dono, "classe": dono,
                      "pid": int(info.get("kCGWindowOwnerPID") or 0) or None, "x": int(caixa.get("X", 0)),
                      "y": int(caixa.get("Y", 0)), "largura": int(caixa.get("Width", 0)),
                      "altura": int(caixa.get("Height", 0)), "minimizada": False})
    return list(reversed(saida))          # o Quartz lista da frente para trás; o app espera da mais antiga à mais nova


def janela_ativa():
    from AppKit import NSWorkspace
    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    pid = app.processIdentifier() if app else None
    da_frente = [j for j in reversed(janelas()) if j["pid"] == pid]
    return da_frente[0]["id"] if da_frente else None


def _pid_da_janela(id_janela):
    return next((j["pid"] for j in janelas() if j["id"] == int(id_janela)), None)


def focar_janela(id_janela):
    from AppKit import NSApplicationActivateIgnoringOtherApps, NSRunningApplication
    pid = _pid_da_janela(id_janela)
    app = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid) if pid else None
    if not app:
        raise OSError("janela não encontrada")
    app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)


def _janela_ax(id_janela):
    """A janela pela acessibilidade (AX) do app dono, casando pela posição (o AX não sabe o número da janela do Quartz)."""
    import ApplicationServices as AX
    alvo = next((j for j in janelas() if j["id"] == int(id_janela)), None)
    if not alvo:
        raise OSError("janela não encontrada")
    app = AX.AXUIElementCreateApplication(alvo["pid"])
    erro, lista = AX.AXUIElementCopyAttributeValue(app, "AXWindows", None)
    for janela in lista or []:
        erro, posicao = AX.AXUIElementCopyAttributeValue(janela, "AXPosition", None)
        if erro == 0:
            _ok, ponto = AX.AXValueGetValue(posicao, AX.kAXValueCGPointType, None)
            if abs(ponto.x - alvo["x"]) < 4 and abs(ponto.y - alvo["y"]) < 4:
                return janela
    if lista:
        return lista[0]
    raise OSError("sem acesso à janela: libere o openTARS em Acessibilidade (Ajustes > Privacidade e Segurança)")


def fechar_janela(id_janela):
    import ApplicationServices as AX
    janela = _janela_ax(id_janela)
    erro, botao = AX.AXUIElementCopyAttributeValue(janela, "AXCloseButton", None)
    if erro or AX.AXUIElementPerformAction(botao, "AXPress"):
        raise OSError("não consegui fechar a janela")


def mover_janela(id_janela, x=None, y=None, largura=None, altura=None, maximizar=None):
    import ApplicationServices as AX
    import Quartz
    janela = _janela_ax(id_janela)
    if maximizar:
        caixa = Quartz.CGDisplayBounds(Quartz.CGMainDisplayID())
        x, y, largura, altura = 0, 25, caixa.size.width, caixa.size.height - 25     # 25: a barra de menus
    if x is not None and y is not None:
        AX.AXUIElementSetAttributeValue(janela, "AXPosition", AX.AXValueCreate(AX.kAXValueCGPointType, Quartz.CGPoint(x, y)))
    if largura and altura:
        AX.AXUIElementSetAttributeValue(janela, "AXSize",
                                        AX.AXValueCreate(AX.kAXValueCGSizeType, Quartz.CGSize(largura, altura)))


def area_util():
    import Quartz
    caixa = Quartz.CGDisplayBounds(Quartz.CGMainDisplayID())
    return 0, 25, int(caixa.size.width), int(caixa.size.height) - 25


# ------------------------------------------------------------
# Programas: os .app das pastas de aplicativos, com o nome que o Finder mostra (traduzido)
# ------------------------------------------------------------
PASTAS_APPS = ("/Applications", "/Applications/Utilities", "/System/Applications", "/System/Applications/Utilities",
               str(Path.home() / "Applications"))


def programas():
    """[{'nome', 'outros_nomes', 'comando', 'id'}] dos apps instalados."""
    try:
        from Foundation import NSFileManager
        exibido = NSFileManager.defaultManager().displayNameAtPath_
    except ImportError:
        exibido = None
    saida, vistos = [], set()
    for pasta in PASTAS_APPS:
        for app in sorted(Path(pasta).glob("*.app")) if Path(pasta).is_dir() else []:
            if app.stem in vistos:
                continue
            vistos.add(app.stem)
            nome = str(exibido(str(app))) if exibido else app.stem
            nome = nome[:-4] if nome.endswith(".app") else nome
            saida.append({"nome": nome, "outros_nomes": [app.stem] if nome != app.stem else [],
                          "comando": ["open", "-a", str(app)], "id": app.stem})
    return saida


def __getattr__(funcao):
    """O que ainda não existe aqui levanta NaoSuportado com a fase, em vez de falhar em silêncio."""
    if funcao.startswith("__"):
        raise AttributeError(funcao)

    def falta(*_args, **_kwargs):
        raise NaoSuportado(f"{funcao} ainda não existe no macos: entra na fase F6 da 5.2")
    return falta
