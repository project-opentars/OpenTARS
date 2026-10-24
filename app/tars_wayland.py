"""openTARS 3.0: mouse e teclado numa sessão Wayland (experimental).

No Wayland, o pyautogui só alcança janelas XWayland. O ydotool (1.0 ou
mais novo, com o serviço ydotoold rodando) injeta eventos pelo kernel
(uinput) e funciona em qualquer janela. Esta classe imita a parte do
pyautogui que o openTARS usa, por cima do ydotool.

Limitação conhecida: o ydotool não sabe onde o ponteiro está; o
"absoluto" dele é ir pro canto e andar dali, e a aceleração do mouse do
sistema pode distorcer. Com a aceleração em "plana" (GNOME: Configurações
> Mouse > Aceleração desligada) fica preciso. Por isso a conferência de
clique (a tela mudou?) do tars_mouse continua valendo aqui."""

import os
import shutil
import subprocess
import time
from pathlib import Path

# Códigos de tecla do kernel (linux/input-event-codes.h)
TECLAS = {
    "esc": 1, "escape": 1, "1": 2, "2": 3, "3": 4, "4": 5, "5": 6, "6": 7, "7": 8, "8": 9, "9": 10, "0": 11,
    "minus": 12, "-": 12, "equal": 13, "=": 13, "backspace": 14, "tab": 15,
    "q": 16, "w": 17, "e": 18, "r": 19, "t": 20, "y": 21, "u": 22, "i": 23, "o": 24, "p": 25,
    "enter": 28, "return": 28, "ctrl": 29, "control": 29, "ctrlleft": 29,
    "a": 30, "s": 31, "d": 32, "f": 33, "g": 34, "h": 35, "j": 36, "k": 37, "l": 38,
    "shift": 42, "shiftleft": 42, "z": 44, "x": 45, "c": 46, "v": 47, "b": 48, "n": 49, "m": 50,
    "comma": 51, ",": 51, "period": 52, ".": 52, "slash": 53, "/": 53, "shiftright": 54,
    "alt": 56, "altleft": 56, "space": 57, " ": 57, "capslock": 58,
    "f1": 59, "f2": 60, "f3": 61, "f4": 62, "f5": 63, "f6": 64, "f7": 65, "f8": 66, "f9": 67, "f10": 68,
    "f11": 87, "f12": 88, "ctrlright": 97, "altright": 100, "altgr": 100,
    "home": 102, "up": 103, "pageup": 104, "pgup": 104, "left": 105, "right": 106, "end": 107,
    "down": 108, "pagedown": 109, "pgdn": 109, "insert": 110, "delete": 111, "del": 111,
    "win": 125, "super": 125, "meta": 125, "command": 125, "winleft": 125, "menu": 139,
}
BOTOES = {"left": 0x00, "right": 0x01, "middle": 0x02}
APERTAR, SOLTAR, CLICAR = 0x40, 0x80, 0xC0


def _socket():
    for candidato in (os.environ.get("YDOTOOL_SOCKET"), f"/run/user/{os.getuid()}/.ydotool_socket",
                      "/tmp/.ydotool_socket"):
        if candidato and Path(candidato).exists():
            return candidato
    return None


def motivo_indisponivel(executar=subprocess.run):
    """None se o ydotool 1.x estiver pronto; senão, o motivo (em inglês, pra IA/log)."""
    if not shutil.which("ydotool"):
        import tars_plataforma
        return tars_plataforma.dica_instalar("ydotool is not installed (sudo apt install ydotool)")
    try:
        ajuda = executar(["ydotool", "mousemove", "--help"], capture_output=True, text=True, timeout=5)
        texto = (ajuda.stdout or "") + (ajuda.stderr or "")
    except Exception as e:
        return f"ydotool failed: {e}"
    if "absolute" not in texto:
        return "ydotool is too old (needs 1.0+, with 'mousemove --absolute')"
    if not _socket():
        return "the ydotoold service is not running (systemctl --user enable --now ydotool, or run ydotoold)"
    return None


class PyautoguiYdotool:
    """O pedaço do pyautogui que o openTARS usa, feito com ydotool."""

    PAUSE = 0.01
    FAILSAFE = False

    def __init__(self, tamanho, executar=None):
        self._tamanho = tuple(tamanho)
        self._pos = (self._tamanho[0] // 2, self._tamanho[1] // 2)
        self._segurando = False   # botão apertado (arrasto): só movimentos relativos
        self._executar = executar or (lambda args: subprocess.run(["ydotool", *args], check=True,
                                                                  stdout=subprocess.DEVNULL,
                                                                  stderr=subprocess.DEVNULL,
                                                                  timeout=10 + 0.06 * sum(len(a) for a in args)))

    def _rodar(self, *args):
        self._executar([str(a) for a in args])

    # --- mouse ---
    def size(self):
        return self._tamanho

    def position(self):
        return self._pos  # o ydotool não lê o ponteiro: é a última posição que o openTARS mandou

    def moveTo(self, x=None, y=None, duration=0, **_k):
        if x is None or y is None:
            return
        x, y = int(x), int(y)
        if self._segurando:
            # O "absoluto" do ydotool passa pelo canto da tela: com o botão
            # apertado isso arrastaria o item até lá (e dispara o canto
            # ativo do GNOME). No meio do arrasto, anda a diferença.
            self._rodar("mousemove", "-x", x - self._pos[0], "-y", y - self._pos[1])
        else:
            self._rodar("mousemove", "--absolute", "-x", x, "-y", y)
        self._pos = (x, y)
        if duration:
            time.sleep(min(float(duration), 0.2))

    def _botao(self, botao, acao, x=None, y=None):
        if x is not None and y is not None:
            self.moveTo(x, y)
        self._rodar("click", hex(BOTOES.get(botao, 0) | acao))

    def click(self, x=None, y=None, button="left", clicks=1, **_k):
        for _ in range(max(1, int(clicks))):
            self._botao(button, CLICAR, x, y)
            x = y = None

    def doubleClick(self, x=None, y=None, button="left", **_k):
        self.click(x, y, button, clicks=2)

    def mouseDown(self, x=None, y=None, button="left", **_k):
        self._botao(button, APERTAR, x, y)
        self._segurando = True

    def mouseUp(self, x=None, y=None, button="left", **_k):
        if x is not None and y is not None:
            self.moveTo(x, y)
        self._rodar("click", hex(BOTOES.get(button, 0) | SOLTAR))
        self._segurando = False

    def scroll(self, quantidade, x=None, y=None, **_k):
        if x is not None and y is not None:
            self.moveTo(x, y)
        # pyautogui: positivo = pra cima; ydotool: wheel positivo = pra baixo
        self._rodar("mousemove", "--wheel", "-x", 0, "-y", -int(quantidade))

    # --- teclado ---
    def _codigo(self, tecla):
        codigo = TECLAS.get(str(tecla).lower())
        if codigo is None:
            raise ValueError(f"unknown key for ydotool: {tecla}")
        return codigo

    def keyDown(self, tecla):
        self._rodar("key", f"{self._codigo(tecla)}:1")

    def keyUp(self, tecla):
        self._rodar("key", f"{self._codigo(tecla)}:0")

    def press(self, teclas, presses=1, **_k):
        for _ in range(max(1, int(presses))):
            for tecla in ([teclas] if isinstance(teclas, str) else teclas):
                c = self._codigo(tecla)
                self._rodar("key", f"{c}:1", f"{c}:0")

    def hotkey(self, *teclas, **_k):
        codigos = [self._codigo(t) for t in teclas]
        self._rodar("key", *[f"{c}:1" for c in codigos], *[f"{c}:0" for c in reversed(codigos)])

    def write(self, texto, interval=0, **_k):
        self._rodar("type", "--", str(texto))

    typewrite = write

    def screenshot(self, *a, **k):
        raise RuntimeError("use the openTARS screen capture (gnome-screenshot/spectacle/grim) on Wayland")
