"""5.2, fase 1: a camada de plataforma (tars_plataforma). No Linux funciona como hoje; no Windows e no macOS as pastas são as do
sistema e o que ainda não existe levanta NaoSuportado dizendo a fase, em vez de falhar em silêncio."""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import tars_plataforma as p  # noqa: E402

assert p.sistema() in ("linux", "windows", "macos")
casa = Path(tempfile.mkdtemp())
os.environ.pop("XDG_CONFIG_HOME", None)
p.Path.home = staticmethod(lambda: casa)           # a casa de mentira vale para os três sistemas

for so, esperado in (("linux", ".config/opentars"), ("macos", "Library/Application Support/opentars"),
                     ("windows", "AppData/Roaming/opentars")):
    p.sistema = lambda so=so: so
    config = p.pastas()["config"]
    assert str(config).replace("\\", "/").endswith(esperado), (so, config)
    assert set(p.pastas()) == {"casa", "config", "dados", "cache"}
p.sistema = lambda: "linux"
os.environ["XDG_DATA_HOME"] = str(casa / "dados-xdg")
assert p.pastas()["dados"] == casa / "dados-xdg" / "opentars"
print("OK: pastas por sistema (XDG no Linux, Library no macOS, AppData no Windows)")

for so in ("macos",):          # o Windows já tem estas funções (F5): testadas no próprio Windows (test_plataforma_windows)
    p.sistema = lambda so=so: so
    for chamada in (lambda: p.lixeira("x"), lambda: p.notificar("a", "b"), p.ler_area_de_transferencia,
                    lambda: p.escrever_area_de_transferencia("x"), lambda: p.autostart("a", "A", ["a"], True)):
        try:
            chamada()
        except p.NaoSuportado as e:
            assert so in str(e) and "fase" in str(e), e
        else:
            raise AssertionError(f"{so}: deveria levantar NaoSuportado")
print("OK: no macOS o que falta levanta NaoSuportado com a fase")

p.sistema = lambda: "linux"
assert p.tecla_comando() == "ctrl"
p.sistema = lambda: "macos"
assert p.tecla_comando() == "command"
p.sistema = lambda: "linux"

chamados = []
original_run, original_which = subprocess.run, shutil.which
R = lambda **k: type("R", (), {"returncode": 0, "stderr": "", "stdout": "oi", **k})()  # noqa: E731
subprocess.run = lambda cmd, **k: (chamados.append(cmd), R())[1]
shutil.which = lambda nome: "/usr/bin/" + nome
p.lixeira("/tmp/x")
assert chamados[-1] == ["gio", "trash", "/tmp/x"]

os.environ.pop("WAYLAND_DISPLAY", None)
os.environ["XDG_SESSION_TYPE"] = "x11"
p.escrever_area_de_transferencia("olá")
assert chamados[-1] == ["xclip", "-selection", "clipboard"], chamados[-1]
os.environ["WAYLAND_DISPLAY"] = "wayland-0"
assert p.ler_area_de_transferencia() == "oi" and chamados[-1][0] == "wl-paste"


def falha_no_wl(cmd, **k):
    chamados.append(cmd)
    if cmd[0] == "wl-copy":
        raise subprocess.CalledProcessError(1, cmd)
    return R()


subprocess.run = falha_no_wl
p.escrever_area_de_transferencia("x")
assert [c[0] for c in chamados[-2:]] == ["wl-copy", "xclip"], chamados[-2:]
print("OK: área de transferência: wl-clipboard só no Wayland, e se ele falha tenta o xclip")

shutil.which = lambda nome: None
for chamada in (lambda: p.lixeira("x"), lambda: p.notificar("a", "b"), lambda: p.escrever_area_de_transferencia("x")):
    try:
        chamada()
    except p.NaoSuportado:
        pass
    else:
        raise AssertionError("sem o programa deveria levantar NaoSuportado")
subprocess.run, shutil.which = original_run, original_which
print("OK: sem gio, notify-send ou xclip levanta NaoSuportado")

os.environ["XDG_CONFIG_HOME"] = str(casa / "cfg")
assert p.autostart("opentars-teste", "openTARS Teste", ["opentars", "--x"], True)
arquivo = p.arquivo_autostart("opentars-teste")
assert arquivo == casa / "cfg" / "autostart" / "opentars-teste.desktop", arquivo
assert "Exec=opentars --x" in arquivo.read_text() and "Name=openTARS Teste" in arquivo.read_text()
assert not p.autostart("opentars-teste", "openTARS Teste", ["opentars"], False) and not arquivo.exists()
print("OK: início automático no Linux (~/.config/autostart)")
print("test_plataforma: TUDO OK.")
