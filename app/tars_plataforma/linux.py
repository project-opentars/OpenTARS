"""Backend do Linux: o que o app já fazia (xdg-open, gio, notify-send, wl-clipboard/xclip/xsel, ~/.config/autostart)."""
import os
import re
import shutil
import subprocess
from pathlib import Path

from . import NaoSuportado

TIMEOUT = 10


def _wayland():
    return bool(os.environ.get("WAYLAND_DISPLAY")) or os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"


def abrir(alvo):
    subprocess.Popen(["xdg-open", str(alvo)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def lixeira(caminho):
    if not shutil.which("gio"):
        raise NaoSuportado("gio not found")
    resultado = subprocess.run(["gio", "trash", str(caminho)], capture_output=True, text=True, timeout=30)
    if resultado.returncode:
        raise OSError((resultado.stderr or "").strip()[:200] or f"gio trash falhou ({resultado.returncode})")


def notificar(titulo, texto):
    if not shutil.which("notify-send"):
        raise NaoSuportado("notify-send não está instalado")
    subprocess.Popen(["notify-send", "-a", "openTARS", "-i", "opentars", str(titulo), str(texto)],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def _comandos(leitura):
    # No Wayland, o wl-clipboard fala com o compositor; xclip/xsel só alcançam a área de transferência do XWayland.
    comandos = ([["xclip", "-selection", "clipboard", "-o"], ["xsel", "--clipboard", "--output"]] if leitura
                else [["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]])
    if _wayland():
        comandos.insert(0, ["wl-paste", "--no-newline"] if leitura else ["wl-copy"])
    disponiveis = [c for c in comandos if shutil.which(c[0])]
    if not disponiveis:
        raise NaoSuportado("nem wl-clipboard, nem xclip, nem xsel estão instalados")
    return disponiveis


def ler_area_de_transferencia():
    erro = None
    for comando in _comandos(leitura=True):
        try:
            return subprocess.run(comando, capture_output=True, text=True, timeout=TIMEOUT, check=True).stdout
        except (OSError, subprocess.SubprocessError) as e:
            erro = e
    raise OSError(f"não consegui ler a área de transferência: {erro}")


def escrever_area_de_transferencia(texto):
    erro = None
    for comando in _comandos(leitura=False):
        try:
            subprocess.run(comando, input=str(texto).encode("utf-8"), capture_output=True, timeout=TIMEOUT, check=True)
            return
        except (OSError, subprocess.SubprocessError) as e:
            erro = e
    raise OSError(f"não consegui escrever na área de transferência: {erro}")


def ler_selecao():
    """A seleção PRIMARY: o texto marcado agora, sem tecla simulada (campo de senha não entra nela)."""
    comandos = [["xclip", "-selection", "primary", "-o"], ["xsel", "--primary", "--output"]]
    if _wayland():
        comandos.insert(0, ["wl-paste", "--primary", "--no-newline"])
    disponiveis = [c for c in comandos if shutil.which(c[0])]
    if not disponiveis:
        raise NaoSuportado("nem wl-clipboard, nem xclip, nem xsel estão instalados")
    for comando in disponiveis:
        try:
            r = subprocess.run(comando, capture_output=True, text=True, timeout=TIMEOUT)
        except (OSError, subprocess.SubprocessError):
            continue
        if r.returncode == 0:
            return r.stdout
    return ""


_TERMINAIS = re.compile(r"term|konsole|kitty|alacritty|tilix|kgx|console|wezterm|foot|ptyxis|guake|terminator|xterm", re.I)


def _classe_da_janela_ativa():
    """WM_CLASS da janela com o foco (só X11; no Wayland o compositor não conta)."""
    try:
        from Xlib import X, display
        tela = display.Display()
        try:
            raiz = tela.screen().root
            ativa = raiz.get_full_property(tela.intern_atom("_NET_ACTIVE_WINDOW"), X.AnyPropertyType)
            if not ativa or not ativa.value:
                return ""
            return " ".join(tela.create_resource_object("window", ativa.value[0]).get_wm_class() or ())
        finally:
            tela.close()
    except Exception:  # noqa: BLE001  (sem X, sem python-xlib, janela que sumiu)
        return ""


def teclas_de_colar():
    return ("ctrl", "shift", "v") if _TERMINAIS.search(_classe_da_janela_ativa()) else ("ctrl", "v")


def arquivo_autostart(nome):
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "autostart" / f"{nome}.desktop"


def autostart(nome, titulo, comando, ligado):
    atalho = arquivo_autostart(nome)
    if ligado:
        atalho.parent.mkdir(parents=True, exist_ok=True)
        atalho.write_text(f"[Desktop Entry]\nType=Application\nName={titulo}\nExec={' '.join(comando)}\nNoDisplay=true\n"
                          "X-GNOME-Autostart-enabled=true\n", encoding="utf-8")
    else:
        atalho.unlink(missing_ok=True)
    return atalho.exists()
