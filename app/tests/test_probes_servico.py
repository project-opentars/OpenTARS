"""5.2: o serviço dos Probes nos três sistemas: instância única (flock no Linux e no macOS, msvcrt.locking no Windows), o
PID legível enquanto ele roda, prioridade baixa sem erro e o comando de subir o serviço (no Windows, pythonw)."""
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["TARS_ARQUIVO_PROBES"] = str(Path(tempfile.mkdtemp(prefix="opentars-probes-")) / "probes.json")
import tars_probes as tp  # noqa: E402

parar = {"ja": False}
fio = threading.Thread(target=lambda: tp.servico("http://127.0.0.1:9", lambda: [], parar=lambda: parar["ja"], intervalo=1))
fio.start()
fim = time.time() + 5
while time.time() < fim and tp.servico_rodando() is None:
    time.sleep(0.1)
try:
    assert tp.servico_rodando() == os.getpid(), tp.arquivo_pid().read_bytes()
    assert tp.servico("http://127.0.0.1:9", lambda: [], parar=lambda: True) == 3
finally:
    parar["ja"] = True
    fio.join(5)
assert not fio.is_alive() and tp.servico_rodando() is None
print("OK: o serviço é instância única, o PID fica legível e a trava some quando ele para")

comando = tp.comando_do_servico()
assert comando[-1] == "--probes", comando
if tp.plataforma.sistema() == "windows":
    assert comando[0].lower().endswith("pythonw.exe") and comando[1].endswith("tars.py"), comando
print(f"OK: comando do serviço: {comando[0]} ... --probes")
print("test_probes_servico: TUDO OK.")
