"""16/10: a janela usa as fontes e as regras do sistema com um cache de fontes só do openTARS (tema.preparar_fontconfig).
Um cache corrompido em ~/.cache/fontconfig derrubava o Qt no primeiro caractere fora da IBM Plex, até no modo seguro.
Confere: os caches do sistema saem, as inclusões relativas viram absolutas, o cache do openTARS entra, e nada muda
quando a pessoa já escolheu um FONTCONFIG_FILE, com TARS_FONTCONFIG_SISTEMA=1 ou sem o fonts.conf do sistema."""
import os
import tempfile
from pathlib import Path

from _util import RAIZ  # noqa: F401

from tars_qt import tema

pasta = Path(tempfile.mkdtemp(prefix="opentars-fc-"))
(pasta / "etc").mkdir()
sistema = pasta / "etc" / "fonts.conf"
sistema.write_text("""<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig>
	<dir>/usr/share/fonts</dir>
	<include ignore_missing="yes">conf.d</include>
	<include ignore_missing="yes">/etc/outro.conf</include>
	<cachedir>/var/cache/fontconfig</cachedir>
	<cachedir prefix="xdg">fontconfig</cachedir>
</fontconfig>
""", encoding="utf-8")

for var in ("FONTCONFIG_FILE", "TARS_FONTCONFIG_SISTEMA"):
    os.environ.pop(var, None)
arquivo = tema.preparar_fontconfig(str(sistema), casa=str(pasta / "cache"))
texto = arquivo.read_text(encoding="utf-8")
assert os.environ["FONTCONFIG_FILE"] == str(arquivo)
assert "/var/cache/fontconfig" not in texto and 'prefix="xdg">fontconfig' not in texto, "os caches de fora saem"
assert f"<cachedir>{pasta / 'cache' / 'opentars' / 'fontconfig'}</cachedir>" in texto
assert f">{pasta / 'etc' / 'conf.d'}</include>" in texto and ">/etc/outro.conf</include>" in texto
assert "<dir>/usr/share/fonts</dir>" in texto, "as fontes do sistema continuam"
print("OK: fontes e regras do sistema, com o cache só do openTARS")

assert tema.preparar_fontconfig(str(sistema), casa=str(pasta / "outro")) is None, "FONTCONFIG_FILE já escolhido: não mexe"
os.environ.pop("FONTCONFIG_FILE")
os.environ["TARS_FONTCONFIG_SISTEMA"] = "1"
assert tema.preparar_fontconfig(str(sistema), casa=str(pasta / "outro")) is None and "FONTCONFIG_FILE" not in os.environ
os.environ.pop("TARS_FONTCONFIG_SISTEMA")
assert tema.preparar_fontconfig(str(pasta / "nao-existe.conf"), casa=str(pasta / "outro")) is None
assert "FONTCONFIG_FILE" not in os.environ
print("OK: respeita FONTCONFIG_FILE, TARS_FONTCONFIG_SISTEMA=1 e a falta do fonts.conf")
print("\nTUDO OK.")
