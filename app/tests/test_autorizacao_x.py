"""Wayland/GNOME: o cookie do XWayland em /run/user/<uid> é achado; sem ele, /dev/null (o comportamento antigo)."""
import os
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
pasta = Path(tempfile.mkdtemp(prefix="run-user-"))
os.environ["XDG_RUNTIME_DIR"] = str(pasta)
import importlib.util
spec = importlib.util.spec_from_file_location("tars_trecho", str(Path(__file__).resolve().parent.parent / "tars.py"))
fonte = (Path(__file__).resolve().parent.parent / "tars.py").read_text(encoding="utf-8")
ini = fonte.index("def achar_autorizacao_x")
fim = fonte.index("if not os.environ.get(\"XAUTHORITY\")")
ns = {"os": os, "Path": Path}
exec(fonte[ini:fim], ns)
achar = ns["achar_autorizacao_x"]
assert achar() is None, "sem cookie nenhum, não acha nada"
cookie = pasta / ".mutter-Xwaylandauth.ABC123"
cookie.write_text("x")
assert achar() == str(cookie), achar()
print("OK: acha o cookie do XWayland (GNOME/Wayland)")
cookie.unlink()
assert achar() is None
print("OK: sem cookie, não inventa caminho")
print("TUDO OK.")
