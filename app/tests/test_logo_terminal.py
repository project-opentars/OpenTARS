"""O logo do terminal: sai só num terminal de verdade (não em pipe) e some com NO_COLOR."""
import io
import os
import sys
from _util import carregar_tars

tars = carregar_tars()

# 1) em pipe (não é tty): nada é impresso
antigo = sys.stdout
sys.stdout = io.StringIO()
tars._mostrar_logo()
saida = sys.stdout.getvalue()
sys.stdout = antigo
assert saida == "", repr(saida[:80])
print("OK: sem terminal de verdade, o logo não aparece")

# 2) com NO_COLOR, nada é impresso mesmo num terminal
class Terminal(io.StringIO):
    def isatty(self):
        return True

antigo = sys.stdout
sys.stdout = Terminal()
os.environ["NO_COLOR"] = "1"
try:
    tars._mostrar_logo()
    saida = sys.stdout.getvalue()
finally:
    del os.environ["NO_COLOR"]
    sys.stdout = antigo
assert saida == "", repr(saida[:80])
print("OK: NO_COLOR desliga o logo")

# 3) num terminal, o logo traz o nome e a versão
sys.stdout = Terminal()
try:
    tars._mostrar_logo()
    saida = sys.stdout.getvalue()
finally:
    sys.stdout = antigo
assert "┏━┓" in saida and "openTARS" in saida and tars.VERSAO in saida, saida[:200]
print("OK: no terminal, o logo traz o nome e a versão")
print("TUDO OK.")
