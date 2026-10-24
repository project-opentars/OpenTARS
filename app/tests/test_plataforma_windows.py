"""5.2 (F5): o backend do Windows de verdade. Só roda no Windows (no CI e no notebook); fora dele, pula."""
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import tars_plataforma as p  # noqa: E402

if p.sistema() != "windows":
    print("test_plataforma_windows: PULADO (não é Windows)")
    sys.exit(0)

texto = "Olá, ação! 日本語 e um emoji 🚀"
p.escrever_area_de_transferencia(texto)
assert p.ler_area_de_transferencia() == texto, repr(p.ler_area_de_transferencia())
print("OK: área de transferência com acento, japonês e emoji")

pasta = Path(tempfile.mkdtemp(prefix="opentars-lixo-"))
arquivo = pasta / "apagar mesmo.txt"
arquivo.write_text("x")
p.lixeira(arquivo)
assert not arquivo.exists()
try:
    p.lixeira(pasta / "nao-existe.txt")
except OSError:
    pass
else:
    raise AssertionError("arquivo que não existe tem de dar erro")
print("OK: lixeira (SHFileOperation com desfazer)")

assert p.autostart("opentars-teste-ci", "openTARS teste", [sys.executable, "-c", "print(1)"], True)
lnk = p.arquivo_autostart("opentars-teste-ci")
assert lnk.exists() and lnk.suffix == ".lnk", lnk
assert not p.autostart("opentars-teste-ci", "openTARS teste", [sys.executable], False) and not lnk.exists()
print("OK: início automático pelo atalho na pasta Inicializar")

p.notificar("openTARS", "teste do CI")   # não espera; só não pode levantar erro
inicio = time.time()
selecao = p.ler_selecao()                # no runner não há o que copiar: volta vazio, rápido e sem erro
assert isinstance(selecao, str) and time.time() - inicio < 3
assert p.teclas_de_colar() == ("ctrl", "v")
print("OK: notificação e seleção sem erro")
print("test_plataforma_windows: TUDO OK.")
