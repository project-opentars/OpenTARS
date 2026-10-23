"""5.2: a instância única no caminho do Windows (TCP em 127.0.0.1 com segredo, cadeado do msvcrt). Fora do Windows, o
msvcrt é de mentira; no Windows (CI), é o de verdade."""
import os
import socket
import sys
import tempfile
import threading
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import tars_instancia as ti  # noqa: E402

os.environ["LOCALAPPDATA"] = tempfile.mkdtemp(prefix="opentars-inst-")
if not ti.WINDOWS:
    travas = set()

    def locking(fd, modo, n):
        chave = os.fstat(fd).st_ino
        if chave in travas:
            raise OSError("travado")
        travas.add(chave)
    ti.msvcrt = types.SimpleNamespace(locking=locking, LK_NBLCK=2)
    ti.WINDOWS = True

a, b = ti.Servidor(), ti.Servidor()
assert a.travar() and not b.travar(), "a segunda abertura não pode virar instância"
recebidos, chegou = [], threading.Event()
assert a.escutar(lambda cmd, ident: (recebidos.append((cmd, ident)), chegou.set()))
assert ti.enviar("acoes", "id123") and chegou.wait(3) and recebidos == [("acoes", "id123")], recebidos
print("OK: no caminho do Windows, a segunda abertura manda o recado pela porta local")

porta = int(a.caminho_socket.read_text().split()[0])
with socket.create_connection(("127.0.0.1", porta), timeout=2) as s:
    s.sendall(b"segredo-errado\tmostrar\n")
    s.settimeout(1)
    try:
        resposta = s.recv(8)
    except socket.timeout:
        resposta = b""
assert not resposta.startswith(b"ok") and len(recebidos) == 1, "recado sem o segredo não vale"
print("OK: recado sem o segredo é ignorado (outro programa do PC não abre o openTARS)")
a.fechar()
print("test_instancia_windows: TUDO OK.")
