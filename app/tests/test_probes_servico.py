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
fim = time.time() + 15         # contêiner de CI ocupado demora a subir a thread do serviço
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

# quem só confere (servico_rodando) segura a trava por um instante: o serviço que sobe nessa hora espera, não desiste
fd_conferindo = os.open(str(tp.arquivo_pid()), os.O_RDONLY)
tp._travar(fd_conferindo, exclusiva=False)
threading.Timer(0.3, lambda: (tp._destravar(fd_conferindo), os.close(fd_conferindo))).start()
parar2 = {"ja": False}
codigo = {}
fio2 = threading.Thread(target=lambda: codigo.update(r=tp.servico("http://127.0.0.1:9", lambda: [], parar=lambda: parar2["ja"],
                                                                  intervalo=1)))
fio2.start()
fim = time.time() + 15
while time.time() < fim and tp.servico_rodando() is None:
    time.sleep(0.1)
assert tp.servico_rodando() == os.getpid() and "r" not in codigo, codigo
parar2["ja"] = True
fio2.join(5)
assert codigo.get("r") == 0, codigo
print("OK: o serviço que sobe enquanto alguém confere o estado espera a trava, em vez de sair achando que há outro")

# a trava dos arquivos (Probes, rotinas) entre a janela e o serviço: cada um com a sua instância, como dois processos.
# No Windows ela não travava nada (só havia fcntl): somas se perdiam e o os.replace dava "acesso negado"
import tars_memoria  # noqa: E402
import tars_rotinas  # noqa: E402
contador = Path(tempfile.mkdtemp(prefix="opentars-trava-")) / "contador.json"
tars_memoria.gravar_texto_atomico(contador, "0")
erros = []


def somar():
    try:
        for _ in range(40):
            with tars_rotinas._Trava(contador):
                n = int(contador.read_text())
                tars_memoria.gravar_texto_atomico(contador, str(n + 1))
    except Exception as e:  # noqa: BLE001
        erros.append(repr(e))


fios = [threading.Thread(target=somar) for _ in range(4)]
for f in fios:
    f.start()
for f in fios:
    f.join(60)
assert not erros and contador.read_text() == "160", (contador.read_text(), erros[:3])
print("OK: a trava dos arquivos vale entre instâncias (janela e serviço): 4 x 40 somas, nenhuma perdida")

comando = tp.comando_do_servico()
assert comando[-1] == "--probes", comando
if tp.plataforma.sistema() == "windows":
    assert comando[0].lower().endswith("pythonw.exe") and comando[1].endswith("tars.py"), comando
print(f"OK: comando do serviço: {comando[0]} ... --probes")
print("test_probes_servico: TUDO OK.")
