"""5.3 (F7, passo 1): a imagem da VM dos Probes (tars_vm), SEM baixar o Debian e SEM ligar uma VM: o que baixa e o que liga são falsos;
qemu-img e genisoimage rodam de verdade, em arquivos pequenos de teste. Pula fora do Linux."""
import hashlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path

if sys.platform != "linux":
    print("PULADO: a VM dos Probes é só do Linux")
    sys.exit(0)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
base = Path(tempfile.mkdtemp(prefix="opentars-vm-"))
os.environ["XDG_DATA_HOME"] = str(base / "dados")
os.environ["HOME"] = str(base / "casa")
(base / "casa").mkdir()
import shutil  # noqa: E402

import tars_vm as vm  # noqa: E402

if not (shutil.which("qemu-img") and shutil.which("genisoimage")):
    print("PULADO: precisa de qemu-img e genisoimage")
    sys.exit(0)

# diagnóstico e o que falta
d = vm.diagnostico()
assert set(d) == {"linux", "kvm", "qemu", "qemu_img", "iso", "livre_gb", "base_pronta"} and d["linux"] and d["base_pronta"] is False
assert vm.o_que_falta({**d, "kvm": False, "qemu": None, "livre_gb": 3.0, "iso": "x", "qemu_img": "x", "linux": True}) == \
    ["kvm", "qemu-system-x86_64", "espaço (3.0 GB livres; precisa de 12)"]
assert vm.o_que_falta({"linux": True, "kvm": True, "qemu": "x", "qemu_img": "x", "iso": "x", "livre_gb": 50, "base_pronta": False}) == []
print("OK: diagnóstico: KVM, qemu, qemu-img, genisoimage e espaço, e o que falta em palavras")

# o hash vem do SHA512SUMS do Debian
conteudo = b"imagem de mentira"
sha = hashlib.sha512(conteudo).hexdigest()
sums = f"{'0' * 128}  debian-12-azure-amd64.tar.xz\n{sha} *{vm.IMAGEM_ORIGEM}\n"
assert vm.hash_da_imagem(sums) == sha and vm.hash_da_imagem("lixo") is None and vm.hash_da_imagem(sums, "outra.qcow2") is None
pedidos = []
destino = vm.baixar_base_debian(destino=base / "d.qcow2", baixar=lambda url, dest, h, prog, algoritmo="sha256": pedidos.append((url, h, algoritmo)) or dest,
                                ler_texto=lambda url: sums)
assert pedidos == [(vm.SERVIDOR + vm.IMAGEM_ORIGEM, sha, "sha512")] and destino == base / "d.qcow2"
try:
    vm.baixar_base_debian(ler_texto=lambda url: "nada", baixar=lambda *a, **k: None)
    raise AssertionError("tinha de recusar sem hash")
except ValueError:
    pass
print("OK: imagem do Debian: o SHA-512 sai do SHA512SUMS e é conferido (sem hash, não baixa)")

# o download de verdade confere o hash e só então põe no lugar (servidor local)
import http.server  # noqa: E402
import threading  # noqa: E402


class Servir(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Length", str(len(conteudo)))
        self.end_headers()
        self.wfile.write(conteudo)


servidor = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Servir)
threading.Thread(target=servidor.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{servidor.server_port}/x.qcow2"
vm.tars_motor_local.baixar(url, base / "ok.qcow2", sha, algoritmo="sha512")
assert (base / "ok.qcow2").read_bytes() == conteudo
try:
    vm.tars_motor_local.baixar(url, base / "ruim.qcow2", "0" * 128, algoritmo="sha512")
    raise AssertionError("hash errado passou")
except ValueError as e:
    assert "SHA512" in str(e)
assert not (base / "ruim.qcow2").exists() and not (base / "ruim.qcow2.parcial").exists()
servidor.shutdown()
print("OK: o download confere SHA-512 e só põe no lugar com o hash certo")

# o cloud-config: sem senha, sem nada do computador, desliga no fim
ud = vm.user_data()
assert ud.startswith("#cloud-config") and "lock_passwd: true" in ud and "power_state:" in ud and "mode: poweroff" in ud
assert all(f"  - {p}" in ud for p in vm.PACOTES_DESKTOP) and "autologin-user=probe" in ud
assert "linux-image-amd64" in ud and "purge" in ud and "update-grub" in ud, "o kernel cloud não tem vídeo: a tela fica preta"
assert "mounts:" not in ud and "chown -R probe:probe /home/probe" in ud and "LABEL=SAIDA" in ud, "o mounts criava a casa como root antes do usuário (login automático quebrava)"
assert ud.index("mkdir -p /home/probe/saida") > ud.index("runcmd:")
assert "--now" not in ud and "cloud-init.disabled" in ud, "parar o cloud-init por dentro mata o power_state (erro de 08/11)"
assert ud.index("runcmd:") < ud.index("power_state:")
assert "/home/" not in ud.replace("/home/probe", ""), "só a casa do usuário da VM aparece, nunca a do PC"
for proibido in (str(Path.home()), "ssh-rsa", "ssh-ed25519", "TARS_CHAVE_API", "nuvem.json", "chpasswd"):
    assert proibido not in ud, proibido
import re  # noqa: E402
assert not re.search(r"^\s*(passwd|password|plain_text_passwd|hashed_passwd)\s*:", ud, re.M), "nenhuma senha no cloud-config"
iso = vm.criar_semente(base / "semente")
assert iso.exists() and b"CIDATA" in iso.read_bytes()[:40000].upper()
assert sorted(p.name for p in (base / "semente").iterdir()) == ["meta-data", "seed.iso", "user-data"], "só a semente entra na VM"
print("OK: cloud-config sem senha nem credencial, desktop leve, desliga sozinho; seed.iso com rótulo cidata e só os dois arquivos")

# a linha do qemu: nunca monta pasta do computador; a missão fecha a rede e só deixa o Ollama
construcao = vm.argumentos_qemu("d.qcow2", "seed.iso", log="c.log")
missao = vm.argumentos_qemu("o.qcow2", internet=False, ollama=11435)
for argv in (construcao, missao):
    texto = " ".join(argv)
    assert "-enable-kvm" in argv and "-display" in argv and "-nodefaults" in argv
    for proibido in ("virtfs", "fsdev", "-usb", "usb-", "hostfwd", "-smb", "9p", "vnc", "spice", "-monitor", "-qmp"):
        assert proibido not in texto, (proibido, texto)
assert "restrict=on" not in " ".join(construcao) and "seed.iso" in " ".join(construcao) and "file:c.log" in " ".join(construcao)
rede = missao[missao.index("-netdev") + 1]
assert rede == "user,id=n0,restrict=on,guestfwd=tcp:10.0.2.100:11434-tcp:127.0.0.1:11435" and "seed.iso" not in " ".join(missao), rede
assert "restrict=on" in vm.argumentos_qemu("o.qcow2", internet=False)[vm.argumentos_qemu("o.qcow2", internet=False).index("-netdev") + 1]
print("OK: qemu: sem pasta do computador, sem USB, sem porta de entrada; a missão fecha a rede (restrict=on) e só encaminha o Ollama")

# overlay descartável: reset = apagar, e a base nunca muda
subprocess.run(["qemu-img", "create", "-f", "qcow2", str(base / "base.qcow2"), "8M"], check=True, capture_output=True)
antes = hashlib.sha256((base / "base.qcow2").read_bytes()).hexdigest()
ov = vm.criar_overlay(base / "base.qcow2", base / "missoes" / "m1.qcow2")
info = subprocess.run(["qemu-img", "info", "--output=json", str(ov)], capture_output=True, text=True, check=True).stdout
assert '"backing-filename"' in info and "base.qcow2" in info and '"format": "qcow2"' in info
vm.apagar_overlay(ov)
assert not ov.exists() and hashlib.sha256((base / "base.qcow2").read_bytes()).hexdigest() == antes
vm.apagar_overlay(ov)         # apagar de novo não é erro
print("OK: overlay: nasce em cima da base, reset apaga e a base fica byte a byte igual")

# a construção inteira, com o download e o qemu falsos (o desktop não é instalado de verdade)
class Processo:
    returncode = 0

    def __init__(self, argv, **kw):
        self.argv = argv

    def poll(self):
        return 0


lancados = []
vm.baixar_base_debian = lambda **k: Path(shutil.copy2(base / "base.qcow2", base / "dados" / "origem.qcow2")) if (base / "dados").mkdir(exist_ok=True) is None else None
vm.o_que_falta = lambda d=None: []
resultado = vm.construir_base(popen=lambda argv, **kw: lancados.append(argv) or Processo(argv), esperar=lambda s: None, avisar=lambda *a: None)
assert vm.imagem_base().exists() and resultado["tamanho_mb"] >= 0 and "segundos" in resultado
assert lancados and lancados[0][0] == "qemu-system-x86_64" and any("seed.iso" in a for a in lancados[0])
assert not (vm.pasta() / "construcao").exists() and not (vm.pasta() / "origem.qcow2").exists(), "a pasta de trabalho some"
print("OK: a construção baixa, monta a semente, liga o qemu, espera, comprime e guarda a base (qemu falso)")
print("TUDO OK.")
