"""5.3 (F7, passos 2 e 3): a missão na VM (tars_vm_missao) sem ligar nenhuma VM: o QEMU e o controle são falsos; o proxy de saída, a leitura da
pasta de saída (7z) e a limpeza rodam de verdade. A VM de verdade foi conferida à parte em 08/11. Pula fora do Linux."""
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

if sys.platform != "linux" or not (shutil.which("qemu-img") and shutil.which("mkfs.vfat") and shutil.which("7z") and shutil.which("genisoimage")):
    print("PULADO: precisa de Linux, qemu-img, mkfs.vfat, 7z e genisoimage")
    sys.exit(0)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
base = Path(tempfile.mkdtemp(prefix="opentars-vmm-"))
os.environ["XDG_DATA_HOME"] = str(base / "dados")
os.environ["XDG_RUNTIME_DIR"] = str(base / "run")
(base / "run").mkdir()
os.chmod(base / "run", 0o700)
import tars_vm  # noqa: E402
import tars_vm_missao as m  # noqa: E402
from PIL import Image  # noqa: E402

# ---- endereço público: só internet de verdade
for ip in ("8.8.8.8", "93.184.216.34", "2606:4700:4700::1111"):
    assert m.endereco_publico(ip), ip
for ip in ("127.0.0.1", "10.0.2.2", "192.168.1.5", "172.16.0.9", "169.254.169.254", "::1", "fe80::1", "224.0.0.1", "0.0.0.0", "::ffff:127.0.0.1", "lixo"):
    assert not m.endereco_publico(ip), ip
print("OK: só endereço público passa (rede local, loopback, link-local, metadados da nuvem, IPv4 dentro de IPv6 e lixo não)")

# ---- proxy: servidor de eco como "internet"
eco = socket.socket(); eco.bind(("127.0.0.1", 0)); eco.listen(5)
recebido_no_eco = []


def servir_eco():
    while True:
        try:
            c, _ = eco.accept()
        except OSError:
            return
        dados = c.recv(4096)
        recebido_no_eco.append(dados)
        c.sendall(b"eco:" + dados)
        c.close()


threading.Thread(target=servir_eco, daemon=True).start()


def resolver_falso(host, porta):
    if host == "ok.teste":
        s = socket.socket(); s.connect(eco.getsockname()); return s       # um upstream já conectado
    return m._resolver_publico(host, porta) if host != "interno.teste" else None


proxy = m.ProxySaida(resolver=resolver_falso).iniciar()


def pedir(requisicao, esperar_eco=None):
    c = socket.create_connection(("127.0.0.1", proxy.porta), timeout=5)
    c.sendall(requisicao)
    resposta = c.recv(4096)
    if esperar_eco is not None:
        c.sendall(esperar_eco)
        resposta += c.recv(4096)
    c.close()
    return resposta


assert pedir(b"CONNECT 127.0.0.1:443 HTTP/1.1\r\n\r\n").startswith(b"HTTP/1.1 403"), "o PC (127.0.0.1) é recusado"
assert pedir(b"CONNECT localhost:443 HTTP/1.1\r\n\r\n").startswith(b"HTTP/1.1 403"), "um nome que aponta para o PC também"
assert pedir(b"CONNECT ok.teste:25 HTTP/1.1\r\n\r\n").startswith(b"HTTP/1.1 403"), "porta de e-mail"
assert pedir(b"CONNECT ok.teste:22 HTTP/1.1\r\n\r\n").startswith(b"HTTP/1.1 403"), "porta de SSH"
assert pedir(b"CONNECT interno.teste:443 HTTP/1.1\r\n\r\n").startswith(b"HTTP/1.1 403"), "nome sem endereço público"
assert pedir(b"lixo sem forma\r\n\r\n").startswith(b"HTTP/1.1 400")
r = pedir(b"CONNECT ok.teste:443 HTTP/1.1\r\n\r\n", esperar_eco=b"ola")
assert r.startswith(b"HTTP/1.1 200 Connection established") and r.endswith(b"eco:ola"), r
recebido_no_eco.clear()
r = pedir(b"GET http://ok.teste/pagina?x=1 HTTP/1.1\r\nHost: ok.teste\r\n\r\n")
assert b"eco:GET /pagina?x=1 HTTP/1.1" in r and recebido_no_eco[0].startswith(b"GET /pagina?x=1 HTTP/1.1"), (r, recebido_no_eco)
time.sleep(0.3)
sites = [(h, p, ok) for _t, h, p, ok, _n in proxy.acessos]
assert ("127.0.0.1", 443, False) in sites and ("ok.teste", 25, False) in sites and ("ok.teste", 443, True) in sites and ("ok.teste", 80, True) in sites, sites
assert proxy.bytes_total > 0
proxy.parar()
tapado = m.ProxySaida(resolver=resolver_falso, limite_mb=0).iniciar()
c = socket.create_connection(("127.0.0.1", tapado.porta), timeout=5); c.sendall(b"CONNECT ok.teste:443 HTTP/1.1\r\n\r\n")
assert c.recv(100).startswith(b"HTTP/1.1 403"), "passou do limite de transferência: recusa"
c.close(); tapado.parar()
print("OK: proxy: recusa o PC, nome que aponta para o PC, porta de e-mail e de SSH; deixa passar HTTPS (CONNECT) e HTTP; anota cada site; tem limite")

# ---- pasta de saída: o disco FAT existe, e a leitura (7z, sem montar) traz só arquivos comuns
disco = m.criar_disco_de_saida(base / "saida.img", mb=8)
assert disco.stat().st_size == 8 * 1024 * 1024 and b"SAIDA" in disco.read_bytes()[:1024]
origem = base / "origem"
(origem / "sub").mkdir(parents=True)
(origem / "relatorio.txt").write_text("preços coletados: 3\n")
(origem / "sub" / "dados.csv").write_text("a,b\n1,2\n")
iso = base / "teste.iso"
subprocess.run(["genisoimage", "-o", str(iso), "-V", "SAIDA", "-R", "-J", str(origem)], check=True, capture_output=True)
achados = m.ler_saida(iso, base / "q1")
assert sorted(a["nome"] for a in achados) == ["relatorio.txt", "sub/dados.csv"], achados
assert Path(achados[0]["caminho"]).is_relative_to(base / "q1")
copiado = m.liberar(next(a for a in achados if a["nome"] == "relatorio.txt"), base / "fora" / "r.txt")
assert copiado.read_text() == "preços coletados: 3\n"
assert m.ler_saida(disco, base / "q2") == [], "disco vazio, nada na saída"
print("OK: pasta de saída: disco FAT com rótulo SAIDA; leitura pelo 7z sem montar; só arquivos comuns; liberar copia um arquivo; disco vazio dá lista vazia")

# ---- a missão inteira, com o QEMU e o controle falsos
class Processo:
    returncode = 0

    def poll(self):
        return 0

    def terminate(self):
        pass

    def wait(self, timeout=None):
        return 0


class ControleFalso:
    def __init__(self):
        self.chamadas = []

    def tela(self, destino):
        Path(destino).parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (1280, 800)).save(destino)
        self.chamadas.append(("tela", Path(destino).name))
        return Path(destino)

    def clicar(self, x, y, botao="esquerdo", duplo=False):
        self.chamadas.append(("clicar", x, y, botao, duplo))

    def digitar(self, texto):
        self.chamadas.append(("digitar", texto))
        return [c for c in texto if not c.isascii()]

    def atalho(self, t):
        self.chamadas.append(("atalho", t))

    def rolar(self, n):
        self.chamadas.append(("rolar", n))

    def desligar_suave(self):
        self.chamadas.append(("desligar",))

    def encerrar(self):
        self.chamadas.append(("encerrar",))


# a base de mentira
(base / "dados" / "opentars" / "vm").mkdir(parents=True)
subprocess.run(["qemu-img", "create", "-f", "qcow2", str(tars_vm.imagem_base()), "8M"], check=True, capture_output=True)
lancados, controle = [], ControleFalso()


def popen_falso(argv, **kw):
    lancados.append(argv)
    return Processo()


roteiro = [{"tipo": "clicar", "x": 567, "y": 775}, {"tipo": "digitar", "texto": "ls é\n"}, {"tipo": "atalho", "teclas": "alt+f4"},
           {"tipo": "terminar", "resultado": "feito: 3 arquivos"}]


def decisor_do_roteiro(tela, historico):
    assert Path(tela).exists() and tela.name.startswith("tela-"), tela
    return roteiro[len(historico)]


passos_vistos = []
r = m.executar(decisor_do_roteiro, internet=True, popen=popen_falso, conectar=lambda caminho, espera: controle, assentar=0, espera_desktop=0, ao_passo=lambda i, f: passos_vistos.append((i, f)))
assert r["resultado"] == "feito: 3 arquivos" and r["motivo"] == "terminou" and len(r["passos"]) == 3, r
assert r["passos"] == ["clicar 567,775", "digitou (sem os caracteres: é)", "atalho alt+f4"] and passos_vistos[0] == (0, "clicar 567,775")
assert ("clicar", 567, 775, "esquerdo", False) in controle.chamadas and ("desligar",) in controle.chamadas and controle.chamadas[-1] == ("encerrar",)
argv = lancados[0]
texto = " ".join(argv)
rede = argv[argv.index("-netdev") + 1]
assert argv[:2] == ["nice", "-n"] and "restrict=on" in rede and "guestfwd=tcp:10.0.2.100:3128-tcp:127.0.0.1:" in rede and "11434" not in texto, rede
assert "saida.img" in texto and "format=raw" in texto and "-qmp unix:" in texto
for proibido in ("virtfs", "fsdev", "-usb", "usb-", "hostfwd", "vnc", "spice", "-monitor"):
    assert proibido not in texto, proibido
assert r["acessos"] == [] and r["arquivos"] == [] and r["quarentena"] is None
assert not [p for p in (base / "run").iterdir()], "o reset apaga overlay, disco de saída, socket, telas e quarentena vazia"
print("OK: missão: roteiro executado (clique, texto, atalho), VM com rede fechada e só o proxy encaminhado, sem pasta do PC; no fim não sobra nada")

# internet desligada: nem o proxy; limites de passos e de tempo; cancelar
lancados.clear()
r = m.executar(lambda t, h: {"tipo": "esperar", "segundos": 0}, limites=m.Limites(passos=3), internet=False, popen=popen_falso, assentar=0, espera_desktop=0, conectar=lambda c, e: ControleFalso())
assert r["motivo"] == "limite de passos" and len(r["passos"]) == 3 and "guestfwd" not in " ".join(lancados[0]) and r["acessos"] == []
r = m.executar(lambda t, h: {"tipo": "esperar", "segundos": 0}, limites=m.Limites(segundos=-1), internet=False, popen=popen_falso, assentar=0, espera_desktop=0, conectar=lambda c, e: ControleFalso())
assert r["motivo"] == "tempo esgotado" and r["passos"] == []
parar = threading.Event(); parar.set()
r = m.executar(lambda t, h: {"tipo": "esperar", "segundos": 0}, internet=False, popen=popen_falso, assentar=0, espera_desktop=0, conectar=lambda c, e: ControleFalso(), cancelar=parar)
assert r["motivo"] == "cancelada"
try:
    m.executar(lambda t, h: {"tipo": "voar"}, internet=False, popen=popen_falso, assentar=0, espera_desktop=0, conectar=lambda c, e: ControleFalso())
    raise AssertionError("ação desconhecida tinha de falhar")
except ValueError:
    pass
assert not list((base / "run").iterdir()), "mesmo com erro, a cópia da VM é apagada"
print("OK: limite de passos e de tempo, cancelar, ação desconhecida: em todos a cópia é apagada")

# sem a imagem montada, avisa em vez de tentar
tars_vm.imagem_base().unlink()
try:
    m.executar(lambda t, h: {"tipo": "terminar"}, popen=popen_falso, assentar=0, espera_desktop=0, conectar=lambda c, e: ControleFalso())
    raise AssertionError("tinha de avisar")
except RuntimeError as e:
    assert "imagem" in str(e)
print("OK: sem a imagem montada, avisa")
print("TUDO OK.")
